"""Корзины «кого дёргать» — кто из учеников требует внимания куратора.

Одно место на всю систему (фаза 61): по этим правилам считаются и числа
на главной куратора, и чипы над таблицей учеников, и блок «что требует
внимания» в карточке. Считать их на фронте нельзя — три экрана разойдутся
в первый же месяц, и куратор перестанет верить числам.

Пороги — настройки школы (`core.school_rules`, раздел «Куратор»), а не числа
в коде: администратор меняет их на экране, действуют со следующего запроса.
Каждое правило закрыто своим тестом
(`students/tests/test_curator_buckets_and_tasks.py`).

Корзина «документы не собраны» (фаза 62) считает по тем же данным, что
матрица экрана «Документы» (`students.documents`): отсюда числа на главной,
чип над таблицей и карточка не расходятся с самой матрицей.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy, gettext_noop

from core import school_rules
from core.phrasing import tn
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
    #: правило, чей срок стоит в подписи: подпись — фраза с числом через черту,
    #: помечена `gettext_noop` и собирается при показе (`words`)
    days: str = ""


BUCKETS: tuple[Bucket, ...] = (
    Bucket(
        "nogoal",
        gettext_lazy("Без цели по экзаменам"),
        gettext_lazy("Не поставлена ни цель IELTS, ни цель SAT — учиться не к чему"),
        "warn",
    ),
    Bucket(
        "nomock",
        gettext_noop(
            "Mock Test не было больше {n} дня|Mock Test не было больше {n} дней|Mock Test не было больше {n} дней"
        ),
        gettext_noop(
            "Последний Mock Test старше {n} дня или его не было вовсе|"
            "Последний Mock Test старше {n} дней или его не было вовсе|"
            "Последний Mock Test старше {n} дней или его не было вовсе"
        ),
        "warn",
        days="MOCK_STALE_DAYS",
    ),
    Bucket(
        "far",
        gettext_noop(
            "Балл далеко от цели, экзамен ближе {n} дня|"
            "Балл далеко от цели, экзамен ближе {n} дней|"
            "Балл далеко от цели, экзамен ближе {n} дней"
        ),
        gettext_noop("До цели по IELTS не хватает {ielts} или больше, по SAT — {sat} или больше, а сдавать скоро"),
        "bad",
        days="EXAM_SOON_DAYS",
    ),
    Bucket(
        "docs",
        gettext_lazy("Документы не собраны"),
        gettext_lazy("Не хватает документов чек-листа или последний отклонён"),
        "warn",
    ),
    Bucket(
        "rejected",
        gettext_lazy("Отклонено и не перевнесено"),
        gettext_lazy("Вы отклонили значение, а ученик так и не внёс новое"),
        "bad",
    ),
)

BUCKET_CODES = tuple(b.code for b in BUCKETS)
#: корзины поступления и экзаменов — только у 11 (`core/parallels.py`)
ADMISSION_BUCKETS = frozenset({"nogoal", "nomock", "far", "docs"})


#: ключ порога в расчётах корзин → правило школы
RULE_CODES = {
    "MOCK_STALE_DAYS": school_rules.MOCK_STALE_DAYS,
    "EXAM_SOON_DAYS": school_rules.EXAM_SOON_DAYS,
    "IELTS_GAP": school_rules.IELTS_GAP,
    "SAT_GAP": school_rules.SAT_GAP,
    "IELTS_JUMP": school_rules.IELTS_JUMP,
    "SAT_JUMP": school_rules.SAT_JUMP,
}


def rules() -> dict:
    """Пороги корзин и резкого скачка — настройки школы, одним запросом."""
    values = school_rules.values()
    return {key: values[code] for key, code in RULE_CODES.items()}


def _number(value: float) -> str:
    """Порог в подписи: «1», «1,5» — без хвоста нулей, запятая по языку."""
    from core.i18n import active_language

    text = f"{value:g}"
    return text if active_language() == "en" else text.replace(".", ",")


def words(bucket: Bucket, conf: dict | None = None) -> tuple[str, str]:
    """Подпись и подсказка корзины на языке ответа; срок правила — числом из настроек."""
    if not bucket.days:
        return str(bucket.title), str(bucket.hint)
    conf = conf or rules()
    gaps = {"ielts": _number(conf["IELTS_GAP"]), "sat": _number(conf["SAT_GAP"])}
    return tn(conf[bucket.days], bucket.title, **gaps), tn(conf[bucket.days], bucket.hint, **gaps)


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

    from core.parallels import has_admission

    out: dict[int, dict] = {}
    for student in students.select_related("exam", "group"):
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

        if not has_admission(student):
            # у 8–10 нет экзаменов, пробников и документов поступления —
            # их корзины к ним не относятся (`core/parallels.py`)
            codes = [code for code in codes if code not in ADMISSION_BUCKETS]
            row["documents_collected"] = row["documents_total"] = 0
            row["documents_expiring"] = False
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
    conf = rules()
    out = []
    for bucket in BUCKETS:
        title, hint = words(bucket, conf)
        out.append(
            {
                "code": bucket.code,
                "title": title,
                "hint": hint,
                "tone": bucket.tone,
                "count": sum(1 for row in state.values() if bucket.code in row["buckets"]),
            }
        )
    return out


def filter_by(students: QuerySet[Student], code: str) -> QuerySet[Student]:
    """Сузить выборку до одной корзины. Неизвестный код ничего не сужает."""
    if code not in BUCKET_CODES:
        return students
    state = state_of(students)
    keep = [pk for pk, row in state.items() if code in row["buckets"]]
    return students.filter(pk__in=keep)


def sharp_jump(model_label: str, field_name: str, old_value: str, new_value: str, conf: dict | None = None) -> bool:
    """Резкий скачок значения: балл вырос слишком сильно, чтобы верить на слово.

    Порог свой у каждого экзамена — настройки школы. Считается на сервере
    и приходит строкой очереди готовым признаком: у куратора и у владельца
    домена «резкий скачок» обязан значить одно и то же. Очередь передаёт
    пороги сама (`conf`), чтобы не читать их на каждую строку.
    """
    if model_label.lower() != "students.examprofile":
        return False
    if field_name not in ("ielts_current", "sat_current"):
        return False
    conf = conf or rules()
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
