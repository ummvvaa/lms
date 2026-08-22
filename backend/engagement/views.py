"""API онбординга, XP и заданий на сегодня."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.domains import ROLE_STUDENT
from engagement import onboarding, scoring, today
from engagement.serializers import OnboardingAnswerSerializer, OnboardingReviewSerializer


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
def game_state(request):
    """XP, уровень, стрик и задания на сегодня."""
    student = _own_student(request)
    if student is None:
        return Response({"detail": "Это экран ученика"}, status=status.HTTP_403_FORBIDDEN)

    payload = scoring.summary(student)
    payload["today"] = today.for_student(student)
    payload["awards"] = scoring.awards_table()
    return Response(payload)
