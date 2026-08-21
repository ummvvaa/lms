"""API учеников и профилей.

Читают все сотрудники, ученик — только себя. Пишет директор и только
в поля своего домена: проверка идёт по реестру `core.domains`.
"""

from __future__ import annotations

from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from core.domains import ROLE_STUDENT
from core.permissions import DomainFieldPermission, IsOwnStudentOrStaff
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamProfile,
    SportProfile,
    Student,
    TalentProfile,
)
from students.serializers import (
    AdmissionProfileSerializer,
    BehaviorProfileSerializer,
    ExamProfileSerializer,
    SportProfileSerializer,
    StudentListSerializer,
    StudentSerializer,
    TalentProfileSerializer,
)


class StudentFilter(filters.FilterSet):
    """Фильтры списка: группа, класс, год выпуска."""

    group = filters.CharFilter(field_name="group__code", lookup_expr="iexact")
    grade = filters.NumberFilter(field_name="grade")
    graduation_year = filters.NumberFilter(field_name="graduation_year")

    class Meta:
        model = Student
        fields = ("group", "grade", "graduation_year", "is_active")


class StudentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Ученики: список и карточка. Правка идёт через профили."""

    queryset = (
        Student.objects.select_related("group", "behavior", "admission", "exam", "talent", "sport")
        .all()
        .order_by("last_name", "first_name")
    )
    permission_classes = [IsOwnStudentOrStaff]
    filterset_class = StudentFilter
    search_fields = ("last_name", "first_name", "email")
    ordering_fields = ("last_name", "grade", "graduation_year")

    def get_serializer_class(self):
        return StudentListSerializer if self.action == "list" else StudentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == ROLE_STUDENT:
            # ученик видит только себя (инвариант №7 и разграничение доступа)
            student = getattr(user, "student", None)
            return qs.filter(pk=student.pk) if student else qs.none()
        return qs

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        """Кабинет ученика: своя карточка без внутренних ярлыков."""
        student = getattr(request.user, "student", None)
        if student is None:
            raise NotFound("У этого пользователя нет карточки ученика")
        return Response(self.get_serializer(student).data)


class BaseProfileViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Профиль одного домена. Ключ — id ученика, а не id профиля."""

    permission_classes = [DomainFieldPermission, IsOwnStudentOrStaff]
    lookup_field = "student_id"
    lookup_url_kwarg = "student_id"
    domain_model_label = ""

    def get_queryset(self):
        qs = self.queryset.select_related("student")
        user = self.request.user
        if user.role == ROLE_STUDENT:
            student = getattr(user, "student", None)
            return qs.filter(student=student) if student else qs.none()
        return qs


class BehaviorProfileViewSet(BaseProfileViewSet):
    queryset = BehaviorProfile.objects.all()
    serializer_class = BehaviorProfileSerializer
    domain_model_label = "students.BehaviorProfile"


class AdmissionProfileViewSet(BaseProfileViewSet):
    queryset = AdmissionProfile.objects.all()
    serializer_class = AdmissionProfileSerializer
    domain_model_label = "students.AdmissionProfile"


class ExamProfileViewSet(BaseProfileViewSet):
    queryset = ExamProfile.objects.all()
    serializer_class = ExamProfileSerializer
    domain_model_label = "students.ExamProfile"


class TalentProfileViewSet(BaseProfileViewSet):
    queryset = TalentProfile.objects.all()
    serializer_class = TalentProfileSerializer
    domain_model_label = "students.TalentProfile"


class SportProfileViewSet(BaseProfileViewSet):
    queryset = SportProfile.objects.all()
    serializer_class = SportProfileSerializer
    domain_model_label = "students.SportProfile"
