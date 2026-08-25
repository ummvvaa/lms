"""API раздела материалов.

Первое, что делает любая вьюха, — `require_access`. Ученик вне
олимпиадной группы получает 404 на всё: раздела для него не существует.
"""

from __future__ import annotations

from django.db.models import Count, Q
from django.http import FileResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, parser_classes, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.audit import apply_changes
from core.domains import Source
from core.models import Notification
from materials import services
from materials.access import has_access, keeps_the_group, require_access, student_of
from materials.files import FileRejected, limits
from materials.models import (
    CollectionItem,
    MaterialCollection,
    MaterialComment,
    MaterialFile,
    MaterialReport,
    MaterialRequest,
    MaterialStatus,
    StudyMaterial,
)
from materials.serializers import (
    CollectionPickSerializer,
    GroupPickSerializer,
    MaterialCollectionSerializer,
    MaterialCommentSerializer,
    MaterialReportSerializer,
    MaterialSerializer,
    ReviewSerializer,
    TopicRequestSerializer,
)
from students.models import Student


class SectionViewSet(viewsets.ModelViewSet):
    """Общая часть: раздел закрыт олимпиадной группой."""

    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        require_access(request.user)


class MaterialViewSet(SectionViewSet):
    """Библиотека и загрузка материалов.

    До одобрения материал виден только автору и проверяющему. Отклонённый
    в библиотеке не появляется, но автор видит его вместе с причиной.
    """

    queryset = StudyMaterial.objects.select_related("author", "subject").prefetch_related("files")
    serializer_class = MaterialSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filterset_fields = ("subject", "status", "author")
    search_fields = ("title", "topic", "description")
    ordering_fields = ("created_at", "helpful_count", "title")

    def get_queryset(self):
        queryset = self.queryset
        user = self.request.user
        student = student_of(user)

        # «Мои материалы»: свои целиком, включая отклонённые с причиной
        if self.request.query_params.get("mine") == "true":
            return queryset.filter(author=student) if student is not None else queryset.none()

        if keeps_the_group(user):
            return queryset
        if student is None:
            # сотрудник не из домена талантов видит только опубликованное
            return queryset.filter(status=MaterialStatus.APPROVED)
        return queryset.filter(Q(status=MaterialStatus.APPROVED) | Q(author=student))

    def perform_create(self, serializer):
        student = student_of(self.request.user)
        if student is None:
            raise PermissionDenied("Материалы выкладывают ученики олимпиадной группы")
        material = serializer.save(author=student, status=MaterialStatus.PENDING)
        self._attach(material, self.request)
        services.announce_upload(material)

    def perform_update(self, serializer):
        material = self.get_object()
        student = student_of(self.request.user)
        if material.author_id != getattr(student, "pk", None):
            raise PermissionDenied("Править материал может только его автор")
        if material.status == MaterialStatus.APPROVED:
            raise PermissionDenied(
                "Одобренный материал не правится: иначе в библиотеке окажется не то, что проверяли. "
                "Загрузите новый и попросите убрать прежний"
            )
        # правка возвращает материал в очередь: проверять надо то, что лежит
        updated = serializer.save(status=MaterialStatus.PENDING, reject_reason="")
        self._attach(updated, self.request)

    def _attach(self, material: StudyMaterial, request) -> None:
        uploads = request.FILES.getlist("files") if hasattr(request, "FILES") else []
        if not uploads:
            return
        try:
            services.attach_files(material, uploads)
        except FileRejected as error:
            raise ValidationError({"files": str(error)}) from error

    def destroy(self, request, *args, **kwargs):
        """Материал уходит в архив: на нём висят комментарии и начисление."""
        material = self.get_object()
        student = student_of(request.user)
        mine = material.author_id == getattr(student, "pk", None)
        if not mine and not keeps_the_group(request.user):
            raise PermissionDenied("Убрать материал может автор или директор талантов")

        from core.archive import archive

        entry = archive(material, actor=request.user)
        return Response({"archived": entry.pk, "detail": f"«{material.title}» убран из библиотеки"})

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"])
    def helpful(self, request, pk=None):
        """«Было полезно». Один голос от ученика, повторное нажатие снимает."""
        student = student_of(request.user)
        if student is None:
            raise PermissionDenied("Отмечать материалы могут ученики")
        material = self.get_object()
        if material.status != MaterialStatus.APPROVED:
            raise PermissionDenied("Отмечать можно то, что уже в библиотеке")
        return Response(services.mark_helpful(material, student))

    @extend_schema(request=ReviewSerializer, responses={200: dict})
    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """Решение Армана: одобрить или отклонить с причиной."""
        if not keeps_the_group(request.user):
            raise PermissionDenied("Материалы проверяет директор талантов")
        payload = ReviewSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        material = self.get_object()
        if payload.validated_data["decision"] == "approve":
            return Response(services.approve(material, actor=request.user))
        return Response(services.reject(material, actor=request.user, reason=payload.validated_data["reason"].strip()))

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["get"])
    def queue(self, request):
        """Очередь проверки: новые материалы и неразобранные жалобы."""
        if not keeps_the_group(request.user):
            raise PermissionDenied("Очередь проверки — у директора талантов")

        pending = self.queryset.filter(status=MaterialStatus.PENDING).order_by("created_at")
        reports = MaterialReport.objects.filter(status=MaterialReport.Status.OPEN).select_related(
            "reporter", "material", "comment"
        )
        return Response(
            {
                "summary": services.queue_summary(pending.count(), reports.count()),
                "pending": MaterialSerializer(pending, many=True, context={"request": request}).data,
                "reports": MaterialReportSerializer(reports, many=True, context={"request": request}).data,
            }
        )

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["get"])
    def limits(self, request):
        """Пределы загрузки теми же числами, что проверяет сервер."""
        return Response(limits())


class MaterialCommentViewSet(SectionViewSet):
    """Вопросы под материалом."""

    queryset = MaterialComment.objects.select_related("author", "material")
    serializer_class = MaterialCommentSerializer
    filterset_fields = ("material",)

    def get_queryset(self):
        # комментарии видны там же, где сам материал
        allowed = MaterialViewSet(request=self.request, kwargs={}).get_queryset()
        return self.queryset.filter(material__in=allowed)

    def perform_create(self, serializer):
        comment = serializer.save(author=self.request.user)
        services.announce_comment(comment)

    def perform_update(self, serializer):
        """Свою реплику правит автор. Чужую не правит никто, включая Армана.

        Убрать чужой комментарий он может — на то он и модератор, — но
        переписать под чужой подписью нельзя: разговор перестал бы быть
        разговором.
        """
        if self.get_object().author_id != self.request.user.pk:
            raise PermissionDenied("Править можно только свой комментарий")
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """Свой комментарий убирает автор, чужой — только Арман."""
        comment = self.get_object()
        if comment.author_id != request.user.pk and not keeps_the_group(request.user):
            raise PermissionDenied("Чужие комментарии убирает директор талантов")

        from core.archive import archive

        archive(comment, actor=request.user)
        return Response({"detail": "Комментарий убран"})


class MaterialReportViewSet(SectionViewSet):
    """Жалобы на материал или комментарий. Разбирает Арман."""

    queryset = MaterialReport.objects.select_related("reporter", "material", "comment")
    serializer_class = MaterialReportSerializer

    def get_queryset(self):
        if keeps_the_group(self.request.user):
            return self.queryset
        # свою жалобу человек видит, чужие — нет
        return self.queryset.filter(reporter=self.request.user)

    def perform_create(self, serializer):
        report = serializer.save(reporter=self.request.user)
        services.announce_report(report)

    def perform_update(self, serializer):
        """Текст жалобы правит только тот, кто её написал."""
        if self.get_object().reporter_id != self.request.user.pk:
            raise PermissionDenied("Править можно только свою жалобу")
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """Свою жалобу можно отозвать, пока её не разобрали."""
        report = self.get_object()
        if report.reporter_id != request.user.pk:
            raise PermissionDenied("Отозвать жалобу может тот, кто её подал")
        if report.status != MaterialReport.Status.OPEN:
            raise PermissionDenied("Эту жалобу уже разобрали — отзывать нечего")
        report.delete()
        return Response({"detail": "Жалоба отозвана"})

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """Пометить жалобу разобранной, записав, что сделали."""
        if not keeps_the_group(request.user):
            raise PermissionDenied("Жалобы разбирает директор талантов")
        report = self.get_object()
        report.status = MaterialReport.Status.RESOLVED
        report.resolution = str(request.data.get("resolution", "")).strip()
        report.resolved_at = timezone.now()
        report.save(update_fields=["status", "resolution", "resolved_at"])
        return Response({"detail": "Жалоба помечена разобранной", "id": report.pk})


class MaterialRequestViewSet(SectionViewSet):
    """Запросы: «нужен разбор по такой-то теме». Видны всем в группе."""

    queryset = MaterialRequest.objects.select_related("author", "subject").prefetch_related("materials")
    serializer_class = TopicRequestSerializer
    filterset_fields = ("subject", "status")
    search_fields = ("topic", "text")

    def perform_create(self, serializer):
        student = student_of(self.request.user)
        if student is None:
            raise PermissionDenied("Запросы заводят ученики олимпиадной группы")
        serializer.save(author=student)

    def perform_update(self, serializer):
        """Формулировку запроса правит тот, кто его завёл, или директор талантов."""
        instance = self.get_object()
        student = student_of(self.request.user)
        if instance.author_id != getattr(student, "pk", None) and not keeps_the_group(self.request.user):
            raise PermissionDenied("Править запрос может тот, кто его завёл, или директор талантов")
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        student = student_of(request.user)
        if instance.author_id != getattr(student, "pk", None) and not keeps_the_group(request.user):
            raise PermissionDenied("Снять запрос может тот, кто его завёл, или директор талантов")

        from core.archive import archive

        archive(instance, actor=request.user)
        return Response({"detail": "Запрос снят"})


class MaterialCollectionViewSet(SectionViewSet):
    """Тематические подборки. Собирает их Арман."""

    queryset = MaterialCollection.objects.prefetch_related("items__material__author", "items__material__subject")
    serializer_class = MaterialCollectionSerializer
    filterset_fields = ("subject",)
    search_fields = ("name", "description")

    def _deny_if_not_curator(self):
        if not keeps_the_group(self.request.user):
            raise PermissionDenied("Подборки собирает директор талантов")

    def perform_create(self, serializer):
        self._deny_if_not_curator()
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        self._deny_if_not_curator()
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        self._deny_if_not_curator()
        collection = self.get_object()
        name = collection.name
        collection.delete()
        return Response({"detail": f"Подборка «{name}» удалена"})

    @extend_schema(request=CollectionPickSerializer, responses={200: dict})
    @action(detail=True, methods=["post"], url_path="add")
    def add_material(self, request, pk=None):
        """Положить материал в подборку. Только одобренный: подборка — маршрут."""
        self._deny_if_not_curator()
        payload = CollectionPickSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        collection = self.get_object()
        material = StudyMaterial.objects.filter(
            pk=payload.validated_data["material"], status=MaterialStatus.APPROVED
        ).first()
        if material is None:
            return Response(
                {"detail": "В подборку кладут только одобренные материалы"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        item, created = CollectionItem.objects.get_or_create(
            collection=collection,
            material=material,
            defaults={"position": payload.validated_data.get("position", 100)},
        )
        if not created:
            item.position = payload.validated_data.get("position", item.position)
            item.save(update_fields=["position"])
        return Response({"detail": f"«{material.title}» в подборке «{collection.name}»", "item": item.pk})

    @extend_schema(request=CollectionPickSerializer, responses={200: dict})
    @action(detail=True, methods=["post"], url_path="remove")
    def remove_material(self, request, pk=None):
        self._deny_if_not_curator()
        payload = CollectionPickSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        removed, _ = CollectionItem.objects.filter(
            collection=self.get_object(), material_id=payload.validated_data["material"]
        ).delete()
        return Response({"detail": "Убрано из подборки" if removed else "Этого материала в подборке и не было"})


# --- Отбор в олимпиадную группу -------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def group_list(request):
    """Экран отбора: кто в группе, кто нет. Ведёт его директор талантов."""
    if not keeps_the_group(request.user):
        raise PermissionDenied("Олимпиадную группу отбирает директор талантов")

    rows = (
        Student.objects.filter(is_active=True)
        .select_related("group")
        .annotate(materials_count=Count("materials", filter=Q(materials__status=MaterialStatus.APPROVED)))
    )
    query = (request.query_params.get("q") or "").strip()
    if query:
        rows = rows.filter(Q(last_name__icontains=query) | Q(first_name__icontains=query))
    if request.query_params.get("grade"):
        rows = rows.filter(grade=request.query_params["grade"])
    if request.query_params.get("member") == "true":
        rows = rows.filter(in_olympiad_group=True)

    members = Student.objects.filter(is_active=True, in_olympiad_group=True).count()
    return Response(
        {
            "members": members,
            "detail": (
                f"В олимпиадной группе {members} — раздел материалов открыт только им"
                if members
                else "В олимпиадной группе пока никого: отметьте тех, кто выступает на олимпиадах"
            ),
            "students": [
                {
                    "id": row.pk,
                    "full_name": row.full_name,
                    "grade": row.grade,
                    "group": row.group.code if row.group_id else "",
                    "in_group": row.in_olympiad_group,
                    "materials": row.materials_count,
                }
                for row in rows[:500]
            ],
        }
    )


@extend_schema(request=GroupPickSerializer, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def group_pick(request):
    """Отметить или снять ученика. Правка идёт через журнал (инвариант №9)."""
    if not keeps_the_group(request.user):
        raise PermissionDenied("Олимпиадную группу отбирает директор талантов")

    payload = GroupPickSerializer(data=request.data)
    payload.is_valid(raise_exception=True)
    student = Student.objects.filter(pk=payload.validated_data["student"]).first()
    if student is None:
        raise NotFound("Такого ученика нет")

    member = payload.validated_data["member"]
    apply_changes(student, {"in_olympiad_group": member}, actor=request.user, source=Source.MANUAL)
    return Response(
        {
            "id": student.pk,
            "in_group": member,
            "detail": (
                f"{student.full_name} в олимпиадной группе — раздел материалов ему открыт"
                if member
                else f"{student.full_name} больше не в олимпиадной группе — раздел закрыт"
            ),
        }
    )


# --- Файлы ----------------------------------------------------------------


@extend_schema(responses={200: bytes})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download(request, pk: int):
    """Отдать файл после проверки прав.

    Прямой ссылки на файл не существует: он лежит вне корня веб-сервера,
    и единственный путь к нему — этот. До одобрения файл виден только
    автору и проверяющему.
    """
    require_access(request.user)
    row = MaterialFile.objects.select_related("material", "material__author").filter(pk=pk).first()
    if row is None:
        raise NotFound("Файла нет")

    material = row.material
    student = student_of(request.user)
    visible = (
        material.status == MaterialStatus.APPROVED
        or keeps_the_group(request.user)
        or (student is not None and material.author_id == student.pk)
    )
    if not visible:
        raise NotFound("Файла нет")

    response = FileResponse(row.file.open("rb"), content_type=row.content_type)
    response["Content-Disposition"] = f'inline; filename="{row.pk}{row.extension}"'
    # файл закрытый: посредники его кэшировать не должны
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@extend_schema(request=None, responses={200: dict})
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def delete_file(request, pk: int):
    """Убрать файл из своего материала до проверки."""
    require_access(request.user)
    row = MaterialFile.objects.select_related("material").filter(pk=pk).first()
    if row is None:
        raise NotFound("Файла нет")
    student = student_of(request.user)
    if row.material.author_id != getattr(student, "pk", None) and not keeps_the_group(request.user):
        raise PermissionDenied("Убрать файл может автор материала")
    name = row.original_name
    row.file.delete(save=False)
    row.delete()
    return Response({"detail": f"Файл «{name}» убран"})


# --- Уведомления ----------------------------------------------------------


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notifications(request):
    """Что нового адресно для этого человека."""
    rows = Notification.objects.filter(recipient=request.user)[:50]
    unread = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return Response(
        {
            "unread": unread,
            "rows": [
                {
                    "id": row.pk,
                    "text": row.text,
                    "link": row.link,
                    "is_read": row.is_read,
                    "created_at": row.created_at,
                }
                for row in rows
            ],
        }
    )


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def notifications_read(request):
    """Пометить уведомления прочитанными."""
    ids = request.data.get("ids")
    rows = Notification.objects.filter(recipient=request.user, is_read=False)
    if ids:
        rows = rows.filter(pk__in=ids)
    marked = rows.update(is_read=True)
    return Response({"marked": marked})


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def section_state(request):
    """Есть ли у человека раздел материалов — и что в нём для него есть.

    Правило одно и живёт в `materials.access`: во вьюхе его второй раз
    не пишем, иначе меню и сам раздел однажды разойдутся.
    """
    return Response(
        {
            "has_access": has_access(request.user),
            "is_curator": keeps_the_group(request.user),
            "limits": limits(),
        }
    )
