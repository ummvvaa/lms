"""Подбор вузов по словесному запросу ученика.

Инвариант №10 держится не промптом, а кодом: модель получает список
программ из справочника и может ссылаться на них только по идентификаторам.
Всё, чего нет в переданном списке, из ответа выбрасывается — выдумать вуз
физически нечем.

Без подключённой модели подбор всё равно работает: фильтры разбираются
правилами, объяснения собираются из движка соответствия. Школа не должна
вставать из-за недоступного провайдера.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from students.models import Student
from suggestions.llm import LLMUnavailable, complete, is_configured
from suggestions.name_matching import normalize, stem
from universities.catalog import CatalogFilters, apply_filters, base_queryset, program_card
from universities.models import Program

#: Сколько программ показываем в подборке.
TOP_N = 6

#: Сколько программ отдаём модели. Больше — лишний контекст и лишние деньги.
CANDIDATES = 40

SYSTEM = """Ты подбираешь ученику программы из справочника школы.

Правила, нарушать нельзя:
- выбирай ТОЛЬКО из переданного списка программ и ссылайся на них по полю id;
- ничего не добавляй от себя: вуза, которого нет в списке, не существует;
- не обещай вероятность поступления и не употребляй слова «шанс», «прогноз»,
  «вероятность» — есть только соответствие требованиям в процентах;
- по каждой позиции скажи: почему подходит, чего не хватает, какой раунд ближайший;
- пиши по-русски, коротко и по делу.
"""

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "id программы из переданного списка"},
                    "why": {"type": "string", "description": "почему подходит"},
                    "missing": {"type": "string", "description": "чего не хватает"},
                },
                "required": ["id", "why"],
            },
        },
        "note": {"type": "string", "description": "общее замечание, если данных мало"},
    },
    "required": ["picks"],
}

#: Слова, которых в подборке быть не должно (инвариант №11).
FORBIDDEN = re.compile(r"шанс|вероятност|прогноз", re.IGNORECASE)


@dataclass
class Picked:
    """Одна позиция подборки."""

    card: dict
    why: str = ""
    missing: str = ""

    def as_dict(self) -> dict:
        payload = dict(self.card)
        payload["why"] = self.why
        payload["missing"] = self.missing
        payload["next_round"] = _next_round(self.card)
        return payload


@dataclass
class PickResult:
    """Результат подбора: позиции, пояснение и признак офлайна."""

    picks: list[Picked] = field(default_factory=list)
    note: str = ""
    offline: bool = False
    filters: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "picks": [p.as_dict() for p in self.picks],
            "note": self.note,
            "offline": self.offline,
            "filters": self.filters,
        }


def _next_round(card: dict) -> dict | None:
    """Ближайший раунд. Дедлайн берётся из справочника, а не сочиняется."""
    rounds = card.get("rounds") or []
    return rounds[0] if rounds else None


#: Страны, о которых спрашивают ученики. Это справочник слов, а не вузов:
#: он нужен, чтобы отличить «нет такой страны в нашем справочнике»
#: от «в запросе вообще не было страны» (инвариант №10).
COUNTRY_WORDS = (
    "Австралия",
    "Австрия",
    "Азербайджан",
    "Великобритания",
    "Венгрия",
    "Германия",
    "Гонконг",
    "Дания",
    "Израиль",
    "Ирландия",
    "Испания",
    "Италия",
    "Казахстан",
    "Канада",
    "Катар",
    "Китай",
    "Корея",
    "Латвия",
    "Литва",
    "Малайзия",
    "Нидерланды",
    "Новая Зеландия",
    "Норвегия",
    "ОАЭ",
    "Польша",
    "Россия",
    "Сингапур",
    "США",
    "Турция",
    "Финляндия",
    "Франция",
    "Чехия",
    "Швейцария",
    "Швеция",
    "Эстония",
    "Южная Корея",
    "Япония",
)

#: Как ученики называют специальности по-русски. Таблица перевода, не выдумка:
#: сами программы по-прежнему берутся только из справочника.
MAJOR_WORDS = {
    "экономика": "Economics",
    "экономику": "Economics",
    "финансы": "Economics",
    "информатика": "Computer Science",
    "программирование": "Computer Science",
    "компьютерные науки": "Computer Science",
    "инженерия": "Engineering",
    "инженер": "Engineering",
    "бизнес": "Business",
    "менеджмент": "Business Management",
    "математика": "Mathematics",
    "данные": "Data Science",
    "аналитика данных": "Data Science",
    "авиация": "Aerospace Engineering",
    # ниже — то, чего в справочнике школы обычно нет. Слова нужны, чтобы
    # ответить «таких данных нет», а не подсунуть что-то похожее
    "медицина": "Medicine",
    "право": "Law",
    "юриспруденция": "Law",
    "психология": "Psychology",
    "дизайн": "Design",
    "архитектура": "Architecture",
    "журналистика": "Journalism",
    "биология": "Biology",
    "химия": "Chemistry",
    "физика": "Physics",
}


def _stems(text: str) -> set[str]:
    """Основы слов запроса — чтобы «Канаду» нашлось по «Канада»."""
    return {stem(word) for word in normalize(text).split() if word}


def _same_root(a: str, b: str) -> bool:
    """Одно ли это слово в разных падежах.

    `stem()` режет окончания грубо: «Япония» даёт `yaponiy`, «Японии» —
    `yaponi`. Сравниваем по общему началу, иначе падеж ломает поиск.
    """
    if not a or not b:
        return False
    shorter, longer = sorted((a, b), key=len)
    return len(shorter) >= 4 and longer.startswith(shorter)


def _match_word(text: str, candidates) -> str:
    """Найти в запросе одно из известных слов, не спотыкаясь о падежи."""
    words = _stems(text)
    lowered = normalize(text)
    for candidate in candidates:
        normalized = normalize(candidate)
        if normalized in lowered:
            return candidate
        parts = normalized.split()
        if all(any(_same_root(stem(part), word) for word in words) for part in parts):
            return candidate
    return ""


def parse_request(text: str, known_countries: list[str], known_majors: list[str]) -> CatalogFilters:
    """Разобрать словесный запрос правилами: страна и специальность.

    Это же работает и без модели — фильтры остаются рабочими всегда.
    """
    country = _match_word(text, known_countries)
    major = _match_word(text, known_majors)
    if not major:
        russian = _match_word(text, MAJOR_WORDS.keys())
        if russian:
            candidate = MAJOR_WORDS[russian]
            major = candidate if candidate in known_majors else ""
    return CatalogFilters(country=country, major=major)


def unknown_request(text: str, known_countries: list[str], known_majors: list[str]) -> str:
    """Чего ученик попросил, а в справочнике этого нет.

    Возвращает человеческое название — страну или специальность, — чтобы
    сказать прямо: данных нет. Выдумывать замену мы не имеем права.
    """
    filters = parse_request(text, known_countries, known_majors)
    if not filters.country:
        country = _match_word(text, COUNTRY_WORDS)
        if country and country not in known_countries:
            return country
    if not filters.major:
        russian = _match_word(text, MAJOR_WORDS.keys())
        if russian and MAJOR_WORDS[russian] not in known_majors:
            # отвечаем тем словом, которое написал ученик, а не переводом
            return russian
    return ""


def _catalog_for(student: Student, filters: CatalogFilters) -> list[dict]:
    programs = apply_filters(base_queryset(), filters)
    cards = [program_card(student, program) for program in programs]
    cards.sort(key=lambda c: (-c["percent"], c["university_name"]))
    return cards


def _offline_reason(card: dict) -> tuple[str, str]:
    """Почему подходит и чего не хватает — словами движка соответствия."""
    if not card["has_requirements"]:
        return ("Требования этой программы ещё не заведены в справочнике", "")
    if card["is_open"]:
        return ("Вы проходите по всем заведённым требованиям", "")
    return (f"Соответствие требованиям {card['percent']}%", card["summary"])


def pick(*, student: Student, text: str, actor=None) -> PickResult:
    """Подобрать программы под словесный запрос."""
    from universities.catalog import facets

    known = facets()
    filters = parse_request(text, known["countries"], known["majors"])
    missing = unknown_request(text, known["countries"], known["majors"])
    cards = [] if missing else _catalog_for(student, filters)

    result = PickResult(filters={"country": filters.country, "major": filters.major})

    if not cards:
        # честный отказ вместо выдумки: справочник по этому запросу пуст
        asked = missing or " и ".join(x for x in (filters.country, filters.major) if x) or text.strip()
        fallback = _catalog_for(student, CatalogFilters())
        result.note = f"В справочнике школы нет программ по запросу «{asked}». " + (
            "Вот что в нём есть — попросите директора по поступлению добавить нужные вузы."
            if fallback
            else "Справочник вузов ещё не наполнен — обратитесь к директору по поступлению."
        )
        result.picks = [Picked(card=card, why=_offline_reason(card)[0]) for card in fallback[:TOP_N]]
        result.offline = not is_configured()
        return result

    by_id = {card["program"]: card for card in cards}

    if not is_configured():
        result.offline = True
        result.note = "Подобрано фильтрами и движком соответствия: модель не подключена."
        for card in cards[:TOP_N]:
            why, missing = _offline_reason(card)
            result.picks.append(Picked(card=card, why=why, missing=missing))
        return result

    listing = "\n".join(
        f"- id={card['program']}: {card['university_name']} ({card['country']}) — {card['program_name']}; "
        f"соответствие {card['percent']}%; {card['summary']}"
        for card in cards[:CANDIDATES]
    )
    profile = _profile_line(student)

    try:
        response = complete(
            system=SYSTEM,
            user=(
                f"Запрос ученика: {text.strip()}\n\n"
                f"Профиль: {profile}\n\n"
                f"Программы справочника (выбирать только отсюда):\n{listing}"
            ),
            purpose="university_pick",
            actor=actor,
            schema=RESULT_SCHEMA,
        )
    except LLMUnavailable:
        return pick_offline(student=student, text=text, cards=cards)

    payload = response.parsed or {}
    for row in payload.get("picks", [])[:TOP_N]:
        card = by_id.get(row.get("id"))
        if card is None:
            # модель назвала программу вне справочника — молча отбрасываем
            continue
        result.picks.append(Picked(card=card, why=_clean(row.get("why", "")), missing=_clean(row.get("missing", ""))))
    result.note = _clean(payload.get("note", ""))

    if not result.picks:
        return pick_offline(student=student, text=text, cards=cards)
    return result


def pick_offline(*, student: Student, text: str, cards: list[dict] | None = None) -> PickResult:
    """Подбор без модели — тем же кодом, что и основной путь."""
    from universities.catalog import facets

    known = facets()
    filters = parse_request(text, known["countries"], known["majors"])
    cards = cards if cards is not None else _catalog_for(student, filters)

    result = PickResult(
        offline=True,
        note="Подобрано фильтрами и движком соответствия: модель недоступна.",
        filters={"country": filters.country, "major": filters.major},
    )
    for card in cards[:TOP_N]:
        why, missing = _offline_reason(card)
        result.picks.append(Picked(card=card, why=why, missing=missing))
    return result


def _clean(text: str) -> str:
    """Убрать из текста запрещённые формулировки (инвариант №11)."""
    if not text:
        return ""
    if FORBIDDEN.search(text):
        return FORBIDDEN.sub("соответствие требованиям", text)
    return text


def _profile_line(student: Student) -> str:
    """Ровно те поля, что нужны задаче: профиль целиком в модель не уходит."""
    exam = getattr(student, "exam", None)
    admission = getattr(student, "admission", None)
    parts = []
    if exam:
        if exam.ielts_current:
            parts.append(f"IELTS {exam.ielts_current}")
        if exam.sat_current:
            parts.append(f"SAT {exam.sat_current}")
        if exam.gpa:
            parts.append(f"GPA {exam.gpa}")
    if admission and admission.target_country:
        parts.append(f"цель — {admission.target_country}")
    return ", ".join(parts) or "баллы ещё не заведены"


def known_program_ids() -> set[int]:
    """Идентификаторы справочника — по ним проверяется ответ модели."""
    return set(Program.objects.filter(is_active=True).values_list("id", flat=True))
