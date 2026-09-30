"""Маленькая школа для проверок учебной части.

Год с одной четвертью вокруг сегодняшнего дня, две группы, три предмета,
два учителя, куратор одной группы, Кымбат, Салтанат, администратор,
ученик с учётной записью. Даты — относительно сегодня по Алматы: прогон
не зависит от того, в какой день его запустили.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from academics import calendar as school_calendar
from academics.cohorts import group_cohort, split_group
from academics.models import (
    AcademicYear,
    Bell,
    GradingScale,
    Quarter,
    ReportSettings,
    Scheme,
    Subject,
    TeacherProfile,
)
from academics.schedule import create_once
from accounts.curators import assign
from accounts.models import Role, User
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ContactRelation,
    ExamProfile,
    ParentContact,
    SportProfile,
    Student,
    StudyGroup,
    TalentProfile,
)

TODAY = timezone.localdate()


def days(n: int) -> dt.date:
    return TODAY + dt.timedelta(days=n)


def school_day(offset: int, calendar=None) -> dt.date:
    """Учебный день не позже `offset` дней от сегодня (назад, если offset < 0)."""
    day = days(offset)
    step = -1 if offset < 0 else 1
    while day.weekday() >= 5 or (calendar is not None and not calendar.is_school_day(day)):
        day += dt.timedelta(days=step)
    return day


def make_student(group, last, first, email, *, user=None, make_user=None) -> Student:
    student = Student.objects.create(last_name=last, first_name=first, email=email, group=group, graduation_year=2027)
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=student)
    if make_user is not None:
        account = make_user("student", email, full_name=f"{last} {first}")
        student.user = account
        student.save(update_fields=["user"])
    return student


@pytest.fixture
def year(db) -> AcademicYear:
    year = AcademicYear.objects.create(title="2026–2027", starts=days(-60), ends=days(260), is_current=True)
    Quarter.objects.create(year=year, number=1, title="1 четверть", starts=days(-60), ends=days(40))
    Quarter.objects.create(year=year, number=2, title="2 четверть", starts=days(50), ends=days(120))
    for number, starts, ends in school_calendar.DEFAULT_BELLS:
        Bell.objects.create(
            year=year, number=number, starts=dt.time.fromisoformat(starts), ends=dt.time.fromisoformat(ends)
        )
    GradingScale.objects.create(year=year)
    ReportSettings.objects.create(year=year)
    return year


@pytest.fixture
def calendar(year):
    return school_calendar.load(year)


@pytest.fixture
def subjects(db) -> dict[str, Subject]:
    return {
        "alg": Subject.objects.create(
            code="alg", title="Алгебра", short_title="Алгебра", sor_max=20, soch_max=30, order=1
        ),
        "eng": Subject.objects.create(code="eng", title="Английский язык", short_title="Английский", order=2),
        "pe": Subject.objects.create(
            code="pe", title="Физкультура", short_title="Физкультура", scheme=Scheme.FO, order=3
        ),
    }


@pytest.fixture
def boston(db) -> StudyGroup:
    return StudyGroup.objects.create(code="BOSTON", parallel=11)


@pytest.fixture
def chicago(db) -> StudyGroup:
    return StudyGroup.objects.create(code="CHICAGO", parallel=11)


@pytest.fixture
def admin(make_user) -> User:
    return make_user("admin", "admin.acad@example.kz", full_name="Администратор", is_staff=True)


@pytest.fixture
def kymbat(make_user) -> User:
    return make_user("director_exam", "kymbat.acad@example.kz", full_name="Кымбат")


@pytest.fixture
def saltanat(make_user) -> User:
    return make_user("director_behavior", "saltanat.acad@example.kz", full_name="Салтанат", sees_whole_school=True)


@pytest.fixture
def curator(make_user, boston, admin) -> User:
    user = make_user("curator", "curator.acad@example.kz", full_name="Асель Куратор")
    assign(group=boston, curator=user, since=days(-70), actor=admin)
    return user


@pytest.fixture
def teacher(make_user, subjects) -> User:
    user = make_user(Role.TEACHER, "teacher.acad@example.kz", full_name="Сапарова Гульнара")
    profile = TeacherProfile.objects.create(user=user, room="204")
    profile.subjects.set([subjects["alg"]])
    return user


@pytest.fixture
def other_teacher(make_user, subjects) -> User:
    user = make_user(Role.TEACHER, "teacher2.acad@example.kz", full_name="Касымова Айжан")
    profile = TeacherProfile.objects.create(user=user, room="305")
    profile.subjects.set([subjects["eng"]])
    return user


@pytest.fixture
def pupils(boston, chicago, make_user) -> dict[str, Student]:
    """Три ученика BOSTON (у первого — учётная запись) и один CHICAGO."""
    return {
        "aliya": make_student(boston, "Ахметова", "Алия", "aliya@example.kz", make_user=make_user),
        "damir": make_student(boston, "Сериков", "Дамир", "damir@example.kz"),
        "nurai": make_student(boston, "Абдрахман", "Нурай", "nurai@example.kz"),
        "stranger": make_student(chicago, "Чужестранцев", "Ерлан", "stranger@example.kz"),
    }


@pytest.fixture
def parent(pupils) -> ParentContact:
    return ParentContact.objects.create(
        student=pupils["aliya"],
        full_name="Ахметова Гульнара",
        relation=ContactRelation.MOTHER,
        phone="8 707 123 45 67",
        is_primary=True,
    )


@pytest.fixture
def cohorts(boston, chicago, pupils, subjects):
    """Составы: вся BOSTON, вся CHICAGO, две подгруппы английского BOSTON."""
    eng1, eng2 = split_group(
        group=boston,
        subject=subjects["eng"],
        parts=[[pupils["aliya"].pk, pupils["damir"].pk], [pupils["nurai"].pk]],
        since=days(-60),
        rule="по уровню",
    )
    return {"boston": group_cohort(boston), "chicago": group_cohort(chicago), "eng1": eng1, "eng2": eng2}


@pytest.fixture
def lesson(year, subjects, teacher, cohorts, calendar):
    """Прошедший урок алгебры BOSTON два учебных дня назад (внутри окна правки)."""
    return create_once(
        subject=subjects["alg"],
        teacher=teacher,
        cohort=cohorts["boston"],
        date=school_day(-2, calendar),
        slot=2,
        room="204",
    )


@pytest.fixture
def eng_lesson(year, subjects, other_teacher, cohorts, calendar):
    """Прошедший урок английского первой подгруппы BOSTON."""
    return create_once(
        subject=subjects["eng"],
        teacher=other_teacher,
        cohort=cohorts["eng1"],
        date=school_day(-2, calendar),
        slot=3,
        room="305",
    )


def login(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def as_teacher(teacher) -> APIClient:
    return login(teacher)


@pytest.fixture
def as_curator(curator) -> APIClient:
    return login(curator)


@pytest.fixture
def as_admin(admin) -> APIClient:
    return login(admin)


@pytest.fixture
def as_kymbat(kymbat) -> APIClient:
    return login(kymbat)


@pytest.fixture
def as_student(pupils) -> APIClient:
    return login(pupils["aliya"].user)


@pytest.fixture
def marked_journal(year, subjects, teacher, other_teacher, cohorts, calendar, pupils):
    """Три прошедших урока алгебры BOSTON у учителя и урок английского CHICAGO у другого.

    Алия на всех уроках, у неё ФО 2 — четвертная выходит ниже порога.
    Дамир не был ни разу — посещаемость ниже порога. Нурай была везде,
    но без оценок. Чужестранцев (CHICAGO) не был на уроке другого учителя:
    учителю алгебры он чужой — ни в одной кнопке его быть не должно.
    """
    from academics.models import Attendance, Grade, Lesson

    now = timezone.now()
    lessons = []
    for slot, back in ((4, -1), (5, -2), (6, -3)):
        lesson = create_once(
            subject=subjects["alg"],
            teacher=teacher,
            cohort=cohorts["boston"],
            date=school_day(back, calendar),
            slot=slot,
            room="204",
        )
        Attendance.objects.create(lesson=lesson, student=pupils["damir"], mark="absent")
        Grade.objects.create(lesson=lesson, student=pupils["aliya"], value=2, created_by=teacher)
        lessons.append(lesson)
    foreign = create_once(
        subject=subjects["eng"],
        teacher=other_teacher,
        cohort=cohorts["chicago"],
        date=school_day(-1, calendar),
        slot=7,
        room="305",
    )
    Attendance.objects.create(lesson=foreign, student=pupils["stranger"], mark="absent")
    Lesson.objects.filter(pk__in=[lesson.pk for lesson in [*lessons, foreign]]).update(marked_at=now)
    return {"own": lessons, "foreign": foreign}
