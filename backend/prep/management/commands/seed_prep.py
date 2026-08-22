"""Демонстрационный банк заданий и один пробный экзамен.

Как и `seed_demo`, работает только при DEBUG: боевой банк наполняет
академический директор — руками или импортом.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from prep.models import Difficulty, MockExam, MockSection, Question, QuestionOption, Section

BANK = [
    (
        "IELTS",
        Section.READING,
        "Matching headings",
        Difficulty.MEDIUM,
        "Прочитайте абзац и выберите подходящий заголовок.",
        [
            ("A", "The cost of migration", False),
            ("B", "Why birds navigate", True),
            ("C", "A history of ornithology", False),
            ("D", "Feeding habits", False),
        ],
        "Абзац целиком о механизмах навигации, стоимость и история в нём не упоминаются.",
    ),
    (
        "IELTS",
        Section.READING,
        "True / False / Not Given",
        Difficulty.HARD,
        "Утверждение: «Все виды возвращаются в то же гнездо». Что верно?",
        [("A", "True", False), ("B", "False", False), ("C", "Not Given", True)],
        "В тексте сказано о «многих видах», про все — ничего, значит Not Given.",
    ),
    (
        "IELTS",
        Section.LISTENING,
        "Form completion",
        Difficulty.EASY,
        "Что записать в поле «Дата заезда»?",
        [("A", "14 May", True), ("B", "4 May", False), ("C", "14 March", False)],
        "В записи звучит fourteenth of May.",
    ),
    (
        "IELTS",
        Section.LISTENING,
        "Multiple choice",
        Difficulty.MEDIUM,
        "Почему говорящий отменил поездку?",
        [("A", "Заболел", False), ("B", "Изменилось расписание", True), ("C", "Не хватило денег", False)],
        "Говорящий прямо упоминает изменение расписания.",
    ),
    (
        "IELTS",
        Section.WRITING,
        "Task 1: описание графика",
        Difficulty.MEDIUM,
        "С чего начинать Task 1?",
        [("A", "С вывода", False), ("B", "С перефразированного вступления", True), ("C", "С личного мнения", False)],
        "Личное мнение в Task 1 не оценивается, начинают с перефразирования задания.",
    ),
    (
        "SAT",
        Section.MATH,
        "Линейные уравнения",
        Difficulty.EASY,
        "Если 3x + 6 = 21, чему равен x?",
        [("A", "3", False), ("B", "5", True), ("C", "7", False), ("D", "9", False)],
        "3x = 15, значит x = 5.",
    ),
    (
        "SAT",
        Section.MATH,
        "Проценты",
        Difficulty.MEDIUM,
        "Цена выросла с 80 до 100. На сколько процентов?",
        [("A", "20%", False), ("B", "25%", True), ("C", "ize 80%", False)],
        "Прирост 20 от базы 80 — это 25%.",
    ),
    (
        "SAT",
        Section.MATH,
        "Квадратные уравнения",
        Difficulty.HARD,
        "Сколько корней у x² + 4x + 4 = 0?",
        [("A", "Ни одного", False), ("B", "Один", True), ("C", "Два", False)],
        "Дискриминант равен нулю — корень один, двукратный.",
    ),
    (
        "SAT",
        Section.VERBAL,
        "Words in context",
        Difficulty.MEDIUM,
        "Слово «reserved» в предложении ближе всего к…",
        [("A", "забронированный", False), ("B", "сдержанный", True), ("C", "запасной", False)],
        "Контекст описывает манеру человека, а не бронирование.",
    ),
    (
        "SAT",
        Section.VERBAL,
        "Command of evidence",
        Difficulty.HARD,
        "Какая строка подтверждает предыдущий ответ?",
        [("A", "строки 4–6", False), ("B", "строки 12–14", True), ("C", "строки 20–22", False)],
        "Именно там автор формулирует тезис, о котором идёт речь.",
    ),
]


class Command(BaseCommand):
    help = "Наполняет банк заданий демонстрационными вопросами (только при DEBUG)"

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_prep работает только при DEBUG=1")

        created = 0
        for exam, section, topic, difficulty, text, options, explanation in BANK:
            if Question.objects.filter(exam_type=exam, topic=topic, text=text).exists():
                continue
            question = Question.objects.create(
                exam_type=exam,
                section=section,
                topic=topic,
                difficulty=difficulty,
                text=text,
                explanation=explanation,
                source="Демонстрационный банк",
            )
            for letter, option_text, is_correct in options:
                QuestionOption.objects.create(question=question, letter=letter, text=option_text, is_correct=is_correct)
            created += 1

        mocks = 0
        for title, exam, minutes, sections in (
            ("Пробный IELTS: чтение и аудирование", "IELTS", 60, ((Section.READING, 2), (Section.LISTENING, 2))),
            ("Пробный SAT: математика и вербальная", "SAT", 90, ((Section.MATH, 3), (Section.VERBAL, 2))),
        ):
            mock, is_new = MockExam.objects.get_or_create(
                title=title, defaults={"exam_type": exam, "time_limit_minutes": minutes}
            )
            if is_new:
                for order, (section, count) in enumerate(sections, start=1):
                    MockSection.objects.create(mock=mock, section=section, question_count=count, order=order)
                mocks += 1

        self.stdout.write(self.style.SUCCESS(f"Готово: заданий {created}, пробных экзаменов {mocks}"))
