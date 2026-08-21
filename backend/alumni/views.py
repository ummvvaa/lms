"""API выпускников, менторства и архива эссе."""

from __future__ import annotations

from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from alumni.models import Alumnus, ArchivedEssay, MentorshipRequest, MentorshipStatus
from alumni.serializers import (
    AlumnusSerializer,
    ArchivedEssaySerializer,
    CreateMentorshipSerializer,
    MentorshipRequestSerializer,
    ReviewMentorshipSerializer,
)
from alumni.services import MentorshipDenied, approve, decline, request_mentorship
from core.domains import ROLE_STUDENT


class AlumnusFilter(filters.FilterSet):
    country = filters.CharFilter(field_name="country", lookup_expr="iexact")
    university = filters.NumberFilter(field_name="university")
    program = filters.CharFilter(field_name="program__name", lookup_expr="icontains")
    year = filters.NumberFilter(field_name="graduation_year")
    mentors_only = filters.BooleanFilter(field_name="mentorship_consent")

    class Meta:
        model = Alumnus
        fields = ("country", "university", "program", "year", "mentors_only")


class AlumnusViewSet(viewsets.ModelViewSet):
    """Каталог выпускников с фильтрами."""

    queryset = Alumnus.objects.select_related("student", "university", "program").prefetch_related(
        "applications__program__university"
    )
    serializer_class = AlumnusSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = AlumnusFilter
    search_fields = ("student__last_name", "student__first_name", "university__name", "current_occupation")
    ordering_fields = ("graduation_year", "country")

    def get_permissions(self):
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        if request.user.role == ROLE_STUDENT:
            return Response({"detail": "Каталог ведут сотрудники"}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if request.user.role == ROLE_STUDENT:
            return Response({"detail": "Каталог ведут сотрудники"}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    partial_update = update

    def destroy(self, request, *args, **kwargs):
        if request.user.role == ROLE_STUDENT:
            return Response({"detail": "Каталог ведут сотрудники"}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)


class MentorshipRequestViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Запросы на менторство. Проходят через сотрудника школы."""

    queryset = MentorshipRequest.objects.select_related("student", "alumnus__student").prefetch_related("meetings")
    serializer_class = MentorshipRequestSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("status", "alumnus", "student")

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if user.role != ROLE_STUDENT:
            return qs

        student = getattr(user, "student", None)
        if student is None:
            return qs.none()

        # выпускник заходит под той же ролью: ему видно только одобренное школой
        alumnus = getattr(student, "alumnus", None)
        if alumnus is not None:
            return qs.filter(alumnus=alumnus, is_visible_to_alumnus=True) | qs.filter(student=student)
        return qs.filter(student=student)

    @extend_schema(request=CreateMentorshipSerializer, responses=MentorshipRequestSerializer)
    @action(detail=False, methods=["post"], url_path="request")
    def create_request(self, request):
        """Ученик просит о менторстве. Выпускник пока ничего не видит."""
        student = getattr(request.user, "student", None)
        if student is None:
            return Response({"detail": "Только ученик может просить о менторстве"}, status=status.HTTP_403_FORBIDDEN)

        serializer = CreateMentorshipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alumnus = Alumnus.objects.filter(pk=serializer.validated_data["alumnus"]).first()
        if alumnus is None:
            return Response({"detail": "Выпускник не найден"}, status=status.HTTP_404_NOT_FOUND)

        try:
            created = request_mentorship(
                student=student,
                alumnus=alumnus,
                topic=serializer.validated_data["topic"],
                message=serializer.validated_data.get("message", ""),
            )
        except MentorshipDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(MentorshipRequestSerializer(created).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ReviewMentorshipSerializer, responses=MentorshipRequestSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Сотрудник одобряет — только теперь запрос уходит выпускнику."""
        if request.user.role == ROLE_STUDENT:
            return Response({"detail": "Запросы рассматривают сотрудники"}, status=status.HTTP_403_FORBIDDEN)
        serializer = ReviewMentorshipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = approve(self.get_object(), reviewer=request.user, note=serializer.validated_data.get("note", ""))
        except MentorshipDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(MentorshipRequestSerializer(updated).data)

    @extend_schema(request=ReviewMentorshipSerializer, responses=MentorshipRequestSerializer)
    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        """Сотрудник отклоняет — выпускник этого запроса не увидит."""
        if request.user.role == ROLE_STUDENT:
            return Response({"detail": "Запросы рассматривают сотрудники"}, status=status.HTTP_403_FORBIDDEN)
        serializer = ReviewMentorshipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = decline(self.get_object(), reviewer=request.user, note=serializer.validated_data.get("note", ""))
        except MentorshipDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(MentorshipRequestSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="accept")
    def alumnus_accepts(self, request, pk=None):
        """Выпускник соглашается — доступно только по переданному запросу."""
        obj = self.get_object()
        if not obj.is_visible_to_alumnus:
            return Response({"detail": "Запрос ещё не передан"}, status=status.HTTP_403_FORBIDDEN)
        obj.status = MentorshipStatus.ACCEPTED
        obj.save(update_fields=["status", "updated_at"])
        return Response(MentorshipRequestSerializer(obj).data)


class ArchivedEssayViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Архив эссе выпускников — только с явного согласия."""

    serializer_class = ArchivedEssaySerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("essay_type", "program", "alumnus")
    search_fields = ("title", "program__university__name")

    def get_queryset(self):
        qs = ArchivedEssay.objects.select_related("alumnus__student", "program__university")
        if self.request.user.role == ROLE_STUDENT:
            # без согласия эссе не показывается никому, кроме сотрудников
            return qs.filter(consent_given=True)
        return qs
