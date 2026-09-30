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
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core import stored_text
from core.domains import spec_of_field

#: Поля вне пяти доменов, которые всё-таки попадают человеку на глаза —
#: в журнале правок, в диалоге удаления, в ошибке импорта. Реестр доменов
#: их не описывает: они не принадлежат ни одному директору.
EXTRA_TITLES: dict[str, tuple[Any, Any]] = {
    "students.Student.first_name": (gettext_lazy("Имя"), gettext_lazy("Имя")),
    "students.Student.last_name": (gettext_lazy("Фамилия"), gettext_lazy("Фамилия")),
    "students.Student.email": (gettext_lazy("Почта ученика"), gettext_lazy("Почта")),
    "students.StudyGroup.parallel": (gettext_lazy("Параллель"), gettext_lazy("Параллель")),
    "students.Student.group": (gettext_lazy("Учебная группа"), gettext_lazy("Группа")),
    "students.Student.is_archived": (gettext_lazy("В архиве"), gettext_lazy("В архиве")),
    "students.StudyGroup.name": (gettext_lazy("Название группы"), gettext_lazy("Группа")),
    "students.StudyGroup.code": (gettext_lazy("Код группы"), gettext_lazy("Код")),
    "accounts.User.email": (gettext_lazy("Почта"), gettext_lazy("Почта")),
    "accounts.User.full_name": (gettext_lazy("Имя и фамилия"), gettext_lazy("Имя")),
    "accounts.User.role": (gettext_lazy("Роль"), gettext_lazy("Роль")),
    "accounts.User.is_active": (gettext_lazy("Доступ включён"), gettext_lazy("Доступ")),
    # раздача паролей списком (фаза 69): в журнале остаётся, скольким выдали
    "accounts.User.passwords_handed_out": (gettext_lazy("Пароли выданы списком"), gettext_lazy("Раздача паролей")),
    # события кабинета куратора (фаза 62): не правки полей, а действия,
    # которые тоже должны читаться в журнале словами
    "students.Student.parent_call": (gettext_lazy("Звонок родителям"), gettext_lazy("Звонок")),
    "students.Student.escalation": (gettext_lazy("Передано владельцу домена"), gettext_lazy("Передано")),
    "students.Student.escalation_returned": (gettext_lazy("Возвращено себе из передачи"), gettext_lazy("Возвращено")),
    "students.Student.document_reminder": (gettext_lazy("Напоминание о документах"), gettext_lazy("Напоминание")),
    # Mock Test файлом (фаза 63): доменного поля правка не трогает, а в журнале
    # видеть её надо — кто и какой Mock Test залил ученику
    "students.Student.mock_import": (gettext_lazy("Загружен Mock Test"), "Mock Test"),
    # пароли и таблица поступления (фаза 65): показ пароля — событие журнала,
    # по нему видно, кто и когда открывал чужой аккаунт
    "students.Student.credential_reveal": (gettext_lazy("Показан пароль ученика"), gettext_lazy("Показан пароль")),
    # ссылка на пароль ученику: у 8–10 почты нет — её выдают на экране
    "students.Student.password_link": (gettext_lazy("Выдана ссылка на пароль"), gettext_lazy("Ссылка на пароль")),
    # перевод на следующий год: у ученика — куда перешёл или выпуск, у школы — сводка
    "students.Student.year_transfer": (gettext_lazy("Перевод на следующий год"), gettext_lazy("Перевод")),
    "students.StudyGroup.year_transfer": (gettext_lazy("Перевод школы на следующий год"), gettext_lazy("Перевод года")),
    "students.Student.credential_set": (gettext_lazy("Записан пароль ученика"), gettext_lazy("Записан пароль")),
    "students.Student.admission_import": (
        gettext_lazy("Загружена таблица поступления"),
        gettext_lazy("Таблица поступления"),
    ),
    # дисциплина и письма (фаза 66)
    "students.Student.attendance_late_edit": (
        gettext_lazy("Посещаемость исправлена задним числом"),
        gettext_lazy("Правка посещаемости"),
    ),
    "students.Student.behavior_remark": (gettext_lazy("Записано замечание"), gettext_lazy("Замечание")),
    "students.Student.behavior_remark_dropped": (gettext_lazy("Замечание снято"), gettext_lazy("Замечание снято")),
    "students.Student.letter_opened": (gettext_lazy("Письмо открыто в почте"), gettext_lazy("Письмо")),
    # учебная часть: причина за период, отчёт родителям, изменения расписания
    "students.Student.excuse": (gettext_lazy("Оформлена уважительная причина"), gettext_lazy("Уважительная причина")),
    "students.Student.excuse_dropped": (gettext_lazy("Снята уважительная причина"), gettext_lazy("Причина снята")),
    "students.Student.report_built": (gettext_lazy("Собран отчёт родителям"), gettext_lazy("Отчёт собран")),
    "students.Student.report_checked": (gettext_lazy("Отчёт родителям проверен"), gettext_lazy("Отчёт проверен")),
    "students.Student.report_exported": (gettext_lazy("Отчёт родителям выгружен"), gettext_lazy("Отчёт выгружен")),
    "students.Student.report_sent": (gettext_lazy("Отчёт отправлен родителям"), gettext_lazy("Отчёт отправлен")),
    "students.Student.report_unsent": (
        gettext_lazy("Отметка об отправке отчёта снята"),
        gettext_lazy("Отправка снята"),
    ),
    "students.Student.report_drafted": (
        gettext_lazy("ИИ написал черновик текстов отчёта"),
        gettext_lazy("Черновик отчёта"),
    ),
    "students.Student.report_texts": (gettext_lazy("Тексты отчёта родителям изменены"), gettext_lazy("Тексты отчёта")),
    "students.Student.english_level": (gettext_lazy("Уровень английского"), gettext_lazy("Уровень английского")),
    "students.Student.teacher_reminded": (
        gettext_lazy("Учителю напомнили об уроке"),
        gettext_lazy("Напоминание учителю"),
    ),
    "academics.Lesson.schedule_change": (gettext_lazy("Изменение расписания"), gettext_lazy("Расписание")),
    "roadmap.Task.title": (gettext_lazy("Название задачи"), gettext_lazy("Задача")),
    "roadmap.Task.due_date": (gettext_lazy("Срок задачи"), gettext_lazy("Срок")),
    "roadmap.Task.status": (gettext_lazy("Статус задачи"), gettext_lazy("Статус")),
    "roadmap.Essay.title": (gettext_lazy("Название эссе"), gettext_lazy("Эссе")),
    "roadmap.Essay.status": (gettext_lazy("Статус эссе"), gettext_lazy("Статус")),
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
        return str(extra[0])
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
        return str(extra[1])
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
        return _("да") if value else _("нет")
    text = str(value)
    if text in ("True", "False"):
        return _("да") if text == "True" else _("нет")
    # «да» и «нет», записанные в журнал словом, и фразы событий из реестра
    # `core.stored_text` хранятся по-русски — читающему на его языке
    if text in ("да", "нет"):  # i18n-skip: сравнение с сохранённым значением журнала
        return _("да") if text == "да" else _("нет")  # i18n-skip: сравнение с сохранённым значением журнала
    localized = stored_text.localize(text)
    if localized != text:
        return localized

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
    old = value_title(model_label, field_name, old_value) or _("пусто")
    new = value_title(model_label, field_name, new_value) or _("пусто")
    return _("{field}: {old} → {new}").format(field=field_title(model_label, field_name), old=old, new=new)


def acting_for_phrase(domain_code: str) -> str:
    """«за домен «Экзамены»» — подпись к правке, сделанной не владельцем домена.

    Одна фраза на все экраны: историю карточки, дайджест, историю
    загрузок. Пустой код — пустая строка: у правки владельца пометки нет.
    """
    from core.domains import DOMAINS

    domain = DOMAINS.get(domain_code or "")
    # с фазы 68 администратор правит любой домен напрямую, и пометка должна
    # читаться сразу: не просто «за домен», а кто именно правил
    return _("правил администратор за домен «{domain}»").format(domain=domain.title) if domain else ""
