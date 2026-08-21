"""Сопоставление имён учеников.

Главный источник тихих ошибок: данные приходят на русском, казахском
и английском, со склонениями, инициалами и однофамильцами. Ошибка здесь
не видна — балл просто уезжает не тому ученику.

Поэтому матчер никогда не «догадывается» молча: он возвращает список
кандидатов с оценкой уверенности, и при неоднозначности решение принимает
человек в интерфейсе.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from students.models import Student

#: Уверенность, выше которой считаем совпадение однозначным.
CONFIDENT = 0.90
#: Ниже этого порога кандидат вообще не показывается.
FLOOR = 0.55
#: Насколько кандидат может отставать от лучшего, чтобы его ещё показывать.
#: Иначе в диалоге «выберите одного» появляется явно чужой человек.
LAG = 0.2

#: Транслитерация: одно и то же имя пишут кириллицей и латиницей.
TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    # казахские буквы
    "ә": "a",
    "ғ": "g",
    "қ": "k",
    "ң": "n",
    "ө": "o",
    "ұ": "u",
    "ү": "u",
    "һ": "h",
    "і": "i",
}

#: Окончания, которые отваливаются при склонении.
#: «Ахметову», «Ахметовой» и «Ахметова» — один человек.
#: Записаны кириллицей для читаемости, а сравниваются уже с транслитерацией:
#: `stem()` работает после `normalize()`, там текст латиницей.
_CASE_ENDINGS_RU = (
    "овой",
    "евой",
    "иной",
    "ому",
    "ова",
    "ева",
    "ову",
    "еву",
    "ой",
    "ым",
    "ем",
    "у",
    "е",
    "ю",
    "а",
    "ы",
    "и",
)


def normalize(text: str) -> str:
    """Привести имя к сравнимому виду: латиница, нижний регистр, без мусора."""
    text = unicodedata.normalize("NFKC", (text or "").strip().lower())
    text = text.replace("ё", "е")
    out = []
    for char in text:
        if char in TRANSLIT:
            out.append(TRANSLIT[char])
        elif char.isalnum() or char.isspace():
            out.append(char)
        else:
            out.append(" ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


#: те же окончания в том виде, в каком их видит `stem()`
CASE_ENDINGS = tuple(sorted({normalize(e) for e in _CASE_ENDINGS_RU} - {""}, key=len, reverse=True))


def stem(word: str) -> str:
    """Отбросить падежное окончание.

    Грубо, но для сопоставления фамилий достаточно: сравниваем основы,
    а не точные формы. Короткие слова не трогаем — там резать нечего.
    """
    if len(word) <= 4:
        return word
    for ending in CASE_ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 4:
            return word[: -len(ending)]
    return word


def tokens(full_name: str) -> list[str]:
    return [t for t in normalize(full_name).split() if t]


def _token_score(a: str, b: str) -> float:
    """Сходство двух слов с учётом инициалов и склонений."""
    if a == b:
        return 1.0
    # инициал против полного имени: «А.» и «Аружан»
    if len(a) == 1 or len(b) == 1:
        return 0.85 if a[0] == b[0] else 0.0
    sa, sb = stem(a), stem(b)
    if sa == sb:
        return 0.97
    if sa.startswith(sb) or sb.startswith(sa):
        return 0.92
    return SequenceMatcher(None, sa, sb).ratio()


def similarity(query: str, candidate: str) -> float:
    """Оценка сходства двух ФИО от 0 до 1.

    Порядок слов не важен: «Ахметова Аружан» и «Аружан Ахметова» — одно.
    Лишние слова в кандидате (отчество) не штрафуются, если запрос короче.
    """
    q, c = tokens(query), tokens(candidate)
    if not q or not c:
        return 0.0

    used: set[int] = set()
    scores: list[float] = []
    for word in q:
        best, best_i = 0.0, None
        for i, other in enumerate(c):
            if i in used:
                continue
            score = _token_score(word, other)
            if score > best:
                best, best_i = score, i
        if best_i is not None and best > 0:
            used.add(best_i)
        scores.append(best)

    base = sum(scores) / len(scores)
    # запрос из одного слова — совпадение по фамилии, но уверенности меньше:
    # однофамильцев в школе много
    if len(q) == 1 and len(c) > 1:
        base *= 0.72
    return round(base, 4)


@dataclass(frozen=True)
class Candidate:
    """Кандидат на совпадение."""

    student_id: int
    full_name: str
    group_code: str | None
    confidence: float

    def as_dict(self) -> dict:
        return {
            "student": self.student_id,
            "full_name": self.full_name,
            "group": self.group_code,
            "confidence": round(self.confidence, 3),
        }


@dataclass(frozen=True)
class MatchOutcome:
    """Результат поиска: кто нашёлся и надо ли спрашивать человека."""

    query: str
    candidates: tuple[Candidate, ...]

    @property
    def best(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None

    @property
    def is_confident(self) -> bool:
        """Однозначно, если лучший уверенно впереди второго."""
        if not self.candidates or self.candidates[0].confidence < CONFIDENT:
            return False
        if len(self.candidates) == 1:
            return True
        # два одинаково похожих — это однофамильцы, решает человек
        return self.candidates[0].confidence - self.candidates[1].confidence >= 0.08

    @property
    def is_ambiguous(self) -> bool:
        """Нашлось несколько похожих — нужен выбор человека."""
        return len(self.candidates) > 1 and not self.is_confident

    @property
    def is_missing(self) -> bool:
        return not self.candidates

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "candidates": [c.as_dict() for c in self.candidates],
            "is_confident": self.is_confident,
            "is_ambiguous": self.is_ambiguous,
            "is_missing": self.is_missing,
            "student": self.best.student_id if self.is_confident and self.best else None,
        }


def find(query: str, *, students=None, limit: int = 5) -> MatchOutcome:
    """Найти ученика по имени или почте.

    Точное совпадение по email — всегда однозначно. Иначе считаем
    сходство по ФИО и возвращаем кандидатов по убыванию уверенности.
    """
    query = (query or "").strip()
    if not query:
        return MatchOutcome(query=query, candidates=())

    if students is None:
        students = Student.objects.filter(is_active=True).select_related("group")
    students = list(students)

    if "@" in query:
        exact = next((s for s in students if s.email.lower() == query.lower()), None)
        if exact:
            return MatchOutcome(
                query=query,
                candidates=(Candidate(exact.pk, exact.full_name, exact.group.code if exact.group_id else None, 1.0),),
            )

    scored = []
    for student in students:
        score = similarity(query, student.full_name)
        if score >= FLOOR:
            scored.append(
                Candidate(student.pk, student.full_name, student.group.code if student.group_id else None, score)
            )

    scored.sort(key=lambda c: (-c.confidence, c.full_name))
    if scored:
        cutoff = scored[0].confidence - LAG
        scored = [c for c in scored if c.confidence >= cutoff]
    return MatchOutcome(query=query, candidates=tuple(scored[:limit]))


def find_many(queries, *, limit: int = 5) -> list[MatchOutcome]:
    """Сопоставить пачку имён за один проход по базе."""
    students = list(Student.objects.filter(is_active=True).select_related("group"))
    return [find(q, students=students, limit=limit) for q in queries]
