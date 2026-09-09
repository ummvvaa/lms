"""Пароли учеников от почты и Common App (фаза 65).

Это единственные данные в системе, которые открывают чужие аккаунты.
Правила — здесь, одним местом:

* в базе только шифртекст (`core.secrets`, ключ `CREDENTIALS_KEY`);
* блок карточки отдаёт лишь «есть / нет»;
* открытый текст выдаёт один вызов `reveal`, и каждый пишется в журнал
  (кто, чей, когда) — событие `credential_reveal`;
* кто вправе смотреть и записывать — списки в реестре доменов
  (`CREDENTIAL_VIEWERS`, `CREDENTIAL_EDITORS`); куратор — своей группы,
  ученик — только свои.
"""

from __future__ import annotations

from core import secrets
from core.audit import record_event
from core.domains import CREDENTIAL_EDITORS, CREDENTIAL_VIEWERS, ROLE_STUDENT
from core.scope import sees_student
from students.models import CredentialKind, Student, StudentCredential

#: Как пароль выглядит в карточке до нажатия «Показать»
MASK = "••••••"


def may_view(user, student: Student) -> bool:
    """Показать пароль: директора, администратор, куратор своей группы, сам ученик."""
    role = getattr(user, "role", "")
    if role == ROLE_STUDENT:
        return getattr(getattr(user, "student", None), "pk", None) == student.pk
    return role in CREDENTIAL_VIEWERS and sees_student(user, student.pk)


def may_edit(user, student: Student) -> bool:
    """Записать пароль: Асем, администратор, куратор своей группы, сам ученик."""
    role = getattr(user, "role", "")
    if role == ROLE_STUDENT:
        return getattr(getattr(user, "student", None), "pk", None) == student.pk
    return role in CREDENTIAL_EDITORS and sees_student(user, student.pk)


def state(student: Student) -> dict[str, bool]:
    """«Есть / нет» по каждому виду — и ничего больше."""
    present = set(StudentCredential.objects.filter(student=student).values_list("kind", flat=True))
    return {kind: kind in present for kind in CredentialKind.values}


def set_credential(student: Student, kind: str, plaintext: str, *, actor) -> bool:
    """Записать пароль шифртекстом. Возвращает, изменилось ли что-то.

    Пустая строка убирает пароль. Тот же пароль повторно не записывается:
    иначе повторный импорт таблицы двигал бы «обновлён» у всех.
    """
    if kind not in CredentialKind.values:
        raise ValueError("Неизвестный вид пароля")
    plaintext = (plaintext or "").strip()
    row = StudentCredential.objects.filter(student=student, kind=kind).first()
    if not plaintext:
        if row is None:
            return False
        row.delete()
        record_event(student=student, code="credential_set", text=f"{CredentialKind(kind).label}: убран", actor=actor)
        return True
    if row is not None:
        try:
            if secrets.decrypt(row.ciphertext) == plaintext:
                return False
        except secrets.KeyMismatch:
            pass
    else:
        row = StudentCredential(student=student, kind=kind)
    row.ciphertext = secrets.encrypt(plaintext)
    row.updated_by = actor if getattr(actor, "pk", None) else None
    row.save()
    record_event(student=student, code="credential_set", text=CredentialKind(kind).label, actor=actor)
    return True


def reveal(student: Student, kind: str, *, actor) -> str | None:
    """Открытый текст пароля — и запись в журнал о показе.

    Запись делается до возврата: показ без следа невозможен, даже если
    ответ потом не дошёл. Нет пароля — `None`, журнал не трогается.
    """
    if kind not in CredentialKind.values:
        raise ValueError("Неизвестный вид пароля")
    row = StudentCredential.objects.filter(student=student, kind=kind).first()
    if row is None:
        return None
    plaintext = secrets.decrypt(row.ciphertext)
    record_event(student=student, code="credential_reveal", text=CredentialKind(kind).label, actor=actor)
    return plaintext
