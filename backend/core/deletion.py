"""Удаление через API: мягкое для данных с историей, жёсткое для справочников.

Инвариант №13. Право берётся из реестра доменов (`can_delete`), а не
пишется в каждой вьюхе: директор удаляет только в своём домене, ученика
целиком сносит только администратор.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response

from core.archive import archive, blockers, preview
from core.audit import model_label
from core.domains import ROLE_TITLES, can_delete, deleters_of


def refuse(role: str, label: str) -> Response:
    """Отказ с указанием, кто это удалять вправе."""
    allowed = ", ".join(ROLE_TITLES.get(item, item) for item in deleters_of(label)) or "никто"
    return Response(
        {"detail": f"Эту запись ведёт другой домен. Удалять её может: {allowed}"},
        status=status.HTTP_403_FORBIDDEN,
    )


class ArchiveDeleteMixin:
    """DELETE отправляет запись в архив вместе со связанным.

    Ответ — не пустой 204, а рассказ о том, что произошло: интерфейс
    показывает его человеку, чтобы удаление не выглядело исчезновением.
    """

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        label = model_label(instance)
        if not can_delete(request.user.role, label):
            return refuse(request.user.role, label)

        summary = preview(instance)
        entry = archive(instance, actor=request.user)
        return Response(
            {
                "archived": entry.pk,
                "title": entry.title,
                "related_count": entry.related_count,
                "detail": (
                    f"{entry.kind_title} «{entry.title}» в архиве"
                    + (f". Вместе с записью ушло: {summary['summary']}" if summary["summary"] else "")
                    + ". Восстановить можно на экране архива"
                ),
            }
        )


class HardDeleteMixin:
    """DELETE удаляет запись физически — так можно только со справочником.

    Если на запись ссылаются, отказываем человеческим текстом, а не
    роняем 500 на `ProtectedError`.
    """

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        label = model_label(instance)
        if not can_delete(request.user.role, label):
            return refuse(request.user.role, label)

        reasons = blockers(instance)
        if reasons:
            return Response(
                {
                    "detail": "Удалить нельзя: на запись ссылаются " + "; ".join(reasons),
                    "blocked_by": reasons,
                },
                status=status.HTTP_409_CONFLICT,
            )

        title = str(instance)
        instance.delete()
        return Response({"detail": f"Удалено: {title}"})
