"""Корзины «кого дёргать» — кто из учеников требует внимания куратора.

Одно место на всю систему (фаза 61): по этим правилам считаются и числа
на главной куратора, и чипы над таблицей учеников, и блок «что требует
внимания» в карточке. Считать их на фронте нельзя — три экрана разойдутся
в первый же месяц, и куратор перестанет верить числам.

Пороги — из настроек (`CURATOR_RULES`), а не из кода: школа меняет их
без выката, тесты фиксируют числами. Каждое правило закрыто своим тестом
(`students/tests/test_phase61.py`).

Корзина «документы не собраны» (фаза 62) считает по тем же данным, что
матрица экрана «Документы» (`students.documents`): отсюда числа на главной,
чип над таблицей и карточка не расходятся с самой матрицей.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import Q, QuerySet
from django.utils import timezone

from students.models import ExamAttempt, ExamGoal, Student

#: Экзамены школы, по которым считаются цели и отставание (фаза 59).
IELTS, SAT = "IELTS", "SAT"


@dataclass(frozen=True)
class Bucket:
    """Корзина: код, человеческая подпись и тон чипа."""

    code: str
    title: str
    #: чем это плохо — одной строкой, для подсказки под чипом
    hint: str
    tone: str


BUCKETS: tuple[Bucket, ...] = (
    Bucket(
        "nogoal",
        "Без цели по экзаменам",
        "Не поставлена ни цель IELTS, ни цель SAT — учиться не к чему",
        "warn",
    ),
    Bucket(
        "nomock",
        "Пробника не было больше месяца",
        "Последний пробник старше 30 дней или его не было вовсе",
        "warn",
    ),
    Bucket(
        "far",
        "Балл далеко от цели, экзамен ближе 60 дней",
        "До цели больше балла по IELTS или больше 100 по SAT, а сдавать скоро",
        "risk",
    ),
    Bucket(
        "docs",
        "Документы не собраны",
        "Не хватает документов чек-листа или последний отклонён",
        "warn",
    ),
    Bucket(
        "rejected",
        "Отклонено и не перевнесено",
        "Вы отклонили значение, а ученик так и не внёс новое",
        "risk",
    ),
)

BUCKET_CODES = tuple(b.code for b in BUCKETS)


def rules() -> dict:
    """Пороги правил. Отдельной функцией — чтобы тест мог их переопределить."""
    return settings.CURATOR_RULES


def _goal_map(students: QuerySet[Student]) -> dict[int, dict[str, ExamGoal]]:
    """Цели по экзаменам: `{ученик: {название экзамена: цель}}`.

    Ключ — название записи справочника (`ExamKind.name`), как во всей
    остальной системе: подбор вузов, напоминания и центр подготовки
    сопоставляют цель с экзаменом именно по названию.
    """
    out: dict[int, dict[str, ExamGoal]] = {}
    rows = ExamGoal.objects.filter(student__in=students).select_related("exam")
    for goal in rows:
        out.setdefault(goal.student_id, {})[goal.exam.name.upper()] = goal
    return out


def _last_mock(students: QuerySet[Student]) -> dict[int, ExamAttempt]:
    """Последний по дате пробник каждого ученика — и школьный, и с платформы.

    До фазы 63 других пробников в системе нет: платформенный прогон
    сохраняется той же строкой `ExamAttempt` с форматом «мок» и источником
    «пройден на платформе», файл учителя — тем же форматом и источником
    «внесён руками» или «импорт».
    """
    out: dict[int, ExamAttempt] = {}
    rows = ExamAttempt.objects.filter(student__in=students, attempt_format="mock").order_by("student_id", "date")
    for row in rows:
        out[row.student_id] = row
    return out


def _rejected_without_retry(students: QuerySet[Student]) -> set[int]:
    """Ученики с отклонённым предложением, после которого не было нового.

    «Не перевнесено» — по времени подачи: отклонили в среду, ученик подал
    заново в четверг — из корзины он вышел, даже если решения ещё нет.
    """
    from core.domains import ROLE_STUDENT
    from suggestions.models import Suggestion, SuggestionStatus

    rows = (
        Suggestion.objects.filter(role=ROLE_STUDENT, changes__student__in=students)
        .values_list("changes__student_id", "status", "created_at")
        .order_by("changes__student_id", "created_at")
    )
    latest: dict[int, str] = {}
    for student_id, status, _created in rows:
        if student_id is not None:
            latest[student_id] = status
    return {student_id for student_id, status in latest.items() if status == SuggestionStatus.REJECTED}


def _target_of(profile, goals: dict[str, ExamGoal], code: str):
    """Цель по экзамену: из цели с датой, иначе из поля профиля."""
    goal = goals.get(code)
    if goal is not None and goal.target_score is not None:
        return float(goal.target_score)
    field = "ielts_target" if code == IELTS else "sat_target"
    value = getattr(profile, field, None)
    return float(value) if value is not None else None


def _exam_date(goals: dict[str, ExamGoal], code: str):
    goal = goals.get(code)
    return goal.exam_date if goal is not None else None


def state_of(students: QuerySet[Student]) -> dict[int, dict]:
    """Собрать по каждому ученику всё, из чего считаются корзины.

    Одним проходом на всю выборку: карточка спрашивает про одного,
    таблица — про сотню, и второй код для второго случая разошёлся бы
    с первым.
    """
    from students.documents import state_of as documents_state

    today = timezone.localdate()
    conf = rules()
    goals = _goal_map(students)
    mocks = _last_mock(students)
    retried = _rejected_without_retry(students)
    documents = documents_state(students)

    out: dict[int, dict] = {}
    for student in students.select_related("exam"):
        profile = getattr(student, "exam", None)
        mine = goals.get(student.pk, {})
        last = mocks.get(student.pk)
        row = {
            "ielts_current": float(profile.ielts_current) if profile and profile.ielts_current is not None else None,
            "sat_current": float(profile.sat_current) if profile and profile.sat_current is not None else None,
            "ielts_target": _target_of(profile, mine, IELTS),
            "sat_target": _target_of(profile, mine, SAT),
            "ielts_exam_date": _exam_date(mine, IELTS),
            "sat_exam_date": _exam_date(mine, SAT),
            "last_mock_date": last.date if last else None,
            "last_mock_exam": last.exam_type if last else "",
            "last_mock_score": float(last.total_score) if last and last.total_score is not None else None,
        }

        codes: list[str] = []
        if row["ielts_target"] is None and row["sat_target"] is None:
            codes.append("nogoal")

        stale = today - timedelta(days=conf["MOCK_STALE_DAYS"])
        if row["last_mock_date"] is None or row["last_mock_date"] < stale:
            codes.append("nomock")

        if _far_from_goal(row, today, conf):
            codes.append("far")

        docs = documents.get(student.pk)
        row["documents_collected"] = docs["collected"] if docs else 0
        row["documents_total"] = docs["total"] if docs else 0
        row["documents_expiring"] = bool(docs and docs["expiring"])
        if docs and docs["missing"]:
            codes.append("docs")

        if student.pk in retried:
            codes.append("rejected")

        row["buckets"] = codes
        row["days_without_mock"] = (today - row["last_mock_date"]).days if row["last_mock_date"] else None
        out[student.pk] = row
    return out


def _far_from_goal(row: dict, today, conf: dict) -> bool:
    """Отстаёт от цели, а экзамен уже скоро — хотя бы по одному экзамену."""
    soon = timedelta(days=conf["EXAM_SOON_DAYS"])
    pairs = (
        ("ielts_current", "ielts_target", "ielts_exam_date", conf["IELTS_GAP"]),
        ("sat_current", "sat_target", "sat_exam_date", conf["SAT_GAP"]),
    )
    for current_key, target_key, date_key, gap in pairs:
        target, date = row[target_key], row[date_key]
        if target is None or date is None:
            continue
        if not (today <= date <= today + soon):
            continue
        current = row[current_key]
        # балла нет вовсе — это тоже «далеко от цели»: сдавать скоро, а нечего
        if current is None or target - current >= gap:
            return True
    return False


def buckets_of(student: Student) -> list[str]:
    """Корзины одного ученика — для карточки."""
    return state_of(Student.objects.filter(pk=student.pk))[student.pk]["buckets"]


def counts(students: QuerySet[Student]) -> list[dict]:
    """Числа по каждой корзине для выборки — главная и чипы берут их отсюда."""
    state = state_of(students)
    return [
        {
            "code": bucket.code,
            "title": bucket.title,
            "hint": bucket.hint,
            "tone": bucket.tone,
            "count": sum(1 for row in state.values() if bucket.code in row["buckets"]),
        }
        for bucket in BUCKETS
    ]


def filter_by(students: QuerySet[Student], code: str) -> QuerySet[Student]:
    """Сузить выборку до одной корзины. Неизвестный код ничего не сужает."""
    if code not in BUCKET_CODES:
        return students
    state = state_of(students)
    keep = [pk for pk, row in state.items() if code in row["buckets"]]
    return students.filter(pk__in=keep)


def sharp_jump(model_label: str, field_name: str, old_value: str, new_value: str) -> bool:
    """Резкий скачок значения: балл вырос слишком сильно, чтобы верить на слово.

    Порог свой у каждого экзамена (`CURATOR_RULES`). Считается на сервере
    и приходит строкой очереди готовым признаком: у куратора и у владельца
    домена «резкий скачок» обязан значить одно и то же.
    """
    if model_label.lower() != "students.examprofile":
        return False
    conf = rules()
    limit = {"ielts_current": conf["IELTS_JUMP"], "sat_current": conf["SAT_JUMP"]}.get(field_name)
    if limit is None:
        return False
    try:
        old, new = float(str(old_value).replace(",", ".")), float(str(new_value).replace(",", "."))
    except (TypeError, ValueError):
        return False
    return abs(new - old) >= limit


def active_students(group_ids: list[int] | None = None) -> QuerySet[Student]:
    """Учащиеся из указанных групп — основа всех подсчётов кабинета."""
    rows = Student.objects.filter(is_active=True)
    if group_ids is not None:
        rows = rows.filter(group_id__in=group_ids)
    return rows.filter(~Q(group__isnull=True))
