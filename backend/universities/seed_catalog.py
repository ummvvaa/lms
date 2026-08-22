"""Стартовый справочник: 20 вузов, куда обычно поступают выпускники.

Это заготовка, а не проверенные данные. Пороги и дедлайны собраны как
ориентир, поэтому каждая запись помечается `data_source=seed` и
`is_verified=False` — в интерфейсе над ней висит оранжевая плашка
(инвариант №14). Снять признак вправе только директор по поступлению,
сверившись с сайтом вуза.

Записи, заведённые школой, к этому набору не относятся: «удалить
стартовый справочник» убирает ровно `data_source=seed`.
"""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.db.models import ProtectedError

from universities.models import (
    AdmissionRequirement,
    AdmissionRound,
    CatalogSource,
    Program,
    StudentUniversity,
    University,
)

#: Дедлайны заданы днём и месяцем: год подставляется ближайший будущий,
#: иначе стартовый справочник с первого дня выглядел бы просроченным.
SEED: tuple[dict, ...] = (
    {
        "name": "University of Toronto",
        "country": "Канада",
        "website": "https://www.utoronto.ca",
        "domain": "utoronto.ca",
        "programs": (
            {
                "name": "Computer Science",
                "req": {"min_gpa": 3.7, "min_ielts": 6.5, "min_toefl": 100, "min_sat": 1400},
                "subjects": "Математика, Информатика",
                "rounds": ((1, 15, "RD"),),
            },
            {
                "name": "Economics",
                "req": {"min_gpa": 3.5, "min_ielts": 6.5, "min_toefl": 100},
                "subjects": "Математика",
                "rounds": ((1, 15, "RD"),),
            },
            {
                "name": "Engineering",
                "req": {"min_gpa": 3.7, "min_ielts": 6.5, "min_sat": 1420},
                "subjects": "Математика, Физика, Химия",
                "rounds": ((1, 15, "RD"),),
            },
        ),
    },
    {
        "name": "University of British Columbia",
        "country": "Канада",
        "website": "https://www.ubc.ca",
        "domain": "ubc.ca",
        "programs": (
            {
                "name": "Computer Science",
                "req": {"min_gpa": 3.6, "min_ielts": 6.5, "min_toefl": 90},
                "subjects": "Математика",
                "rounds": ((1, 15, "RD"),),
            },
            {
                "name": "Business Management",
                "req": {"min_gpa": 3.5, "min_ielts": 6.5, "min_toefl": 90},
                "rounds": ((1, 15, "RD"),),
            },
        ),
    },
    {
        "name": "McGill University",
        "country": "Канада",
        "website": "https://www.mcgill.ca",
        "domain": "mcgill.ca",
        "programs": (
            {
                "name": "Mathematics",
                "req": {"min_gpa": 3.5, "min_ielts": 6.5, "min_toefl": 90, "min_sat": 1300},
                "subjects": "Математика",
                "rounds": ((1, 15, "RD"),),
            },
            {
                "name": "Economics",
                "req": {"min_gpa": 3.5, "min_ielts": 6.5, "min_toefl": 90},
                "rounds": ((1, 15, "RD"),),
            },
        ),
    },
    {
        "name": "New York University",
        "country": "США",
        "website": "https://www.nyu.edu",
        "domain": "nyu.edu",
        "programs": (
            {
                "name": "Computer Science",
                "req": {"min_gpa": 3.7, "min_ielts": 7.0, "min_toefl": 100, "min_sat": 1450, "min_act": 32},
                "subjects": "Математика, Информатика",
                "portfolio": False,
                "rounds": ((11, 1, "ED"), (1, 5, "RD")),
            },
            {
                "name": "Business",
                "req": {"min_gpa": 3.7, "min_ielts": 7.0, "min_sat": 1450},
                "rounds": ((11, 1, "ED"), (1, 5, "RD")),
            },
        ),
    },
    {
        "name": "Purdue University",
        "country": "США",
        "website": "https://www.purdue.edu",
        "domain": "purdue.edu",
        "programs": (
            {
                "name": "Engineering",
                "req": {"min_gpa": 3.5, "min_ielts": 6.5, "min_toefl": 88, "min_sat": 1300, "min_act": 28},
                "subjects": "Математика, Физика",
                "rounds": ((11, 1, "EA"), (1, 15, "RD")),
            },
            {
                "name": "Data Science",
                "req": {"min_gpa": 3.5, "min_ielts": 6.5, "min_sat": 1300},
                "subjects": "Математика",
                "rounds": ((1, 15, "RD"),),
            },
        ),
    },
    {
        "name": "Arizona State University",
        "country": "США",
        "website": "https://www.asu.edu",
        "domain": "asu.edu",
        "programs": (
            {
                "name": "Computer Science",
                "req": {"min_gpa": 3.0, "min_ielts": 6.0, "min_toefl": 79, "min_sat": 1120},
                "rounds": ((2, 1, "Rolling"),),
            },
            {
                "name": "Business",
                "req": {"min_gpa": 3.0, "min_ielts": 6.0, "min_toefl": 79},
                "rounds": ((2, 1, "Rolling"),),
            },
        ),
    },
    {
        "name": "University of Manchester",
        "country": "Великобритания",
        "website": "https://www.manchester.ac.uk",
        "domain": "manchester.ac.uk",
        "programs": (
            {
                "name": "Computer Science",
                "req": {"min_ielts": 6.5, "min_toefl": 90},
                "subjects": "Математика",
                "rounds": ((1, 29, "RD"),),
            },
            {
                "name": "Economics",
                "req": {"min_ielts": 6.5, "min_toefl": 90},
                "subjects": "Математика",
                "rounds": ((1, 29, "RD"),),
            },
        ),
    },
    {
        "name": "University of Edinburgh",
        "country": "Великобритания",
        "website": "https://www.ed.ac.uk",
        "domain": "ed.ac.uk",
        "programs": (
            {
                "name": "Computer Science",
                "req": {"min_ielts": 6.5, "min_toefl": 92},
                "subjects": "Математика",
                "rounds": ((1, 29, "RD"),),
            },
            {
                "name": "Mathematics",
                "req": {"min_ielts": 6.5, "min_toefl": 92},
                "subjects": "Математика",
                "rounds": ((1, 29, "RD"),),
            },
        ),
    },
    {
        "name": "King's College London",
        "country": "Великобритания",
        "website": "https://www.kcl.ac.uk",
        "domain": "kcl.ac.uk",
        "programs": (
            {
                "name": "Business Management",
                "req": {"min_ielts": 7.0, "min_toefl": 100},
                "rounds": ((1, 29, "RD"),),
            },
            {
                "name": "Economics",
                "req": {"min_ielts": 7.0, "min_toefl": 100},
                "subjects": "Математика",
                "rounds": ((1, 29, "RD"),),
            },
        ),
    },
    {
        "name": "University of Amsterdam",
        "country": "Нидерланды",
        "website": "https://www.uva.nl",
        "domain": "uva.nl",
        "programs": (
            {
                "name": "Economics",
                "req": {"min_ielts": 6.5, "min_toefl": 92},
                "subjects": "Математика",
                "rounds": ((5, 1, "RD"),),
            },
            {
                "name": "Data Science",
                "req": {"min_ielts": 6.5, "min_toefl": 92},
                "subjects": "Математика",
                "rounds": ((1, 15, "RD"),),
            },
        ),
    },
    {
        "name": "Delft University of Technology",
        "country": "Нидерланды",
        "website": "https://www.tudelft.nl",
        "domain": "tudelft.nl",
        "programs": (
            {
                "name": "Aerospace Engineering",
                "req": {"min_ielts": 6.5, "min_toefl": 90},
                "subjects": "Математика, Физика",
                "rounds": ((1, 15, "RD"),),
            },
            {
                "name": "Computer Science",
                "req": {"min_ielts": 6.5, "min_toefl": 90},
                "subjects": "Математика, Физика",
                "rounds": ((1, 15, "RD"),),
            },
        ),
    },
    {
        "name": "Technical University of Munich",
        "country": "Германия",
        "website": "https://www.tum.de",
        "domain": "tum.de",
        "programs": (
            {
                "name": "Computer Science",
                "req": {"min_ielts": 6.5, "min_toefl": 88},
                "subjects": "Математика, Физика, Информатика",
                "rounds": ((5, 31, "RD"),),
            },
            {
                "name": "Engineering",
                "req": {"min_ielts": 6.5, "min_toefl": 88},
                "subjects": "Математика, Физика",
                "rounds": ((5, 31, "RD"),),
            },
        ),
    },
    {
        "name": "RWTH Aachen University",
        "country": "Германия",
        "website": "https://www.rwth-aachen.de",
        "domain": "rwth-aachen.de",
        "programs": (
            {
                "name": "Engineering",
                "req": {"min_ielts": 6.0, "min_toefl": 80},
                "subjects": "Математика, Физика",
                "rounds": ((7, 15, "RD"),),
            },
            {
                "name": "Computer Science",
                "req": {"min_ielts": 6.0, "min_toefl": 80},
                "subjects": "Математика, Информатика",
                "rounds": ((7, 15, "RD"),),
            },
        ),
    },
    {
        "name": "National University of Singapore",
        "country": "Сингапур",
        "website": "https://www.nus.edu.sg",
        "domain": "nus.edu.sg",
        "programs": (
            {
                "name": "Computer Science",
                "req": {"min_gpa": 3.7, "min_ielts": 6.5, "min_toefl": 92, "min_sat": 1450},
                "subjects": "Математика, Информатика",
                "rounds": ((3, 1, "RD"),),
            },
            {
                "name": "Business",
                "req": {"min_gpa": 3.5, "min_ielts": 6.5, "min_sat": 1400},
                "rounds": ((3, 1, "RD"),),
            },
        ),
    },
    {
        "name": "Nanyang Technological University",
        "country": "Сингапур",
        "website": "https://www.ntu.edu.sg",
        "domain": "ntu.edu.sg",
        "programs": (
            {
                "name": "Engineering",
                "req": {"min_gpa": 3.5, "min_ielts": 6.5, "min_toefl": 90, "min_sat": 1350},
                "subjects": "Математика, Физика",
                "rounds": ((3, 1, "RD"),),
            },
            {
                "name": "Data Science",
                "req": {"min_gpa": 3.6, "min_ielts": 6.5, "min_sat": 1400},
                "subjects": "Математика",
                "rounds": ((3, 1, "RD"),),
            },
        ),
    },
    {
        "name": "Korea University",
        "country": "Южная Корея",
        "website": "https://www.korea.ac.kr",
        "domain": "korea.ac.kr",
        "programs": (
            {
                "name": "Business",
                "req": {"min_gpa": 3.3, "min_ielts": 6.5, "min_toefl": 85},
                "rounds": ((10, 15, "EA"), (3, 15, "RD")),
            },
            {
                "name": "Computer Science",
                "req": {"min_gpa": 3.5, "min_ielts": 6.5, "min_toefl": 85},
                "subjects": "Математика",
                "rounds": ((3, 15, "RD"),),
            },
        ),
    },
    {
        "name": "Yonsei University",
        "country": "Южная Корея",
        "website": "https://www.yonsei.ac.kr",
        "domain": "yonsei.ac.kr",
        "programs": (
            {
                "name": "Economics",
                "req": {"min_gpa": 3.3, "min_ielts": 6.5, "min_toefl": 88},
                "subjects": "Математика",
                "rounds": ((3, 15, "RD"),),
            },
            {
                "name": "Engineering",
                "req": {"min_gpa": 3.4, "min_ielts": 6.5, "min_toefl": 88},
                "subjects": "Математика, Физика",
                "rounds": ((3, 15, "RD"),),
            },
        ),
    },
    {
        "name": "Bilkent University",
        "country": "Турция",
        "website": "https://www.bilkent.edu.tr",
        "domain": "bilkent.edu.tr",
        "programs": (
            {
                "name": "Computer Science",
                "req": {"min_gpa": 3.0, "min_ielts": 6.5, "min_toefl": 87, "min_sat": 1250},
                "subjects": "Математика",
                "rounds": ((6, 30, "Rolling"),),
            },
            {
                "name": "Business",
                "req": {"min_gpa": 3.0, "min_ielts": 6.5, "min_toefl": 87},
                "rounds": ((6, 30, "Rolling"),),
            },
        ),
    },
    {
        "name": "Koç University",
        "country": "Турция",
        "website": "https://www.ku.edu.tr",
        "domain": "ku.edu.tr",
        "programs": (
            {
                "name": "Engineering",
                "req": {"min_gpa": 3.2, "min_ielts": 6.5, "min_toefl": 80, "min_sat": 1250},
                "subjects": "Математика, Физика",
                "rounds": ((5, 31, "Rolling"),),
            },
            {
                "name": "Economics",
                "req": {"min_gpa": 3.0, "min_ielts": 6.5, "min_toefl": 80},
                "rounds": ((5, 31, "Rolling"),),
            },
        ),
    },
    {
        "name": "Universiti Malaya",
        "country": "Малайзия",
        "website": "https://www.um.edu.my",
        "domain": "um.edu.my",
        "programs": (
            {
                "name": "Computer Science",
                "req": {"min_gpa": 3.0, "min_ielts": 6.0, "min_toefl": 79},
                "subjects": "Математика",
                "rounds": ((4, 30, "Rolling"),),
            },
            {
                "name": "Business Management",
                "req": {"min_gpa": 3.0, "min_ielts": 6.0, "min_toefl": 79},
                "rounds": ((4, 30, "Rolling"),),
            },
        ),
    },
)


def upcoming(month: int, day: int, *, today: date | None = None) -> date:
    """Ближайшая будущая дата с этим числом и месяцем.

    Стартовый справочник не должен с порога показывать просроченные
    дедлайны: до 29 февраля дата сдвигается на 28-е.
    """
    today = today or date.today()
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:  # 29 февраля в невисокосном году
            candidate = date(year, month, 28)
        if candidate >= today:
            return candidate
    return date(today.year + 1, month, min(day, 28))


def seed_flags() -> dict:
    """Признаки, которые получает каждая запись стартового справочника."""
    return {"data_source": CatalogSource.SEED, "is_verified": False}


@transaction.atomic
def create_seed(*, today: date | None = None) -> dict:
    """Завести стартовый справочник. Существующие записи не трогает."""
    created = {"universities": 0, "programs": 0, "requirements": 0, "rounds": 0}
    for item in SEED:
        university, is_new = University.objects.get_or_create(
            name=item["name"],
            defaults={
                "country": item["country"],
                "website": item["website"],
                "domain": item["domain"],
                **seed_flags(),
            },
        )
        if not is_new:
            # вуз завела школа — стартовый набор его не переписывает
            continue
        created["universities"] += 1
        for program_item in item["programs"]:
            program = Program.objects.create(
                university=university, name=program_item["name"], level="bachelor", **seed_flags()
            )
            created["programs"] += 1
            AdmissionRequirement.objects.create(
                program=program,
                required_subjects=program_item.get("subjects", ""),
                portfolio_required=program_item.get("portfolio", False),
                source_url=item["website"],
                notes="Заготовка стартового справочника. Сверьте с сайтом вуза перед тем, как показывать ученику.",
                **program_item["req"],
                **seed_flags(),
            )
            created["requirements"] += 1
            for month, day, round_type in program_item["rounds"]:
                AdmissionRound.objects.create(
                    program=program,
                    round_type=round_type,
                    deadline=upcoming(month, day, today=today),
                    source_url=item["website"],
                    **seed_flags(),
                )
                created["rounds"] += 1
    return created


def seed_stats() -> dict:
    """Сколько записей стартового справочника сейчас в базе."""
    universities = University.objects.filter(data_source=CatalogSource.SEED)
    return {
        "universities": universities.count(),
        "programs": Program.objects.filter(data_source=CatalogSource.SEED).count(),
        "unverified": universities.filter(is_verified=False).count(),
        "held_by_students": StudentUniversity.objects.filter(program__data_source=CatalogSource.SEED).count(),
        "own_universities": University.objects.exclude(data_source=CatalogSource.SEED).count(),
    }


class SeedInUse(Exception):
    """Программы стартового справочника лежат в списках учеников."""

    def __init__(self, held: int):
        self.held = held
        super().__init__(
            f"Программы стартового справочника стоят в списках учеников: {held}. "
            "Уберите их из списков или подтвердите удаление вместе со связями."
        )


@transaction.atomic
def drop_seed(*, force: bool = False) -> dict:
    """Убрать записи с источником `seed`. Заведённое школой остаётся."""
    universities = University.objects.filter(data_source=CatalogSource.SEED)
    held = StudentUniversity.objects.filter(program__data_source=CatalogSource.SEED)
    held_count = held.count()
    if held_count and not force:
        raise SeedInUse(held_count)
    removed_links = 0
    if held_count:
        removed_links = held_count
        held.delete()
    stats = {
        "universities": universities.count(),
        "programs": Program.objects.filter(data_source=CatalogSource.SEED).count(),
        "student_links": removed_links,
    }
    try:
        universities.delete()
    except ProtectedError as error:  # чужие связи, о которых мы не знали
        raise SeedInUse(held_count) from error
    return stats
