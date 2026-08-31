"""API онбординга, XP и заданий на сегодня."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.deletion import refuse
from core.domains import ROLE_STUDENT, can_delete, owns_model
from core.permissions import DomainFieldPermission
from engagement import onboarding, scoring, today
from engagement.models import CareerDirection, CareerQuestion, CareerRun
from engagement.serializers import (
    CareerQuestionSerializer,
    CareerRunRequestSerializer,
    CareerRunSerializer,
    OnboardingAnswerSerializer,
    OnboardingReviewSerializer,
)


def _own_student(request):
    return getattr(request.user, "student", None)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def onboarding_state(request):
    """Где ученик в квизе: что отвечено, какой вопрос следующий."""
    student = _own_student(request)
    if student is None:
        return Response({"detail": "Квиз проходит ученик"}, status=status.HTTP_403_FORBIDDEN)
    return Response(onboarding.state(student))


@extend_schema(request=OnboardingAnswerSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def onboarding_answer(request):
    """Ответить на один шаг. Прогресс сохраняется сразу, а не в конце."""
    student = _own_student(request)
    if student is None:
        return Response({"detail": "Квиз проходит ученик"}, status=status.HTTP_403_FORBIDDEN)

    serializer = OnboardingAnswerSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        result = onboarding.answer(
            student,
            code=serializer.validated_data["question"],
            value=serializer.validated_data.get("value", ""),
            actor=request.user,
        )
    except ValueError as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(result)


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def onboarding_skip(request):
    """Отложить квиз. Вернуться можно в любой момент."""
    student = _own_student(request)
    if student is None:
        return Response({"detail": "Квиз проходит ученик"}, status=status.HTTP_403_FORBIDDEN)
    return Response(onboarding.skip(student))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def onboarding_pending(request):
    """Что ученики написали о себе и ждёт подтверждения директора."""
    if request.user.role == ROLE_STUDENT:
        return Response({"detail": "Список подтверждений ведёт директор"}, status=status.HTTP_403_FORBIDDEN)
    return Response(onboarding.pending_for(request.user.role))


@extend_schema(request=OnboardingReviewSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def onboarding_review(request, pk: int):
    """Подтвердить слова ученика, поправить их или снять."""
    if request.user.role == ROLE_STUDENT:
        return Response({"detail": "Решение принимает директор"}, status=status.HTTP_403_FORBIDDEN)

    serializer = OnboardingReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        result = onboarding.review(
            pk,
            decision=serializer.validated_data["decision"],
            value=serializer.validated_data.get("value"),
            actor=request.user,
        )
    except ValueError as error:
        return Response({"detail": str(error)}, status=status.HTTP_404_NOT_FOUND)
    return Response(result)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def journey_state(request):
    """Лестница шагов ученика: пять шагов пути с прогрессом (фаза 37)."""
    from engagement import journey

    student = _own_student(request)
    if student is None:
        return Response({"detail": "Это экран ученика"}, status=status.HTTP_403_FORBIDDEN)
    return Response(journey.build(student))


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def game_state(request):
    """XP, уровень, стрик и задания на сегодня."""
    student = _own_student(request)
    if student is None:
        return Response({"detail": "Это экран ученика"}, status=status.HTTP_403_FORBIDDEN)

    payload = scoring.summary(student)
    payload["today"] = today.for_student(student)
    payload["awards"] = scoring.awards_table()
    return Response(payload)


# --- Профтест (фаза 45) ----------------------------------------------------


class CareerQuestionViewSet(viewsets.ModelViewSet):
    """Анкета профтеста. Ведёт директор школы, читают все.

    Вопросы — справочник домена «Профиль и дисциплина», а не константы
    в коде: школа меняет формулировки без выката.
    """

    queryset = CareerQuestion.objects.all()
    serializer_class = CareerQuestionSerializer
    permission_classes = [DomainFieldPermission]
    domain_model_label = "engagement.CareerQuestion"

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(is_active=True) if self.request.user.role == ROLE_STUDENT else qs

    def create(self, request, *args, **kwargs):
        if not owns_model(request.user.role, self.domain_model_label):
            return refuse(request.user.role, self.domain_model_label)
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not can_delete(request.user.role, self.domain_model_label):
            return refuse(request.user.role, self.domain_model_label)
        if instance.answers.exists():
            return Response(
                {
                    "detail": f"На вопрос уже отвечали: {instance.answers.count()}. "
                    "Снимите галочку «Показывать в анкете» — ответы должны остаться читаемыми"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def career_state(request):
    """Состояние профтеста: доступен ли, анкета и прошлые проходы."""
    from engagement import career

    student = _own_student(request)
    if student is None:
        return Response({"detail": "Профтест проходит ученик"}, status=status.HTTP_403_FORBIDDEN)

    state = career.availability()
    runs = CareerRun.objects.filter(student=student).prefetch_related("directions__programs", "answers__question")
    return Response(
        {
            "available": state.available,
            "detail": state.detail,
            "questions": CareerQuestionSerializer(career.questions(), many=True).data,
            "runs": CareerRunSerializer(runs, many=True).data,
        }
    )


@extend_schema(request=CareerRunRequestSerializer, responses={201: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def career_run(request):
    """Пройти анкету и получить разбор.

    Без ключа модели раздел отвечает «недоступно» и говорит почему:
    разбор правилами дал бы бессмысленный результат.
    """
    from engagement import career

    student = _own_student(request)
    if student is None:
        return Response({"detail": "Профтест проходит ученик"}, status=status.HTTP_403_FORBIDDEN)

    serializer = CareerRunRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    answers = {row["question"]: row.get("value", "") for row in serializer.validated_data["answers"]}
    try:
        run = career.run_for(student, answers=answers, actor=request.user, role=request.user.role)
    except career.CareerUnavailable as error:
        return Response({"detail": str(error), "available": False}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(CareerRunSerializer(run).data, status=status.HTTP_201_CREATED)


@extend_schema(responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def career_agree(request, pk: int):
    """«Согласен с направлением» — оно уходит предложением директору."""
    from engagement import career

    student = _own_student(request)
    if student is None:
        return Response({"detail": "Профтест проходит ученик"}, status=status.HTTP_403_FORBIDDEN)

    direction = CareerDirection.objects.filter(pk=pk, run__student=student).first()
    if direction is None:
        return Response({"detail": "Такого направления нет"}, status=status.HTTP_404_NOT_FOUND)
    if direction.agreed_at is not None:
        return Response({"detail": "Это направление уже отправлено директору", "ok": False})

    outcome = career.agree(direction, user=request.user, student=student)
    return Response(outcome, status=status.HTTP_200_OK if outcome["ok"] else status.HTTP_400_BAD_REQUEST)
