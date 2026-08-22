"""Снятие и возврат признака «данные не подтверждены» (инвариант №14).

Право есть только у директора по поступлению: он владелец домена
`admission`, и справочник ведёт он. Подтверждение вуза распространяется
на его программы, требования и раунды — сверяются они одним заходом
по одному и тому же сайту.
"""

from __future__ import annotations

from django.utils import timezone

from core.audit import record_change
from core.domains import DOMAINS, Source
from universities.models import AdmissionRequirement, AdmissionRound, Program, University

#: Что можно подтвердить: ключ запроса → модель и человеческое название.
VERIFIABLE = {
    "university": (University, "вуз"),
    "program": (Program, "программу"),
    "requirement": (AdmissionRequirement, "требования"),
    "round": (AdmissionRound, "раунд"),
}

#: Роль, которой можно снимать признак.
VERIFIER_ROLE = DOMAINS["admission"].role


class NotVerifiable(ValueError):
    """Такой вид записи подтверждать нечем."""


def can_verify(role: str) -> bool:
    return role == VERIFIER_ROLE


def _mark(instance, *, verified: bool, actor) -> bool:
    """Проставить признак одной записи. Возвращает True, если что-то менялось."""
    if instance.is_verified == verified:
        return False
    record_change(
        instance=instance,
        field_name="is_verified",
        old_value=instance.is_verified,
        new_value=verified,
        actor=actor,
        source=Source.MANUAL,
    )
    instance.is_verified = verified
    instance.verified_at = timezone.now() if verified else None
    instance.verified_by = actor if verified else None
    instance.save(update_fields=["is_verified", "verified_at", "verified_by"])
    return True


def set_verified(kind: str, pk: int, *, verified: bool, actor) -> dict:
    """Подтвердить запись справочника (или вернуть плашку обратно)."""
    if kind not in VERIFIABLE:
        raise NotVerifiable(f"Подтверждать «{kind}» система не умеет")
    model, title = VERIFIABLE[kind]
    instance = model.objects.filter(pk=pk).first()
    if instance is None:
        raise LookupError(f"Не нашли {title} с номером {pk}")

    changed = 1 if _mark(instance, verified=verified, actor=actor) else 0
    # у вуза сверяется вся его часть справочника разом: программы,
    # требования и раунды берутся с того же сайта
    if kind == "university":
        for program in Program.objects.filter(university=instance):
            changed += 1 if _mark(program, verified=verified, actor=actor) else 0
            requirement = getattr(program, "requirement", None)
            if requirement is not None:
                changed += 1 if _mark(requirement, verified=verified, actor=actor) else 0
            for admission_round in program.rounds.all():
                changed += 1 if _mark(admission_round, verified=verified, actor=actor) else 0

    return {
        "kind": kind,
        "id": instance.pk,
        "is_verified": instance.is_verified,
        "changed": changed,
        "verification_note": instance.verification_note,
        "detail": (
            f"Подтверждено, плашка снята. Затронуто записей: {changed}"
            if verified
            else f"Признак «не подтверждено» возвращён. Затронуто записей: {changed}"
        ),
    }
