"""Демонстрационные данные для ручной и браузерной проверки.

Инвариант №8 запрещает фикстуры с выдуманными учениками в боевой базе,
поэтому команда работает только при DEBUG и требует явного запуска.
Никакой автозагрузки при старте контейнера здесь нет и быть не должно.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

LAST_NAMES = [
    "Сериков",
    "Тлеубаев",
    "Ахметов",
    "Оспанов",
    "Байжанов",
    "Ким",
    "Ли",
    "Нурланов",
    "Сагындык",
    "Ержанов",
    "Абдрахман",
    "Мусаев",
    "Дуйсенов",
    "Калиев",
    "Сулейменов",
    "Жумабек",
    "Токтаров",
    "Исаев",
    "Бекмуратов",
    "Шаяхмет",
]
FIRST_NAMES = [
    "Дамир",
    "Жанна",
    "Алина",
    "Ерасыл",
    "Айсулу",
    "Тимур",
    "Дана",
    "Санжар",
    "Камила",
    "Нурлан",
    "Асель",
    "Арман",
    "Мадина",
    "Ислам",
    "Аружан",
]


class Command(BaseCommand):
    help = "Наполняет базу демонстрационными данными (только при DEBUG)"

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, default=40, help="Сколько учеников создать")
        parser.add_argument("--wipe", action="store_true", help="Сначала снести прежние демо-данные")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo работает только при DEBUG=1")

        from alumni.models import Alumnus, AlumnusApplication, ArchivedEssay
        from roadmap.models import Essay, EssayVersion, Task
        from students.models import (
            Activity,
            AdmissionProfile,
            BehaviorProfile,
            Competition,
            ExamAttempt,
            ExamProfile,
            SportProfile,
            Student,
            StudyGroup,
            TalentProfile,
        )
        from universities.models import (
            AdmissionRequirement,
            AdmissionRound,
            Program,
            StudentUniversity,
            University,
        )

        rnd = random.Random(20260822)

        if options["wipe"]:
            StudentUniversity.objects.all().delete()
            Task.objects.all().delete()
            EssayVersion.objects.all().delete()
            Essay.objects.all().delete()
            ExamAttempt.objects.all().delete()
            Activity.objects.all().delete()
            Competition.objects.all().delete()
            Student.objects.filter(email__endswith="@demo.local").delete()
            ArchivedEssay.objects.all().delete()
            AlumnusApplication.objects.all().delete()
            Alumnus.objects.all().delete()
            AdmissionRequirement.objects.all().delete()
            AdmissionRound.objects.all().delete()
            Program.objects.all().delete()
            University.objects.all().delete()

        # --- Справочник вузов ------------------------------------------
        catalog = [
            ("University of Toronto", "Канада", "utoronto.ca", "Computer Science", 3.3, 6.5, 90, 1350, 29),
            ("University of British Columbia", "Канада", "ubc.ca", "Engineering", 3.2, 6.5, 90, 1300, 28),
            (
                "Delft University of Technology",
                "Нидерланды",
                "tudelft.nl",
                "Aerospace Engineering",
                3.5,
                6.5,
                90,
                None,
                None,
            ),
            ("University of Amsterdam", "Нидерланды", "uva.nl", "Economics", 3.0, 6.5, 92, None, None),
            ("Technical University of Munich", "Германия", "tum.de", "Informatics", 3.4, 6.5, 88, None, None),
            (
                "University of Manchester",
                "Великобритания",
                "manchester.ac.uk",
                "Business Management",
                3.1,
                6.5,
                90,
                None,
                None,
            ),
            ("University College London", "Великобритания", "ucl.ac.uk", "Mathematics", 3.6, 7.0, 100, 1450, 32),
            ("Nazarbayev University", "Казахстан", "nu.edu.kz", "Computer Science", 3.0, 6.0, 79, 1200, 25),
            ("Purdue University", "США", "purdue.edu", "Data Science", 3.2, 6.5, 88, 1330, 29),
            ("Arizona State University", "США", "asu.edu", "Business", 2.8, 6.0, 79, 1120, 22),
        ]
        programs: list[Program] = []
        for name, country, domain, major, gpa, ielts, toefl, sat, act in catalog:
            # демо-данные не опираются на стартовую заготовку: иначе выпускники
            # оказываются «поступившими» на программу-заглушку, и её потом
            # не снести, не тронув историю
            university = University.objects.filter(name=name).exclude(data_source="seed").first()
            if university is None:
                university = University.objects.create(
                    name=name if not University.objects.filter(name=name).exists() else f"{name} (демо)",
                    country=country,
                    domain=domain,
                    website=f"https://{domain}",
                )
            program, _ = Program.objects.get_or_create(university=university, name=major, level="bachelor")
            programs.append(program)
            AdmissionRequirement.objects.get_or_create(
                program=program,
                defaults={
                    "min_gpa": Decimal(str(gpa)),
                    "min_ielts": Decimal(str(ielts)),
                    "min_toefl": toefl,
                    "min_sat": sat,
                    "min_act": act,
                    "source_url": f"https://{domain}/admissions",
                },
            )
            base = date.today() + timedelta(days=rnd.randint(30, 240))
            for round_type, shift in (("ED", 0), ("RD", 60)):
                AdmissionRound.objects.get_or_create(
                    program=program,
                    round_type=round_type,
                    defaults={"deadline": base + timedelta(days=shift), "source_url": f"https://{domain}/deadlines"},
                )

        # --- Группы и ученики -------------------------------------------
        groups = [
            StudyGroup.objects.get_or_create(code=code, defaults={"grade": grade, "curator": curator})[0]
            for code, grade, curator in (("11A", 11, "Салтанат"), ("11B", 11, "Салтанат"), ("10A", 10, "Асем"))
        ]

        created = 0
        for i in range(options["students"]):
            email = f"demo{i:03d}@demo.local"
            if Student.objects.filter(email=email).exists():
                continue
            group = groups[i % len(groups)]
            student = Student.objects.create(
                last_name=LAST_NAMES[i % len(LAST_NAMES)],
                first_name=FIRST_NAMES[i % len(FIRST_NAMES)],
                email=email,
                grade=group.grade,
                group=group,
                graduation_year=2027 if group.grade == 11 else 2028,
            )
            created += 1
            BehaviorProfile.objects.create(
                student=student,
                attendance_percent=rnd.randint(70, 100),
                remarks_count=rnd.randint(0, 6),
                homework_percent=rnd.randint(50, 100),
                status=rnd.choice(["can_execute", "needs_supervision", "critical"]),
            )
            AdmissionProfile.objects.create(
                student=student,
                target_country=rnd.choice(["Канада", "Нидерланды", "Германия", "США", "Казахстан"]),
                target_major=rnd.choice(["Computer Science", "Economics", "Engineering", "Business"]),
                has_common_app=rnd.random() > 0.5,
                status=rnd.choice(["A", "B", "C"]),
            )
            ExamProfile.objects.create(
                student=student,
                ielts_current=Decimal(str(rnd.choice([5.5, 6.0, 6.5, 7.0, 7.5]))),
                ielts_target=Decimal("7.5"),
                sat_current=rnd.choice([1100, 1200, 1280, 1350, 1420]),
                sat_target=1450,
                gpa=Decimal(str(round(rnd.uniform(2.8, 4.0), 2))),
                hours_per_week=rnd.randint(2, 12),
            )
            TalentProfile.objects.create(
                student=student,
                main_track=rnd.choice(["olympiad", "research", "startup", "leadership", "volunteering"]),
                portfolio_status=rnd.choice(["strong", "medium", "weak"]),
            )
            SportProfile.objects.create(
                student=student,
                sport_kind=rnd.choice(["Футбол", "Волейбол", "Плавание", "Шахматы", ""]),
                level=rnd.choice(["school", "city", "regional", "national", ""]),
            )
            for n in range(rnd.randint(0, 3)):
                ExamAttempt.objects.create(
                    student=student,
                    exam_type="IELTS",
                    attempt_format="mock",
                    date=date.today() - timedelta(days=30 * (n + 1)),
                    total_score=Decimal(str(rnd.choice([5.5, 6.0, 6.5, 7.0]))),
                )
            for program in rnd.sample(programs, rnd.randint(0, 4)):
                StudentUniversity.objects.get_or_create(
                    student=student,
                    program=program,
                    defaults={"tier": rnd.choice(["reach", "target", "safety"])},
                )
            for _ in range(rnd.randint(0, 5)):
                Task.objects.create(
                    student=student,
                    title=rnd.choice(
                        ["Сдать IELTS", "Написать personal statement", "Собрать документы", "Заполнить Common App"]
                    ),
                    category=rnd.choice(["test", "essay", "documents", "university"]),
                    priority=rnd.choice(["high", "medium", "low"]),
                    status=rnd.choice(["todo", "in_progress", "review", "done"]),
                    due_date=date.today() + timedelta(days=rnd.randint(-20, 180)),
                )

        # --- Привязка к тестовому ученику -------------------------------
        from accounts.models import User

        test_user = User.objects.filter(email="test.student@lms.local").first()
        if test_user is not None:
            student = getattr(test_user, "student", None)
            if student is not None:
                exam, _ = ExamProfile.objects.get_or_create(student=student)
                exam.ielts_current = Decimal("6.0")
                exam.sat_current = 1250
                exam.gpa = Decimal("3.40")
                exam.save()
                for program in programs[:3]:
                    StudentUniversity.objects.get_or_create(student=student, program=program)
                if not student.essays.exists():
                    essay = Essay.objects.create(
                        student=student, essay_type="personal_statement", title="Personal statement"
                    )
                    EssayVersion.objects.create(essay=essay, number=1, text="Первый черновик.", word_count=2)
                if not student.tasks.exists():
                    for title, category in (("Сдать IELTS", "test"), ("Написать эссе", "essay")):
                        Task.objects.create(
                            student=student,
                            title=title,
                            category=category,
                            priority="high",
                            due_date=date.today() + timedelta(days=45),
                        )

        # --- Выпускники ---------------------------------------------------
        if not Alumnus.objects.exists():
            for i in range(6):
                program = programs[i % len(programs)]
                graduate = Student.objects.create(
                    last_name=LAST_NAMES[-(i + 1)],
                    first_name=FIRST_NAMES[-(i + 1)],
                    email=f"alumnus{i}@demo.local",
                    grade=11,
                    graduation_year=2024 + (i % 2),
                    is_active=False,
                )
                alumnus = Alumnus.objects.create(
                    student=graduate,
                    graduation_year=graduate.graduation_year,
                    university=program.university,
                    program=program,
                    country=program.university.country,
                    current_occupation="Студент 1 курса",
                    admission_gpa=Decimal("3.60"),
                    admission_ielts=Decimal("7.0"),
                    admission_sat=1380,
                    admission_activities=rnd.randint(2, 8),
                    mentorship_consent=i % 2 == 0,
                )
                AlumnusApplication.objects.create(alumnus=alumnus, program=program, outcome="enrolled")
                if i == 0:
                    ArchivedEssay.objects.create(
                        alumnus=alumnus,
                        program=program,
                        essay_type="personal_statement",
                        title="Как я выбрал Computer Science",
                        consent_given=True,
                        text="Демонстрационный текст архивного эссе. " * 20,
                    )

        self.stdout.write(self.style.SUCCESS(f"Готово: учеников создано {created}, программ {len(programs)}"))
