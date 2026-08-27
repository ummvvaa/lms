"""API центра подготовки: банк, тренировки, пробные экзамены."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.deletion import HardDeleteMixin
from core.domains import ROLE_STUDENT, can_write
from prep import services
from prep.imports import import_questions
from prep.models import MockExam, MockRun, PracticeSession, Question, Section
from prep.serializers import (
    AnswerSerializer,
    FinishSerializer,
    MockExamSerializer,
    QuestionImportSerializer,
    QuestionSerializer,
    ReviewMockSerializer,
    StartPracticeSerializer,
)


def _keeps_the_bank(user) -> bool:
    """Банк заданий ведёт тот, кто владеет доменом экзаменов."""
    return can_write(user.role, "students.ExamAttempt", "total_score")


class QuestionViewSet(HardDeleteMixin, viewsets.ModelViewSet):
    """Банк заданий. Ведёт академический директор — руками или импортом.

    Вопрос удаляется физически: истории у него нет. Но если по нему уже
    отвечали, ссылка держит запись — отказ приходит человеческим текстом
    со списком того, что мешает.
    """

    queryset = Question.objects.prefetch_related("options").all()
    serializer_class = QuestionSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("exam_type", "section", "difficulty", "is_active")
    search_fields = ("topic", "text", "source")

    def get_queryset(self):
        if self.request.user.role == ROLE_STUDENT:
            # верный ответ ученику в списке заданий не отдаём
            return self.queryset.none()
        return self.queryset

    def _deny_if_not_owner(self):
        if not _keeps_the_bank(self.request.user):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Банк заданий ведёт академический директор")

    def perform_create(self, serializer):
        self._deny_if_not_owner()
        serializer.save()

    def perform_update(self, serializer):
        self._deny_if_not_owner()
        serializer.save()

    def perform_destroy(self, instance):
        self._deny_if_not_owner()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


class MockExamViewSet(HardDeleteMixin, viewsets.ModelViewSet):
    """Пробные экзамены. Ученик видит только активные."""

    queryset = MockExam.objects.prefetch_related("sections").all()
    serializer_class = MockExamSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("exam_type", "is_active")

    def get_queryset(self):
        if self.request.user.role == ROLE_STUDENT:
            return self.queryset.filter(is_active=True)
        return self.queryset

    def perform_create(self, serializer):
        if not _keeps_the_bank(self.request.user):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Пробные экзамены собирает академический директор")
        serializer.save()


@extend_schema(request=QuestionImportSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def questions_import(request):
    """Импорт банка из файла. Строка с ошибкой не роняет весь файл.

    Банк ведёт академический директор, а файл грузит администратор
    (фаза 35): загрузка файлов — единственное, что он делает за чужой домен.
    """
    from core.domains import can_upload_files

    if not can_upload_files(request.user.role):
        return Response(
            {"detail": "Файлы загружает администратор. Задания заводятся руками на экране «Пробные»"},
            status=status.HTTP_403_FORBIDDEN,
        )

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response({"detail": "Файл не приложен"}, status=status.HTTP_400_BAD_REQUEST)
    dry_run = str(request.data.get("dry_run", "")).lower() in {"1", "true", "yes"}
    return Response(import_questions(uploaded, dry_run=dry_run).as_dict())


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bank_overview(request):
    """Что вообще есть в банке — по экзаменам, секциям и темам."""
    from django.db.models import Count

    rows = (
        Question.objects.filter(is_active=True)
        .values("exam_type", "section", "topic", "difficulty")
        .annotate(n=Count("id"))
        .order_by("exam_type", "section", "topic")
    )
    sections = dict(Section.choices)
    return Response(
        {
            "total": sum(row["n"] for row in rows),
            "rows": [{**row, "section_title": sections.get(row["section"], row["section"])} for row in rows],
        }
    )


# --- тренировка ----------------------------------------------------------


def _own_student(request):
    return getattr(request.user, "student", None)


def _own_session(request, pk: int) -> PracticeSession | None:
    student = _own_student(request)
    if student is None:
        return None
    return PracticeSession.objects.filter(pk=pk, student=student).first()


@extend_schema(request=StartPracticeSerializer, responses={201: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def practice_start(request):
    """Собрать тренировку по секции и сложности."""
    student = _own_student(request)
    if student is None:
        return Response({"detail": "Тренируется ученик"}, status=status.HTTP_403_FORBIDDEN)

    serializer = StartPracticeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        session = services.start_practice(
            student,
            exam_type=data["exam_type"],
            section=data.get("section", ""),
            difficulty=data.get("difficulty", ""),
            topic=data.get("topic", ""),
            size=data.get("size", services.DEFAULT_PRACTICE_SIZE),
        )
    except services.PrepError as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(services.session_payload(session), status=status.HTTP_201_CREATED)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def practice_detail(request, pk: int):
    """Текущее состояние тренировки."""
    session = _own_session(request, pk)
    if session is None:
        return Response({"detail": "Сессии нет"}, status=status.HTTP_404_NOT_FOUND)
    finished = session.status != "running"
    return Response(services.session_payload(session, with_answers=finished))


@extend_schema(request=AnswerSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def practice_answer(request, pk: int):
    """Ответить на одно задание."""
    session = _own_session(request, pk)
    if session is None:
        return Response({"detail": "Сессии нет"}, status=status.HTTP_404_NOT_FOUND)

    serializer = AnswerSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        result = services.answer_question(
            session,
            answer_id=serializer.validated_data["answer_id"],
            option_id=serializer.validated_data.get("option"),
            seconds=serializer.validated_data.get("seconds", 0),
        )
    except services.PrepError as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(result)


@extend_schema(request=FinishSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def practice_finish(request, pk: int):
    """Завершить тренировку и получить разбор."""
    session = _own_session(request, pk)
    if session is None:
        return Response({"detail": "Сессии нет"}, status=status.HTTP_404_NOT_FOUND)

    serializer = FinishSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if hasattr(session, "mock_run"):
        return Response(services.finish_mock(session.mock_run, seconds=serializer.validated_data.get("seconds", 0)))
    return Response(services.finish_practice(session, seconds=serializer.validated_data.get("seconds", 0)))


# --- пробный экзамен ------------------------------------------------------


@extend_schema(request=None, responses={201: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mock_start(request, pk: int):
    """Начать пробный экзамен."""
    student = _own_student(request)
    if student is None:
        return Response({"detail": "Мок проходит ученик"}, status=status.HTTP_403_FORBIDDEN)

    mock = MockExam.objects.filter(pk=pk).prefetch_related("sections").first()
    if mock is None:
        return Response({"detail": "Такого мока нет"}, status=status.HTTP_404_NOT_FOUND)

    try:
        run, shortages = services.start_mock(student, mock)
    except services.PrepError as error:
        return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

    payload = services.session_payload(run.session)
    payload.update(
        {
            "run": run.pk,
            "mock": mock.title,
            "time_limit_minutes": mock.time_limit_minutes,
            "shortages": [
                {"section": row.section, "asked": row.asked, "available": row.available} for row in shortages
            ],
        }
    )
    return Response(payload, status=status.HTTP_201_CREATED)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_runs(request):
    """Мои пробные экзамены."""
    student = _own_student(request)
    if student is None:
        return Response({"detail": "Это экран ученика"}, status=status.HTTP_403_FORBIDDEN)

    rows = MockRun.objects.filter(student=student).select_related("mock", "exam_attempt", "session")
    return Response(
        [
            {
                "id": run.pk,
                "mock": run.mock.title,
                "exam_type": run.mock.exam_type,
                "session": run.session_id,
                "status": run.session.status,
                "score": float(run.exam_attempt.total_score) if run.exam_attempt else None,
                "counted_in_profile": run.counted_in_profile,
                "created_at": run.created_at,
            }
            for run in rows
        ]
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def platform_mocks(request):
    """Платформенные моки — отдельным списком у академического директора."""
    if request.user.role == ROLE_STUDENT:
        return Response({"detail": "Список ведёт академический директор"}, status=status.HTTP_403_FORBIDDEN)

    rows = (
        MockRun.objects.exclude(exam_attempt__isnull=True)
        .select_related("student", "mock", "exam_attempt", "session")
        .order_by("-created_at")
    )
    return Response(
        [
            {
                "id": run.pk,
                "student": run.student_id,
                "student_name": run.student.full_name,
                "mock": run.mock.title,
                "exam_type": run.mock.exam_type,
                "score": float(run.exam_attempt.total_score) if run.exam_attempt else None,
                "correct": run.session.correct,
                "total": run.session.total,
                "counted_in_profile": run.counted_in_profile,
                "reviewed_at": run.reviewed_at,
                "created_at": run.created_at,
            }
            for run in rows
        ]
    )


@extend_schema(request=ReviewMockSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def review_platform_mock(request, pk: int):
    """Учитывать ли платформенный мок в текущем балле."""
    if not _keeps_the_bank(request.user):
        return Response({"detail": "Решение принимает академический директор"}, status=status.HTTP_403_FORBIDDEN)

    run = MockRun.objects.filter(pk=pk).select_related("exam_attempt", "student__exam", "mock").first()
    if run is None:
        return Response({"detail": "Прохождения нет"}, status=status.HTTP_404_NOT_FOUND)

    serializer = ReviewMockSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return Response(services.review_mock(run, count_it=serializer.validated_data["count_it"], actor=request.user))
