"""API движка предложений и именованных действий."""

from __future__ import annotations

from celery.result import AsyncResult
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.domains import ROLE_STUDENT, domain_of_role
from suggestions import commands as command_registry
from suggestions import tasks as background
from suggestions.engine import accept_above, apply_suggestion, refresh_old_values, revert_suggestion
from suggestions.models import Suggestion, SuggestionStatus
from suggestions.serializers import (
    AcceptAboveSerializer,
    ApplySerializer,
    EssayQuestionsSerializer,
    ExplainSerializer,
    PasteSerializer,
    ResolveAmbiguitySerializer,
    SuggestionSerializer,
    UploadSerializer,
)


def _deny_students(request):
    """Ученик не работает с предложениями (инвариант №3 — применяет сотрудник)."""
    if request.user.role == ROLE_STUDENT:
        return Response({"detail": "Предложения ведут сотрудники"}, status=status.HTTP_403_FORBIDDEN)
    return None


class SuggestionViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """Предложения своего домена."""

    queryset = Suggestion.objects.prefetch_related("changes__student").all()
    serializer_class = SuggestionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("status", "domain_code", "command")

    def get_queryset(self):
        user = self.request.user
        if user.role == ROLE_STUDENT:
            return Suggestion.objects.none()
        domain = domain_of_role(user.role)
        qs = super().get_queryset()
        # директор видит предложения своего домена; администратор — все
        return qs if domain is None else qs.filter(domain_code=domain.code)

    def retrieve(self, request, *args, **kwargs):
        """Предпросмотр: перед показом перечитываем текущие значения."""
        suggestion = self.get_object()
        refresh_old_values(suggestion)
        return Response(self.get_serializer(suggestion).data)

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        """Применить принятые строки. Частичное принятие — галочками."""
        denied = _deny_students(request)
        if denied:
            return denied
        serializer = ApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        suggestion = self.get_object()
        result = apply_suggestion(suggestion, actor=request.user, change_ids=serializer.validated_data.get("changes"))
        return Response(result)

    @action(detail=True, methods=["post"], url_path="accept-above")
    def accept_above_threshold(self, request, pk=None):
        """«Принять все выше порога» — явное действие, попадает в журнал."""
        denied = _deny_students(request)
        if denied:
            return denied
        serializer = AcceptAboveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            accept_above(self.get_object(), threshold=serializer.validated_data["threshold"], actor=request.user)
        )

    @action(detail=True, methods=["post"])
    def revert(self, request, pk=None):
        """Откат: обратный набор изменений, тоже через аудит."""
        denied = _deny_students(request)
        if denied:
            return denied
        return Response(revert_suggestion(self.get_object(), actor=request.user))

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        suggestion = self.get_object()
        suggestion.status = SuggestionStatus.REJECTED
        suggestion.save(update_fields=["status"])
        return Response({"status": suggestion.status})

    @action(detail=True, methods=["post"], url_path="resolve-ambiguity")
    def resolve_ambiguity(self, request, pk=None):
        """«Нашлось двое, выберите» — человек указал, кто именно."""
        denied = _deny_students(request)
        if denied:
            return denied
        serializer = ResolveAmbiguitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from django.apps import apps

        from core.audit import to_text
        from core.domains import can_write
        from suggestions.models import SuggestionChange

        if not can_write(request.user.role, data["model"], data["field"]):
            return Response({"detail": "Поле чужого домена"}, status=status.HTTP_403_FORBIDDEN)

        suggestion = self.get_object()
        instance = apps.get_model(data["model"]).objects.filter(student_id=data["student"]).first()
        change = SuggestionChange.objects.create(
            suggestion=suggestion,
            student_id=data["student"],
            model_label=data["model"],
            object_id=str(instance.pk) if instance else "",
            field_name=data["field"],
            old_value=to_text(getattr(instance, data["field"], None)) if instance else "",
            new_value=to_text(data["value"]),
            # человек выбрал сам — уверенность полная
            confidence=1,
            source_quote=data.get("source_quote", ""),
            is_accepted=True,
        )
        from suggestions.serializers import SuggestionChangeSerializer

        return Response(SuggestionChangeSerializer(change).data, status=status.HTTP_201_CREATED)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def available_commands(request):
    """Кнопки, доступные роли. Не чат — именованные действия."""
    return Response({"commands": command_registry.for_role(request.user.role)})


@extend_schema(request=PasteSerializer, responses={202: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def paste(request):
    """«Вставить как есть»: текст → фоновый разбор → предпросмотр."""
    denied = _deny_students(request)
    if denied:
        return denied

    serializer = PasteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    domain = domain_of_role(request.user.role)
    if domain is None:
        return Response({"detail": "У роли нет домена"}, status=status.HTTP_403_FORBIDDEN)

    task = background.parse_paste.delay(
        text=serializer.validated_data["text"],
        actor_id=request.user.pk,
        role=request.user.role,
        domain_code=domain.code,
        command=serializer.validated_data.get("command", "paste_as_is"),
    )
    return Response({"task": task.id}, status=status.HTTP_202_ACCEPTED)


@extend_schema(request=UploadSerializer, responses={202: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload(request):
    """«Загрузить файл»: разбор в фоне."""
    denied = _deny_students(request)
    if denied:
        return denied

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response({"detail": "Файл не приложен"}, status=status.HTTP_400_BAD_REQUEST)
    domain = domain_of_role(request.user.role)
    if domain is None:
        return Response({"detail": "У роли нет домена"}, status=status.HTTP_403_FORBIDDEN)

    raw = uploaded.read()
    content = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else str(raw)
    task = background.parse_file.delay(
        content=content,
        filename=uploaded.name,
        actor_id=request.user.pk,
        role=request.user.role,
        domain_code=domain.code,
    )
    return Response({"task": task.id}, status=status.HTTP_202_ACCEPTED)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def task_status(request, task_id: str):
    """Статус фоновой задачи — фронт опрашивает и показывает прогресс."""
    result = AsyncResult(task_id)
    payload: dict = {"id": task_id, "state": result.state}
    if result.state == "PROGRESS":
        payload["progress"] = result.info
    elif result.successful():
        payload["result"] = result.result
    elif result.failed():
        payload["error"] = str(result.info)
    return Response(payload)


@extend_schema(request=ExplainSerializer, responses={202: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def explain_match(request):
    """ИИ объясняет соответствие. Ученику — про себя, сотруднику — про любого."""
    serializer = ExplainSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    student_id = serializer.validated_data["student"]

    if request.user.role == ROLE_STUDENT:
        own = getattr(request.user, "student", None)
        if own is None or own.pk != student_id:
            return Response({"detail": "Доступен только свой профиль"}, status=status.HTTP_403_FORBIDDEN)

    task = background.explain_match.delay(
        student_id=student_id, program_id=serializer.validated_data["program"], actor_id=request.user.pk
    )
    return Response({"task": task.id}, status=status.HTTP_202_ACCEPTED)


@extend_schema(request=EssayQuestionsSerializer, responses={202: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def essay_questions(request):
    """Вопросы по эссе. ИИ не пишет и не переписывает текст."""
    from roadmap.models import Essay

    serializer = EssayQuestionsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    essay = Essay.objects.filter(pk=serializer.validated_data["essay"]).first()
    if essay is None:
        return Response({"detail": "Эссе не найдено"}, status=status.HTTP_404_NOT_FOUND)
    if request.user.role == ROLE_STUDENT:
        own = getattr(request.user, "student", None)
        if own is None or essay.student_id != own.pk:
            return Response({"detail": "Чужое эссе"}, status=status.HTTP_403_FORBIDDEN)

    task = background.essay_questions.delay(
        essay_id=essay.pk, prompt=serializer.validated_data["prompt"], actor_id=request.user.pk
    )
    return Response({"task": task.id}, status=status.HTTP_202_ACCEPTED)
