"""Посев учебной части для разработки — исключение по решению владельца (25.09.2026).

Вымышленная школа как в референсе: 11 групп по 16–18 учеников, подгруппы
английского (по уровню) и информатики (пополам), потоки физкультуры, IELTS
и SAT, учителя, расписание на год, сентябрь с отметками и оценками, родители
с телефонами без почты. Все записи помечены `is_fictional` и уходят
`purge_fictional`. Работает только при `DEBUG=1` и отказывается, если
в базе есть настоящие ученики.
"""

from __future__ import annotations

import datetime as dt
import random

from django.db import transaction
from django.utils import timezone

from academics import calendar as school_calendar
from academics.cohorts import group_cohort, make_stream, member_ids, split_group
from academics.models import (
    AcademicYear,
    Attendance,
    Bell,
    Break,
    Cohort,
    Excuse,
    Grade,
    GradingScale,
    Holiday,
    Lesson,
    LessonKind,
    LessonStatus,
    Quarter,
    ReportSettings,
    Scheme,
    Subject,
    TeacherProfile,
)
from academics.schedule import create_weekly
from accounts.models import Identity, IdentityProvider, Role, User
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

FICTIONAL_DOMAIN = "fictional.local"

GROUPS = (
    "BOSTON",
    "CHICAGO",
    "SEOUL",
    "MIT",
    "TOKYO",
    "CAMBRIDGE",
    "STANFORD",
    "OXFORD",
    "MILANO",
    "HARVARD",
    "AMSTERDAM",
)
PAIRS = (
    ("BOSTON", "CHICAGO"),
    ("SEOUL", "MIT"),
    ("TOKYO", "CAMBRIDGE"),
    ("STANFORD", "OXFORD"),
    ("MILANO", "HARVARD"),
    ("AMSTERDAM",),
)
BLOCK_1 = ("BOSTON", "SEOUL", "MIT", "CHICAGO")
BLOCK_2 = ("TOKYO", "CAMBRIDGE", "STANFORD", "OXFORD")

#: код, название, короткое, часов в неделю, схема, максимум СОР, максимум СОЧ
SUBJECTS = (
    ("alg", "Алгебра", "Алгебра", 3, Scheme.KZ, 20, 30),
    ("geo", "Геометрия", "Геометрия", 2, Scheme.KZ, 15, 25),
    ("phy", "Физика", "Физика", 2, Scheme.KZ, 15, 25),
    ("chem", "Химия", "Химия", 2, Scheme.KZ, 15, 25),
    ("bio", "Биология", "Биология", 2, Scheme.KZ, 15, 25),
    ("eng", "Английский язык", "Английский", 3, Scheme.KZ, 15, 25),
    ("kaz", "Казахский язык и литература", "Каз. язык и лит.", 3, Scheme.KZ, 15, 25),
    ("rus", "Русский язык и литература", "Рус. язык и лит.", 2, Scheme.KZ, 15, 25),
    ("hkz", "История Казахстана", "История РК", 2, Scheme.KZ, 15, 25),
    ("hw", "Всемирная история", "Всемирн. история", 1, Scheme.KZ, 15, 20),
    ("gg", "География", "География", 1, Scheme.KZ, 15, 20),
    ("inf", "Информатика", "Информатика", 2, Scheme.KZ, 15, 25),
    ("pe", "Физкультура", "Физкультура", 2, Scheme.FO, 10, 10),
    ("ielts", "IELTS", "IELTS", 2, Scheme.FO, 10, 10),
    ("sat", "SAT Math", "SAT Math", 1, Scheme.FO, 10, 10),
)

#: фамилия, имя, предметы, кабинет
TEACHERS = (
    ("Касымова", "Айжан", ("eng", "ielts"), "305"),
    ("Ким", "Мария", ("eng", "ielts"), "306"),
    ("Ли", "Елена", ("eng", "ielts"), "307"),
    ("Оразбаева", "Жулдыз", ("eng",), "308"),
    ("Сапарова", "Гульнара", ("alg", "geo"), ""),
    ("Досмухамедов", "Ерлан", ("phy",), "110"),
    ("Абдиева", "Жанар", ("chem",), "112"),
    ("Сеитова", "Раушан", ("bio",), "114"),
    ("Омарова", "Динара", ("kaz",), ""),
    ("Петрова", "Светлана", ("rus",), ""),
    ("Тлеубаев", "Нуржан", ("hkz", "hw"), ""),
    ("Жаксылыкова", "Самал", ("gg",), ""),
    ("Ахметов", "Тимур", ("inf",), "118"),
    ("Нурпеисова", "Алия", ("inf",), "119"),
    ("Абенов", "Бауыржан", ("pe",), "Спортзал"),
    ("Ибраев", "Руслан", ("sat",), "214"),
    ("Бекмуханова", "Гаухар", ("alg", "geo"), ""),
    ("Искаков", "Марат", ("alg", "geo"), ""),
    ("Садыкова", "Лаура", ("phy",), "210"),
    ("Есенова", "Айсулу", ("phy",), "310"),
    ("Кенжебаев", "Ардак", ("chem",), "212"),
    ("Мамырова", "Эльмира", ("chem",), "312"),
    ("Нуртаев", "Берик", ("bio",), "214"),
    ("Рахимова", "Зульфия", ("bio",), "314"),
    ("Смагулова", "Индира", ("kaz",), ""),
    ("Утепов", "Даурен", ("kaz",), ""),
    ("Шарипова", "Мадина", ("rus",), ""),
    ("Турсынова", "Гульмира", ("rus",), ""),
    ("Жанибеков", "Серик", ("hkz", "hw"), ""),
    ("Мухамеджанов", "Олжас", ("hkz", "hw"), ""),
    ("Сарсенбаева", "Айнур", ("gg",), ""),
    ("Ткаченко", "Ольга", ("eng",), "309"),
    ("Хамитов", "Азамат", ("eng",), "310"),
    ("Оразова", "Жанна", ("eng", "ielts"), "311"),
    ("Дюсенова", "Карлыгаш", ("eng", "ielts"), "312"),
    ("Серикбаев", "Нурлан", ("inf",), "218"),
    ("Ермекова", "Галия", ("inf",), "219"),
    ("Абишев", "Канат", ("pe",), "Спортзал 2"),
    ("Иманбаева", "Светлана", ("sat",), "215"),
)

CURATORS = (
    ("Асель", "Нурланова", ("BOSTON", "CHICAGO", "SEOUL")),
    ("Акбота", "Сейдахметова", ("MIT", "TOKYO")),
    ("Айдана", "Касенова", ("CAMBRIDGE", "STANFORD")),
    ("Фарангиз", "Юсупова", ("OXFORD", "MILANO")),
    ("Сурия", "Ахметжанова", ("HARVARD", "AMSTERDAM")),
)

FIRST_NAMES = (
    "Айгерим",
    "Алия",
    "Аяулым",
    "Дана",
    "Диана",
    "Жанель",
    "Камила",
    "Мадина",
    "Нурай",
    "Сабина",
    "Томирис",
    "Улжан",
    "Алихан",
    "Арман",
    "Бекзат",
    "Данияр",
    "Ербол",
    "Ислам",
    "Мирас",
    "Нурсултан",
    "Санжар",
    "Тимур",
    "Ерасыл",
    "Жандос",
)
LAST_NAMES = (
    "Ахметова",
    "Бекова",
    "Жумабаева",
    "Каирова",
    "Мухтар",
    "Нурланова",
    "Оспанова",
    "Сериккызы",
    "Толегенова",
    "Абдрахман",
    "Сериков",
    "Тлеубаев",
    "Абдуллин",
    "Байжанов",
    "Ермеков",
    "Жаксыбеков",
    "Кенжебаев",
    "Мусин",
    "Нуртазин",
    "Сагындыков",
)

TOPICS = {
    "eng": (
        "Education systems around the world",
        "Reading: studying abroad",
        "Present perfect vs past simple",
        "Writing an opinion essay",
        "Listening: campus life",
        "Vocabulary: university subjects",
        "Speaking: describing plans",
        "Conditionals review",
    ),
    "ielts": (
        "Listening Section 1–2",
        "Reading: True / False / Not Given",
        "Writing Task 1: линейный график",
        "Speaking Part 2: карточка",
        "Reading: Matching headings",
    ),
    "alg": (
        "Производная функции",
        "Правила дифференцирования",
        "Производная сложной функции",
        "Касательная к графику",
        "Экстремумы функции",
        "Первообразная",
    ),
    "geo": ("Векторы в пространстве", "Координаты вектора", "Скалярное произведение", "Уравнение плоскости"),
    "phy": ("Электромагнитная индукция", "Самоиндукция", "Переменный ток", "Трансформатор", "Колебательный контур"),
}
HOMEWORK = (
    "Упр. 4–6 на с. 32",
    "Эссе 180 слов",
    "Прочитать текст на с. 40",
    "Тест 2 из сборника",
    "Подготовить рассказ на 2 минуты",
)

BREAKS = (
    ("Осенние каникулы", "2026-10-26", "2026-11-01"),
    ("Зимние каникулы", "2026-12-28", "2027-01-10"),
    ("Весенние каникулы", "2027-03-20", "2027-03-29"),
)
QUARTERS = (
    (1, "2026-09-01", "2026-10-23"),
    (2, "2026-11-02", "2026-12-25"),
    (3, "2027-01-11", "2027-03-19"),
    (4, "2027-03-30", "2027-05-25"),
)


class SeedRefused(RuntimeError):
    """Сеять нельзя — текст объясняет почему."""


def _date(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


def _translit(text: str) -> str:
    from core.exports import TRANSLIT

    return text.lower().translate(TRANSLIT).replace(" ", "")


@transaction.atomic
def seed(*, password: str = "", actor=None) -> dict:
    """Посеять всё. Настоящие ученики в базе — отказ."""
    from django.conf import settings

    if not settings.DEBUG:
        raise SeedRefused("Посев работает только при DEBUG=1")
    if Student.all_objects.filter(is_fictional=False).exists():
        raise SeedRefused("В базе есть настоящие ученики: посев для разработки отказывается")
    rng = random.Random(20260925)
    year = _year()
    subjects = _subjects()
    teachers = _teachers(subjects, password)
    groups = {code: StudyGroup.objects.get_or_create(code=code, defaults={"grade": 11})[0] for code in GROUPS}
    students = _students(groups, rng)
    _curators(groups, password)
    _review_accounts(students, password)
    cohorts = _cohorts(groups, students, subjects, rng)
    calendar = school_calendar.load(year)
    series_count = _schedule(groups, cohorts, subjects, teachers, calendar, rng, actor)
    marked = _september(calendar, rng, teachers)
    return {
        "groups": len(groups),
        "students": sum(len(v) for v in students.values()),
        "teachers": len(teachers),
        "series": series_count,
        "lessons": Lesson.objects.count(),
        "marked": marked,
    }


def _year() -> AcademicYear:
    year = AcademicYear.objects.filter(is_current=True).first()
    if year is None:
        year = AcademicYear.objects.create(
            title="2026–2027", starts=_date("2026-09-01"), ends=_date("2027-05-25"), is_current=True, is_fictional=True
        )
    for number, starts, ends in QUARTERS:
        Quarter.objects.get_or_create(
            year=year,
            number=number,
            defaults={"title": f"{number} четверть", "starts": _date(starts), "ends": _date(ends)},
        )
    for title, starts, ends in BREAKS:
        Break.objects.get_or_create(year=year, title=title, defaults={"starts": _date(starts), "ends": _date(ends)})
    Holiday.objects.get_or_create(year=year, date=_date("2026-12-16"), defaults={"title": "День Независимости"})
    if not year.bells.exists():
        for number, starts, ends in school_calendar.DEFAULT_BELLS:
            Bell.objects.create(
                year=year, number=number, starts=dt.time.fromisoformat(starts), ends=dt.time.fromisoformat(ends)
            )
    GradingScale.objects.get_or_create(year=year)
    ReportSettings.objects.get_or_create(year=year)
    return year


def _subjects() -> dict[str, Subject]:
    out = {}
    for order, (code, title, short, _hours, scheme, sor, soch) in enumerate(SUBJECTS):
        out[code], _ = Subject.objects.update_or_create(
            code=code,
            defaults={
                "title": title,
                "short_title": short,
                "scheme": scheme,
                "sor_max": sor,
                "soch_max": soch,
                "order": order,
                "is_fictional": True,
            },
        )
    return out


def _user(email: str, full_name: str, role: str, password: str) -> User:
    user, _ = User.objects.get_or_create(email=email, defaults={"role": role, "full_name": full_name})
    user.role = role
    user.full_name = full_name
    user.is_fictional = True
    user.is_active = True
    user.must_change_password = False
    if password:
        user.set_password(password)
    elif not user.has_usable_password():
        user.set_unusable_password()
    user.save()
    Identity.objects.get_or_create(
        provider=IdentityProvider.PASSWORD, email=email, defaults={"user": user, "is_primary": True}
    )
    return user


def _teachers(subjects: dict[str, Subject], password: str) -> dict[str, User]:
    out = {}
    for last, first, codes, room in TEACHERS:
        email = f"{_translit(first)}_{_translit(last)}@{FICTIONAL_DOMAIN}"
        user = _user(email, f"{last} {first}", Role.TEACHER, password)
        profile, _ = TeacherProfile.objects.get_or_create(user=user)
        profile.room = room
        profile.is_fictional = True
        profile.save()
        profile.subjects.set([subjects[c] for c in codes])
        out[last] = user
    return out


def _curators(groups: dict[str, StudyGroup], password: str) -> None:
    from accounts.curators import AssignmentRefused, assign

    for first, last, codes in CURATORS:
        user = _user(
            f"{_translit(first)}_{_translit(last)}@{FICTIONAL_DOMAIN}", f"{last} {first}", Role.CURATOR, password
        )
        for code in codes:
            try:
                assign(group=groups[code], curator=user, since=_date("2026-09-01"))
            except AssignmentRefused:
                pass


#: учётные записи для просмотра владельцем: пять директоров и один ученик
REVIEW_STAFF = (
    ("saltanat", Role.DIRECTOR_BEHAVIOR, "Салтанат Посев"),
    ("asem", Role.DIRECTOR_ADMISSION, "Асем Посев"),
    ("kymbat", Role.DIRECTOR_EXAM, "Кымбат Посев"),
    ("arman", Role.DIRECTOR_TALENT, "Арман Посев"),
    ("nurlybek", Role.DIRECTOR_SPORT, "Нурлыбек Посев"),
)


def _review_accounts(students: dict[str, list[Student]], password: str) -> None:
    """Директора и один ученик посева — чтобы владелец мог пройти по экранам всех ролей.

    Ученик привязывается к первой карточке BOSTON по её почте; без пароля
    вход закрыт, как и остальным записям посева.
    """
    from students.linking import link_user

    for local, role, full_name in REVIEW_STAFF:
        user = _user(f"{local}@{FICTIONAL_DOMAIN}", full_name, role, password)
        user.sees_whole_school = role == Role.DIRECTOR_BEHAVIOR
        user.save(update_fields=["sees_whole_school"])
    first = next((row for rows in students.values() for row in rows), None)
    if first is not None:
        pupil = _user(first.email, f"{first.last_name} {first.first_name}", Role.STUDENT, password)
        link_user(pupil)


def _students(groups: dict[str, StudyGroup], rng: random.Random) -> dict[str, list[Student]]:
    out: dict[str, list[Student]] = {}
    counter = 0
    for code, group in groups.items():
        rows = []
        size = 16 + (counter % 3)
        for _i in range(size):
            counter += 1
            first = rng.choice(FIRST_NAMES)
            last = rng.choice(LAST_NAMES)
            email = f"{_translit(first)}.{_translit(last)}.{counter}@{FICTIONAL_DOMAIN}"
            student, created = Student.objects.get_or_create(
                email=email,
                defaults={
                    "last_name": last,
                    "first_name": first,
                    "grade": 11,
                    "group": group,
                    "graduation_year": 2027,
                    "is_fictional": True,
                },
            )
            if created:
                for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
                    model.objects.get_or_create(student=student)
                level = rng.random()
                ExamProfile.objects.filter(student=student).update(
                    ielts_current=round(4.5 + level * 3 * 2) / 2 if rng.random() < 0.7 else None
                )
                ParentContact.objects.create(
                    student=student,
                    full_name=f"{last if last.endswith('а') else last + 'а'} Гульнара",
                    relation=ContactRelation.MOTHER,
                    phone=f"+7 7{rng.randint(0, 7)}{rng.randint(1000000, 9999999)}",
                    is_primary=True,
                )
                if rng.random() < 0.6:
                    ParentContact.objects.create(
                        student=student,
                        full_name=f"{last.rstrip('а')} Ерлан",
                        relation=ContactRelation.FATHER,
                        phone=f"8 7{rng.randint(0, 7)}{rng.randint(1000000, 9999999)}",
                    )
            rows.append(student)
        out[code] = rows
    return out


def _cohorts(groups, students, subjects, rng) -> dict[str, Cohort]:
    """Группы, подгруппы английского и информатики, потоки физкультуры, IELTS и SAT."""
    out: dict[str, Cohort] = {}
    since = _date("2026-09-01")
    for code, group in groups.items():
        out[code] = group_cohort(group)
        out[code].is_fictional = True
        out[code].save(update_fields=["is_fictional"])
        rows = students[code]
        if code != "MIT":
            by_level = sorted(rows, key=lambda s: (-(float(s.exam.ielts_current or 0)), s.last_name))
            half = (len(by_level) + 1) // 2
            eng = split_group(
                group=group,
                subject=subjects["eng"],
                parts=[[s.pk for s in by_level[:half]], [s.pk for s in by_level[half:]]],
                since=since,
                rule="по уровню английского",
            )
            for index, cohort in enumerate(eng, start=1):
                cohort.is_fictional = True
                cohort.save(update_fields=["is_fictional"])
                out[f"{code}:eng{index}"] = cohort
        by_name = sorted(rows, key=lambda s: (s.last_name, s.first_name))
        half = (len(by_name) + 1) // 2
        inf = split_group(
            group=group,
            subject=subjects["inf"],
            parts=[[s.pk for s in by_name[:half]], [s.pk for s in by_name[half:]]],
            since=since,
            rule="по списку пополам",
        )
        for index, cohort in enumerate(inf, start=1):
            cohort.is_fictional = True
            cohort.save(update_fields=["is_fictional"])
            out[f"{code}:inf{index}"] = cohort
    for pair in PAIRS:
        if len(pair) > 1:
            stream = make_stream(name=" + ".join(pair), parts=[out[p] for p in pair])
            stream.is_fictional = True
            stream.save(update_fields=["is_fictional"])
            out[f"P:{'+'.join(pair)}"] = stream
    a = make_stream(name="Поток A · BOSTON 1 + CHICAGO 1", parts=[out["BOSTON:eng1"], out["CHICAGO:eng1"]])
    b = make_stream(name="Поток B · BOSTON 2 + CHICAGO 2", parts=[out["BOSTON:eng2"], out["CHICAGO:eng2"]])
    for stream, key in ((a, "P:ielts-a"), (b, "P:ielts-b")):
        stream.is_fictional = True
        stream.save(update_fields=["is_fictional"])
        out[key] = stream
    return out


def _block(code: str) -> int:
    return 0 if code in BLOCK_1 else 1 if code in BLOCK_2 else 2


def _schedule(groups, cohorts, subjects, teachers, calendar, rng, actor) -> int:
    """Раскладка по сетке: сначала пары, потом подгруппы, потом остальное.

    Повторный посев расписание не удваивает: если у составов посева уроки
    уже есть, раскладка пропускается.
    """
    if Lesson.objects.filter(course__cohort__is_fictional=True).exists():
        return 0
    subject_teachers = {
        "alg": ("Сапарова", "Бекмуханова", "Искаков"),
        "geo": ("Сапарова", "Бекмуханова", "Искаков"),
        "phy": ("Досмухамедов", "Садыкова", "Есенова"),
        "chem": ("Абдиева", "Кенжебаев", "Мамырова"),
        "bio": ("Сеитова", "Нуртаев", "Рахимова"),
        "kaz": ("Омарова", "Смагулова", "Утепов"),
        "rus": ("Петрова", "Шарипова", "Турсынова"),
        "hkz": ("Тлеубаев", "Жанибеков", "Мухамеджанов"),
        "hw": ("Тлеубаев", "Жанибеков", "Мухамеджанов"),
        "gg": ("Жаксылыкова", "Жаксылыкова", "Сарсенбаева"),
    }
    eng_pairs = {
        "BOSTON": ("Касымова", "Ким"),
        "CHICAGO": ("Касымова", "Ким"),
        "SEOUL": ("Ли", "Ким"),
        "MIT": ("Касымова",),
    }

    def eng_teachers(code):
        return eng_pairs.get(code) or (("Ткаченко", "Хамитов") if _block(code) == 1 else ("Оразова", "Дюсенова"))

    def inf_teachers(code):
        return ("Ахметов", "Нурпеисова") if _block(code) == 0 else ("Серикбаев", "Ермекова")

    rooms = {code: str(201 + index) for index, code in enumerate(GROUPS)}

    def room_of(teacher_last, code):
        room = TeacherProfile.objects.get(user=teachers[teacher_last]).room
        return room or rooms[code]

    units: list[dict] = []

    def unit(group_codes, subject_code, lessons):
        units.append({"groups": tuple(group_codes), "subject": subject_code, "lessons": lessons})

    for pair in PAIRS:
        pid = f"P:{'+'.join(pair)}" if len(pair) > 1 else pair[0]
        pe = "Абенов" if _block(pair[0]) == 0 else "Абишев"
        sat = "Ибраев" if _block(pair[0]) == 0 else "Иманбаева"
        for _i in range(2):
            unit(pair, "pe", [("pe", pe, pid, room_of(pe, pair[0]))])
        unit(pair, "sat", [("sat", sat, pid, room_of(sat, pair[0]))])
        for _i in range(2):
            if pair[0] == "BOSTON":
                unit(pair, "ielts", [("ielts", "Касымова", "P:ielts-a", "305"), ("ielts", "Ким", "P:ielts-b", "306")])
            elif pair[0] == "SEOUL":
                unit(pair, "ielts", [("ielts", "Ли", pid, "307")])
            else:
                who = "Оразова" if _block(pair[0]) == 1 else "Дюсенова"
                unit(pair, "ielts", [("ielts", who, pid, room_of(who, pair[0]))])
    for code in GROUPS:
        et = eng_teachers(code)
        for _i in range(3):
            if len(et) == 1:
                unit((code,), "eng", [("eng", et[0], code, room_of(et[0], code))])
            else:
                unit(
                    (code,),
                    "eng",
                    [
                        ("eng", et[0], f"{code}:eng1", room_of(et[0], code)),
                        ("eng", et[1], f"{code}:eng2", room_of(et[1], code)),
                    ],
                )
        it = inf_teachers(code)
        for _i in range(2):
            unit(
                (code,),
                "inf",
                [
                    ("inf", it[0], f"{code}:inf1", room_of(it[0], code)),
                    ("inf", it[1], f"{code}:inf2", room_of(it[1], code)),
                ],
            )
        for subject_code, _t, _s, hours, _sch, _a, _b in SUBJECTS:
            if subject_code in subject_teachers:
                who = subject_teachers[subject_code][_block(code)]
                for _i in range(hours):
                    unit((code,), subject_code, [(subject_code, who, code, room_of(who, code))])

    busy_group: set[tuple[str, int, int]] = set()
    busy_teacher: set[tuple[str, int, int]] = set()
    per_day: dict[tuple[str, int], int] = {}
    order = (
        [u for u in units if len(u["groups"]) > 1]
        + [u for u in units if len(u["groups"]) == 1 and len(u["lessons"]) > 1]
        + [u for u in units if len(u["groups"]) == 1 and len(u["lessons"]) == 1]
    )
    placed = 0
    week_monday = _date("2026-08-31")
    for u in order:
        days = sorted(range(1, 6), key=lambda wd: (max(per_day.get((g, wd), 0) for g in u["groups"]), rng.random()))
        done = False
        for max_slot in (6, 7, 8):
            for wd in days:
                for slot in range(1, max_slot + 1):
                    if any((g, wd, slot) in busy_group for g in u["groups"]) or any(
                        (t, wd, slot) in busy_teacher for _s, t, _c, _r in u["lessons"]
                    ):
                        continue
                    for g in u["groups"]:
                        busy_group.add((g, wd, slot))
                        per_day[(g, wd)] = per_day.get((g, wd), 0) + 1
                    for subject_code, teacher_last, cohort_key, room in u["lessons"]:
                        busy_teacher.add((teacher_last, wd, slot))
                        starts = week_monday + dt.timedelta(days=wd - 1)
                        # первая учебная неделя начинается 1 сентября (вторник); понедельник — 7 сентября
                        if not calendar.is_school_day(starts):
                            starts += dt.timedelta(days=7)
                        create_weekly(
                            subject=subjects[subject_code],
                            teacher=teachers[teacher_last],
                            cohort=cohorts[cohort_key],
                            starts=starts,
                            slot=slot,
                            room=room,
                            calendar=calendar,
                            actor=actor,
                        )
                        placed += 1
                    done = True
                    break
                if done:
                    break
            if done:
                break
    return placed


def _september(calendar, rng, teachers) -> int:
    """Прошедшие уроки: отметки, оценки, темы, СОР и СОЧ, пара неотмеченных.

    Повторный посев отметки не трогает: они уже стоят, и второй раз
    строки уроков не пишутся.
    """
    if Attendance.objects.filter(lesson__course__cohort__is_fictional=True).exists():
        return 0
    day = school_calendar.today()
    now = timezone.now()
    lessons = list(
        Lesson.objects.filter(date__lte=day, status=LessonStatus.PLANNED)
        .select_related("course", "course__subject", "course__cohort")
        .order_by("date", "slot")
    )
    levels: dict[int, float] = {}
    for student in Student.objects.filter(is_fictional=True).select_related("exam"):
        levels[student.pk] = 0.45 + rng.random() * 0.5
    by_course: dict[int, list[Lesson]] = {}
    for lesson in lessons:
        by_course.setdefault(lesson.course_id, []).append(lesson)
    for rows in by_course.values():
        course = rows[0].course
        topics = TOPICS.get(course.subject.code)
        for index, lesson in enumerate(rows):
            lesson.topic = topics[index % len(topics)] if topics else f"{course.subject.short_title}: тема {index + 1}"
            if course.subject.code == "eng" and rng.random() < 0.7:
                lesson.homework = rng.choice(HOMEWORK)
            lesson.save(update_fields=["topic", "homework"])
        if course.subject.scheme != Scheme.KZ:
            continue
        for start, kind, number, maximum in (
            ("2026-09-14", LessonKind.SOR, 1, course.subject.sor_max),
            ("2026-10-05", LessonKind.SOR, 2, course.subject.sor_max),
            ("2026-10-19", LessonKind.SOCH, 1, course.subject.soch_max),
        ):
            target = next(
                (row for row in Lesson.objects.filter(course=course, date__gte=_date(start)).order_by("date")), None
            )
            if target is not None and target.kind == LessonKind.FO:
                target.kind, target.number, target.max_score = kind, number, maximum
                target.topic = (
                    "Суммативное оценивание за четверть"
                    if kind == LessonKind.SOCH
                    else f"Суммативное оценивание за раздел {number}"
                )
                target.save(update_fields=["kind", "number", "max_score", "topic"])
    marked = 0
    skip_every = 0
    ill: dict[int, tuple[dt.date, dt.date]] = {}
    sample = list(levels)
    rng.shuffle(sample)
    for sid in sample[:6]:
        starts = _date("2026-09-14") + dt.timedelta(days=rng.randint(0, 8))
        ill[sid] = (starts, starts + dt.timedelta(days=2))
    for sid, (starts, ends) in list(ill.items())[:3]:
        Excuse.objects.create(student_id=sid, starts=starts, ends=ends, reason="Болезнь", document="certificate")
    for lesson in (
        Lesson.objects.filter(date__lte=day, status=LessonStatus.PLANNED)
        .select_related("course", "course__subject", "course__cohort")
        .order_by("date", "slot")
    ):
        if not calendar.lesson_finished(lesson.date, lesson.slot):
            continue
        skip_every += 1
        if skip_every % 47 == 0 and lesson.date >= day - dt.timedelta(days=6):
            continue  # забытая отметка: куратор увидит «не отмечен»
        ids = member_ids(lesson.course.cohort, lesson.date)
        attendance = []
        grades = []
        for sid in ids:
            level = levels.get(sid, 0.6)
            sick = ill.get(sid)
            absent = bool(sick and sick[0] <= lesson.date <= sick[1]) or rng.random() < 0.04
            if absent:
                attendance.append(Attendance(lesson=lesson, student_id=sid, mark="absent"))
                continue
            if rng.random() < 0.03:
                attendance.append(Attendance(lesson=lesson, student_id=sid, mark="late"))
            if lesson.kind != LessonKind.FO:
                value = max(
                    1,
                    min(
                        lesson.max_score or 10, round((lesson.max_score or 10) * (level + (rng.random() - 0.5) * 0.25))
                    ),
                )
                grades.append(Grade(lesson=lesson, student_id=sid, value=value, created_by=lesson.teacher))
            elif rng.random() < 0.3:
                value = max(2, min(10, round(10 * level + (rng.random() - 0.5) * 3)))
                grades.append(Grade(lesson=lesson, student_id=sid, value=value, created_by=lesson.teacher))
        Attendance.objects.bulk_create(attendance)
        Grade.objects.bulk_create(grades)
        lesson.marked_at = now
        lesson.marked_by = lesson.teacher
        lesson.save(update_fields=["marked_at", "marked_by"])
        marked += 1
    return marked


# --- Учебная часть для браузерного прогона ---------------------------------------------

#: почта учителя прогона — та же, что в `accounts/probe.py`
PROBE_TEACHER = "teacher@probe.local"
#: второй учитель прогона: чужие уроки в расписании, чтобы у учителя прогона были не все
PROBE_OTHER = "teacher2@probe.local"
#: предметы группам прогона: (код, чей учитель, уроков в неделю)
PROBE_PLAN = (("alg", PROBE_TEACHER, 3), ("phy", PROBE_TEACHER, 2), ("eng", PROBE_OTHER, 3), ("hkz", PROBE_OTHER, 2))


def seed_probe(*, actor=None) -> dict:
    """Год, предметы, составы и недельное расписание для групп прогона.

    Учеников не заводит: их сеет сценарий через API. Повторный запуск
    на живой базе ничего не дублирует — уроки заводятся только там,
    где у группы их ещё нет.
    """
    from django.conf import settings

    if not settings.DEBUG:
        raise SeedRefused("Посев работает только при DEBUG=1")
    teacher = User.objects.filter(email=PROBE_TEACHER, role=Role.TEACHER).first()
    if teacher is None:
        raise SeedRefused("Учётной записи учителя прогона нет: сначала create_probe_users")
    year = _year()
    subjects = _subjects()
    calendar = school_calendar.load(year)
    other = _user(PROBE_OTHER, "Прогон Второй учитель", Role.TEACHER, "")
    staff = {PROBE_TEACHER: teacher, PROBE_OTHER: other}
    for user, codes, room in ((teacher, ("alg", "phy"), "204"), (other, ("eng", "hkz"), "305")):
        profile, _ = TeacherProfile.objects.get_or_create(user=user)
        profile.room = room
        profile.is_fictional = True
        profile.save()
        profile.subjects.set([subjects[c] for c in codes])
    groups = list(StudyGroup.objects.filter(is_active=True, archived_at__isnull=True).order_by("code"))
    placed = 0
    week_monday = school_calendar.week_start(school_calendar.today())
    for index, group in enumerate(groups):
        cohort = group_cohort(group)
        cohort.is_fictional = True
        cohort.save(update_fields=["is_fictional"])
        if Lesson.objects.filter(course__cohort=cohort).exists():
            continue
        slot = 1
        for code, email, hours in PROBE_PLAN:
            for hour in range(hours):
                weekday = (index + hour * 2 + slot) % 5
                starts = week_monday + dt.timedelta(days=weekday) - dt.timedelta(days=21)
                while not calendar.is_school_day(starts):
                    starts += dt.timedelta(days=1)
                create_weekly(
                    subject=subjects[code],
                    teacher=staff[email],
                    cohort=cohort,
                    starts=starts,
                    slot=(slot % 6) + 1,
                    room="204" if email == PROBE_TEACHER else "305",
                    calendar=calendar,
                    actor=actor,
                )
                placed += 1
                slot += 1
    return {"groups": len(groups), "subjects": len(subjects), "series": placed, "lessons": Lesson.objects.count()}
