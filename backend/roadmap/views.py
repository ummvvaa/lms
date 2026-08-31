"""API роадмапа и эссе."""

from __future__ import annotations

from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.deletion import ArchiveDeleteMixin, HardDeleteMixin
from core.domains import ROLE_STUDENT
from roadmap.models import ApplicationPlan, Essay, EssayComment, EssayVersion, Task, TaskComment, TaskTemplate
from roadmap.permissions import OwnCommentOrCurator, OwnStudentOrStaff, StaffOnly
from roadmap.serializers import (
    ApplicationPlanSerializer,
    EssayCommentSerializer,
    EssaySerializer,
    EssayVersionSerializer,
    GenerateTasksSerializer,
    TaskCommentSerializer,
    TaskSerializer,
    TaskTemplateSerializer,
)
from roadmap.services import complete, generate_all
from students.models import Student


def _visible_students(user):
    """Ученик видит себя, сотрудник — всех."""
    if user.role == ROLE_STUDENT:
        student = getattr(user, "student", None)
        return Student.objects.filter(pk=student.pk) if student else Student.objects.none()
    return Student.objects.all()


class TaskFilter(filters.FilterSet):
    group = filters.CharFilter(field_name="student__group__code")
    due_before = filters.DateFilter(field_name="due_date", lookup_expr="lte")

    class Meta:
        model = Task
        fields = ("student", "status", "category", "priority", "group")


class TaskViewSet(ArchiveDeleteMixin, viewsets.ModelViewSet):
    """Задачи ученика. Два представления на фронте — таймлайн и доска."""

    queryset = Task.objects.select_related(
        "student", "admission_round__program__university", "template"
    ).prefetch_related("comments")
    serializer_class = TaskSerializer
    permission_classes = [OwnStudentOrStaff]
    filterset_class = TaskFilter
    search_fields = ("title", "description")
    ordering_fields = ("due_date", "priority", "status")

    def get_queryset(self):
        return super().get_queryset().filter(student__in=_visible_students(self.request.user))

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        """Смена статуса — перетаскивание карточки на доске."""
        task = self.get_object()
        new_status = request.data.get("status")
        if new_status not in dict(Task._meta.get_field("status").choices):
            return Response({"detail": "Неизвестный статус"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TaskSerializer(complete(task, status=new_status)).data)

    @action(detail=False, methods=["get"], url_path="my")
    def my(self, request):
        """Роадмап текущего ученика."""
        student = getattr(request.user, "student", None)
        if student is None:
            return Response({"detail": "У пользователя нет карточки ученика"}, status=404)
        tasks = self.get_queryset().filter(student=student)
        return Response(TaskSerializer(tasks, many=True).data)


class TaskTemplateViewSet(HardDeleteMixin, viewsets.ModelViewSet):
    """Шаблоны задач. Истории у шаблона нет — удаляется физически."""

    queryset = TaskTemplate.objects.all()
    serializer_class = TaskTemplateSerializer
    permission_classes = [StaffOnly]
    filterset_fields = ("category", "is_active", "graduation_year", "grade")


class TaskCommentViewSet(viewsets.ModelViewSet):
    """Комментарии к задаче: пишет любой, правит и убирает только автор."""

    queryset = TaskComment.objects.select_related("author", "task__student").all()
    serializer_class = TaskCommentSerializer
    permission_classes = [OwnCommentOrCurator]
    filterset_fields = ("task",)

    def get_queryset(self):
        """Ученик видит комментарии только к своим задачам."""
        return super().get_queryset().filter(task__student__in=_visible_students(self.request.user))

    def perform_create(self, serializer):
        """Комментарий уходит только к той задаче, которая человеку видна.

        Без этой проверки ученик мог написать под чужой задачей: `get_queryset`
        закрывает чтение, а создание шло мимо него.
        """
        task = serializer.validated_data.get("task")
        if task is not None and task.student_id not in _visible_students(self.request.user).values_list(
            "pk", flat=True
        ):
            raise PermissionDenied("Эта задача вам не видна")
        serializer.save(author=self.request.user)


class EssayViewSet(ArchiveDeleteMixin, viewsets.ModelViewSet):
    """Эссе. ИИ к тексту на этой фазе не подключается вообще."""

    queryset = Essay.objects.select_related("student", "program", "curator").prefetch_related("versions", "comments")
    serializer_class = EssaySerializer
    permission_classes = [OwnStudentOrStaff]
    filterset_fields = ("student", "status", "essay_type")

    def get_queryset(self):
        return super().get_queryset().filter(student__in=_visible_students(self.request.user))

    @action(detail=True, methods=["post"], url_path="versions")
    def add_version(self, request, pk=None):
        """Новая версия текста. Номер выдаётся сервером."""
        essay = self.get_object()
        last = essay.versions.order_by("-number").values_list("number", flat=True).first()
        number = (last or 0) + 1
        version = EssayVersion.objects.create(
            essay=essay,
            number=number,
            text=request.data.get("text", ""),
            author=request.user,
        )
        return Response(EssayVersionSerializer(version).data, status=201)

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        """Отправить эссе на проверку куратору.

        Отправка — действие, за него начисляется XP (инвариант №12).
        Оценка текста на начисление не влияет никак.
        """
        from engagement.models import XPKind
        from engagement.scoring import award
        from roadmap.models import EssayStatus

        essay = self.get_object()
        if not essay.versions.exists():
            return Response({"detail": "Сначала сохраните текст"}, status=status.HTTP_400_BAD_REQUEST)

        essay.status = EssayStatus.REVIEW
        essay.save(update_fields=["status", "updated_at"])
        award(
            essay.student,
            kind=XPKind.ESSAY_SUBMITTED,
            object_label="roadmap.Essay",
            object_id=str(essay.pk),
            note=essay.title[:250],
        )
        return Response(EssaySerializer(essay).data)


class EssayCommentViewSet(viewsets.ModelViewSet):
    """Замечания к эссе: пишет куратор, правит и убирает только автор."""

    queryset = EssayComment.objects.select_related("author", "essay__student").all()
    serializer_class = EssayCommentSerializer
    permission_classes = [OwnCommentOrCurator]
    filterset_fields = ("essay", "version")

    def get_queryset(self):
        return super().get_queryset().filter(essay__student__in=_visible_students(self.request.user))

    def perform_create(self, serializer):
        """Замечание пишут к тому эссе, которое человеку видно."""
        essay = serializer.validated_data.get("essay")
        if essay is not None and essay.student_id not in _visible_students(self.request.user).values_list(
            "pk", flat=True
        ):
            raise PermissionDenied("Это эссе вам не видно")
        serializer.save(author=self.request.user)


@extend_schema(request=GenerateTasksSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_roadmap(request):
    """Сгенерировать задачи из шаблонов потока и дедлайнов вузов."""
    if request.user.role == ROLE_STUDENT:
        return Response({"detail": "Роадмап генерируют сотрудники"}, status=status.HTTP_403_FORBIDDEN)

    serializer = GenerateTasksSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    students = Student.objects.filter(is_active=True)
    if data.get("student"):
        students = students.filter(pk=data["student"])
    if data.get("group"):
        students = students.filter(group__code=data["group"])
    if data.get("graduation_year"):
        students = students.filter(graduation_year=data["graduation_year"])

    return Response(generate_all(students.prefetch_related("universities"), author=request.user))


# --- План поступления по вузу (фаза 41) -------------------------------------


class PlanPermission(permissions.BasePermission):
    """План ведёт сам ученик целиком; сотрудник только читает своих учеников.

    В отличие от задач и эссе, план — собственность ученика: он его
    создаёт, генерирует задачи и удаляет. Ограничение `STUDENT_ACTIONS`
    здесь не действует.
    """

    message = "Свой план ведёт ученик"

    def has_permission(self, request, view) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role != ROLE_STUDENT:
            return request.method in permissions.SAFE_METHODS
        return True

    def has_object_permission(self, request, view, obj) -> bool:
        if request.user.role != ROLE_STUDENT:
            return request.method in permissions.SAFE_METHODS
        student = getattr(request.user, "student", None)
        return student is not None and obj.student_id == student.pk


class ApplicationPlanViewSet(
    ArchiveDeleteMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Планы поступления. Ученик ведёт свои, сотрудник читает своих учеников.

    План не правится PATCH-ом: вместо этого перегенерируются задачи —
    поэтому `UpdateModelMixin` намеренно не включён (та же логика,
    что у документов портфолио).
    """

    queryset = ApplicationPlan.objects.select_related(
        "student", "program__university", "admission_round", "pending_suggestion"
    ).prefetch_related("tasks")
    serializer_class = ApplicationPlanSerializer
    permission_classes = [PlanPermission]
    filterset_fields = ("student", "program", "generation_status")

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role == ROLE_STUDENT:
            student = getattr(self.request.user, "student", None)
            return qs.filter(student=student) if student else qs.none()
        return qs

    def create(self, request, *args, **kwargs):
        """Создать план по программе и запустить генерацию задач в фоне."""
        from roadmap.models import ApplicationPlan
        from universities.models import AdmissionRound, Program

        student = getattr(request.user, "student", None)
        if student is None:
            return Response({"detail": "План создаёт ученик"}, status=status.HTTP_403_FORBIDDEN)

        program = Program.objects.filter(pk=request.data.get("program")).first()
        if program is None:
            return Response({"detail": "Программа не найдена"}, status=status.HTTP_404_NOT_FOUND)
        existing = ApplicationPlan.objects.filter(student=student, program=program).first()
        if existing is not None:
            return Response(
                {"detail": "План по этой программе уже есть", "id": existing.pk},
                status=status.HTTP_409_CONFLICT,
            )

        # раунд — ближайший будущий для программы, если он есть
        admission_round = (
            AdmissionRound.objects.filter(program=program).order_by("deadline").first()
            if request.data.get("admission_round") is None
            else AdmissionRound.objects.filter(pk=request.data.get("admission_round")).first()
        )
        plan = ApplicationPlan.objects.create(
            student=student,
            program=program,
            admission_round=admission_round,
            generation_status=ApplicationPlan.Generation.RUNNING,
        )
        from roadmap.tasks import generate_plan

        generate_plan.delay(plan.pk)
        return Response(self.get_serializer(plan).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """Удалить план — в архив, вместе с его задачами. Это делает ученик."""
        from core.archive import archive

        plan = self.get_object()
        if request.user.role != ROLE_STUDENT:
            return Response({"detail": "Свой план убирает ученик"}, status=status.HTTP_403_FORBIDDEN)
        entry = archive(plan, actor=request.user)
        return Response({"archived": entry.pk, "detail": f"План «{plan.program.university.name}» в архиве"})

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        """Сгенерированные задачи, ждущие применения учеником."""
        plan = self.get_object()
        suggestion = plan.pending_suggestion
        if suggestion is None:
            return Response({"changes": [], "ready": plan.generation_status == "done"})
        from suggestions.serializers import SuggestionSerializer

        return Response(SuggestionSerializer(suggestion).data)

    @action(detail=True, methods=["post"])
    def apply_tasks(self, request, pk=None):
        """Применить сгенерированные задачи — это делает сам ученик."""
        plan = self.get_object()
        if request.user.role != ROLE_STUDENT:
            return Response({"detail": "Задачи плана применяет ученик"}, status=status.HTTP_403_FORBIDDEN)
        from roadmap.plans import apply_plan

        result = apply_plan(plan, actor=request.user)
        return Response(result)

    @action(detail=True, methods=["get"])
    def tasks(self, request, pk=None):
        """Задачи плана, сгруппированные по этапам (категориям)."""
        plan = self.get_object()
        from roadmap.plans import STAGE_ORDER
        from roadmap.serializers import TaskSerializer

        rows = plan.tasks.select_related("admission_round", "plan__admission_round").all()
        serialized = TaskSerializer(rows, many=True).data
        by_stage: dict[str, list] = {}
        for task in serialized:
            by_stage.setdefault(task["category"], []).append(task)
        order = {code: i for i, code in enumerate(STAGE_ORDER)}
        stages = sorted(by_stage.items(), key=lambda kv: order.get(kv[0], 99))
        return Response({"stages": [{"category": code, "tasks": tasks} for code, tasks in stages]})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def plan_attention(request):
    """Директору по поступлению: планы учеников и где прогресс нулевой при близком дедлайне."""
    import datetime as dt

    from django.utils import timezone

    from core.domains import DOMAINS, ROLE_ADMIN
    from roadmap.models import ApplicationPlan

    if request.user.role not in (DOMAINS["admission"].role, ROLE_ADMIN):
        return Response({"detail": "Планы учеников ведёт директор по поступлению"}, status=status.HTTP_403_FORBIDDEN)

    today = timezone.localdate()
    soon = today + dt.timedelta(days=30)
    plans = ApplicationPlan.objects.select_related(
        "student", "program__university", "admission_round"
    ).prefetch_related("tasks")
    stalled = []
    for plan in plans:
        tasks = list(plan.tasks.all())
        done = sum(1 for t in tasks if t.status == "done")
        deadline = plan.deadline
        if deadline is not None and today <= deadline <= soon and done == 0 and tasks:
            stalled.append(
                {
                    "id": plan.pk,
                    "student": plan.student_id,
                    "student_name": plan.student.full_name,
                    "university": plan.program.university.name,
                    "deadline": deadline.isoformat(),
                    "days_left": (deadline - today).days,
                }
            )
    return Response({"total": plans.count(), "stalled": stalled})
