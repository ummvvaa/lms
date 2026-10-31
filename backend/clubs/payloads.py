"""Ответы ручек кружков: одно место, чтобы ученик, ментор и администратор видели кружок одинаково."""

from __future__ import annotations

from django.utils import timezone

from clubs import services
from clubs.models import Club, ClubEnrollment, ClubHomework
from core.parallels import parallel_of


def when(value) -> str | None:
    return timezone.localtime(value).isoformat() if value else None


def student_brief(student) -> dict:
    return {
        "id": student.pk,
        "full_name": student.full_name,
        "short_name": f"{student.last_name} {student.first_name}".strip(),
        "group": student.group.code if student.group_id else "",
        "group_id": student.group_id,
        "parallel": parallel_of(student),
    }


def meetings(club: Club) -> list[dict]:
    return [
        {
            "weekday": m.weekday,
            "day": m.get_weekday_display(),
            "starts": f"{m.starts:%H:%M}",
            "ends": f"{m.ends:%H:%M}",
        }
        for m in sorted(club.meetings.all(), key=lambda m: (m.weekday, m.starts))
    ]


def club_card(club: Club) -> dict:
    """Карточка кружка: то, что видят все, кому кружок открыт."""
    return {
        "id": club.pk,
        "title": club.title,
        "description": club.description,
        "mentor_name": club.mentor_name,
        "schedule": services.schedule_words(club.meetings.all()),
        "meetings": meetings(club),
        "parallels": services.parallels_of(club),
        "enroll_until": when(club.enroll_until),
        "open": services.is_open(club),
        "marks_enabled": club.marks_enabled,
    }


def club_admin(club: Club, enrolled: int = 0) -> dict:
    """Строка списка у администратора: карточка, учётка ментора, записанные, архив."""
    return {
        **club_card(club),
        "mentor": club.mentor_id,
        "mentor_account": (club.mentor.full_name or club.mentor.email) if club.mentor_id else "",
        "enrolled": enrolled,
        "archived": club.archived_at is not None,
    }


def enrollment_row(row: ClubEnrollment) -> dict:
    return {
        "id": row.pk,
        "student": student_brief(row.student),
        "enrolled_at": when(row.enrolled_at),
        "ended_at": when(row.ended_at),
        "left": row.ended_at is not None,
    }


def homework_row(row: ClubHomework) -> dict:
    return {
        "id": row.pk,
        "club": row.club_id,
        "text": row.text,
        "due": row.due.isoformat(),
        "file_name": row.file_name if row.file else "",
        "has_file": bool(row.file),
        "created_at": when(row.created_at),
        "updated_at": when(row.updated_at),
        "author": (row.created_by.full_name or row.created_by.email) if row.created_by_id else "",
    }
