"""API центра подготовки: банк, тренировки, пробные экзамены."""

from __future__ import annotations

from django.http import Http404
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.deletion import HardDeleteMixin
from core.domains import ROLE_STUDENT, can_write
from prep import services
from prep.imports import import_questions
from prep.models import (
    MockExam,
    MockRun,
    PracticeAnswer,
    PracticeSession,
    Question,
    QuestionPassage,
    Section,
    TheoryLesson,
)
from prep.serializers import (
    AnswerSerializer,
    FinishSerializer,
    MockExamSerializer,
    OpenAnswerReviewSerializer,
    PassageSerializer,
    QuestionImportSerializer,
    QuestionSerializer,
    ReviewMockSerializer,
    StartPracticeSerializer,
    TheoryLessonSerializer,
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
    filterset_fields = ("exam_type", "section", "difficulty", "is_active", "passage")
    search_fields = ("topic", "text", "source")

    def get_queryset(self):
        if self.request.user.role == ROLE_STUDENT:
            # верный ответ ученику в списке заданий не отдаём
            return self.queryset.none()
        return self.queryset

    def _deny_if_not_owner(self):
        if not _keeps_the_bank(self.request.user):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied(_("Банк заданий ведёт академический директор"))

    # право проверяется до разбора формы: чужому директору отвечаем «не ваш
    # банк», а не «нужно хотя бы два варианта ответа»
    def create(self, request, *args, **kwargs):
        self._deny_if_not_owner()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._deny_if_not_owner()
        return super().update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        self._deny_if_not_owner()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


class PassageViewSet(viewsets.ModelViewSet):
    """Источники банка: текст для чтения и аудио для аудирования.

    Ведёт академический директор, как и сами задания. Ученику список закрыт:
    пассаж он видит внутри тренировки, вместе со своими вопросами. Удаление —
    скрытие: на источник ссылаются задания, а на задания — ответы учеников.
    """

    queryset = QuestionPassage.objects.all().order_by("-id")
    serializer_class = PassageSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ("exam_type", "section", "kind", "is_active")
    search_fields = ("title", "body")

    def get_queryset(self):
        if self.request.user.role == ROLE_STUDENT:
            return self.queryset.none()
        return self.queryset

    def _deny_if_not_owner(self):
        if not _keeps_the_bank(self.request.user):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied(_("Банк заданий ведёт академический директор"))

    # право проверяется до разбора формы: чужому директору отвечаем «не ваш
    # банк», а не «нужно хотя бы два варианта ответа»
    def create(self, request, *args, **kwargs):
        self._deny_if_not_owner()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._deny_if_not_owner()
        return super().update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        self._deny_if_not_owner()
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        instance.questions.update(is_active=False)


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

            raise PermissionDenied(_("Mock Test онлайн собирает академический директор"))
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
            {"detail": _("Файлы загружает администратор. Задания заводятся руками на экране «Mock Test онлайн»")},
            status=status.HTTP_403_FORBIDDEN,
        )

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response({"detail": _("Файл не приложен")}, status=status.HTTP_400_BAD_REQUEST)

    raw = uploaded.read()
    content = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else str(raw)
    # аудио и картинки приложены отдельными файлами, подбираются по имени
    media: dict[str, tuple[bytes, str]] = {}
    for key, files in request.FILES.lists():
        if key == "file":
            continue
        for handle in files:
            media[handle.name] = (handle.read(), handle.content_type or "application/octet-stream")

    dry_run = str(request.data.get("dry_run", "")).lower() in {"1", "true", "yes"}
    return Response(import_questions(content, media=media, dry_run=dry_run).as_dict())


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
        return Response({"detail": _("Тренируется ученик")}, status=status.HTTP_403_FORBIDDEN)

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
            size=data.get("size"),
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
        return Response({"detail": _("Сессии нет")}, status=status.HTTP_404_NOT_FOUND)
    finished = session.status != "running"
    return Response(services.session_payload(session, with_answers=finished))


@extend_schema(request=AnswerSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def practice_answer(request, pk: int):
    """Ответить на одно задание."""
    session = _own_session(request, pk)
    if session is None:
        return Response({"detail": _("Сессии нет")}, status=status.HTTP_404_NOT_FOUND)

    serializer = AnswerSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        result = services.answer_question(
            session,
            answer_id=serializer.validated_data["answer_id"],
            option_id=serializer.validated_data.get("option"),
            seconds=serializer.validated_data.get("seconds", 0),
            text=serializer.validated_data.get("text", ""),
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
        return Response({"detail": _("Сессии нет")}, status=status.HTTP_404_NOT_FOUND)

    serializer = FinishSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if hasattr(session, "mock_run"):
        return Response(services.finish_mock(session.mock_run, seconds=serializer.validated_data.get("seconds", 0)))
    return Response(services.finish_practice(session, seconds=serializer.validated_data.get("seconds", 0)))


# --- открытые ответы: Writing и Speaking проверяет человек -----------------


def _open_answer_row(row) -> dict:
    question = row.question
    return {
        "id": row.pk,
        "student_id": row.session.student_id,
        "student": row.session.student.full_name,
        "group": row.session.student.group.code if row.session.student.group_id else "",
        "exam_type": question.exam_type,
        "section": question.section,
        "section_title": question.get_section_display(),
        "topic": question.topic,
        "task": question.text,
        "criteria": question.criteria,
        "word_limit": question.word_limit,
        "minute_limit": question.minute_limit,
        "answer": row.text,
        "words": len(row.text.split()),
        "answered_at": row.session.finished_at or row.answered_at,
        "reviewed": row.reviewed_at is not None,
        "score": float(row.review_score) if row.review_score is not None else None,
        "comment": row.review_comment,
        "reviewed_at": row.reviewed_at,
    }


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def open_answers(request):
    """Открытые ответы учеников: что ждёт проверки и что уже проверено."""
    from prep.models import OPEN_TYPES, SessionStatus

    if not _keeps_the_bank(request.user):
        return Response(
            {"detail": _("Открытые ответы проверяет академический директор")}, status=status.HTTP_403_FORBIDDEN
        )
    rows = (
        PracticeAnswer.objects.filter(question__question_type__in=OPEN_TYPES)
        .exclude(text="")
        .exclude(session__status=SessionStatus.RUNNING)
        .select_related("question", "session__student__group")
        .order_by("reviewed_at", "-id")
    )
    waiting = rows.filter(reviewed_at__isnull=True)
    state = request.query_params.get("state") or "waiting"
    shown = waiting if state == "waiting" else rows.filter(reviewed_at__isnull=False).order_by("-reviewed_at")
    return Response({"waiting": waiting.count(), "results": [_open_answer_row(row) for row in shown[:200]]})


@extend_schema(request=OpenAnswerReviewSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def open_answer_review(request, pk: int):
    """Проверить открытый ответ: оценка по шкале экзамена и комментарий."""
    from django.utils import timezone

    from core.domains import scale_of
    from prep.models import OPEN_TYPES

    if not _keeps_the_bank(request.user):
        return Response(
            {"detail": _("Открытые ответы проверяет академический директор")}, status=status.HTTP_403_FORBIDDEN
        )
    row = (
        PracticeAnswer.objects.filter(pk=pk, question__question_type__in=OPEN_TYPES)
        .exclude(text="")
        .select_related("question", "session__student__group")
        .first()
    )
    if row is None:
        return Response({"detail": _("Такого ответа нет")}, status=status.HTTP_404_NOT_FOUND)
    serializer = OpenAnswerReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    score = serializer.validated_data.get("score")
    scale = scale_of(row.question.exam_type, section=True) or scale_of(row.question.exam_type)
    if score is not None and scale is not None and not scale.holds(score):
        return Response(
            {"detail": _("Оценка {exam} — {hint}").format(exam=row.question.exam_type, hint=scale.hint)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    row.review_score = score
    row.review_comment = str(serializer.validated_data.get("comment") or "").strip()
    row.reviewed_by = request.user
    row.reviewed_at = timezone.now()
    row.save(update_fields=["review_score", "review_comment", "reviewed_by", "reviewed_at"])
    return Response(_open_answer_row(row))


# --- пробный экзамен ------------------------------------------------------


@extend_schema(request=None, responses={201: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mock_start(request, pk: int):
    """Начать пробный экзамен."""
    student = _own_student(request)
    if student is None:
        return Response({"detail": _("Mock Test проходит ученик")}, status=status.HTTP_403_FORBIDDEN)

    mock = MockExam.objects.filter(pk=pk).prefetch_related("sections").first()
    if mock is None:
        return Response({"detail": _("Такого Mock Test нет")}, status=status.HTTP_404_NOT_FOUND)

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
        return Response({"detail": _("Это экран ученика")}, status=status.HTTP_403_FORBIDDEN)

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
                # решение директора с подписью: после отказа ученик читает «не засчитан»
                "review_state": run.review_state,
                "review_state_title": run.review_title(),
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
        return Response({"detail": _("Список ведёт академический директор")}, status=status.HTTP_403_FORBIDDEN)

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
                "review_state": run.review_state,
                "review_state_title": run.review_title(for_director=True),
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
        return Response({"detail": _("Решение принимает академический директор")}, status=status.HTTP_403_FORBIDDEN)

    run = MockRun.objects.filter(pk=pk).select_related("exam_attempt", "student__exam", "mock").first()
    if run is None:
        return Response({"detail": _("Прохождения нет")}, status=status.HTTP_404_NOT_FOUND)

    serializer = ReviewMockSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return Response(services.review_mock(run, count_it=serializer.validated_data["count_it"], actor=request.user))


# --- Центр подготовки: прогресс, статистика, теория (фаза 42) --------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def center_exams(request):
    """Семь плиток экзаменов с прогрессом ученика."""
    from prep import prep_center

    student = _own_student(request)
    if student is None:
        return Response({"detail": _("Центр подготовки — экран ученика")}, status=status.HTTP_403_FORBIDDEN)
    # размер тренировки стоит в подписи кнопки — число приходит отсюда, экран его не знает
    return Response({"exams": prep_center.exams(student), "practice_size": services.practice_size()})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def center_sections(request, exam: str):
    """Секции экзамена с прогрессом «решено N из M»."""
    from prep import prep_center

    student = _own_student(request)
    if student is None:
        return Response({"detail": _("Центр подготовки — экран ученика")}, status=status.HTTP_403_FORBIDDEN)
    return Response({"sections": prep_center.sections(student, exam)})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def center_topics(request, exam: str, section: str):
    """Темы секции с прогрессом по каждой отдельно."""
    from prep import prep_center

    student = _own_student(request)
    if student is None:
        return Response({"detail": _("Центр подготовки — экран ученика")}, status=status.HTTP_403_FORBIDDEN)
    return Response({"topics": prep_center.topics(student, exam, section)})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def center_statistics(request, exam: str):
    """Статистика по экзамену: прогноз, до цели, рост, серия, календарь, слабые."""
    from prep import prep_center

    student = _own_student(request)
    if student is None:
        return Response({"detail": _("Статистика — экран ученика")}, status=status.HTTP_403_FORBIDDEN)
    return Response(prep_center.statistics(student, exam))


class TheoryLessonViewSet(HardDeleteMixin, viewsets.ModelViewSet):
    """Теория: ведёт академический директор, читают ученики.

    Уроки без истории — удаление физическое (инвариант №13). Файл урока
    отдаётся своим маршрутом после проверки прав.
    """

    queryset = TheoryLesson.objects.all()
    serializer_class = TheoryLessonSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("exam_type", "section", "level")

    def get_queryset(self):
        qs = super().get_queryset()
        # ученику — только показываемые уроки
        if self.request.user.role == ROLE_STUDENT:
            return qs.filter(is_active=True)
        return qs

    def _deny_if_not_owner(self):
        from rest_framework.exceptions import PermissionDenied

        if not _keeps_the_bank(self.request.user):
            raise PermissionDenied(_("Теорию ведёт академический директор"))

    def perform_create(self, serializer):
        self._deny_if_not_owner()
        serializer.save()

    def perform_update(self, serializer):
        self._deny_if_not_owner()
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """Убрать урок (D37, фаза 62): скрыть, а не удалить физически.

        Тот же приём, что у вопроса банка: урок исчезает у ученика,
        у академического директора остаётся в списке скрытым. Право —
        из реестра (`DELETE_RULES`), как у всех справочников.
        """
        from core.deletion import refuse
        from core.domains import can_delete

        lesson = self.get_object()
        if not can_delete(request.user.role, "prep.TheoryLesson"):
            return refuse(request.user.role, "prep.TheoryLesson")
        lesson.is_active = False
        lesson.save(update_fields=["is_active"])
        return Response({"detail": _("Урок «{title}» скрыт: ученики его больше не видят").format(title=lesson.title)})


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def theory_file(request, pk: int):
    """Файл урока теории — после проверки прав, вне корня веб-сервера."""
    from django.http import FileResponse

    from prep.models import TheoryLesson

    lesson = TheoryLesson.objects.filter(pk=pk).first()
    if lesson is None or not lesson.file:
        raise Http404(_("Файла нет"))
    if request.user.role == ROLE_STUDENT and not lesson.is_active:
        raise Http404(_("Файла нет"))
    response = FileResponse(lesson.file.open("rb"), content_type=lesson.file_content_type or "application/octet-stream")
    response["Content-Disposition"] = f'inline; filename="theory-{lesson.pk}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@extend_schema(responses={200: None})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def passage_audio(request, pk: int):
    """Аудио источника — только ученику внутри тренировки и сотрудникам."""
    from django.http import FileResponse

    passage = QuestionPassage.objects.filter(pk=pk).first()
    if passage is None or not passage.audio:
        raise Http404(_("Аудио нет"))
    # ученику — только аудио из его собственной тренировки: прямой адрес чужого
    # источника отвечает так же, как несуществующий
    student = _own_student(request)
    if request.user.role == ROLE_STUDENT and not (
        student is not None
        and PracticeAnswer.objects.filter(session__student=student, question__passage=passage).exists()
    ):
        raise Http404(_("Аудио нет"))
    response = FileResponse(passage.audio.open("rb"), content_type=passage.audio_content_type or "audio/mpeg")
    response["Content-Disposition"] = f'inline; filename="audio-{passage.pk}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
