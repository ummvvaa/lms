"""API роадмапа и эссе."""

from __future__ import annotations

from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.domains import ROLE_STUDENT
from roadmap.models import Essay, EssayComment, EssayVersion, Task, TaskComment, TaskTemplate
from roadmap.permissions import OwnStudentOrStaff, StaffOnly
from roadmap.serializers import (
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


class TaskViewSet(viewsets.ModelViewSet):
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


class TaskTemplateViewSet(viewsets.ModelViewSet):
    queryset = TaskTemplate.objects.all()
    serializer_class = TaskTemplateSerializer
    permission_classes = [StaffOnly]
    filterset_fields = ("category", "is_active", "graduation_year", "grade")


class TaskCommentViewSet(viewsets.ModelViewSet):
    queryset = TaskComment.objects.select_related("author", "task__student").all()
    serializer_class = TaskCommentSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("task",)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class EssayViewSet(viewsets.ModelViewSet):
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


class EssayCommentViewSet(viewsets.ModelViewSet):
    queryset = EssayComment.objects.select_related("author", "essay__student").all()
    serializer_class = EssayCommentSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("essay", "version")

    def perform_create(self, serializer):
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
