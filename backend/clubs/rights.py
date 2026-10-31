"""Кто что видит в кружках — граница «свой кружок» одним местом.

Роли — из реестра (`core.domains.CABINET_WRITERS`, `CABINET_READERS`), здесь
только граница: ментор видит свой кружок и записанных в него сейчас;
администратор — все кружки и может всё, что ментор (общее правило LMS).
Чужой кружок ментору отвечает 404, а не 403: по 403 было бы видно, что он есть.
"""

from __future__ import annotations

from core.domains import ROLE_ADMIN, ROLE_MENTOR

#: Кто читает заметки ментора об ученике. Одно место, как у заметок куратора
#: (`students.notes.NOTE_READERS`). Ментор — только своего кружка. Куратора,
#: директоров и ученика здесь нет и не будет: заметка — то, что ментор пишет
#: для себя и администратора (страж — `clubs/tests/test_club_notes.py`).
NOTE_READERS: tuple[str, ...] = (ROLE_MENTOR, ROLE_ADMIN)


def _role(user) -> str:
    return getattr(user, "role", "")


def mentored_clubs(user):
    """Кружки, которые ведёт ментор; архивные — нет."""
    from clubs.models import Club

    if _role(user) != ROLE_MENTOR or not getattr(user, "pk", None):
        return Club.objects.none()
    return Club.objects.filter(mentor=user)


def mentored_student_ids(user) -> list[int]:
    """Ученики, записанные сейчас в кружки ментора, — граница `core.scope`."""
    from clubs.models import ClubEnrollment

    return list(
        ClubEnrollment.objects.filter(club__in=mentored_clubs(user), ended_at__isnull=True)
        .values_list("student_id", flat=True)
        .distinct()
    )


def club_of(user, pk):
    """Кружок, который человек ведёт: администратору — любой живой, ментору — свой."""
    from clubs.models import Club

    try:
        number = int(pk)
    except (TypeError, ValueError):
        return None
    if _role(user) == ROLE_ADMIN:
        return Club.objects.filter(pk=number).first()
    return mentored_clubs(user).filter(pk=number).first()


def leads(user, club) -> bool:
    """Ведёт ли человек этот кружок: ментор своего или администратор."""
    if club is None:
        return False
    if _role(user) == ROLE_ADMIN:
        return True
    return _role(user) == ROLE_MENTOR and club.mentor_id == getattr(user, "pk", None)


def reads_notes(user, club) -> bool:
    """Видит ли человек заметки ментора этого кружка."""
    return _role(user) in NOTE_READERS and leads(user, club)
