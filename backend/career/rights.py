"""Кто ведёт профтест и кто читает его результаты.

Роль у учётки одна, а тесты ведёт тот, у кого в предметах учителя есть
предмет профориентации (`Subject.is_career`), при любой роли — так же,
как уроки отмечает тот, кто записан учителем (решение владельца,
29.09.2026). Журналы для этого не нужны (решение владельца, 13.10.2026:
учителю дали предмет в карточке, а все уроки профориентации стоят у
другого — раздел всё равно его): журнал только подсказывает группы по
умолчанию — свои составы; без журнала учитель выбирает любую группу.
Администратор — как всегда, за всех. Результаты и разборы читают учитель
профориентации, администратор, директор по поступлению, куратор — по своим
группам (решение владельца, 08.10.2026). Граница — группа ученика.
"""

from __future__ import annotations

from accounts.curators import curated_group_ids
from core.domains import ROLE_ADMIN, ROLE_CURATOR, ROLE_STUDENT
from students.models import StudyGroup

ADMISSION_DIRECTOR = "director_admission"


def career_courses(user):
    """Журналы предмета профориентации, где человек записан учителем."""
    from academics.models import Course

    if user is None or not getattr(user, "pk", None) or getattr(user, "role", "") == ROLE_STUDENT:
        return Course.objects.none()
    return Course.objects.filter(
        teacher=user, archived_at__isnull=True, subject__is_career=True, subject__in_lms=True
    ).select_related("cohort")


def teaches_career(user) -> bool:
    """В предметах учителя есть предмет профориентации — единственный источник права.

    Журнал предмета добавляет его в профиль сам (`academics.schedule`), так что
    тот, кто ведёт уроки профориентации, сюда тоже попадает.
    """
    from academics.models import TeacherProfile

    if user is None or not getattr(user, "pk", None) or getattr(user, "role", "") == ROLE_STUDENT:
        return False
    return TeacherProfile.objects.filter(user=user, subjects__is_career=True, subjects__in_lms=True).exists()


def manages(user) -> bool:
    """Загружает тесты, включает их, назначает группам, запускает разбор."""
    return getattr(user, "role", "") == ROLE_ADMIN or teaches_career(user)


def _all_group_ids() -> list[int]:
    return list(StudyGroup.objects.filter(is_active=True).values_list("pk", flat=True))


def taught_group_ids(user) -> list[int]:
    """Группы, которым учитель профориентации назначает тесты и чьи результаты читает.

    Есть журналы профориентации — группы их составов; журналов нет, а предмет
    в профиле есть — любая группа (решение владельца, 13.10.2026). Тому, кто
    профориентацию не ведёт, — пусто.
    """
    from academics.cohorts import group_ids_of

    out: list[int] = []
    for course in career_courses(user):
        for gid in group_ids_of(course.cohort):
            if gid not in out:
                out.append(gid)
    if not out and teaches_career(user):
        return _all_group_ids()
    return out


def visible_group_ids(user) -> list[int]:
    """Группы, чьи результаты и разборы человек читает. Ученику — пусто."""
    role = getattr(user, "role", "")
    if role in (ROLE_ADMIN, ADMISSION_DIRECTOR):
        return _all_group_ids()
    if role == ROLE_STUDENT or not role:
        return []
    out = taught_group_ids(user)
    if role == ROLE_CURATOR:
        for gid in curated_group_ids(user):
            if gid not in out:
                out.append(gid)
    return out


def reads(user) -> bool:
    """Открыт ли человеку раздел результатов вообще: роль или хотя бы одна группа."""
    if getattr(user, "role", "") in (ROLE_ADMIN, ADMISSION_DIRECTOR):
        return True
    return bool(visible_group_ids(user))


def sees_group(user, group_id: int | None) -> bool:
    return group_id is not None and group_id in visible_group_ids(user)


def sees_student(user, student) -> bool:
    """Читает ли человек результаты ученика — по его группе."""
    if student is None:
        return False
    role = getattr(user, "role", "")
    if role in (ROLE_ADMIN, ADMISSION_DIRECTOR):
        return True
    return sees_group(user, student.group_id)
