"""Кому отвечает эндпойнт — объявлением в самом классе вьюхи.

Права и выборку многим вьюхам даёт общий базовый класс без маршрута:
профиль домена, дочерняя таблица ученика, раздел олимпиадников, справочник.
Наследник о них молчал, и по его коду не было видно, кто получает ответ, —
ошибиться можно было, взяв не ту основу. Теперь базовый класс перечисляет,
какую аудиторию он обслуживает, а каждый наследник пишет свою `audience`
сам. Не объявил или объявил то, чего основа не умеет, — класс не создаётся,
и это видно на первом же запуске тестов.
"""

# i18n-skip-file: подписи аудиторий и ошибки настройки — для читающего код, на экран не выходят

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured
from django.db import models


class Audience(models.TextChoices):
    """Кто получает ответ эндпойнта. Значения — для читающего код, не для экрана."""

    OWN_OR_SCOPED = "own_or_scoped", "ученик — только своё, сотрудник — ученики своей области (`scope_to_user`)"
    OLYMPIAD_SECTION = "olympiad_section", "олимпиадная группа и директор талантов (`require_access`)"
    STAFF_DIRECTORY = "staff_directory", "все сотрудники; ученику — только действующие записи для выбора"


class DeclaredAudience:
    """Примесь базового класса вьюх: наследник объявляет аудиторию сам.

    Базовый класс задаёт `audiences` — что он умеет. Класс, который сам
    `audiences` не задаёт, — эндпойнт: он обязан написать `audience`
    в своём теле, а не получить её по наследству.
    """

    audiences: tuple[Audience, ...] = ()
    audience: Audience | None = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "audiences" in cls.__dict__:
            return
        declared = cls.__dict__.get("audience")
        if declared is None:
            raise ImproperlyConfigured(f"{cls.__module__}.{cls.__name__}: объявите `audience` — кому отвечает эндпойнт")
        if declared not in cls.audiences:
            raise ImproperlyConfigured(
                f"{cls.__module__}.{cls.__name__}: основа обслуживает {list(cls.audiences)}, а не {declared}"
            )
