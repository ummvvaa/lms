"""Разбор результатов профтеста моделью — под поступление за рубеж, подробно.

Школа в Казахстане готовит учеников к поступлению в зарубежные вузы:
модель знает это из `SYSTEM` и не называет местных выпускных экзаменов.
Модель получает не ответы, а профиль: все шкалы теста с баллом и подписью
диапазона, разделённые на сильные (верхний диапазон теста — на них
строятся направления), средние (выше порога разбора — дополняют направление)
и слабые с отвергаемыми (ниже порога); параллель, баллы и цели по экзаменам
из карточки, вузы из списка ученика. Имени ученика в запросе нет — только
номер (как у остальных операций помощника).

Разбор подробный, «от А до Я» (решение владельца, 04.11.2026): общий вывод
по всему профилю, профиль интересов — смысл каждой шкалы, два–четыре
направления, каждое на сильной шкале; объём каждой части задан в `SYSTEM`.
Направление, которое не опирается ни на одну сильную шкалу, отбрасывается.
Программы и цифры порогов — только из каталога (`AdmissionRequirement`,
инвариант 10): программы модель называет номерами, порогов нет — экзамены
без цифр. Ответ хранится строками `CareerAnalysis`, `CareerAnalysisScale`
и `CareerAnalysisDirection`; в доменные поля ученика ничего не пишется.

Один набор сданных попыток разбирается один раз (`fingerprint`):
повторный запуск по тем же попыткам возвращает готовый разбор, пока
учитель не нажмёт «Пересчитать» (решение владельца, 08.10.2026).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from academics.keep_subjects import KEPT
from career.models import (
    AnalysisStatus,
    CareerAnalysis,
    CareerAnalysisDirection,
    CareerAnalysisScale,
    CareerAttempt,
    CareerRange,
)
from career.scoring import bounds
from core.parallels import ADMISSION_PARALLEL, parallel_of
from students.models import AttemptFormat, ExamAttempt, Student
from universities.models import AdmissionRequirement, Program, StudentUniversity

#: сколько программ каталога отдаём модели — как у прежнего профтеста
CANDIDATES = 60
#: направлений от двух до четырёх, если есть хотя бы одна сильная шкала
MIN_DIRECTIONS = 2
MAX_DIRECTIONS = 4
#: по скольким верхним диапазонам теста строятся направления — только по самому верхнему
STRONG_RANGES = 1
#: правила, по которым считается новый разбор (`CareerAnalysis.rules`)
RULES = 3
#: предел ответа без рассуждения: рассуждению провайдер добавляет запас `LLM_REASONING_RESERVE`.
#: Подробный ответ на три теста (35 шкал профиля, четыре направления) — около 8 000 токенов;
#: предел вдвое выше, чтобы ответ не оборвался на длинном профиле
MAX_TOKENS = 16000

#: место шкалы в профиле: верхний диапазон, выше порога разбора, ниже порога
STRONG, MIDDLE, LOW = "strong", "middle", "low"
#: заголовки групп шкал в запросе модели
LEVEL_TITLES = (  # i18n-skip: промпт ИИ
    (STRONG, "Сильные шкалы — верхний диапазон теста, на них строятся направления:"),
    (
        MIDDLE,
        "Средние шкалы — выше порога разбора ({threshold}), но ниже верхнего диапазона: своих направлений "
        "не дают, могут дополнять направление по сильной шкале:",
    ),
    (LOW, "Слабые и отвергаемые шкалы — ниже порога разбора ({threshold}):"),
)

# fmt: off
SYSTEM = (  # i18n-skip: промпт ИИ — язык ответа модели настраивается отдельно
    """Ты — профориентолог частной школы в Казахстане. Школа ведёт 8–11 классы и готовит
учеников к поступлению в зарубежные вузы. Разбор результатов тестов профориентации читает
профориентолог школы и обсуждает его с учеником и родителями: разбор должен объяснить профиль
интересов от А до Я, показать, куда двигаться для поступления за рубеж и что делать уже сейчас.

Пиши подробно и по делу: разбор — основа разговора с учеником и родителями, короткие общие
фразы им не помогают. Объём каждой части:
- общий вывод — шесть–десять предложений: весь профиль интересов от самых сильных шкал
  до отвергаемых, как интересы сочетаются между собой и что это значит для выбора
  специальности за рубежом;
- профиль интересов — по каждой шкале из списка, ни одной не пропуская, одна–две фразы о том,
  что значит её балл: и у сильных, и у средних, и у слабых и отвергаемых шкал;
- «почему подходит» — четыре–шесть предложений: через конкретные шкалы, их баллы
  и их сочетание;
- «что сдавать для поступления» — по каждому экзамену отдельно, каждый с новой строки:
  нужен ли он для этого направления, текущий балл ученика, пороги программ каталога,
  сколько не хватает или что порог уже пройден;
- «что подтянуть в школе» — каждый предмет с новой строки и с объяснением, зачем он нужен
  этому направлению;
- «что сделать уже сейчас» — три–пять конкретных шагов, каждый с новой строки.

Правила, нарушать нельзя:
- опирайся только на результаты тестов, баллы ученика и программы, которые даны ниже;
  ничего не додумывай о личности ученика;
- направлений — от двух до четырёх. Каждое направление обязано опираться хотя бы на одну
  сильную шкалу — из самого верхнего диапазона теста; одна сильная шкала может дать несколько
  направлений. Средние шкалы могут дополнять направление по сильной шкале («математика,
  12 из 12, вместе с интересом к бизнесу, 6 из 12, — Economics»), но направления только
  из средних шкал не бывает. У каждого направления перечисли сильные шкалы, на которые
  оно опирается, — названиями точно как в списке. Сильных шкал нет — направлений не давай,
  а профиль интересов и общий вывод напиши так же подробно и скажи, к чему можно присмотреться;
- местные выпускные и вступительные экзамены (ЕНТ, ОГЭ, ЕГЭ и подобные) не упоминай никогда.
  Для поступления за рубеж сдают IELTS или TOEFL, SAT и другие экзамены, которые требуют
  программы из списка;
- цифры порогов (IELTS, TOEFL, SAT, ACT, GPA) бери только из требований программ, которые
  даны ниже. Порогов нет — называй экзамены без цифр и пиши «пороги — по программам
  в каталоге». Есть балл ученика и порог программы — сравни их: сколько не хватает
  или что порог уже пройден;
- программы указывай только номерами из списка ниже; программы, которой нет в списке,
  не существует — не называй её никак; подходящих нет — оставь список программ пустым;
- что подтянуть в школе — из предметов подготовки, которые ведёт школа (они перечислены ниже),
  плюс один профильный школьный предмет направления;
- шаги уже сейчас — для портфолио: олимпиады, проекты, волонтёрство, летние школы. Ученику
  8–10 класса — с привязкой ко времени («в 10 классе», «до осени 11 класса») и без давления:
  программы для него — ориентир на будущее, а не выбор;
- экзамены, предметы и шаги читают и ученик, и профориентолог: пиши их без обращения
  и без третьего лица — «IELTS: сейчас 6.0, порог программ 6.5 — не хватает 0.5»,
  «Участвовать в олимпиаде по биологии в 10 классе»;
- не обещай поступление и не употребляй слова «шанс», «вероятность», «прогноз»;
- не ставь диагнозов и не оценивай ученика как человека: пиши об интересах и сильных сторонах;
- пиши понятно для ученика и родителя: простыми словами, но не коротко — понятность не в том,
  чтобы сократить, а в том, чтобы объяснить. Без служебных слов — без названий полей,
  без «переданных результатов», «данных запроса», «справочника», без номеров программ
  в тексте. Объясняй через шкалы и баллы: «интерес к языкам — самый высокий в тесте,
  11 из 12»."""
)
# fmt: on

RESULT_SCHEMA = {  # i18n-skip: схема ответа для модели ИИ
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "общий вывод, шесть–десять предложений: весь профиль от самых сильных шкал "
            "до отвергаемых, как интересы сочетаются и что это значит для выбора специальности за рубежом",
        },
        "profile": {
            "type": "array",
            "description": "профиль интересов: по каждой шкале из списка, в том же порядке, ни одной не пропуская",
            "items": {
                "type": "object",
                "properties": {
                    "scale": {"type": "string", "description": "название шкалы точно как в списке"},
                    "meaning": {"type": "string", "description": "одна–две фразы: что значит балл этой шкалы"},
                },
                "required": ["scale", "meaning"],
            },
        },
        "directions": {
            "type": "array",
            "description": "от двух до четырёх направлений, каждое на сильной шкале; сильных нет — пустой список",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "направление по-русски"},
                    "title_abroad": {
                        "type": "string",
                        "description": "как специальность называется в зарубежных вузах, по-английски: "
                        "Linguistics, Education, International Relations",
                    },
                    "scales": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "сильные шкалы, на которые опирается направление, названиями точно как в списке",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "почему подходит — четыре–шесть предложений через шкалы, баллы и их сочетание",
                    },
                    "professions": {"type": "string", "description": "три–пять профессий через запятую"},
                    "exams": {
                        "type": "string",
                        "description": "что сдавать для поступления за рубеж — по экзамену на строку: нужен ли, "
                        "балл ученика, пороги программ каталога, сколько не хватает или что пройдено",
                    },
                    "subjects": {
                        "type": "string",
                        "description": "что подтянуть в школе — по предмету на строку, с объяснением зачем",
                    },
                    "next_steps": {
                        "type": "string",
                        "description": "три–пять конкретных шагов для портфолио уже сейчас, каждый с новой строки",
                    },
                    "programs": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "номера программ из списка",
                    },
                },
                "required": ["title", "scales", "reasoning", "exams", "subjects", "next_steps"],
            },
        },
    },
    "required": ["summary", "profile", "directions"],
}


class AnalysisRefused(ValueError):
    """Разбор не запускается — причина словами."""


@dataclass(frozen=True)
class Plan:
    """Что сделает запуск: новые разборы, готовые и кого пропустили."""

    create: list[tuple[Student, list[CareerAttempt]]]
    reuse: list[CareerAnalysis]
    skipped: list[tuple[Student, str]]


@dataclass(frozen=True)
class ScaleLine:
    """Шкала попытки: балл, наибольший возможный, подпись диапазона и место в профиле."""

    title: str
    score: int
    top: int
    label: str
    #: `STRONG` — верхний диапазон теста, `MIDDLE` — выше порога разбора, `LOW` — ниже порога
    level: str

    @property
    def strong(self) -> bool:
        return self.level == STRONG

    def __str__(self) -> str:
        text = f"- {self.title}: {self.score}" + (f" из {self.top}" if self.top else "")  # i18n-skip: промпт ИИ
        return text + (f" — {self.label}" if self.label else "")


def fingerprint_of(attempts: list[CareerAttempt]) -> str:
    return ",".join(str(pk) for pk in sorted(attempt.pk for attempt in attempts))


def is_strong(ranges: list[CareerRange], scale_id: int, score: int) -> bool:
    """Балл в верхнем диапазоне шкалы: свои диапазоны шкалы важнее общих.

    У теста без диапазонов сравнивать не с чем — сильной считается любая
    шкала выше порога, как было до разделения.
    """
    own = [r for r in ranges if r.scale_id == scale_id]
    pool = own or [r for r in ranges if r.scale_id is None]
    if not pool:
        return True
    top = sorted(pool, key=lambda r: (-r.high, -r.low))[:STRONG_RANGES]
    return score > top[0].high or any(r.low <= score <= r.high for r in top)


def profile(attempt: CareerAttempt) -> list[ScaleLine]:
    """Все шкалы попытки по убыванию балла — и сильные, и отвергаемые."""
    test = attempt.test
    threshold = test.analysis_min_score
    ranges = list(test.ranges.all())
    tops = bounds(test)
    rows = list(attempt.scores.select_related("scale"))
    rows.sort(key=lambda row: (-row.score, row.scale.order))
    return [
        ScaleLine(
            title=row.scale.title,
            score=row.score,
            top=tops.get(row.scale_id, (0, 0))[1],
            label=row.label,
            level=LOW if row.score < threshold else STRONG if is_strong(ranges, row.scale_id, row.score) else MIDDLE,
        )
        for row in rows
    ]


def profile_lines(attempt: CareerAttempt) -> list[str]:
    """Шкалы попытки не ниже порога теста строками; пусто — разбирать нечего."""
    return [str(line) for line in profile(attempt) if line.level != LOW]


def _key(title: str) -> str:
    """Название шкалы для сверки с ответом модели: без регистра, кавычек и «ё»."""
    return " ".join(str(title).casefold().replace("ё", "е").strip(" «»\"'.").split())  # i18n-skip: сверка букв


def _candidates(student: Student) -> list[Program]:
    """Программы каталога: сначала из списка ученика, потом по рейтингу вуза.

    Ученику 8–10 класса программы тоже уходят — как ориентир на будущее,
    текст об этом говорит сам (`_prompt`).
    """
    own = list(
        StudentUniversity.objects.filter(
            student=student, program__is_active=True, program__university__is_active=True
        ).values_list("program_id", flat=True)
    )
    rows = list(
        Program.objects.filter(is_active=True, university__is_active=True)
        .select_related("university", "requirement")
        .order_by("university__world_rank", "university__name", "name")
    )
    rows.sort(key=lambda program: program.pk not in own)
    return rows[:CANDIDATES]


def _number(value) -> str:
    """6.50 → 6.5, 1300.0 → 1300."""
    return format(value.normalize(), "f") if hasattr(value, "normalize") else str(value)


def thresholds(requirement: AdmissionRequirement | None) -> list[str]:
    """Пороги программы словами для модели; пусто — у программы порогов в каталоге нет."""
    if requirement is None:
        return []
    out = [
        f"{name} {_number(value)}"
        for name, value in (
            ("IELTS", requirement.min_ielts),
            ("TOEFL", requirement.min_toefl),
            ("SAT", requirement.min_sat),
            ("ACT", requirement.min_act),
            ("GPA", requirement.min_gpa),
        )
        if value is not None
    ]
    if requirement.required_subjects.strip():
        out.append(f"предметы: {requirement.required_subjects.strip()}")  # i18n-skip: промпт ИИ
    return out


def _requirement(program: Program) -> AdmissionRequirement | None:
    try:
        return program.requirement
    except AdmissionRequirement.DoesNotExist:
        return None


def _years(parallel: int) -> str:
    years = ADMISSION_PARALLEL - parallel
    return f"{years} {'год' if years == 1 else 'года'}"  # i18n-skip: промпт ИИ


def student_lines(student: Student) -> list[str]:
    """Что известно об ученике из карточки: параллель, экзамены, вузы. Без имени."""
    parallel = parallel_of(student)
    lines = [f"Ученик №{student.pk}, {parallel} класс."]  # i18n-skip: промпт ИИ
    if parallel < ADMISSION_PARALLEL:
        lines.append(f"До 11 класса, когда подаются документы в вузы, — {_years(parallel)}.")  # i18n-skip: промпт ИИ
    else:
        lines.append("Ученик в 11 классе: документы в вузы подаются в этом учебном году.")  # i18n-skip: промпт ИИ
    exams: list[str] = []
    profile_row = getattr(student, "exam", None)
    if profile_row is not None and profile_row.archived_at is None:
        for name, current, target in (
            ("IELTS", profile_row.ielts_current, profile_row.ielts_target),
            ("SAT", profile_row.sat_current, profile_row.sat_target),
        ):
            parts = [f"сейчас {_number(current)}" if current is not None else ""]  # i18n-skip: промпт ИИ
            parts.append(f"цель {_number(target)}" if target is not None else "")  # i18n-skip: промпт ИИ
            if any(parts):
                exams.append(f"{name}: " + ", ".join(p for p in parts if p))
    latest: dict[str, ExamAttempt] = {}
    for attempt in ExamAttempt.objects.filter(
        student=student, attempt_format=AttemptFormat.MOCK, total_score__isnull=False
    ).order_by("-date", "-id"):
        latest.setdefault(attempt.exam_type, attempt)
    for exam_type, attempt in latest.items():
        exams.append(
            f"Mock Test {exam_type}: {_number(attempt.total_score)} ({attempt.date:%m.%Y})"
        )  # i18n-skip: промпт ИИ
    if exams:
        lines.append("Баллы и цели по экзаменам:")  # i18n-skip: промпт ИИ
        lines.extend(f"- {row}" for row in exams)
    else:
        lines.append("Баллов по экзаменам в карточке пока нет.")  # i18n-skip: промпт ИИ
    own = list(
        StudentUniversity.objects.filter(student=student)
        .select_related("program__university")
        .order_by("-is_priority", "tier", "id")
    )
    if own:
        countries = sorted({row.program.university.country for row in own if row.program.university.country})
        lines.append(
            "Вузы из списка ученика: "
            + "; ".join(f"{row.program.name} · {row.program.university.name}" for row in own)
            + (f". Страны: {', '.join(countries)}." if countries else ".")
        )  # i18n-skip: промпт ИИ
    return lines


def _prompt(student: Student, attempts: list[CareerAttempt], programs: list[Program]) -> str:
    """Запрос модели: ученик без имени, профиль с диапазонами, предметы школы, программы каталога."""
    lines = student_lines(student)
    junior = parallel_of(student) < ADMISSION_PARALLEL
    lines += ["", "Результаты тестов профориентации — все шкалы каждого теста:"]  # i18n-skip: промпт ИИ
    strong = False
    scales = 0
    for attempt in attempts:
        test = attempt.test
        when = timezone.localtime(attempt.finished_at).strftime("%d.%m.%Y") if attempt.finished_at else ""
        lines.append("")
        lines.append(f"Тест «{test.title}»" + (f", пройден {when}" if when else "") + ":")  # i18n-skip: промпт ИИ
        rows = profile(attempt)
        scales += len(rows)
        strong = strong or any(row.strong for row in rows)
        for level, title in LEVEL_TITLES:
            group = [row for row in rows if row.level == level]
            if group:
                lines.append(title.format(threshold=test.analysis_min_score))
                lines.extend(str(row) for row in group)
    lines.append("")
    lines.append(
        "Предметы подготовки, которые ведёт школа: " + ", ".join(name for name, _aliases in KEPT) + "."
    )  # i18n-skip: промпт ИИ
    lines.append("")
    with_thresholds = False
    if programs:
        if junior:
            lines.append(
                "Программы каталога школы — ориентир на будущее, а не выбор (только из них можно выбирать):"
            )  # i18n-skip: промпт ИИ
        else:
            lines.append("Программы каталога школы (только из них можно выбирать):")  # i18n-skip: промпт ИИ
        for program in programs:
            limits = thresholds(_requirement(program))
            with_thresholds = with_thresholds or any(not row.startswith("предметы") for row in limits)
            country = f" ({program.university.country})" if program.university.country else ""
            lines.append(
                f"- id={program.pk}: {program.name} · {program.university.name}{country} · "
                f"{program.get_level_display()}"
                + (f" · пороги: {', '.join(limits)}" if limits else " · порогов в каталоге нет")  # i18n-skip: промпт ИИ
            )
    else:
        lines.append("Программ в каталоге школы пока нет: список программ оставь пустым.")  # i18n-skip: промпт ИИ
    lines.append("")
    lines.append(
        f"Профиль интересов — по каждой шкале из списков выше, все {scales}, в том же порядке."
    )  # i18n-skip: промпт ИИ
    if strong:
        lines.append(
            "Назови от двух до четырёх направлений; каждое — на сильной шкале, "
            "одна сильная шкала может дать несколько направлений."
        )  # i18n-skip: промпт ИИ
    else:
        lines.append(
            "Сильных шкал нет: направлений не давай; профиль интересов и общий вывод напиши "
            "так же подробно и назови, к чему можно присмотреться."
        )  # i18n-skip: промпт ИИ
    if with_thresholds:
        lines.append(
            "Цифры порогов — только из списка программ выше; балл ученика сравни с порогом подходящих программ."
        )  # i18n-skip: промпт ИИ
    else:
        lines.append(
            "Порогов в каталоге нет: экзамены назови без цифр и напиши «пороги — по программам в каталоге»."
        )  # i18n-skip: промпт ИИ
    return "\n".join(lines)


def plan(students: list[Student], tests: list, *, force: bool = False) -> Plan:
    """Кому разбор нужен: у ученика сданы все выбранные тесты и набор ещё не разбирался."""
    from career.services import done_attempts

    create: list[tuple[Student, list[CareerAttempt]]] = []
    reuse: list[CareerAnalysis] = []
    skipped: list[tuple[Student, str]] = []
    wanted = {test.pk for test in tests}
    for student in students:
        attempts = list(done_attempts(student, tests))
        have = {attempt.test_id for attempt in attempts}
        if have != wanted:
            skipped.append((student, _("сданы не все выбранные тесты")))
            continue
        if not any(profile_lines(attempt) for attempt in attempts):
            skipped.append((student, _("ни одна шкала не выше порога — разбирать нечего")))
            continue
        key = fingerprint_of(attempts)
        existing = (
            CareerAnalysis.objects.filter(student=student, fingerprint=key)
            .exclude(status__in=(AnalysisStatus.FAILED, AnalysisStatus.CANCELLED))
            .first()
        )
        if existing is not None and not force:
            reuse.append(existing)
            continue
        create.append((student, attempts))
    return Plan(create=create, reuse=reuse, skipped=skipped)


@transaction.atomic
def open_analysis(student: Student, attempts: list[CareerAttempt], *, actor, language: str) -> CareerAnalysis:
    row = CareerAnalysis.objects.create(
        student=student, fingerprint=fingerprint_of(attempts), created_by=actor, language=language, rules=RULES
    )
    row.attempts.set(attempts)
    return row


def _text(value) -> str:
    """Поле ответа модели строкой: список шагов — по строке на шаг."""
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def run(analysis: CareerAnalysis) -> CareerAnalysis:
    """Один вызов модели; ошибка остаётся у разбора с причиной."""
    from core.i18n import active_language, render
    from suggestions.llm import LLMUnavailable, complete

    student = analysis.student
    attempts = list(analysis.attempts.select_related("test").order_by("finished_at", "id"))
    programs = _candidates(student)
    known = {program.pk: program for program in programs}
    lines = [(attempt.test.title, line) for attempt in attempts for line in profile(attempt)]
    strong = {_key(line.title) for _test, line in lines if line.strong}
    try:
        answer = complete(
            language=active_language(),
            system=SYSTEM,
            user=_prompt(student, attempts, programs),
            purpose="career_test",
            actor=analysis.created_by,
            role=getattr(analysis.created_by, "role", ""),
            schema=RESULT_SCHEMA,
            max_tokens=MAX_TOKENS,
        )
    except LLMUnavailable as error:
        analysis.status = AnalysisStatus.FAILED
        analysis.error = (str(error) or render(analysis.language, "Модель сейчас недоступна"))[:300]
        analysis.finished_at = timezone.now()
        analysis.save(update_fields=["status", "error", "finished_at"])
        return analysis

    parsed = answer.parsed if isinstance(answer.parsed, dict) else {}
    rows = parsed.get("directions")
    analysis.summary = _text(parsed.get("summary"))
    # сильных шкал нет — направлений нет, даже если модель их прислала: подробный профиль и вывод
    if not strong:
        rows = []
    empty = not analysis.summary or (bool(strong) and (not isinstance(rows, list) or not rows))
    if empty:
        analysis.status = AnalysisStatus.FAILED
        analysis.error = render(analysis.language, "Модель вернула пустой разбор — попробуйте пересчитать")
        analysis.finished_at = timezone.now()
        analysis.save(update_fields=["summary", "status", "error", "finished_at"])
        return analysis

    save_profile(analysis, lines, parsed.get("profile"))
    order = 0
    for item in rows:
        if order >= MAX_DIRECTIONS:
            break
        if not isinstance(item, dict) or not _text(item.get("title")):
            continue
        # направление только из средних шкал не бывает: без опоры на сильную шкалу — отброшено
        basis = item.get("scales") if isinstance(item.get("scales"), list) else []
        if not any(_key(title) in strong for title in basis):
            continue
        order += 1
        direction = CareerAnalysisDirection.objects.create(
            analysis=analysis,
            order=order,
            title=_text(item["title"])[:150],
            title_abroad=_text(item.get("title_abroad"))[:150],
            reasoning=_text(item.get("reasoning")),
            professions=_text(item.get("professions")),
            exams=_text(item.get("exams")),
            subjects=_text(item.get("subjects")),
            next_steps=_text(item.get("next_steps")),
        )
        picked = [known[pid] for pid in (item.get("programs") or []) if isinstance(pid, int) and pid in known]
        if picked:
            direction.programs.set(picked)
    if strong and order == 0:
        analysis.status = AnalysisStatus.FAILED
        analysis.error = render(analysis.language, "Разбор пришёл без направлений — попробуйте пересчитать")
    else:
        analysis.status = AnalysisStatus.DONE
        analysis.error = ""
    analysis.finished_at = timezone.now()
    analysis.save(update_fields=["summary", "status", "error", "finished_at"])
    return analysis


def save_profile(analysis: CareerAnalysis, lines: list[tuple[str, ScaleLine]], answer) -> None:
    """Профиль интересов: строка на каждую шкалу теста, смысл — из ответа модели по названию.

    Шкалы и баллы — из попыток, а не из ответа: модель пропустила шкалу —
    строка всё равно есть, с баллом и подписью, без объяснения. Одинаковые
    названия в разных тестах разбираются по порядку.
    """
    meanings: dict[str, list[str]] = {}
    for item in answer if isinstance(answer, list) else []:
        if isinstance(item, dict) and _text(item.get("meaning")):
            meanings.setdefault(_key(item.get("scale") or ""), []).append(_text(item.get("meaning")))

    def meaning_of(title: str) -> str:
        queue = meanings.get(_key(title))
        return queue.pop(0) if queue else ""

    CareerAnalysisScale.objects.bulk_create(
        CareerAnalysisScale(
            analysis=analysis,
            order=order,
            test_title=test_title[:200],
            title=line.title[:120],
            score=line.score,
            top=line.top,
            label=line.label[:120],
            meaning=meaning_of(line.title),
        )
        for order, (test_title, line) in enumerate(lines, start=1)
    )


# --- версия для ученика -----------------------------------------------------------------

# fmt: off
STUDENT_SYSTEM = (  # i18n-skip: промпт ИИ — язык ответа модели настраивается отдельно
    """Ты переписываешь разбор результатов тестов профориентации так, чтобы его читал сам ученик.
Школа в Казахстане готовит учеников к поступлению в зарубежные вузы.

Правила, нарушать нельзя:
- обращайся к ученику на «ты»; пиши о его интересах и сильных сторонах: «у тебя выраженный
  интерес к…», «тебе может подойти…»;
- сохрани подробность: каждая часть не короче исходной — общий вывод те же шесть–десять
  предложений, «почему подходит» те же четыре–шесть, в профиле интересов — каждая шкала
  с тем же смыслом. Не сокращай и не обобщай, только перепиши для ученика;
- не упоминай учителя, обсуждение, родителей, «стоит рассмотреть с учеником» и любые
  слова, обращённые к кому-то, кроме ученика;
- сохрани смысл, направления, профессии, экзамены, предметы и шаги: ничего не добавляй
  и не убирай; новых направлений и новых цифр порогов не придумывай;
- местные выпускные и вступительные экзамены (ЕНТ, ОГЭ, ЕГЭ и подобные) не упоминай никогда;
- не обещай поступление и не употребляй слова «шанс», «вероятность», «прогноз»;
- не оценивай ученика как человека, не ставь диагнозов;
- пиши тепло и понятно, простыми словами, но не коротко; без общих фраз и без служебных
  слов — без названий полей, «переданных результатов», «справочника»."""
)
# fmt: on

STUDENT_SCHEMA = {  # i18n-skip: схема ответа для модели ИИ
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "общий вывод для ученика, на «ты», не короче исходного"},
        "profile": {
            "type": "array",
            "description": "профиль интересов для ученика — по каждой шкале из переданного разбора",
            "items": {
                "type": "object",
                "properties": {
                    "order": {"type": "integer", "description": "номер шкалы из переданного разбора"},
                    "meaning": {"type": "string", "description": "что значит балл — для ученика, на «ты»"},
                },
                "required": ["order", "meaning"],
            },
        },
        "directions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "order": {"type": "integer", "description": "номер направления из переданного разбора"},
                    "why": {
                        "type": "string",
                        "description": "почему подходит — для ученика, на «ты», не короче исходного",
                    },
                },
                "required": ["order", "why"],
            },
        },
    },
    "required": ["summary", "profile", "directions"],
}


def _student_prompt(analysis: CareerAnalysis) -> str:
    # i18n-skip: промпт ИИ — текст запроса модели, не интерфейс
    lines = ["Разбор для учителя:", f"Общий вывод: {analysis.summary}"]  # i18n-skip: промпт ИИ
    scales = list(analysis.scales.all())
    if scales:
        lines.append("")
        lines.append("Профиль интересов:")  # i18n-skip: промпт ИИ
        for scale in scales:
            mark = f"{scale.score}" + (f" из {scale.top}" if scale.top else "")
            lines.append(
                f"Шкала {scale.order}: {scale.title}, {mark}"
                + (f" — {scale.label}" if scale.label else "")
                + (f": {scale.meaning}" if scale.meaning else "")
            )  # i18n-skip: промпт ИИ
    for direction in analysis.directions.all():
        lines.append("")
        lines.append(
            f"Направление {direction.order}: {direction.title}"
            + (f" ({direction.title_abroad})" if direction.title_abroad else "")
        )  # i18n-skip: промпт ИИ
        lines.append(f"Почему подходит: {direction.reasoning}")  # i18n-skip: промпт ИИ
        # i18n-skip: подписи строк запроса модели
        for label, value in (
            ("Профессии", direction.professions),
            ("Что сдавать для поступления", direction.exams),
            ("Что подтянуть в школе", direction.subjects),
            ("Что сделать уже сейчас", direction.next_steps),
        ):
            if value:
                lines.append(f"{label}: {value}")
    lines.append("")
    lines.append(
        "Перепиши общий вывод, смысл каждой шкалы профиля и объяснение каждого направления для ученика."
    )  # i18n-skip: промпт ИИ
    return "\n".join(lines)


class StudentVersionUnavailable(RuntimeError):
    """Версию для ученика написать не удалось — причина словами."""


def write_student_version(analysis: CareerAnalysis, *, actor) -> CareerAnalysis:
    """Переписать готовый разбор для ученика — один вызов, результат хранится рядом.

    Вызывается при первом «Показать ученику»; повторный показ версию не переписывает,
    «Пересчитать» заводит новый разбор, и версия пишется заново.
    """
    from core.i18n import active_language, render
    from suggestions.llm import LLMUnavailable, complete

    if analysis.status != AnalysisStatus.DONE:
        raise StudentVersionUnavailable(_("Показать ученику можно только готовый разбор"))
    try:
        answer = complete(
            language=active_language(),
            system=STUDENT_SYSTEM,
            user=_student_prompt(analysis),
            purpose="career_test",
            actor=actor,
            role=getattr(actor, "role", ""),
            schema=STUDENT_SCHEMA,
            max_tokens=MAX_TOKENS,
        )
    except LLMUnavailable as error:
        raise StudentVersionUnavailable(str(error) or render(analysis.language, "Модель сейчас недоступна")) from error
    parsed = answer.parsed if isinstance(answer.parsed, dict) else {}
    summary = str(parsed.get("summary") or "").strip()
    rows = parsed.get("directions")
    if not summary or not isinstance(rows, list):
        raise StudentVersionUnavailable(
            render(analysis.language, "Модель вернула пустой разбор — попробуйте пересчитать")
        )
    by_order = {d.order: d for d in analysis.directions.all()}
    for item in rows:
        if not isinstance(item, dict):
            continue
        direction = by_order.get(item.get("order"))
        if direction is None:
            continue
        direction.reasoning_student = str(item.get("why") or "").strip()
        direction.save(update_fields=["reasoning_student"])
    by_scale = {scale.order: scale for scale in analysis.scales.all()}
    for item in parsed.get("profile") if isinstance(parsed.get("profile"), list) else []:
        scale = by_scale.get(item.get("order")) if isinstance(item, dict) else None
        if scale is None:
            continue
        scale.meaning_student = str(item.get("meaning") or "").strip()
        scale.save(update_fields=["meaning_student"])
    analysis.summary_student = summary
    analysis.save(update_fields=["summary_student"])
    return analysis
