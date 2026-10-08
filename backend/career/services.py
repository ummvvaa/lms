"""Тесты профориентации: создание из файла, назначение, кому что открыто."""

from __future__ import annotations

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from career.files import ParsedTest
from career.models import (
    AttemptStatus,
    CareerAssignment,
    CareerAttempt,
    CareerItem,
    CareerItemChoice,
    CareerRange,
    CareerScale,
    CareerTest,
    CareerTestOption,
)
from students.models import Student, StudyGroup


@transaction.atomic
def create_test(parsed: ParsedTest, *, data: bytes, file_name: str, actor) -> CareerTest:
    """Записать разобранную книгу строками своих таблиц. Файл — рядом, в закрытом хранилище."""
    assert parsed.ok, "only an error-free workbook may be stored"
    test = CareerTest.objects.create(
        title=parsed.title,
        instruction=parsed.instruction,
        analysis_min_score=parsed.threshold,
        created_by=actor,
        file_name=file_name[:200],
        is_fictional=bool(getattr(actor, "is_fictional", False)),
    )
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "xlsx"
    test.file.save(f"test.{ext}", ContentFile(data), save=True)
    CareerTestOption.objects.bulk_create(
        [
            CareerTestOption(test=test, order=i, label=label, value=value)
            for i, (label, value) in enumerate(parsed.options, 1)
        ]
    )
    scales = {
        code: CareerScale.objects.create(test=test, code=code, title=title, description=desc, order=i)
        for i, (code, title, desc) in enumerate(parsed.scales, 1)
    }
    for item in parsed.items:
        row = CareerItem.objects.create(
            test=test, number=item.number, text=item.text, scale=scales.get(item.scale), sign=item.sign
        )
        CareerItemChoice.objects.bulk_create(
            [
                CareerItemChoice(item=row, order=i, label=choice.label, scale=scales[choice.scale], value=choice.value)
                for i, choice in enumerate(item.choices, 1)
            ]
        )
    CareerRange.objects.bulk_create(
        [
            CareerRange(
                test=test,
                scale=scales.get(rng.scale) if rng.scale else None,
                low=rng.low,
                high=rng.high,
                label=rng.label,
                order=i,
            )
            for i, rng in enumerate(parsed.ranges, 1)
        ]
    )
    return test


def live_tests():
    return CareerTest.objects.filter(archived_at__isnull=True)


def tests_for(student: Student):
    """Включённые тесты, назначенные ученику — группе целиком или ему лично."""
    if student is None:
        return CareerTest.objects.none()
    condition = Q(assignments__student=student)
    if student.group_id:
        condition |= Q(assignments__group_id=student.group_id, assignments__student__isnull=True)
    return live_tests().filter(is_active=True).filter(condition).distinct().order_by("created_at", "id")


def assigned_student_ids(test: CareerTest, group: StudyGroup) -> list[int]:
    """Ученики группы, которым тест открыт: вся группа или отмеченные."""
    rows = list(test.assignments.filter(group=group))
    if not rows:
        return []
    students = Student.objects.filter(group=group, is_active=True).order_by("last_name", "first_name", "id")
    if any(row.student_id is None for row in rows):
        return list(students.values_list("pk", flat=True))
    picked = {row.student_id for row in rows if row.student_id}
    return [pk for pk in students.values_list("pk", flat=True) if pk in picked]


@transaction.atomic
def assign(test: CareerTest, groups: list[dict], *, actor) -> None:
    """Заменить назначения теста: список {group, students|null}; пусто — снять всё."""
    test.assignments.all().delete()
    for row in groups:
        group = row["group"]
        students = row.get("students")
        if students is None:
            CareerAssignment.objects.create(test=test, group=group, assigned_by=actor)
            continue
        for student in students:
            CareerAssignment.objects.create(test=test, group=group, student=student, assigned_by=actor)


def assigned_groups(test: CareerTest) -> list[dict]:
    """Назначения теста по группам: вся группа или список учеников."""
    out: dict[int, dict] = {}
    for row in test.assignments.select_related("group").order_by("group__code", "id"):
        entry = out.setdefault(row.group_id, {"group": row.group, "whole": False, "students": []})
        if row.student_id is None:
            entry["whole"] = True
        else:
            entry["students"].append(row.student_id)
    return list(out.values())


def live_attempt(test: CareerTest, student: Student) -> CareerAttempt | None:
    return CareerAttempt.objects.filter(test=test, student=student, archived_at__isnull=True).first()


def start_attempt(test: CareerTest, student: Student) -> CareerAttempt:
    """Открыть попытку или вернуть идущую. Сданную второй раз не начать (Д1)."""
    attempt = live_attempt(test, student)
    if attempt is not None:
        return attempt
    return CareerAttempt.objects.create(test=test, student=student)


def allow_retake(attempt: CareerAttempt, *, actor) -> None:
    """Прежняя попытка уходит в историю, ученик может пройти тест заново."""
    attempt.archived_at = timezone.now()
    attempt.retake_allowed_by = actor
    attempt.save(update_fields=["archived_at", "retake_allowed_by"])


def done_attempts(student: Student, tests=None):
    qs = CareerAttempt.objects.filter(
        student=student, status=AttemptStatus.DONE, archived_at__isnull=True, test__archived_at__isnull=True
    )
    if tests is not None:
        qs = qs.filter(test__in=tests)
    return qs.select_related("test")
