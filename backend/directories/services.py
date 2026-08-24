"""Что можно сделать с записью справочника: посчитать ссылки, скрыть, заменить.

Удалять запись, на которую ссылаются, нельзя — иначе история активностей
и профилей начнёт вести в пустоту. Но и тупик «удалить нельзя, разбирайтесь
сами» не годится: рядом с отказом всегда есть два выхода — скрыть из списка
выбора или перенести ссылки на другую запись.
"""

from __future__ import annotations

import re
import unicodedata

from django.db import models, transaction

from core.archive import manager_of
from core.phrasing import counted, listing


def _relations(instance: models.Model):
    """Обратные связи, по которым на запись справочника ссылаются."""
    for relation in instance._meta.related_objects:
        yield relation, relation.related_model, relation.field.name


def usage(instance: models.Model) -> list[dict]:
    """Кто ссылается на запись: вид записи, сколько и сколько из них в архиве."""
    rows: list[dict] = []
    for _relation, related_model, field_name in _relations(instance):
        query = manager_of(related_model).filter(**{field_name: instance})
        count = query.count()
        if not count:
            continue
        archived = 0
        if hasattr(related_model, "all_objects"):
            archived = query.filter(archived_at__isnull=False).count()
        rows.append(
            {
                "model": f"{related_model._meta.app_label}.{related_model._meta.object_name}",
                "title": str(related_model._meta.verbose_name_plural),
                "count": count,
                "archived": archived,
            }
        )
    return rows


def usage_total(instance: models.Model) -> int:
    return sum(row["count"] for row in usage(instance))


def usage_phrase(instance: models.Model) -> str:
    """«используется в 14 активностях» — человеческим языком."""
    rows = usage(instance)
    if not rows:
        return ""
    parts = []
    for row in rows:
        text = f"{row['count']} — {row['title'].lower()}"
        if row["archived"]:
            text += f" (из них в архиве: {row['archived']})"
        parts.append(text)
    return listing(parts)


def deletion_verdict(instance: models.Model) -> dict:
    """Можно ли удалить и что сказать человеку, если нельзя."""
    rows = usage(instance)
    total = sum(row["count"] for row in rows)
    if not total:
        return {
            "can_delete": True,
            "usage": rows,
            "usage_total": 0,
            "message": f"«{instance.name}» нигде не используется — можно удалить насовсем",
            "options": [],
        }
    kind = str(instance._meta.verbose_name).capitalize()
    return {
        "can_delete": False,
        "usage": rows,
        "usage_total": total,
        "message": (
            f"{kind} «{instance.name}» используется: {usage_phrase(instance)}. Удалить нельзя. "
            f"Можно скрыть запись из списка выбора или заменить её на другую"
        ),
        "options": [
            {
                "action": "hide",
                "title": "Скрыть",
                "hint": "Запись останется в старых записях, но в списке выбора её больше не будет",
            },
            {
                "action": "replace",
                "title": "Заменить",
                "hint": f"Перенести {counted(total, ('ссылку', 'ссылки', 'ссылок'))} на другую запись и удалить эту",
            },
        ],
    }


@transaction.atomic
def replace(instance: models.Model, target: models.Model) -> dict:
    """Перенести все ссылки на другую запись и удалить исходную.

    Ссылки переносятся и у архивных записей: вернувшийся из архива ученик
    не должен обнаружить у себя предмет, которого уже нет.
    """
    if instance.pk == target.pk:
        raise ValueError("Заменять запись на саму себя нечем")
    if type(instance) is not type(target):
        raise ValueError("Заменять можно только записью того же справочника")

    moved = 0
    for _relation, related_model, field_name in _relations(instance):
        moved += manager_of(related_model).filter(**{field_name: instance}).update(**{field_name: target})

    name = instance.name
    instance.delete()
    return {
        "moved": moved,
        "deleted": name,
        "target": target.name,
        "detail": f"«{name}» заменена на «{target.name}», перенесено ссылок: {moved}",
    }


# --- Похожие написания --------------------------------------------------

#: буквы, которые в кириллице и латинице выглядят одинаково: «Матем.»
#: и «Матем.» могут отличаться одной такой буквой и выглядеть близнецами
LOOKALIKE = str.maketrans("aAeEoOpPcCxXyYkKmMhHtTbB", "аАеЕоОрРсСхХуУкКмМнНтТвВ")


def normalized(name: str) -> str:
    """Написание без регистра, точек, дефисов и пробелов."""
    text = unicodedata.normalize("NFKC", name or "").casefold().translate(LOOKALIKE)
    text = text.replace("ё", "е")
    return re.sub(r"[^\w]+", "", text, flags=re.UNICODE)


def _stem(name: str) -> str:
    """Огрублённая основа: «Матем» и «Математика» сходятся по первым буквам."""
    return normalized(name)[:5]


def duplicate_groups(model: type[models.Model]) -> list[dict]:
    """«Возможно, это одно и то же» — группы похожих написаний.

    Автоматически ничего не склеиваем: решение о том, что «Матем.» и
    «Математика» — один предмет, принимает директор. Наше дело — заметить.
    """
    rows = list(model.objects.all())
    groups: dict[str, list] = {}
    for row in rows:
        key = _stem(row.name)
        if len(key) < 3:
            continue
        groups.setdefault(key, []).append(row)

    out = []
    for key, items in sorted(groups.items()):
        if len(items) < 2:
            continue
        out.append(
            {
                "key": key,
                "entries": [
                    {
                        "id": item.pk,
                        "name": item.name,
                        "is_active": item.is_active,
                        "usage_total": usage_total(item),
                    }
                    for item in sorted(items, key=lambda i: -usage_total(i))
                ],
            }
        )
    return out
