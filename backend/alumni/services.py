"""Переход ученик → выпускник и работа с менторством."""

from __future__ import annotations

from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from accounts.models import Identity, IdentityProvider, Role
from alumni.models import Alumnus, AlumnusApplication, ApplicationOutcome, MentorshipRequest, MentorshipStatus
from students.models import Student
from universities.models import ApplicationStatus

#: За сколько до выпуска предлагаем привязать личную почту.
LINK_OFFER_DAYS = 60

#: Как статус заявки ученика ложится на результат выпускника.
OUTCOME_BY_APPLICATION = {
    ApplicationStatus.ACCEPTED: ApplicationOutcome.ADMITTED,
    ApplicationStatus.REJECTED: ApplicationOutcome.REJECTED,
    ApplicationStatus.WAITLIST: ApplicationOutcome.WAITLIST,
}


def graduation_date(student: Student) -> date:
    """Дата выпуска — 1 июня года выпуска."""
    return date(student.graduation_year, 6, 1)


def needs_identity_offer(student: Student, *, today: date | None = None) -> bool:
    """Пора ли предложить привязать личную почту.

    За два месяца до выпуска и только если второй идентичности ещё нет:
    школьный Entra отключат, и человек потеряет доступ.
    """
    today = today or timezone.localdate()
    if student.user_id is None:
        return False
    has_personal = Identity.objects.filter(user_id=student.user_id, provider=IdentityProvider.EMAIL_LINK).exists()
    if has_personal:
        return False
    return today >= graduation_date(student) - timedelta(days=LINK_OFFER_DAYS)


@transaction.atomic
def promote(student: Student, *, contact_email: str = "") -> Alumnus:
    """Перевести ученика в выпускники.

    Профиль на момент поступления снимается срезом: дальше он не меняется
    вслед за правками карточки — это исторический факт.
    """
    exam = getattr(student, "exam", None)
    alumnus, created = Alumnus.objects.get_or_create(
        student=student,
        defaults={
            "graduation_year": student.graduation_year,
            "admission_gpa": exam.gpa if exam else None,
            "admission_ielts": exam.ielts_current if exam else None,
            "admission_sat": exam.sat_current if exam else None,
            "admission_activities": student.activities.count(),
            "contact_email": contact_email,
        },
    )

    if created:
        # результаты по заявкам переносим строками
        for row in student.universities.select_related("program__university").all():
            outcome = OUTCOME_BY_APPLICATION.get(row.application_status)
            if outcome is None:
                continue
            AlumnusApplication.objects.get_or_create(
                alumnus=alumnus, program=row.program, defaults={"outcome": outcome}
            )
            if outcome == ApplicationOutcome.ADMITTED and alumnus.university_id is None:
                alumnus.university = row.program.university
                alumnus.program = row.program
                alumnus.country = row.program.university.country
                alumnus.save(update_fields=["university", "program", "country"])

    if student.is_active:
        student.is_active = False
        student.save(update_fields=["is_active"])

    if student.user_id and student.user.role == Role.STUDENT:
        # роль остаётся `student`: выпускник продолжает видеть свой кабинет,
        # но карточка уже неактивна. Отдельной роли для выпускника нет.
        pass

    return alumnus


def promote_due(*, today: date | None = None) -> dict:
    """Автоматический перевод по дате выпуска — задача Celery."""
    today = today or timezone.localdate()
    due = Student.objects.filter(is_active=True, graduation_year__lte=today.year).exclude(alumnus__isnull=False)
    promoted = 0
    for student in due.select_related("exam", "user"):
        if today >= graduation_date(student):
            promote(student)
            promoted += 1
    return {"promoted": promoted}


# --- Менторство ---


class MentorshipDenied(Exception):
    """Действие недопустимо на текущем статусе."""


@transaction.atomic
def request_mentorship(*, student: Student, alumnus: Alumnus, topic: str, message: str = "") -> MentorshipRequest:
    """Ученик просит о менторстве. Выпускник об этом пока не знает."""
    if not alumnus.mentorship_consent:
        raise MentorshipDenied("Этот выпускник не давал согласия на менторство")
    return MentorshipRequest.objects.create(
        student=student,
        alumnus=alumnus,
        topic=topic,
        message=message,
        status=MentorshipStatus.REQUESTED,
        is_visible_to_alumnus=False,
    )


@transaction.atomic
def approve(request: MentorshipRequest, *, reviewer, note: str = "") -> MentorshipRequest:
    """Сотрудник одобряет запрос — только теперь он уходит выпускнику."""
    if request.status != MentorshipStatus.REQUESTED:
        raise MentorshipDenied("Запрос уже рассмотрен")
    request.status = MentorshipStatus.SENT
    request.is_visible_to_alumnus = True
    request.reviewed_by = reviewer
    request.review_note = note
    request.save(update_fields=["status", "is_visible_to_alumnus", "reviewed_by", "review_note", "updated_at"])
    return request


@transaction.atomic
def decline(request: MentorshipRequest, *, reviewer, note: str = "") -> MentorshipRequest:
    """Сотрудник отклоняет запрос. Выпускник его не увидит никогда."""
    if request.status != MentorshipStatus.REQUESTED:
        raise MentorshipDenied("Запрос уже рассмотрен")
    request.status = MentorshipStatus.DECLINED
    request.is_visible_to_alumnus = False
    request.reviewed_by = reviewer
    request.review_note = note
    request.save(update_fields=["status", "is_visible_to_alumnus", "reviewed_by", "review_note", "updated_at"])
    return request


def visible_to_alumnus(alumnus: Alumnus):
    """Что выпускник вправе видеть: только пропущенное сотрудником."""
    return alumnus.mentorship_requests.filter(is_visible_to_alumnus=True)
