"""Кто что делает в учебной части — по таблице `docs/academics.md` и решениям.

| Действие                         | Учитель       | Куратор     | Кымбат | Админ | Салтанат |
| расписание на чтение             | свои уроки    | свои группы | всё    | всё   | нет      |
| добавить, изменить, удалить урок | нет           | нет         | да     | да    | нет      |
| отметить посещаемость            | свои и замены | нет         | нет    | да    | нет      |
| «у» — уважительная причина       | нет           | период      | нет    | да    | нет      |
| оценка                           | свои, 7 дней  | нет         | после  | да    | нет      |
| итог четверти                    | выставляет    | видит       | правит | да    | нет      |
| посещаемость на чтение по урокам | свои уроки    | свои группы | все    | все   | все      |
| отчёт родителям                  | нет (404)     | свои группы | все    | все   | все      |
| оценки ученика на чтение         | свои предметы | свои группы | все    | все   | нет      |

Асем, Арман и Нурлыбек читают оценки в карточке (вкладка «Успеваемость»),
но не правят: у них нет ни журнала, ни расписания (ответ владельца, шаг 6).

Границу «свои ученики» держит `core.scope`, здесь только роли.
"""

from __future__ import annotations

from core.domains import ROLE_ADMIN, ROLE_CURATOR, ROLE_STUDENT, ROLE_TEACHER

EXAM_DIRECTOR = "director_exam"
SCHOOL_DIRECTOR = "director_behavior"
ADMISSION_DIRECTOR = "director_admission"
TALENT_DIRECTOR = "director_talent"
SPORT_DIRECTOR = "director_sport"

#: Правят расписание, составы, учебный год, шкалу и настройки отчётов
SCHEDULE_EDITORS: tuple[str, ...] = (EXAM_DIRECTOR, ROLE_ADMIN)
#: Видят всё расписание, все журналы и успеваемость по школе
ACADEMICS_READERS: tuple[str, ...] = (EXAM_DIRECTOR, ROLE_ADMIN)
#: Оформляют уважительную причину за период
EXCUSE_WRITERS: tuple[str, ...] = (ROLE_CURATOR, ROLE_ADMIN)
#: Читают посещаемость по урокам: куратор своих групп, Салтанат и Кымбат — всех
ATTENDANCE_READERS: tuple[str, ...] = (ROLE_CURATOR, SCHOOL_DIRECTOR, EXAM_DIRECTOR, ROLE_ADMIN)
#: Напоминают учителю о неотмеченном уроке
REMINDERS: tuple[str, ...] = (ROLE_CURATOR, EXAM_DIRECTOR, ROLE_ADMIN)
#: Отчёты родителям делают куратор (свои группы), Кымбат, Салтанат и администратор
#: (все группы) — и только они (решение владельца, 27.09.2026): читают, проверяют,
#: пишут слово, собирают по ученику и отмечают отправку
REPORT_READERS: tuple[str, ...] = (ROLE_CURATOR, EXAM_DIRECTOR, SCHOOL_DIRECTOR, ROLE_ADMIN)
REPORT_WRITERS: tuple[str, ...] = REPORT_READERS
#: Видят оценки ученика: он сам, куратор его группы, учитель своих составов, Кымбат,
#: администратор; Асем, Арман и Нурлыбек — только читают (Салтанат оценок не видит)
GRADE_READERS: tuple[str, ...] = (
    ROLE_STUDENT,
    ROLE_CURATOR,
    ROLE_TEACHER,
    EXAM_DIRECTOR,
    ADMISSION_DIRECTOR,
    TALENT_DIRECTOR,
    SPORT_DIRECTOR,
    ROLE_ADMIN,
)
#: Видят пропуски по урокам в «Рисках» — правила посещаемости по урокам
RISK_READERS: tuple[str, ...] = (SCHOOL_DIRECTOR, ROLE_ADMIN)


def edits_schedule(role: str) -> bool:
    return role in SCHEDULE_EDITORS


def reads_all(role: str) -> bool:
    return role in ACADEMICS_READERS


def writes_excuse(role: str) -> bool:
    return role in EXCUSE_WRITERS


def reads_attendance(role: str) -> bool:
    return role in ATTENDANCE_READERS


def reminds(role: str) -> bool:
    return role in REMINDERS


def reads_reports(role: str) -> bool:
    return role in REPORT_READERS


def writes_reports(role: str) -> bool:
    return role in REPORT_WRITERS


def reads_grades(role: str) -> bool:
    return role in GRADE_READERS


def reads_risks(role: str) -> bool:
    return role in RISK_READERS


def marks_lesson(user, lesson) -> bool:
    """Отмечает урок тот, кто его ведёт (или заменяет), и администратор.

    Роль здесь не важна (решение владельца, 29.09.2026): классный час ведёт
    куратор, математику — директор талантов, и каждый отмечает свой урок.
    Остальные права роли от этого не расширяются.
    """
    if not lesson.in_lms:
        # предмет «только расписание»: журнал школа ведёт не в LMS
        return False
    role = getattr(user, "role", "")
    if role == ROLE_ADMIN:
        return True
    if role == ROLE_STUDENT or not getattr(user, "pk", None):
        return False
    return lesson.actual_teacher_id is not None and lesson.actual_teacher_id == user.pk


def grades_lesson(user, lesson) -> bool:
    """Ставит оценку тот же, кто отмечает; Кымбат правит оценки после окна."""
    if not lesson.in_lms:
        return False
    role = getattr(user, "role", "")
    if role in (ROLE_ADMIN, EXAM_DIRECTOR):
        return True
    return role == ROLE_TEACHER and lesson.actual_teacher_id == user.pk


def owns_course(user, course) -> bool:
    """Журнал ведёт его учитель; Кымбат и администратор открывают любой.

    У предмета «только расписание» журнала нет ни у кого.
    """
    if not course.subject.in_lms:
        return False
    role = getattr(user, "role", "")
    if role in ACADEMICS_READERS:
        return True
    return role == ROLE_TEACHER and course.teacher_id == user.pk


def sees_course(user, course) -> bool:
    """Читает журнал: учитель свой, Кымбат и администратор любой, куратор — своих групп."""
    if not course.subject.in_lms:
        return False
    role = getattr(user, "role", "")
    if owns_course(user, course):
        return True
    if role == ROLE_CURATOR:
        from academics.cohorts import group_ids_of
        from accounts.curators import curated_group_ids

        return bool(set(group_ids_of(course.cohort)) & set(curated_group_ids(user)))
    return False
