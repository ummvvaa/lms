"""Мягкое удаление: запись исчезает из интерфейса, но остаётся в базе.

Инвариант №13: всё, у чего есть история, физически не удаляется. Иначе
журнал изменений начнёт ссылаться в пустоту, а восстановить удалённое
по ошибке будет нечем.

Менеджер `objects` архивные записи не показывает — поэтому списки,
дашборды и агрегаты чистятся сами, без правки каждого запроса.
`all_objects` видит всё: им пользуются экран архива и восстановление.
"""

from __future__ import annotations

from django.db import models


class ActiveManager(models.Manager):
    """Только живые записи. Это и есть «исчезает из интерфейса»."""

    def get_queryset(self):
        return super().get_queryset().filter(archived_at__isnull=True)


class Archivable(models.Model):
    """Общие поля мягкого удаления.

    `archive_batch` — номер одного удаления. По нему восстанавливается
    ровно то, что ушло вместе: ученик, архивированный сегодня, не должен
    поднимать из архива задачу, удалённую отдельно месяц назад.
    """

    archived_at = models.DateTimeField("В архиве с", null=True, blank=True, db_index=True)
    archive_batch = models.UUIDField("Номер удаления", null=True, blank=True, db_index=True)

    objects = ActiveManager()
    all_objects = models.Manager()  # noqa: DJ012 — менеджеры идут после своих полей

    class Meta:
        abstract = True
        # `base_manager_name` намеренно не задан: без него Django заводит
        # обычный неотфильтрованный менеджер для связей и `refresh_from_db`,
        # и архивная запись не «пропадает» изнутри кода. Задать его здесь
        # всё равно нельзя — свой `class Meta` у наследника перекрывает
        # родительский целиком

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None
