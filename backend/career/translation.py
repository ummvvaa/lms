"""Перевод разбора и «Общая картина по всем тестам» — для выгрузки в Word.

Разбор пишется на языке того, кто его запускал; Word можно скачать на любом
из трёх языков. Перевод делается моделью один раз и хранится строками
`CareerAnalysisTranslation` (и шкалы, и направления — по порядку в разборе),
оригинал не трогается. Повторная выгрузка на том же языке модель не зовёт.
Профориентолог правил разбор после перевода (`edited_at` позже перевода) —
перевод устарел и делается заново.

«Общая картина» связывает готовые разборы ученика: что повторяется в разных
тестах, где они согласуются и расходятся, какие направления подтверждаются
несколькими тестами. Пишется сразу на языке выгрузки и хранится по языку
(`CareerOverview`), пока набор разборов и их правки не изменились (`basis`).

Обе задачи — модели с теми же запретами, что у разбора: без местных
экзаменов, без «шанса» и «вероятности», без новых цифр и направлений.
Казахский — по глоссарию школы: термины заданы в `GLOSSARY`.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from career.models import (
    CareerAnalysis,
    CareerAnalysisTranslation,
    CareerDirectionTranslation,
    CareerOverview,
    CareerScaleTranslation,
)
from career.word import AnalysisText, OverviewText

#: предел ответа: перевод — примерно та же длина, что разбор (`analysis.MAX_TOKENS`)
MAX_TOKENS = 16000
OVERVIEW_TOKENS = 6000

#: Термины школы для перевода — из глоссария ru — kk — en, их модель берёт как есть
GLOSSARY = """Термины школы — переводи только так:
- Mock Test — «Mock Test» на всех языках, слово «пробник» не используется;
- ФО, СОР, СОЧ — kk: ҚБ, БЖБ, ТЖБ; en: FA, SAU, Term SA;
- четверть — kk: тоқсан; en: term; параллель, класс — kk: сынып; en: grade;
- вуз — kk: ЖОО; en: university; программа вуза — kk: бағдарлама; en: programme;
- профтест — kk: кәсіптік тест; en: career test; портфолио — kk: портфолио; en: portfolio;
- олимпиада — kk: олимпиада; en: olympiad; летняя школа — kk: жазғы мектеп; en: summer school;
- предметы подготовки школы (SAT Math, SAT Verbal, EEP, General English) — как есть."""  # i18n-skip: промпт ИИ

# fmt: off
TRANSLATE_SYSTEM = (  # i18n-skip: промпт ИИ — язык ответа модели задаётся отдельно
    """Ты переводишь разбор результатов тестов профориентации частной школы в Казахстане,
которая готовит учеников к поступлению в зарубежные вузы. Разбор читают профориентолог
и родители ученика.

Правила, нарушать нельзя:
- переводи всё: общий вывод, названия тестов и шкал, подписи диапазонов, смысл каждой
  шкалы, названия направлений и все их части — ничего не пропускай и не добавляй;
- смысл и цифры не меняй: баллы, пороги, даты, классы и годы остаются как есть;
  не сокращай и не обобщай — перевод не короче оригинала;
- не переводи названия вузов и программ, английские названия специальностей, IELTS,
  TOEFL, SAT, ACT, GPA, Duolingo, Common App, Mock Test;
- местные выпускные и вступительные экзамены (ЕНТ, ОГЭ, ЕГЭ и подобные) не упоминай;
- не употребляй слова «шанс», «вероятность», «прогноз» (по-казахски — «мүмкіндік»,
  «ықтималдық», по-английски — «chance», «probability», «prediction»);
- строки, которые в оригинале идут с новой строки, в переводе тоже с новой строки;
- казахский — литературный, обращение на «Сіз», без кальки с русского порядка слов;
  английский — британский школьный.

"""
    + GLOSSARY
)

OVERVIEW_SYSTEM = (  # i18n-skip: промпт ИИ — язык ответа модели задаётся отдельно
    """Ты — профориентолог частной школы в Казахстане, которая готовит учеников к поступлению
в зарубежные вузы. Ученик прошёл несколько тестов профориентации, по каждому есть готовый
разбор. Напиши общую картину по всем тестам — её читают профориентолог и родители ученика.

Четыре части, каждая — три–шесть предложений:
- что повторяется в разных тестах: интересы и сильные стороны, которые видны больше чем
  в одном тесте, с названиями тестов и шкал;
- где тесты согласуются: какие выводы разных тестов подтверждают друг друга;
- где тесты расходятся: в чём разборы дают разную картину и как это понимать; не расходятся —
  так и напиши;
- какие направления подтверждаются несколькими тестами: направления из разборов, которые
  опираются на результаты больше чем одного теста; таких нет — так и напиши.

Правила, нарушать нельзя:
- опирайся только на разборы ниже; ничего не додумывай о личности ученика; новых направлений,
  программ, вузов и цифр, которых нет в разборах, не называй;
- цифры порогов (IELTS, TOEFL, SAT, ACT, GPA) — только те, что уже есть в разборах;
- местные выпускные и вступительные экзамены (ЕНТ, ОГЭ, ЕГЭ и подобные) не упоминай никогда;
- не обещай поступление и не употребляй слова «шанс», «вероятность», «прогноз»;
- не ставь диагнозов и не оценивай ученика как человека: пиши об интересах и сильных сторонах;
- пиши понятно для родителя, простыми словами, но не коротко; без служебных слов.

"""
    + GLOSSARY
)
# fmt: on

TRANSLATE_SCHEMA = {  # i18n-skip: схема ответа для модели ИИ
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "общий вывод в переводе"},
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"order": {"type": "integer"}, "title": {"type": "string"}},
                "required": ["order", "title"],
            },
        },
        "scales": {
            "type": "array",
            "description": "каждая шкала профиля, по номеру из оригинала",
            "items": {
                "type": "object",
                "properties": {
                    "order": {"type": "integer"},
                    "title": {"type": "string"},
                    "label": {"type": "string"},
                    "meaning": {"type": "string"},
                },
                "required": ["order", "title"],
            },
        },
        "directions": {
            "type": "array",
            "description": "каждое направление, по номеру из оригинала",
            "items": {
                "type": "object",
                "properties": {
                    "order": {"type": "integer"},
                    "title": {"type": "string"},
                    "reasoning": {"type": "string"},
                    "professions": {"type": "string"},
                    "exams": {"type": "string"},
                    "subjects": {"type": "string"},
                    "next_steps": {"type": "string"},
                },
                "required": ["order", "title"],
            },
        },
    },
    "required": ["summary", "scales", "directions"],
}

OVERVIEW_SCHEMA = {  # i18n-skip: схема ответа для модели ИИ
    "type": "object",
    "properties": {
        "repeats": {"type": "string", "description": "что повторяется в разных тестах"},
        "agreements": {"type": "string", "description": "где тесты согласуются"},
        "differences": {"type": "string", "description": "где тесты расходятся"},
        "confirmed": {"type": "string", "description": "какие направления подтверждаются несколькими тестами"},
    },
    "required": ["repeats", "agreements", "differences", "confirmed"],
}

DIRECTION_FIELDS = ("title", "reasoning", "professions", "exams", "subjects", "next_steps")


class TranslationFailed(RuntimeError):
    """Перевод или общая картина не получились — причина словами."""


def _text(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def changed_at(analysis: CareerAnalysis):
    """Когда текст разбора стал таким, как сейчас: последняя правка или готовность."""
    return analysis.edited_at or analysis.finished_at or analysis.created_at


# --- Перевод ---------------------------------------------------------------------------


def fresh_translation(analysis: CareerAnalysis, language: str) -> CareerAnalysisTranslation | None:
    """Сохранённый перевод, если разбор после него не правили."""
    row = analysis.translations.filter(language=language).first()
    if row is None or row.created_at < changed_at(analysis):
        return None
    return row


def _translate_prompt(text: AnalysisText) -> str:
    # i18n-skip: промпт ИИ — текст запроса модели, не интерфейс
    lines = ["Разбор для перевода.", "", f"Общий вывод: {text.summary}", ""]  # i18n-skip: промпт ИИ
    for order, title in enumerate(dict.fromkeys(scale.test for scale in text.scales), start=1):
        lines.append(f"Тест {order}: {title}")  # i18n-skip: промпт ИИ
    lines.append("")
    for order, scale in enumerate(text.scales, start=1):
        lines.append(
            f"Шкала {order}: {scale.title} | диапазон: {scale.label or '—'} | смысл: {scale.meaning or '—'}"
        )  # i18n-skip: промпт ИИ
    for order, direction in enumerate(text.directions, start=1):
        lines.append("")
        lines.append(f"Направление {order}:")  # i18n-skip: промпт ИИ
        # i18n-skip: подписи строк запроса модели
        for label, value in (
            ("Название", direction.title),
            ("Почему подходит", direction.reasoning),
            ("Профессии", direction.professions),
            ("Что сдавать для поступления", direction.exams),
            ("Что подтянуть в школе", direction.subjects),
            ("Что сделать уже сейчас", direction.next_steps),
        ):
            lines.append(f"{label}: {value}")
    lines.append("")
    lines.append(
        "Переведи общий вывод, каждый тест, каждую шкалу и каждое направление по номеру; "
        "у шкалы, где диапазона или смысла нет («—»), оставь пустую строку."
    )  # i18n-skip: промпт ИИ
    return "\n".join(lines)


def translate(analysis: CareerAnalysis, text: AnalysisText, language: str, *, actor) -> CareerAnalysisTranslation:
    """Перевести разбор моделью и сохранить; прежний перевод на этот язык заменяется."""
    from core.i18n import render
    from suggestions.llm import LLMUnavailable, complete

    try:
        answer = complete(
            language=language,
            system=TRANSLATE_SYSTEM,
            user=_translate_prompt(text),
            purpose="career_test",
            actor=actor,
            role=getattr(actor, "role", ""),
            schema=TRANSLATE_SCHEMA,
            max_tokens=MAX_TOKENS,
        )
    except LLMUnavailable as error:
        raise TranslationFailed(str(error) or render(language, "Модель сейчас недоступна")) from error
    parsed = answer.parsed if isinstance(answer.parsed, dict) else {}
    summary = _text(parsed.get("summary"))
    if not summary and _text(text.summary):
        raise TranslationFailed(_("Модель вернула пустой перевод"))
    tests = {
        item.get("order"): _text(item.get("title"))
        for item in parsed.get("tests") or []
        if isinstance(item, dict) and _text(item.get("title"))
    }
    scales = {item.get("order"): item for item in parsed.get("scales") or [] if isinstance(item, dict)}
    directions = {item.get("order"): item for item in parsed.get("directions") or [] if isinstance(item, dict)}
    titles = {title: tests.get(order, "") for order, title in enumerate(dict.fromkeys(s.test for s in text.scales), 1)}
    with transaction.atomic():
        analysis.translations.filter(language=language).delete()
        row = CareerAnalysisTranslation.objects.create(analysis=analysis, language=language, summary=summary)
        CareerScaleTranslation.objects.bulk_create(
            CareerScaleTranslation(
                translation=row,
                order=order,
                test_title=titles.get(scale.test, "")[:200],
                title=_text(scales.get(order, {}).get("title"))[:120],
                label=_text(scales.get(order, {}).get("label"))[:120],
                meaning=_text(scales.get(order, {}).get("meaning")),
            )
            for order, scale in enumerate(text.scales, start=1)
        )
        CareerDirectionTranslation.objects.bulk_create(
            CareerDirectionTranslation(
                translation=row,
                order=order,
                **{name: _text(directions.get(order, {}).get(name)) for name in DIRECTION_FIELDS},
            )
            for order in range(1, len(text.directions) + 1)
        )
    return row


def apply(text: AnalysisText, row: CareerAnalysisTranslation) -> AnalysisText:
    """Разбор в переводе; чего модель не перевела — остаётся оригиналом."""
    from dataclasses import replace

    scales = {item.order: item for item in row.scales.all()}
    directions = {item.order: item for item in row.directions.all()}
    tests = {}
    out_scales = []
    for order, scale in enumerate(text.scales, start=1):
        item = scales.get(order)
        if item is None:
            out_scales.append(scale)
            continue
        if item.test_title:
            tests.setdefault(scale.test, item.test_title)
        out_scales.append(
            replace(
                scale,
                test=item.test_title or scale.test,
                title=item.title or scale.title,
                label=item.label or scale.label,
                meaning=item.meaning or scale.meaning,
            )
        )
    out_directions = []
    for order, direction in enumerate(text.directions, start=1):
        item = directions.get(order)
        changes = {name: getattr(item, name) for name in DIRECTION_FIELDS if item and getattr(item, name)}
        out_directions.append(replace(direction, **changes))
    return replace(
        text,
        summary=row.summary or text.summary,
        tests=[(tests.get(title, title), when) for title, when in text.tests],
        scales=out_scales,
        directions=out_directions,
    )


# --- Общая картина -------------------------------------------------------------------------


def basis_of(analyses: list[CareerAnalysis]) -> str:
    """Набор разборов и их правки: изменилось что-то — общая картина пишется заново."""
    return ";".join(f"{row.pk}:{changed_at(row).timestamp():.0f}" for row in analyses)[:400]


def fresh_overview(student, analyses: list[CareerAnalysis], language: str) -> CareerOverview | None:
    row = CareerOverview.objects.filter(student=student, language=language).first()
    if row is None or row.basis != basis_of(analyses):
        return None
    return row


def _overview_prompt(texts: list[AnalysisText]) -> str:
    # i18n-skip: промпт ИИ — текст запроса модели, не интерфейс
    lines = []
    for order, text in enumerate(texts, start=1):
        lines.append(
            f"Разбор {order}: тесты — " + ", ".join(f"«{title}»" for title, _when in text.tests)
        )  # i18n-skip: промпт ИИ
        lines.append(f"Общий вывод: {text.summary}")  # i18n-skip: промпт ИИ
        lines.append("Профиль интересов:")  # i18n-skip: промпт ИИ
        for scale in text.scales:
            mark = f"{scale.score}" + (f" из {scale.top}" if scale.top else "")  # i18n-skip: промпт ИИ
            lines.append(
                f"- {scale.title} ({scale.test}): {mark}"
                + (" — сильная шкала" if scale.strong else "")  # i18n-skip: промпт ИИ
                + (f"; {scale.meaning}" if scale.meaning else "")
            )
        lines.append("Направления:")  # i18n-skip: промпт ИИ
        for direction in text.directions:
            abroad = f" ({direction.title_abroad})" if direction.title_abroad else ""
            lines.append(f"- {direction.title}{abroad}: {direction.reasoning}")
        lines.append("")
    lines.append("Напиши общую картину по всем тестам — четыре части.")  # i18n-skip: промпт ИИ
    return "\n".join(lines)


def write_overview(student, analyses: list[CareerAnalysis], texts: list[AnalysisText], language: str, *, actor):
    """Общая картина моделью, сразу на языке выгрузки; хранится по языку."""
    from core.i18n import render
    from suggestions.llm import LLMUnavailable, complete

    try:
        answer = complete(
            language=language,
            system=OVERVIEW_SYSTEM,
            user=_overview_prompt(texts),
            purpose="career_test",
            actor=actor,
            role=getattr(actor, "role", ""),
            schema=OVERVIEW_SCHEMA,
            max_tokens=OVERVIEW_TOKENS,
        )
    except LLMUnavailable as error:
        raise TranslationFailed(str(error) or render(language, "Модель сейчас недоступна")) from error
    parsed = answer.parsed if isinstance(answer.parsed, dict) else {}
    parts = {name: _text(parsed.get(name)) for name in ("repeats", "agreements", "differences", "confirmed")}
    if not any(parts.values()):
        raise TranslationFailed(_("Модель вернула пустую общую картину"))
    row, _created = CareerOverview.objects.update_or_create(
        student=student,
        language=language,
        defaults={**parts, "basis": basis_of(analyses), "created_at": timezone.now()},
    )
    return row


def overview_text(row: CareerOverview) -> OverviewText:
    return OverviewText(row.repeats, row.agreements, row.differences, row.confirmed)
