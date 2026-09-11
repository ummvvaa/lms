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
    # события кабинета куратора (фаза 62): не правки полей, а действия,
    # которые тоже должны читаться в журнале словами
    "students.Student.parent_call": ("Звонок родителям", "Звонок"),
    "students.Student.escalation": ("Передано владельцу домена", "Передано"),
    "students.Student.escalation_returned": ("Возвращено себе из передачи", "Возвращено"),
    "students.Student.document_reminder": ("Напоминание о документах", "Напоминание"),
    # пробник файлом (фаза 63): доменного поля правка не трогает, а в журнале
    # видеть её надо — кто и какой пробник залил ученику
    "students.Student.mock_import": ("Загружен пробник", "Пробник"),
    # пароли и таблица поступления (фаза 65): показ пароля — событие журнала,
    # по нему видно, кто и когда открывал чужой аккаунт
    "students.Student.credential_reveal": ("Показан пароль ученика", "Показан пароль"),
    "students.Student.credential_set": ("Записан пароль ученика", "Записан пароль"),
    "students.Student.admission_import": ("Загружена таблица поступления", "Таблица поступления"),
    # дисциплина и письма (фаза 66)
    "students.Student.attendance_late_edit": ("Посещаемость исправлена задним числом", "Правка посещаемости"),
    "students.Student.behavior_remark": ("Записано замечание", "Замечание"),
    "students.Student.behavior_remark_dropped": ("Замечание снято", "Замечание снято"),
    "students.Student.letter_opened": ("Письмо открыто в почте", "Письмо"),
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


def acting_for_phrase(domain_code: str) -> str:
    """«за домен «Экзамены»» — подпись к правке, сделанной не владельцем домена.

    Одна фраза на все экраны: историю карточки, дайджест, историю
    загрузок. Пустой код — пустая строка: у правки владельца пометки нет.
    """
    from core.domains import DOMAINS

    domain = DOMAINS.get(domain_code or "")
    # с фазы 68 администратор правит любой домен напрямую, и пометка должна
    # читаться сразу: не просто «за домен», а кто именно правил
    return f"правил администратор за домен «{domain.title}»" if domain else ""
