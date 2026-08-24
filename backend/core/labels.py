"""Человеческие названия полей и значений — единственная точка перевода.

Реестр доменов (`core.domains`) знает подпись каждого доменного поля.
Здесь эта подпись достаётся по метке модели и имени колонки, а для
недоменных моделей подхватывается `verbose_name` самой колонки.

Никакой экран и никакой сериализатор не собирает название поля из имени
переменной: `replace('_', ' ')` и подстановка `field_name` в текст —
дефект (инвариант №2, фаза 17).
"""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist

from core.domains import spec_of_field

#: Поля вне пяти доменов, которые всё-таки попадают человеку на глаза —
#: в журнале правок, в диалоге удаления, в ошибке импорта. Реестр доменов
#: их не описывает: они не принадлежат ни одному директору.
EXTRA_TITLES: dict[str, tuple[str, str]] = {
    "students.Student.first_name": ("Имя", "Имя"),
    "students.Student.last_name": ("Фамилия", "Фамилия"),
    "students.Student.email": ("Почта ученика", "Почта"),
    "students.Student.grade": ("Класс", "Класс"),
    "students.Student.group": ("Учебная группа", "Группа"),
    "students.Student.is_archived": ("В архиве", "В архиве"),
    "students.StudyGroup.name": ("Название группы", "Группа"),
    "students.StudyGroup.code": ("Код группы", "Код"),
    "accounts.User.email": ("Почта", "Почта"),
    "accounts.User.full_name": ("Имя и фамилия", "Имя"),
    "accounts.User.role": ("Роль", "Роль"),
    "accounts.User.is_active": ("Доступ включён", "Доступ"),
    "roadmap.Task.title": ("Название задачи", "Задача"),
    "roadmap.Task.due_date": ("Срок задачи", "Срок"),
    "roadmap.Task.status": ("Статус задачи", "Статус"),
    "roadmap.Essay.title": ("Название эссе", "Эссе"),
    "roadmap.Essay.status": ("Статус эссе", "Статус"),
}


def _model(label: str):
    try:
        return apps.get_model(label)
    except (LookupError, ValueError):
        return None


def _django_field(label: str, field_name: str):
    model = _model(label)
    if model is None:
        return None
    try:
        return model._meta.get_field(field_name)
    except (FieldDoesNotExist, AttributeError):
        return None


def field_title(model_label: str, field_name: str) -> str:
    """Полное человеческое название поля: «Текущий балл IELTS»."""
    spec = spec_of_field(model_label, field_name)
    if spec is not None:
        return spec.title
    extra = EXTRA_TITLES.get(f"{model_label}.{field_name}")
    if extra:
        return extra[0]
    field = _django_field(model_label, field_name)
    verbose = getattr(field, "verbose_name", "") if field is not None else ""
    return str(verbose) if verbose else field_name


def field_short(model_label: str, field_name: str) -> str:
    """Короткая подпись для колонки таблицы и строки журнала: «IELTS»."""
    spec = spec_of_field(model_label, field_name)
    if spec is not None:
        return spec.short_title
    extra = EXTRA_TITLES.get(f"{model_label}.{field_name}")
    if extra:
        return extra[1]
    return field_title(model_label, field_name)


def field_unit(model_label: str, field_name: str) -> str:
    """Единица измерения поля: «балл», «%», «ч». Пусто — единицы нет."""
    spec = spec_of_field(model_label, field_name)
    return spec.unit if spec else ""


def model_title(model_label: str, *, plural: bool = False) -> str:
    """Как называется сама сущность: «Пробная сдача», «Активности»."""
    model = _model(model_label)
    if model is None:
        return model_label
    name = model._meta.verbose_name_plural if plural else model._meta.verbose_name
    return str(name)


def value_title(model_label: str, field_name: str, value: Any) -> str:
    """Человеческое значение: `critical` → «Критично», `True` → «да».

    В журнале и в дайджесте директор читает подписи, а не машинные коды.
    Значение неизвестного вида возвращается как есть.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "да" if value else "нет"
    text = str(value)
    if text in ("True", "False"):
        return "да" if text == "True" else "нет"

    field = _django_field(model_label, field_name)
    choices = getattr(field, "choices", None) if field is not None else None
    if choices:
        for raw, title in choices:
            if str(raw) == text:
                return str(title)
    if field is not None and field.is_relation:
        related = field.related_model
        manager = getattr(related, "all_objects", getattr(related, "_default_manager", None))
        if manager is not None and text.isdigit():
            obj = manager.filter(pk=int(text)).first()
            if obj is not None:
                return str(obj)
    return text


def describe_change(model_label: str, field_name: str, old_value: Any, new_value: Any) -> str:
    """Одна строка журнала словами: «Текущий балл IELTS: 6.0 → 6.5»."""
    old = value_title(model_label, field_name, old_value) or "пусто"
    new = value_title(model_label, field_name, new_value) or "пусто"
    return f"{field_title(model_label, field_name)}: {old} → {new}"
