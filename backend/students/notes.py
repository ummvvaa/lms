"""Заметки куратора: кто читает, кто пишет (фаза 62).

Список читателей — одно место. Добавить Асем или кого-то ещё — одна
правка здесь, а не поиск по вьюхам. Ученик в этом списке не появится
никогда: заметки — то, что школа пишет о ребёнке для себя, и это
инвариант, а не настройка (страж — тест `test_phase62`).

Куратор читает и пишет заметки только об учениках своих групп — граница
та же, что у всего кабинета (`core.scope`). Кымбат и Салтанат читают
по всей школе, не пишут: заметка — инструмент куратора.
"""

from __future__ import annotations

from rest_framework import mixins, serializers, status, viewsets
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from core.domains import ROLE_CURATOR
from core.scope import visible_students
from students.models import CuratorNote

#: Кто видит заметки. Владелец домена документов (Асем) сюда не входит
#: по решению владельца продукта; ученик — не входит по инварианту.
NOTE_READERS: tuple[str, ...] = (ROLE_CURATOR, "director_exam", "director_behavior")

#: Кто пишет и убирает в архив. С фазы 66 — и директор школы: ей нужно
#: оставить куратору запись в карточке, а куратор об этом узнаёт
#: уведомлением. Ученику заметки не показываются никогда.
NOTE_WRITERS: tuple[str, ...] = (ROLE_CURATOR, "director_behavior")


class NotePermission(BasePermission):
    message = "Заметки куратора читают куратор, академический директор и директор школы"

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return user.role in NOTE_READERS
        return user.role in NOTE_WRITERS


class CuratorNoteSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = CuratorNote
        fields = ("id", "student", "text", "author_name", "author_role", "created_at")
        read_only_fields = ("id", "author_name", "author_role", "created_at")

    def get_author_name(self, obj) -> str:
        who = obj.author
        return (who.full_name or who.email) if who else "система"

    def validate_text(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Заметка пустая")
        return value


class CuratorNoteViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """Заметки: список по ученику, новая, в архив. Правки нет — пишут заново."""

    queryset = CuratorNote.objects.select_related("author", "student").all()
    serializer_class = CuratorNoteSerializer
    permission_classes = [IsAuthenticated, NotePermission]
    filterset_fields = ("student",)

    def get_queryset(self):
        # куратор — только свои группы; чужой ученик отсюда не выходит (404)
        return super().get_queryset().filter(student__in=visible_students(self.request.user))

    def perform_create(self, serializer):
        student = serializer.validated_data["student"]
        if not visible_students(self.request.user).filter(pk=student.pk).exists():
            from rest_framework.exceptions import NotFound

            raise NotFound("Ученика нет в ваших группах")
        note = serializer.save(author=self.request.user, author_role=self.request.user.role)
        _tell_curator(note)

    def destroy(self, request, *args, **kwargs):
        from core.archive import archive

        note = self.get_object()
        entry = archive(note, actor=request.user)
        return Response({"archived": entry.pk, "detail": "Заметка в архиве"}, status=status.HTTP_200_OK)


def _tell_curator(note) -> None:
    """Заметку директора школы куратор группы видит уведомлением (фаза 66).

    В обратную сторону не пишем: заметки куратора Салтанат и так читает
    списком, а поток уведомлений на директора школы был бы шумом.
    """
    from accounts.curators import curator_of
    from core.models import Notification
    from materials.services import notify

    if note.author_role != "director_behavior" or note.student.group_id is None:
        return
    assignment = curator_of(note.student.group)
    if assignment is None or assignment.curator_id == getattr(note.author, "pk", None):
        return
    notify(
        assignment.curator,
        kind=Notification.Kind.NOTE_FOR_CURATOR,
        template="Директор школы оставила заметку о {student}",
        link=f"/students/{note.student_id}?tab=notes",
        student=note.student.full_name,
    )
