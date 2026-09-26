"""Телефоны родителей: казахстанские номера приводятся к `+7XXXXXXXXXX`.

Однозначные варианты — «8 707 123 45 67», «7071234567», «+7 (707) 123-45-67» —
становятся одним видом, по которому набирают и копируют в мессенджер.
Иностранные с «+» и всё, что не читается как казахстанский номер,
остаются как записали.
"""

from __future__ import annotations

import re

DIGITS = re.compile(r"\D+")


def normalize_kz(raw: str | None) -> str:
    """Казахстанский номер к `+7XXXXXXXXXX`; остальное как есть."""
    text = (raw or "").strip()
    if not text:
        return ""
    digits = DIGITS.sub("", text)
    if text.startswith("+") and not digits.startswith("7"):
        return text
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10 and digits[0] == "7" and not text.startswith("+"):
        return "+7" + digits
    return text
