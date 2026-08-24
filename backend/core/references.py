"""Приведение строки к записи справочника.

В файле импорта и в ячейке таблицы человек пишет «Футбол», а в базе лежит
ссылка на запись справочника. Перевод — здесь, в одном месте: иначе импорт,
батч и API начнут расходиться в том, что считать известным видом спорта.

Молча заводить новую запись справочника нельзя: тогда опечатка в файле
создаст четвёртую «Матем.» и весь смысл справочника пропадёт. Поэтому
неизвестное значение отклоняется с текстом, объясняющим, что делать.
"""

from __future__ import annotations

from typing import Any

from django.db import models


def is_directory(model: type[models.Model]) -> bool:
    """Модель-справочник, к записям которой можно обращаться по названию."""
    return bool(getattr(model, "resolve_by_name", False))


def find(model: type[models.Model], value: Any) -> Any:
    """Запись справочника по ключу или по названию.

    Название сверяется без учёта регистра, точек и пробелов: «Матем.»
    и «матем» найдут одну и ту же запись, если она заведена. Ничего
    похожего — `LookupError` с готовым к показу текстом.
    """
    if value in (None, ""):
        return None
    if isinstance(value, models.Model):
        return value

    text = str(value).strip()
    if text.isdigit():
        found = model.objects.filter(pk=int(text)).first()
        if found is not None:
            return found

    from directories.services import normalized

    wanted = normalized(text)
    for row in model.objects.all():
        if normalized(row.name) == wanted:
            return row

    raise LookupError(
        f"«{text}» — такого значения нет в справочнике «{model._meta.verbose_name_plural}». "
        f"Заведите эту запись в справочнике или выберите значение из списка"
    )


def resolve(field, value: Any) -> Any:
    """Значение поля-ссылки: инстанс, ключ или название записи справочника."""
    related = field.related_model
    if value in (None, ""):
        return None
    if isinstance(value, models.Model) or not is_directory(related):
        return value
    return find(related, value)
