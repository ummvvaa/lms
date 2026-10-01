"""Запись изменений доменных полей в журнал (инвариант №9).

Единственная точка, через которую доменные поля меняются программно.
Всё, что пишет в профили — API, импорт, применение предложений, фоновая
сверка — проходит здесь и оставляет след с указанием источника.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import models
from django.utils.translation import gettext as _

from core.domains import ROLE_CURATOR, Source, can_upload_files, domain_of_field, spec_of_field
from core.labels import field_title
from core.models import AuditLog
from core.references import resolve as resolve_reference


def model_label(instance_or_model: Any) -> str:
    """`app_label.ModelName` для инстанса или класса модели."""
    meta = instance_or_model._meta
    return f"{meta.app_label}.{meta.object_name}"


def to_text(value: Any) -> str:
    """Значение поля в виде строки для журнала."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "да" if value else "нет"  # i18n-skip: значение журнала, по нему же откат читает булево обратно
    if isinstance(value, models.Model):
        # запись справочника пишем названием, а не ключом: журнал читает
        # человек, и «Футбол» ему говорит больше, чем «3». По названию же
        # значение и возвращается обратно при откате (фаза 18)
        if getattr(value, "resolve_by_name", False):
            return value.name
        return str(value.pk)
    return str(value)


class ValueRejected(ValueError):
    """Значение не подходит колонке. Текст пригоден для показа человеку."""


#: Как человек и журнал пишут «да» и «нет». `to_text` сохраняет булево
#: именно так, и обратный путь — откат импорта, применение предложения —
#: обязан эти слова понимать: иначе значение уходит в базу, а вернуться
#: оттуда не может.
TRUE_WORDS = {"да", "иә", "true", "yes", "1", "+", "есть", "бар", "y"}  # i18n-skip: разбор ввода и журнала
FALSE_WORDS = {"нет", "жоқ", "false", "no", "0", "-", "n", ""}  # i18n-skip: разбор ввода и журнала


def to_bool(value: Any) -> bool | None:
    """Булево из того, что написал человек или записал журнал."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in TRUE_WORDS:
        return True
    if text in FALSE_WORDS:
        return False
    return None


def coerce(instance: Any, field_name: str, value: Any) -> Any:
    """Привести значение к типу колонки или отказать с внятным текстом.

    В отличие от `normalize`, ошибку не глотает: директор, набравший буквы
    в числовой ячейке, должен увидеть причину отказа, а не страницу 500.
    Границы шкалы берутся из реестра доменов — «указано 12.5, максимальный
    балл 9» полезнее, чем «недопустимое значение».
    """
    try:
        field = instance._meta.get_field(field_name)
    except FieldDoesNotExist as error:
        raise ValueRejected(_("Такого поля у этой записи нет — выберите колонку из списка")) from error
    if field.is_relation:
        # ссылка на справочник: «Футбол» из файла — это запись SportType,
        # а не строка. Неизвестное название отклоняется с подсказкой
        try:
            return resolve_reference(field, value)
        except LookupError as error:
            raise ValueRejected(str(error)) from error
    if value is None or value == "":
        return None if value == "" else value
    # подпись берём из реестра доменов, а не из `verbose_name` колонки:
    # человек читает одно и то же название поля во всех отказах (фаза 17)
    title = field_title(model_label(instance), field_name)
    if isinstance(field, models.BooleanField):
        flag = to_bool(value)
        if flag is None:
            raise ValueRejected(
                _("«{value}» не подходит для поля «{field}»: нужно «да» или «нет»").format(value=value, field=title)
            )
        return flag
    if field.choices:
        return choice_key(field, value, title=str(title))
    try:
        field.to_python(value)
    except (ValidationError, TypeError, ValueError) as error:
        raise ValueRejected(_("«{value}» не подходит для поля «{field}»").format(value=value, field=title)) from error
    check_bounds(instance, field_name, value, title=str(title))
    return normalize(instance, field_name, value)


def choice_key(field, value: Any, *, title: str = "") -> Any:
    """Ключ варианта поля со списком: сам ключ или его подпись на любом языке интерфейса.

    Строка не из списка раньше ложилась в колонку как есть: `to_python`
    варианты не проверяет, и «Работает самостоятельно», набранное в карточке
    подписью, или опечатка в таблице оседали в поле, по которому строятся
    дашборды (инвариант 6). Подпись из файла или с экрана переводится в ключ,
    остальное отклоняется с перечнем вариантов.
    """
    text = str(value).strip()
    folded = text.casefold()
    for key, label in field.flatchoices:
        if text == str(key) or folded == str(key).casefold() or folded in _label_forms(label):
            return key
    options = ", ".join(f"«{label}»" for _key, label in field.flatchoices)
    raise ValueRejected(
        _("«{value}» не подходит для поля «{field}»: выберите один из вариантов — {options}").format(
            value=value, field=title, options=options
        )
    )


def _label_forms(label) -> set[str]:
    """Подпись варианта на всех языках интерфейса, без регистра."""
    from django.utils import translation

    from core.i18n import INTERFACE_LANGUAGES

    forms = set()
    for language in INTERFACE_LANGUAGES:
        with translation.override(language):
            forms.add(str(label).strip().casefold())
    return forms


def check_bounds(instance: Any, field_name: str, value: Any, *, title: str = "") -> None:
    """Проверить значение по границам шкалы из реестра доменов.

    Сначала шкала экзамена (D4, D17): у балла IELTS и SAT разные пределы
    и шаг, и «12.5» у IELTS должно отбиваться так же, как «1315» у SAT.
    Нет шкалы у экзамена — действует общая граница поля.
    """
    from core.domains import scale_for

    # шкала — про числа: ссылке «экзамен цели» и текстам она не нужна
    try:
        column = instance._meta.get_field(field_name)
    except FieldDoesNotExist:
        return
    if column.is_relation or not isinstance(column, models.DecimalField | models.IntegerField | models.FloatField):
        return
    spec = spec_of_field(model_label(instance), field_name)
    scale = scale_for(instance, field_name)
    if scale is not None and str(value).strip() != "":
        if not scale.holds(value):
            shown = title or (spec.title if spec else field_name)
            try:
                number = float(str(value).replace(",", "."))
            except (TypeError, ValueError):
                number = None
            if number is not None and number > float(scale.maximum):
                edge = _("максимальный балл — {number}").format(number=_short(float(scale.maximum)))
            elif number is not None and number < float(scale.minimum):
                edge = _("минимальный балл — {number}").format(number=_short(float(scale.minimum)))
            else:
                edge = _("шаг шкалы — {number}").format(number=_short(float(scale.step)))
            raise ValueRejected(
                _("«{field}»: указано {value}, {limit} (шкала {scale}). Проверьте значение").format(
                    field=shown, value=value, limit=edge, scale=scale.hint
                )
            )
        return
    if spec is None or (spec.minimum is None and spec.maximum is None):
        return
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return
    title = title or spec.title
    if spec.maximum is not None and number > spec.maximum:
        raise ValueRejected(_out_of_range(title, value, _limit(spec, spec.maximum, top=True)))
    if spec.minimum is not None and number < spec.minimum:
        raise ValueRejected(_out_of_range(title, value, _limit(spec, spec.minimum, top=False)))


def _out_of_range(title, value, limit: str) -> str:
    """«IELTS»: указано 12, максимальный балл — 9. Проверьте значение»."""
    return _("«{field}»: указано {value}, {limit}. Проверьте значение").format(field=title, value=value, limit=limit)


def _limit(spec, bound: float, *, top: bool) -> str:
    """«максимальный балл — 9», «максимум — 100%», «минимум — 400».

    Единицу приклеиваем по-русски, а не через пробел: «максимум — 9 балл»
    читается как ошибка перевода.
    """
    number = _short(bound)
    if spec.unit == "балл":  # i18n-skip: сравнение с единицей из реестра доменов
        text = _("максимальный балл — {number}") if top else _("минимальный балл — {number}")
    elif spec.unit == "%":
        text = _("максимум — {number}%") if top else _("минимум — {number}%")
    elif spec.unit == "ч":  # i18n-skip: сравнение с единицей из реестра доменов
        text = _("максимум — {number} ч") if top else _("минимум — {number} ч")
    elif spec.unit:
        text = _("максимум — {number} {unit}") if top else _("минимум — {number} {unit}")
    else:
        text = _("максимум — {number}") if top else _("минимум — {number}")
    return text.format(number=number, unit=spec.unit)


def _short(number: float) -> str:
    return str(int(number)) if float(number).is_integer() else str(number)


def normalize(instance: Any, field_name: str, value: Any) -> Any:
    """Привести значение к тому виду, в котором его хранит колонка.

    Без этого повторный импорт того же файла выглядит как изменение:
    `Decimal("3.8")` и прочитанное из базы `Decimal("3.80")` — одно и то же
    число, но разные строки в журнале.
    """
    try:
        field = instance._meta.get_field(field_name)
    except FieldDoesNotExist:
        return value
    if field.is_relation:
        try:
            return resolve_reference(field, value)
        except LookupError:
            return value
    if value is None:
        return value
    if isinstance(field, models.BooleanField):
        flag = to_bool(value)
        return value if flag is None else flag
    try:
        value = field.to_python(value)
    except (ValidationError, TypeError, ValueError):
        return value
    if isinstance(field, models.DecimalField) and isinstance(value, Decimal) and field.decimal_places is not None:
        value = value.quantize(Decimal(1).scaleb(-field.decimal_places))
    return value


def student_id_of(instance: Any) -> int | None:
    """Ученик, к которому относится объект, если он есть."""
    if hasattr(instance, "student_id"):
        return instance.student_id
    if instance.__class__.__name__ == "Student":
        return instance.pk
    return None


def student_group_of(instance: Any) -> str:
    """Код группы ученика на момент записи — снимком, а не ссылкой (фаза 60).

    Ссылка на группу читалась бы после перевода ученика уже как новая группа,
    а журнал должен отвечать, в чьей группе он был, когда это подтверждали.
    """
    student_id = student_id_of(instance)
    if student_id is None:
        return ""
    student = instance if instance.__class__.__name__ == "Student" else getattr(instance, "student", None)
    if student is None:
        return ""
    group = getattr(student, "group", None)
    return group.code if group is not None else ""


def record_change(
    *,
    instance: Any,
    field_name: str,
    old_value: Any,
    new_value: Any,
    actor=None,
    source: str = Source.MANUAL,
    suggestion=None,
    import_batch=None,
) -> AuditLog | None:
    """Записать одно изменение. Если значение не поменялось — записи нет."""
    old_text, new_text = to_text(old_value), to_text(new_value)
    if old_text == new_text:
        return None
    label = model_label(instance)
    domain = domain_of_field(label, field_name)
    # автор пишет не в свой домен — так делает только администратор при
    # загрузке файла или вставке текста (фаза 35). Помечаем, за какой
    # домен он действовал: владелец домена прочитает это в истории.
    # Считается здесь, в единственной точке записи, а не в каждом
    # вызывающем коде — иначе правка из админки осталась бы без пометки
    acting_for = ""
    actor_role = getattr(actor, "role", "") if actor is not None else ""
    if domain is not None and can_upload_files(actor_role) and actor_role != domain.role:
        acting_for = domain.code
    entry = AuditLog.objects.create(
        actor=actor,
        actor_role=actor_role,
        model_label=label,
        object_id=str(instance.pk),
        student_id=student_id_of(instance),
        student_group=student_group_of(instance),
        field_name=field_name,
        domain_code=domain.code if domain else "",
        acting_for=acting_for,
        old_value=old_text,
        new_value=new_text,
        source=source,
        suggestion=suggestion,
        import_batch=import_batch,
    )
    # куратор внёс значение сам — висящее предложение ученика по этому полю
    # закрывается как перекрытое. Здесь, в единственной точке записи журнала:
    # правка с экрана, импорт куратора и пакетное сохранение идут сюда же.
    # Решение по очереди сюда не попадает — у него источник «предложил ученик»
    if actor_role == ROLE_CURATOR and suggestion is None and source in (Source.MANUAL, Source.IMPORT):
        from suggestions.superseding import by_field

        by_field(instance, field_name, new_value, actor=actor)
    return entry


def record_event(*, student, code: str, text: str, actor=None, source: str = Source.MANUAL) -> AuditLog:
    """Событие по ученику, у которого нет поля: звонок, передача, напоминание (фаза 62).

    Пишется тем же журналом, что и правки: у куратора один экран истории,
    и звонок родителям должен стоять в нём рядом с подтверждённым баллом.
    Подпись события — в `core.labels.EXTRA_TITLES`, а не имя кода.
    """
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_role=getattr(actor, "role", "") or "",
        student_group=student.group.code if getattr(student, "group_id", None) else "",
        model_label="students.Student",
        object_id=str(student.pk),
        student_id=student.pk,
        field_name=code,
        old_value="",
        new_value=text[:2000],
        source=source,
    )


def apply_changes(
    instance: Any,
    changes: dict[str, Any],
    *,
    actor=None,
    source: str = Source.MANUAL,
    suggestion=None,
    import_batch=None,
) -> list[AuditLog]:
    """Применить набор изменений к объекту и записать их в журнал.

    Старые значения снимаются до присваивания. Возвращает созданные записи
    аудита; сохраняются только затронутые поля.
    """
    touched: dict[str, tuple[Any, Any]] = {}
    for field_name, raw_value in changes.items():
        new_value = normalize(instance, field_name, raw_value)
        old_value = getattr(instance, field_name, None)
        if to_text(old_value) == to_text(new_value):
            continue
        touched[field_name] = (old_value, new_value)
        setattr(instance, field_name, new_value)
    if not touched:
        return []
    # попытка из таблицы Асем (фаза 65): настоящая дата снимает «дата не указана»
    if "date" in touched and getattr(instance, "date_unknown", False):
        instance.date_unknown = False
        touched["date_unknown"] = (True, False)
    # частичная уникальность проверяется до `save()` (D24, D35): база ответила бы
    # `IntegrityError` и человек увидел бы 500, а здесь отказ читается словами
    from core.uniqueness import conflict_of, touches

    if instance.pk is None or touches(instance, touched):
        reason = conflict_of(instance)
        if reason:
            raise ValueRejected(reason)
    # сигнал post_save увидит этот флаг и не запишет те же поля второй раз
    instance._audit_handled = tuple(touched)
    if instance.pk is None:
        instance.save()
    else:
        update_fields = set(touched)
        if any(f.name == "updated_at" for f in instance._meta.fields):
            update_fields.add("updated_at")
        instance.save(update_fields=sorted(update_fields))
    entries: list[AuditLog] = []
    for field_name, (old_value, new_value) in touched.items():
        entry = record_change(
            instance=instance,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            actor=actor,
            source=source,
            suggestion=suggestion,
            import_batch=import_batch,
        )
        if entry:
            entries.append(entry)
    return entries
