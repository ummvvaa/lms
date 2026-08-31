"""API движка предложений и именованных действий."""

from __future__ import annotations

from celery.result import AsyncResult
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import (
    action,
    api_view,
    parser_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core import jobs
from core.domains import DOMAINS, ROLE_ADMIN, ROLE_STUDENT, domain_of_role
from suggestions import commands as command_registry
from suggestions import llm
from suggestions import tasks as background
from suggestions.budget import BudgetExceeded, check_available
from suggestions.budget import report as budget_report
from suggestions.engine import (
    accept_above,
    apply_suggestion,
    create_student_suggestions,
    refresh_old_values,
    revert_suggestion,
)
from suggestions.models import Suggestion, SuggestionStatus
from suggestions.serializers import (
    AcceptAboveSerializer,
    ApplySerializer,
    AssistantAskSerializer,
    AssistantMessageSerializer,
    AssistantThreadSerializer,
    ConfirmManySerializer,
    EssayQuestionsSerializer,
    ExplainSerializer,
    OperationSerializer,
    ParseActivitySerializer,
    ParseImageSerializer,
    ParseUniversitySerializer,
    PasteSerializer,
    ProposeSerializer,
    ResolveAmbiguitySerializer,
    ReviewSerializer,
    SuggestionSerializer,
    UploadSerializer,
    VerifyRequirementsSerializer,
)


def _deny_students(request):
    """Ученик не работает с предложениями (инвариант №3 — применяет сотрудник)."""
    if request.user.role == ROLE_STUDENT:
        return Response({"detail": "Предложения ведут сотрудники"}, status=status.HTTP_403_FORBIDDEN)
    return None


def _student_suggestion_guard(request, suggestion: Suggestion):
    """Предложение ученика подтверждает владелец домена поля (фаза 37).

    Балл IELTS решает академический директор, соревнование — директор
    спорта. Администратор видит очередь, но решение не его: он не владеет
    ни одним доменом.
    """
    if suggestion.role != ROLE_STUDENT:
        return None
    domain = DOMAINS.get(suggestion.domain_code)
    if domain is None or request.user.role != domain.role:
        owner = f" — {domain.owner_name} ({domain.title})" if domain else ""
        return Response(
            {"detail": f"Предложение ученика подтверждает владелец домена{owner}"},
            status=status.HTTP_403_FORBIDDEN,
        )
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
        denied = _student_suggestion_guard(request, suggestion)
        if denied:
            return denied
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
        suggestion = self.get_object()
        denied = _student_suggestion_guard(request, suggestion)
        if denied:
            return denied
        return Response(accept_above(suggestion, threshold=serializer.validated_data["threshold"], actor=request.user))

    @action(detail=True, methods=["post"])
    def revert(self, request, pk=None):
        """Откат: обратный набор изменений, тоже через аудит."""
        denied = _deny_students(request)
        if denied:
            return denied
        suggestion = self.get_object()
        denied = _student_suggestion_guard(request, suggestion)
        if denied:
            return denied
        return Response(revert_suggestion(suggestion, actor=request.user))

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        from django.utils import timezone

        denied = _deny_students(request)
        if denied:
            return denied
        suggestion = self.get_object()
        denied = _student_suggestion_guard(request, suggestion)
        if denied:
            return denied
        suggestion.status = SuggestionStatus.REJECTED
        # причина отклонения — её прочитает ученик в кабинете (фаза 37)
        suggestion.reject_reason = str(request.data.get("reason") or "")[:250]
        suggestion.resolved_at = timezone.now()
        suggestion.save(update_fields=["status", "reject_reason", "resolved_at"])
        return Response({"status": suggestion.status})

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """Решение по предложению ученика: подтвердить, поправить, отклонить.

        «Поправить и подтвердить» меняет значение строки перед применением —
        в журнале источником всё равно останется «предложил ученик»,
        а актором — директор, который решил.
        """
        from django.utils import timezone

        denied = _deny_students(request)
        if denied:
            return denied
        suggestion = self.get_object()
        denied = _student_suggestion_guard(request, suggestion)
        if denied:
            return denied

        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data["decision"] == "decline":
            suggestion.status = SuggestionStatus.REJECTED
            suggestion.reject_reason = data["reason"].strip()
            suggestion.resolved_at = timezone.now()
            suggestion.save(update_fields=["status", "reject_reason", "resolved_at"])
            return Response({"status": suggestion.status, "reject_reason": suggestion.reject_reason})

        edited = data.get("values") or {}
        for change in suggestion.changes.all():
            if str(change.pk) in edited:
                change.new_value = edited[str(change.pk)]
                change.save(update_fields=["new_value"])
        ids = list(suggestion.changes.filter(is_applied=False).values_list("pk", flat=True))
        result = apply_suggestion(suggestion, actor=request.user, change_ids=ids)
        return Response(result)

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
        from core.domains import can_write_for
        from suggestions.models import SuggestionChange

        suggestion = self.get_object()
        # администратор дописывает строку только за домен предложения (фаза 35)
        if not can_write_for(request.user.role, suggestion.domain_code, data["model"], data["field"]):
            return Response({"detail": "Поле чужого домена"}, status=status.HTTP_403_FORBIDDEN)
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


# --- Фаза 37: ученик вносит, директор подтверждает --------------------------


@extend_schema(request=ProposeSerializer, responses={201: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def propose(request):
    """Ученик предлагает данные о себе.

    В профиль ничего не пишется: строки становятся предложением, решение
    принимает владелец домена. Чужой ученик и поля без флага в реестре
    отбиваются здесь, на сервере, а не прячутся в интерфейсе.
    """
    if request.user.role != ROLE_STUDENT:
        return Response({"detail": "Данные о себе вносит ученик"}, status=status.HTTP_403_FORBIDDEN)
    student = getattr(request.user, "student", None)
    if student is None:
        return Response({"detail": "У этой записи нет карточки ученика"}, status=status.HTTP_403_FORBIDDEN)

    serializer = ProposeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    created, rejected = create_student_suggestions(
        author=request.user, student=student, rows=serializer.validated_data["rows"]
    )
    return Response(
        {
            "suggestions": [s.pk for s in created],
            "accepted": sum(s.changes.count() for s in created),
            "rejected": [{"field": r.get("field", ""), "reason": r["reason"]} for r in rejected],
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_400_BAD_REQUEST,
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_proposals(request):
    """Предложения самого ученика: что на проверке, что решено и почему."""
    from suggestions.student_queue import mine_payload

    if request.user.role != ROLE_STUDENT:
        return Response({"detail": "Это кабинет ученика"}, status=status.HTTP_403_FORBIDDEN)
    return Response({"results": mine_payload(request.user)})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def students_queue(request):
    """Очередь «От учеников»: сначала то, что сильнее расходится с текущим."""
    from suggestions.student_queue import queue_payload

    denied = _deny_students(request)
    if denied:
        return denied
    return Response({"results": queue_payload(request.user.role)})


@extend_schema(request=ConfirmManySerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def students_queue_confirm(request):
    """Массовое подтверждение отмеченных предложений учеников."""
    denied = _deny_students(request)
    if denied:
        return denied
    serializer = ConfirmManySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    own = domain_of_role(request.user.role)
    if own is None:
        return Response(
            {"detail": "Предложение ученика подтверждает владелец домена"}, status=status.HTTP_403_FORBIDDEN
        )

    confirmed, results = 0, []
    rows = Suggestion.objects.filter(
        pk__in=serializer.validated_data["suggestions"],
        role=ROLE_STUDENT,
        status=SuggestionStatus.PENDING,
        domain_code=own.code,
    )
    for suggestion in rows:
        ids = list(suggestion.changes.filter(is_applied=False).values_list("pk", flat=True))
        outcome = apply_suggestion(suggestion, actor=request.user, change_ids=ids)
        confirmed += 1
        results.append({"id": suggestion.pk, **outcome})
    return Response({"confirmed": confirmed, "results": results})


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
    domain_code, problem = _acting_domain(request, serializer.validated_data.get("domain", ""))
    if problem:
        return problem

    kwargs = {
        "text": serializer.validated_data["text"],
        "actor_id": request.user.pk,
        "role": request.user.role,
        "domain_code": domain_code,
        "command": serializer.validated_data.get("command", "paste_as_is"),
    }
    task = background.parse_paste.delay(**kwargs)
    jobs.start(
        user=request.user,
        kind="paste",
        title="Разбор вставленного текста",
        task_id=task.id,
        retry_task="suggestions.parse_paste",
        retry_payload=kwargs,
    )
    return Response({"task": task.id}, status=status.HTTP_202_ACCEPTED)


def _acting_domain(request, requested: str = ""):
    """Домен, за который идёт разбор: у директора — свой, у администратора — выбранный.

    Директор выбирать не может: домен в запросе ему ничего не добавляет.
    Администратор обязан выбрать — иначе непонятно, чьи это данные,
    и валидатору нечем отсеять чужое (фаза 35).
    """
    from core.domains import DOMAINS, can_upload_files

    own = domain_of_role(request.user.role)
    if own is not None:
        return own.code, None
    if not can_upload_files(request.user.role):
        return None, Response({"detail": "У роли нет домена"}, status=status.HTTP_403_FORBIDDEN)
    code = (requested or "").strip()
    if code in DOMAINS:
        return code, None
    titles = ", ".join(f"«{d.title}»" for d in DOMAINS.values())
    return None, Response(
        {"detail": f"Сначала выберите домен, чьи данные вы вставляете: {titles}"},
        status=status.HTTP_400_BAD_REQUEST,
    )


@extend_schema(request=UploadSerializer, responses={202: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload(request):
    """«Загрузить файл»: разбор в фоне. С фазы 35 — только администратор, за выбранный домен."""
    from core.domains import can_upload_files

    denied = _deny_students(request)
    if denied:
        return denied
    if not can_upload_files(request.user.role):
        return Response(
            {"detail": "Файлы загружает администратор. Вставьте текст — разбор тот же"},
            status=status.HTTP_403_FORBIDDEN,
        )
    domain_code, problem = _acting_domain(request, str(request.data.get("domain") or ""))
    if problem:
        return problem

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response({"detail": "Файл не приложен"}, status=status.HTTP_400_BAD_REQUEST)

    raw = uploaded.read()
    content = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else str(raw)
    kwargs = {
        "content": content,
        "filename": uploaded.name,
        "actor_id": request.user.pk,
        "role": request.user.role,
        "domain_code": domain_code,
    }
    task = background.parse_file.delay(**kwargs)
    jobs.start(
        user=request.user,
        kind="parse_file",
        title=f"Разбор файла «{uploaded.name}»",
        task_id=task.id,
        retry_task="suggestions.parse_file",
        retry_payload=kwargs,
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

    kwargs = {
        "student_id": student_id,
        "program_id": serializer.validated_data["program"],
        "actor_id": request.user.pk,
    }
    task = background.explain_match.delay(**kwargs)
    jobs.start(
        user=request.user,
        kind="explain_match",
        title="Объяснение соответствия",
        task_id=task.id,
        retry_task="suggestions.explain_match",
        retry_payload=kwargs,
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

    kwargs = {"essay_id": essay.pk, "prompt": serializer.validated_data["prompt"], "actor_id": request.user.pk}
    task = background.essay_questions.delay(**kwargs)
    jobs.start(
        user=request.user,
        kind="essay_questions",
        title=f"Вопросы по эссе «{essay.title}»",
        task_id=task.id,
        link="/essays",
        retry_task="suggestions.essay_questions",
        retry_payload=kwargs,
    )
    return Response({"task": task.id}, status=status.HTTP_202_ACCEPTED)


# --- Фаза 20: подключение модели ------------------------------------------


class LLMThrottle(ScopedRateThrottle):
    """Отдельный предел на операции с моделью: они стоят денег."""

    scope = "llm"


def _llm_guard(request):
    """Общая проверка перед любой операцией с моделью."""
    denied = _deny_students(request)
    if denied:
        return denied
    if domain_of_role(request.user.role) is None:
        return Response({"detail": "У вашей роли нет домена"}, status=status.HTTP_403_FORBIDDEN)
    try:
        check_available()
    except BudgetExceeded as error:
        # лимит выбран — говорим прямо, а не показываем пустой результат
        return Response({"detail": str(error)}, status=status.HTTP_402_PAYMENT_REQUIRED)
    return None


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def llm_status(request):
    """Подключена ли модель и почему кнопка работает или нет."""
    return Response(llm.status())


@extend_schema(request=OperationSerializer, responses={202: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([LLMThrottle])
def run_operation(request):
    """Операция уровня управления: сводка, список, письмо, задачи."""
    guard = _llm_guard(request)
    if guard:
        return guard

    payload = OperationSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    code = payload.validated_data["code"]
    if command_registry.get(code) is None:
        return Response({"detail": "Такой команды нет"}, status=status.HTTP_400_BAD_REQUEST)
    if request.user.role not in (command_registry.get(code).roles or ()):
        return Response({"detail": "Эта команда не для вашей роли"}, status=status.HTTP_403_FORBIDDEN)

    kwargs = {
        "code": code,
        "actor_id": request.user.pk,
        "role": request.user.role,
        "payload": payload.validated_data,
    }
    task = background.run_operation.delay(**kwargs)
    jobs.start(
        user=request.user,
        kind="operation",
        title=command_registry.get(code).title,
        task_id=task.id,
        retry_task="suggestions.run_operation",
        retry_payload=kwargs,
    )
    return Response({"task": task.id}, status=status.HTTP_202_ACCEPTED)


@extend_schema(request=ParseUniversitySerializer, responses={202: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([LLMThrottle])
def parse_university(request):
    """Название или ссылка → карточка вуза предложением."""
    guard = _llm_guard(request)
    if guard:
        return guard

    payload = ParseUniversitySerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    kwargs = {"text": payload.validated_data["text"], "actor_id": request.user.pk, "role": request.user.role}
    task = background.parse_university.delay(**kwargs)
    jobs.start(
        user=request.user,
        kind="parse_university",
        title=f"Разбор вуза «{payload.validated_data['text'][:60]}»",
        task_id=task.id,
        retry_task="suggestions.parse_university",
        retry_payload=kwargs,
    )
    return Response({"task": task.id}, status=status.HTTP_202_ACCEPTED)


@extend_schema(request=VerifyRequirementsSerializer, responses={202: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([LLMThrottle])
def verify_requirements(request):
    """Сверить требования программы с официальным сайтом вуза.

    Ходит только по белому списку: сайт этого вуза и Common App. Ничего
    не меняет — расхождение уходит предложением.
    """
    if request.user.role not in (DOMAINS["admission"].role, ROLE_ADMIN):
        return Response({"detail": "Справочник вузов ведёт директор по поступлению"}, status=status.HTTP_403_FORBIDDEN)
    guard = _llm_guard(request)
    if guard:
        return guard

    payload = VerifyRequirementsSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    kwargs = {
        "program_id": payload.validated_data["program"],
        "actor_id": request.user.pk,
        "role": request.user.role,
    }
    task = background.verify_requirements.delay(**kwargs)
    jobs.start(
        user=request.user,
        kind="verify_requirements",
        title="Сверка требований с сайтом вуза",
        task_id=task.id,
        link="/directory",
        retry_task="suggestions.verify_requirements",
        retry_payload=kwargs,
    )
    return Response({"task": task.id}, status=status.HTTP_202_ACCEPTED)


@extend_schema(request=ParseActivitySerializer, responses={202: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([LLMThrottle])
def parse_activity(request):
    """Описание словами → активность предложением."""
    guard = _llm_guard(request)
    if guard:
        return guard

    payload = ParseActivitySerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    kwargs = {
        "text": payload.validated_data["text"],
        "student_id": payload.validated_data["student"],
        "actor_id": request.user.pk,
        "role": request.user.role,
    }
    task = background.parse_activity.delay(**kwargs)
    jobs.start(
        user=request.user,
        kind="parse_activity",
        title="Разбор описания активности",
        task_id=task.id,
        retry_task="suggestions.parse_activity",
        retry_payload=kwargs,
    )
    return Response({"task": task.id}, status=status.HTTP_202_ACCEPTED)


@extend_schema(request=ParseImageSerializer, responses={202: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
@throttle_classes([LLMThrottle])
def parse_image(request):
    """Фото грамоты или скриншот с баллами → предложение."""
    guard = _llm_guard(request)
    if guard:
        return guard

    payload = ParseImageSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    uploaded = payload.validated_data["file"]

    from materials.files import FileRejected, inspect

    try:
        info = inspect(uploaded)
    except FileRejected as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    if not info.content_type.startswith("image/"):
        return Response({"detail": "Нужна картинка: JPG или PNG"}, status=status.HTTP_400_BAD_REQUEST)

    uploaded.seek(0)
    task = background.parse_image.delay(
        payload=uploaded.read(),
        media_type=info.content_type,
        kind=payload.validated_data["kind"],
        student_id=payload.validated_data["student"],
        actor_id=request.user.pk,
        role=request.user.role,
    )
    # повтора у распознавания нет: файл живёт один запрос, и хранить
    # картинку ради кнопки «повторить» мы не станем — её загружают заново
    jobs.start(
        user=request.user,
        kind="parse_image",
        title="Распознавание изображения",
        task_id=task.id,
        link=f"/students/{payload.validated_data['student']}",
    )
    return Response({"task": task.id}, status=status.HTTP_202_ACCEPTED)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def llm_spend(request):
    """Экран расходов на модель. Ведёт его администратор."""
    if request.user.role != ROLE_ADMIN:
        return Response({"detail": "Расходы на модель ведёт администратор"}, status=status.HTTP_403_FORBIDDEN)
    days = int(request.query_params.get("days", 30))
    return Response(budget_report(days=max(1, min(days, 365))))


# --- Помощник в углу (фаза 25) ---------------------------------------------


def _own_thread(request, thread_id: int):
    from suggestions.models import AssistantThread

    return AssistantThread.objects.filter(pk=thread_id, user=request.user).first()


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def assistant_quick(request):
    """Быстрые кнопки под роль — четыре штуки, видны сразу при открытии."""
    from suggestions import assistant

    return Response(
        {
            "buttons": [
                {"code": q.code, "title": q.title, "needs": q.needs, "hint": q.hint}
                for q in assistant.quick_for(request.user.role)
            ],
            "model": llm.status(),
        }
    )


@extend_schema(responses=AssistantThreadSerializer(many=True))
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def assistant_threads(request):
    """История диалогов — каждый видит только свои."""
    from suggestions.models import AssistantThread

    if request.method == "POST":
        thread = AssistantThread.objects.create(user=request.user)
        return Response(AssistantThreadSerializer(thread).data, status=status.HTTP_201_CREATED)
    rows = AssistantThread.objects.filter(user=request.user)[:30]
    return Response(AssistantThreadSerializer(rows, many=True).data)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def assistant_thread_detail(request, pk: int):
    """Сообщения одного диалога. Чужой диалог — 404, а не 403."""
    thread = _own_thread(request, pk)
    if thread is None:
        return Response({"detail": "Диалог не найден"}, status=status.HTTP_404_NOT_FOUND)
    return Response(
        {
            "thread": AssistantThreadSerializer(thread).data,
            "messages": AssistantMessageSerializer(thread.messages.all(), many=True).data,
        }
    )


@extend_schema(request=AssistantAskSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([LLMThrottle])
def assistant_ask(request):
    """Вопрос помощнику: быстрая кнопка или свободный текст.

    Любое изменение данных — только предложением (инвариант №3): ответ
    несёт `suggestion`, применяет человек. Домен проверяет валидатор
    предложений на сервере, а не подпись кнопки.
    """
    from suggestions import assistant
    from suggestions.models import AssistantMessage, AssistantThread

    payload = AssistantAskSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    data = payload.validated_data

    thread = None
    if data.get("thread"):
        thread = _own_thread(request, data["thread"])
        if thread is None:
            return Response({"detail": "Диалог не найден"}, status=status.HTTP_404_NOT_FOUND)
    if thread is None:
        thread = AssistantThread.objects.create(user=request.user)

    code = (data.get("command") or "").strip()
    text = (data.get("text") or "").strip()
    students = data.get("students") or []
    screen = (data.get("screen") or "").strip()

    if code:
        titles = {q.code: q.title for q in assistant.quick_for(request.user.role)}
        question = titles.get(code, code) + (f": {text}" if text else "")
    else:
        question = text
    AssistantMessage.objects.create(thread=thread, author="user", text=question, command=code)

    if code:
        answer = assistant.run_quick(code, actor=request.user, role=request.user.role, student_ids=students, text=text)
    else:
        answer = assistant.free_text(
            text=text, actor=request.user, role=request.user.role, student_ids=students, screen=screen
        )

    reply = AssistantMessage.objects.create(
        thread=thread,
        author="assistant",
        text=answer["text"],
        lines="\n".join(answer["lines"]),
        command=code,
        suggestion_id=answer["suggestion"],
        offline=answer["offline"],
        affected=answer["affected"],
    )
    if not thread.title:
        thread.title = question[:200]
    thread.save(update_fields=["title", "updated_at"])

    return Response(
        {
            "thread": AssistantThreadSerializer(thread).data,
            "message": AssistantMessageSerializer(reply).data,
            # почему ответ проще обычного: ключа нет, лимит выбран или
            # модель не ответила. В истории останется только признак
            # «собрано правилами» — причина к тому времени уже неважна
            "note": answer.get("note", ""),
        }
    )
