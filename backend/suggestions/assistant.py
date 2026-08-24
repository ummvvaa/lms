"""Помощник в углу: быстрые кнопки под роль и свободный ввод.

Кнопки, считающиеся правилами, работают и без ключа модели. Свободный
ввод без модели получает честный отказ, а не пустой ответ. Любое
изменение данных идёт через `Suggestion` — помощник в основные таблицы
не пишет никогда (инвариант №3), домен проверяет валидатор предложений.

Ученику помощник не называет внутренние ярлыки: его ответы собираются
только из того, что ученик и так видит (задачи, готовность, соответствие).
Эссе помощник не пишет: текст эссе в модель не отправляется вовсе,
на просьбу «напиши» отвечает наводящими вопросами.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from students.models import Student
from suggestions import operations
from suggestions.llm import LLMUnavailable, complete, is_configured

BEHAVIOR = "director_behavior"
ADMISSION = "director_admission"
EXAM = "director_exam"
TALENT = "director_talent"
SPORT = "director_sport"
ADMIN = "admin"
STUDENT = "student"


@dataclass(frozen=True)
class Quick:
    """Быстрая кнопка: код, подпись и что ей нужно на вход."""

    code: str
    title: str
    #: none | student | text | image
    needs: str
    hint: str = ""


#: Четыре кнопки на роль — состав из задания фазы 25.
QUICK: dict[str, tuple[Quick, ...]] = {
    STUDENT: (
        Quick("today", "Что делать сегодня", "none", "Задачи с ближайшими сроками"),
        Quick("why_percent", "Почему у меня такой процент", "none", "Из чего складывается готовность"),
        Quick("pick_universities", "Помоги выбрать вузы", "none", "Куда вы проходите уже сейчас"),
        Quick("explain_task", "Объясни задачу", "none", "Ближайшая задача — что и зачем"),
    ),
    BEHAVIOR: (
        Quick("focus_today", "Кому звонить сегодня", "none"),
        Quick("group_summary", "Сводка по группе", "none", "По отфильтрованным или по всем"),
        Quick("out_of_sight", "Кто пропал из виду", "none"),
        Quick("parent_letter", "Черновик письма родителю", "student"),
    ),
    ADMISSION: (
        Quick("check_balance", "Проверь баланс списка", "student"),
        Quick("deadlines_soon", "Ближайшие дедлайны", "none"),
        Quick("no_common_app", "Кто без Common App", "none"),
        Quick("parse_university", "Разбери вуз по ссылке", "text", "Название или адрес страницы"),
    ),
    EXAM: (
        Quick("mock_drop", "Кто просел по мокам", "none"),
        Quick("prep_plan", "План подготовки для ученика", "student"),
        Quick("intensive_group", "Собери группу на интенсив", "none"),
        Quick("parse_score_screenshot", "Разбери скрин с баллами", "image"),
    ),
    TALENT: (
        Quick("weak_portfolio", "У кого слабое портфолио", "none"),
        Quick("pick_track", "Подбери трек", "student"),
        Quick("contests_for_track", "Найди конкурсы под трек", "student"),
        Quick("parse_activity", "Разбери активность", "text", "Опишите словами, что было"),
    ),
    SPORT: (
        Quick("no_certificates", "У кого нет сертификатов", "none"),
        Quick("rate_sport_profile", "Оцени спортивный профиль", "student"),
        Quick("competitions_calendar", "Календарь соревнований", "none"),
        Quick("parse_certificate", "Распознай грамоту", "image"),
    ),
    ADMIN: (
        Quick("focus_today", "На кого смотреть сегодня", "none"),
        Quick("group_summary", "Сводка по школе", "none"),
        Quick("out_of_sight", "Кто пропал из виду", "none"),
        Quick("deadlines_soon", "Ближайшие дедлайны", "none"),
    ),
}


def quick_for(role: str) -> tuple[Quick, ...]:
    return QUICK.get(role, ())


def _reply(
    text: str,
    *,
    lines: list[str] | None = None,
    offline: bool = True,
    suggestion: int | None = None,
    affected: int = 0,
) -> dict:
    return {
        "text": text,
        "lines": lines or [],
        "offline": offline,
        "suggestion": suggestion,
        "affected": affected,
    }


def _name(student: Student) -> str:
    return f"{student.last_name} {student.first_name}".strip()


def _students(student_ids: list[int] | None):
    qs = Student.objects.filter(is_active=True)
    if student_ids:
        qs = qs.filter(pk__in=student_ids)
    return qs.order_by("last_name", "first_name", "id")


def _one_student(student_ids: list[int] | None) -> Student | None:
    if not student_ids or len(student_ids) != 1:
        return None
    return Student.objects.filter(pk=student_ids[0]).first()


NEED_ONE = "Нужен один ученик: откройте его карточку или отметьте одного в таблице — и нажмите кнопку ещё раз."


# --- Правила: директора ----------------------------------------------------


def out_of_sight(*, student_ids=None, **_kwargs) -> dict:
    """Посещаемость просела или профиль давно не обновлялся."""
    horizon = timezone.now() - timedelta(days=14)
    lines: list[str] = []
    for student in _students(student_ids).select_related("behavior"):
        behavior = getattr(student, "behavior", None)
        if behavior is None:
            continue
        attendance = behavior.attendance_percent
        if attendance is not None and attendance < 75:
            lines.append(f"{_name(student)} — посещаемость {attendance}%")
        elif behavior.updated_at < horizon and attendance is None:
            lines.append(f"{_name(student)} — профиль не обновлялся больше двух недель")
    if not lines:
        return _reply("Никто не пропал: посещаемость в норме, профили обновляются.")
    return _reply(f"Стоит вернуть в поле зрения: {len(lines)}.", lines=lines[:15])


def deadlines_soon(*, student_ids=None, **_kwargs) -> dict:
    """Раунды подачи из списков учеников на ближайшие 60 дней."""
    from universities.models import StudentUniversity

    today = timezone.localdate()
    rows = (
        StudentUniversity.objects.filter(
            admission_round__isnull=False,
            admission_round__deadline__gte=today,
            admission_round__deadline__lte=today + timedelta(days=60),
        )
        .select_related("student", "program__university", "admission_round")
        .order_by("admission_round__deadline")
    )
    if student_ids:
        rows = rows.filter(student_id__in=student_ids)
    lines = [
        f"{row.admission_round.deadline:%d.%m} — {row.program.university.name}, "
        f"{row.program.name} — {_name(row.student)}"
        for row in rows[:15]
    ]
    if not lines:
        return _reply("В ближайшие 60 дней дедлайнов по спискам учеников нет.")
    return _reply(f"Дедлайны на ближайшие 60 дней: {len(lines)}.", lines=lines)


def no_common_app(*, student_ids=None, **_kwargs) -> dict:
    rows = _students(student_ids).filter(admission__has_common_app=False)
    lines = [_name(s) for s in rows[:20]]
    if not lines:
        return _reply("У всех, у кого заполнен профиль поступления, Common App заведён.")
    return _reply(f"Без Common App: {rows.count()}.", lines=lines)


def mock_drop(*, student_ids=None, **_kwargs) -> dict:
    """Последний мок ниже предыдущего — по попыткам формата `mock`."""
    from students.models import ExamAttempt

    lines: list[str] = []
    for student in _students(student_ids):
        attempts = list(
            ExamAttempt.objects.filter(student=student, attempt_format="mock", total_score__isnull=False).order_by(
                "-date", "-id"
            )[:2]
        )
        if len(attempts) == 2 and attempts[0].total_score < attempts[1].total_score:
            lines.append(
                f"{_name(student)} — {attempts[0].exam_type}: " f"{attempts[1].total_score} → {attempts[0].total_score}"
            )
    if not lines:
        return _reply("Никто не просел: последние моки не ниже предыдущих.")
    return _reply(f"Просели по мокам: {len(lines)}.", lines=lines[:15])


def intensive_group(*, student_ids=None, **_kwargs) -> dict:
    """Кандидаты на интенсив: текущий балл заметно ниже целевого."""
    lines: list[str] = []
    for student in _students(student_ids).select_related("exam"):
        exam = getattr(student, "exam", None)
        if exam is None:
            continue
        ielts_gap = (
            exam.ielts_current is not None
            and exam.ielts_target is not None
            and exam.ielts_current + 1 <= exam.ielts_target
        )
        if ielts_gap:
            lines.append(f"{_name(student)} — IELTS {exam.ielts_current} при цели {exam.ielts_target}")
        elif exam.sat_current is not None and exam.sat_target is not None and exam.sat_current + 150 <= exam.sat_target:
            lines.append(f"{_name(student)} — SAT {exam.sat_current} при цели {exam.sat_target}")
    if not lines:
        return _reply("Кандидатов на интенсив нет: разрыв с целью меньше порога у всех.")
    return _reply(
        f"Кандидаты на интенсив: {len(lines)}. Дальше можно поставить им задачу — напишите её словами.",
        lines=lines[:20],
    )


def weak_portfolio(*, student_ids=None, **_kwargs) -> dict:
    lines: list[str] = []
    for student in _students(student_ids).select_related("talent"):
        talent = getattr(student, "talent", None)
        if talent is None:
            continue
        activities = student.activities.count()
        if talent.portfolio_status == "weak" or (not talent.portfolio_status and activities == 0):
            note = "нет активностей" if activities == 0 else f"активностей: {activities}"
            lines.append(f"{_name(student)} — {note}")
    if not lines:
        return _reply("Слабых портфолио по текущим данным нет.")
    return _reply(f"Слабое портфолио: {len(lines)}.", lines=lines[:20])


def pick_track(*, student_ids=None, **_kwargs) -> dict:
    student = _one_student(student_ids)
    if student is None:
        return _reply(NEED_ONE)
    counts: dict[str, int] = {}
    for activity in student.activities.all():
        counts[activity.get_category_display()] = counts.get(activity.get_category_display(), 0) + 1
    if not counts:
        return _reply(
            f"У {_name(student)} пока нет активностей — трек не из чего выводить. "
            "Начните с одной-двух записей: олимпиада, проект или волонтёрство."
        )
    top = sorted(counts.items(), key=lambda kv: -kv[1])
    lines = [f"{title}: {count}" for title, count in top]
    return _reply(
        f"По активностям {_name(student)} сильнее всего направление «{top[0][0]}» — логично строить трек вокруг него.",
        lines=lines,
    )


def contests_for_track(*, student_ids=None, **_kwargs) -> dict:
    """Только то, что есть в базе: выдумывать внешние конкурсы нельзя."""
    student = _one_student(student_ids)
    if student is None:
        return _reply(NEED_ONE)
    today = timezone.localdate()
    upcoming = student.activities.filter(date__gte=today).order_by("date")
    lines = [f"{a.date:%d.%m} — {a.title}" for a in upcoming[:10]]
    if not lines:
        return _reply(
            "Предстоящих конкурсов в базе нет. Помощник не подбирает внешние списки из головы — "
            "заведите конкурс активностью с датой, и он появится здесь."
        )
    return _reply(f"Запланировано у {_name(student)}: {len(lines)}.", lines=lines)


def no_certificates(*, student_ids=None, **_kwargs) -> dict:
    lines: list[str] = []
    for student in _students(student_ids).select_related("sport"):
        sport = getattr(student, "sport", None)
        if sport is None or sport.sport_type_id is None:
            continue
        if not student.competitions.filter(has_certificate=True).exists():
            lines.append(f"{_name(student)} — {sport.sport_type.name}")
    if not lines:
        return _reply("У всех спортсменов есть хотя бы один сертификат.")
    return _reply(f"Спортсмены без сертификатов: {len(lines)}.", lines=lines[:20])


def rate_sport_profile(*, student_ids=None, **_kwargs) -> dict:
    student = _one_student(student_ids)
    if student is None:
        return _reply(NEED_ONE)
    sport = getattr(student, "sport", None)
    if sport is None or sport.sport_type_id is None:
        return _reply(f"{_name(student)} не отмечен спортсменом: вид спорта в профиле не задан.")
    competitions = student.competitions.count()
    with_cert = student.competitions.filter(has_certificate=True).count()
    lines = [
        f"Вид спорта: {sport.sport_type.name}",
        f"Уровень: {sport.get_level_display() or 'не указан'}",
        f"Соревнований в базе: {competitions}, с сертификатом: {with_cert}",
    ]
    if sport.leadership_role:
        lines.append(f"Лидерская роль: {sport.leadership_role}")
    missing = []
    if not with_cert:
        missing.append("нет ни одного сертификата")
    if not sport.level:
        missing.append("не указан уровень")
    tail = f" Чего не хватает: {', '.join(missing)}." if missing else " Профиль заполнен."
    return _reply(f"Спортивный профиль {_name(student)} по данным системы.{tail}", lines=lines)


def competitions_calendar(*, student_ids=None, **_kwargs) -> dict:
    from students.models import Competition

    today = timezone.localdate()
    rows = Competition.objects.filter(date__gte=today).select_related("student").order_by("date")
    if student_ids:
        rows = rows.filter(student_id__in=student_ids)
    lines = [f"{row.date:%d.%m} — {row.name} — {_name(row.student)}" for row in rows[:15]]
    if not lines:
        return _reply("Предстоящих соревнований в базе нет.")
    return _reply(f"Ближайшие соревнования: {len(lines)}.", lines=lines)


# --- Правила: ученик -------------------------------------------------------


def student_today(*, student: Student, **_kwargs) -> dict:
    tasks = (
        student.tasks.exclude(status="done")
        .order_by("due_date", "priority", "id")
        .select_related("admission_round")[:5]
    )
    lines = []
    for task in tasks:
        when = f" — до {task.due_date:%d.%m}" if task.due_date else ""
        lines.append(f"{task.title}{when}")
    if not lines:
        return _reply("Открытых задач нет. Загляните в каталог — выбранные вузы сами превратятся в план.")
    return _reply("Ближайшие задачи по плану:", lines=lines)


def student_why_percent(*, student: Student, **_kwargs) -> dict:
    """Готовность по блокам. Проценты — соответствие, не шанс поступления."""
    from core.readiness import compute

    readiness = compute(student)
    lines = [f"{part.title}: {round(part.value)}% (вес {round(part.weight)}%)" for part in readiness.parts]
    tail = ""
    if readiness.weakest is not None:
        tail = f" Больше всего добавит блок «{readiness.weakest.title}»."
    return _reply(
        f"Ваша готовность — {round(readiness.score)}%. Это соответствие требованиям и заполненность "
        f"профиля, а не вероятность поступления.{tail}",
        lines=lines,
    )


def student_pick_universities(*, student: Student, **_kwargs) -> dict:
    from universities.matching import open_programs

    results = open_programs(student)
    if not results:
        return _reply(
            "В справочнике пока нет программ, по которым можно посчитать соответствие. "
            "Загляните в каталог позже или спросите директора по поступлению."
        )
    top = sorted(results, key=lambda r: -r.percent)[:5]
    lines = [f"{r.university_name} — {r.program_name} — {r.percent}%" for r in top]
    return _reply(
        "Куда вы проходите уже сейчас — по проценту соответствия требованиям (это не шанс поступления):",
        lines=lines,
    )


def student_explain_task(*, student: Student, **_kwargs) -> dict:
    task = student.tasks.exclude(status="done").order_by("due_date", "id").select_related("admission_round").first()
    if task is None:
        return _reply("Открытых задач нет — объяснять нечего.")
    lines = [f"Задача: {task.title}"]
    if task.description:
        lines.append(task.description)
    if task.due_date:
        lines.append(f"Срок: {task.due_date:%d.%m.%Y}")
    if task.admission_round_id:
        lines.append("Срок привязан к дедлайну вуза: сдвинется дедлайн — сдвинется и задача.")
    if task.category == "essay":
        lines.append(
            "Эссе помощник за вас не пишет. Подумайте: какой случай из жизни показывает то, "
            "о чём просит тема? Что вы сделали сами? Что поняли после?"
        )
    return _reply("Разбор ближайшей задачи:", lines=lines)


# --- Свободный ввод --------------------------------------------------------

#: Просьба поставить задачу — уходит в bulk_tasks и создаёт предложение.
TASK_INTENT = re.compile(r"(поставь|создай|добавь|назнач)\w*\s+(?:\w+\s+){0,3}?задач", re.IGNORECASE)

#: Просьба написать эссе — ученику отвечаем вопросами, а не текстом.
ESSAY_INTENT = re.compile(
    r"(напиши|перепиши|сочини|допиши)\w*.{0,40}эссе|эссе.{0,40}(напиши|перепиши|сочини)",
    re.IGNORECASE | re.S,
)

NO_MODEL_TEXT = (
    "Свободные вопросы отвечает модель, а она сейчас не подключена. "
    "Быстрые кнопки работают и без неё — выберите одну из них."
)


def free_text(*, text: str, actor, role: str, student_ids=None, screen: str = "") -> dict:
    """Свободный ввод: намерение «поставить задачу» — через предложение,
    остальное — вопрос модели. Без модели — честный отказ."""
    if role != STUDENT and TASK_INTENT.search(text):
        if not student_ids:
            return _reply(
                "Кому ставим? Отфильтруйте таблицу или отметьте учеников — задача уйдёт именно им, "
                "а не всем двумстам пятидесяти."
            )
        outcome = operations.bulk_tasks(student_ids=list(student_ids), wish=text, actor=actor, role=role)
        payload = outcome.as_dict()
        return _reply(
            payload["text"] or payload["detail"],
            lines=payload["lines"],
            offline=payload["offline"],
            suggestion=payload["suggestion"],
            # затронутые — это ученики, а не строки-поля предложения
            affected=len(student_ids),
        )

    if role == STUDENT and ESSAY_INTENT.search(text):
        return _reply(
            "Эссе помощник не пишет и не переписывает — приёмная комиссия ждёт ваш голос, не машинный. "
            "Помогу вопросами: о каком случае вы хотите рассказать? Что вы в нём сделали сами? "
            "Что поняли после — и как это связано с программой, куда подаёте?"
        )

    if not is_configured():
        return _reply(NO_MODEL_TEXT)

    system = (
        "Ты помощник внутренней школьной платформы подготовки к поступлению. "
        "Отвечай коротко и по-русски. Не выдумывай вузы, программы и требования: "
        "если данных нет в вопросе, скажи об этом прямо. "
        "Проценты называй «соответствием требованиям», никогда — шансом или вероятностью поступления."
    )
    if role == STUDENT:
        system += (
            " Ты говоришь с учеником: не используй внутренние ярлыки и категории сотрудников, "
            "не пиши и не переписывай эссе — только задавай наводящие вопросы."
        )
    context = f"Экран: {screen}." if screen else ""
    if student_ids:
        context += f" Выбрано учеников: {len(student_ids)}."
    try:
        response = complete(
            system=system,
            user=f"{context}\n{text}".strip(),
            purpose="assistant_chat",
            actor=actor,
            role=role,
            max_tokens=700,
        )
    except LLMUnavailable:
        return _reply(NO_MODEL_TEXT)
    answer = (response.content or "").strip()
    if not answer:
        return _reply(NO_MODEL_TEXT)
    return _reply(answer, offline=False)


# --- Диспетчер -------------------------------------------------------------


def run_quick(code: str, *, actor, role: str, student_ids=None, text: str = "") -> dict:
    """Выполнить быструю кнопку. Неизвестный код — честный отказ."""
    allowed = {q.code for q in quick_for(role)}
    if code not in allowed:
        return _reply("Такой кнопки у вашей роли нет.")

    if role == STUDENT:
        student = getattr(actor, "student", None)
        if student is None:
            return _reply("У вашей учётной записи нет карточки ученика — попросите администратора связать их.")
        handlers = {
            "today": student_today,
            "why_percent": student_why_percent,
            "pick_universities": student_pick_universities,
            "explain_task": student_explain_task,
        }
        return handlers[code](student=student)

    # операции фазы 20 — вызываются как есть, с их же путём без модели
    if code == "focus_today":
        return _outcome(operations.focus_today(actor=actor, role=role))
    if code == "group_summary":
        ids = list(student_ids or _students(None).values_list("id", flat=True)[:250])
        return _outcome(operations.explain_list(student_ids=ids, actor=actor, role=role))
    if code == "parent_letter":
        student = _one_student(student_ids)
        if student is None:
            return _reply(NEED_ONE)
        return _outcome(operations.parent_letter(student_id=student.pk, actor=actor, role=role))
    if code == "check_balance":
        student = _one_student(student_ids)
        if student is None:
            return _reply(NEED_ONE)
        return _outcome(operations.check_balance(student_id=student.pk, actor=actor, role=role))
    if code == "prep_plan":
        student = _one_student(student_ids)
        if student is None:
            return _reply(NEED_ONE)
        return _outcome(operations.prep_plan(student_id=student.pk, actor=actor, role=role))
    if code == "parse_university":
        return _parse_university(text=text, actor=actor, role=role)
    if code == "parse_activity":
        return _parse_activity(text=text, actor=actor, role=role, student_ids=student_ids)

    rules = {
        "out_of_sight": out_of_sight,
        "deadlines_soon": deadlines_soon,
        "no_common_app": no_common_app,
        "mock_drop": mock_drop,
        "intensive_group": intensive_group,
        "weak_portfolio": weak_portfolio,
        "pick_track": pick_track,
        "contests_for_track": contests_for_track,
        "no_certificates": no_certificates,
        "rate_sport_profile": rate_sport_profile,
        "competitions_calendar": competitions_calendar,
    }
    handler = rules.get(code)
    if handler is None:
        return _reply("Эта кнопка принимает файл или изображение — воспользуйтесь полем загрузки рядом с ней.")
    return handler(student_ids=student_ids)


def _outcome(outcome) -> dict:
    payload = outcome.as_dict()
    return _reply(
        payload["text"] or payload["detail"],
        lines=payload["lines"],
        offline=payload["offline"],
        suggestion=payload["suggestion"],
        affected=payload["rows"],
    )


def _parse_university(*, text: str, actor, role: str) -> dict:
    from suggestions.extraction import NeedsModel
    from suggestions.extraction import parse_university as run

    if not text.strip():
        return _reply("Пришлите название вуза или ссылку на его страницу — тогда будет что разбирать.")
    try:
        result = run(text=text, actor=actor, role=role)
    except NeedsModel as error:
        return _reply(str(error))
    return _reply(
        result.get("detail") or "Разобрал: смотрите предпросмотр.",
        suggestion=result.get("suggestion"),
        offline=False,
        affected=result.get("rows") or 0,
    )


def _parse_activity(*, text: str, actor, role: str, student_ids=None) -> dict:
    from suggestions.extraction import NeedsModel
    from suggestions.extraction import parse_activity as run

    student = _one_student(student_ids)
    if student is None:
        return _reply(NEED_ONE)
    if not text.strip():
        return _reply("Опишите активность словами: что было, когда, чем закончилось.")
    try:
        result = run(text=text, student_id=student.pk, actor=actor, role=role)
    except NeedsModel as error:
        return _reply(str(error))
    return _reply(
        result.get("detail") or "Разобрал: смотрите предпросмотр.",
        suggestion=result.get("suggestion"),
        offline=False,
        affected=result.get("rows") or 0,
    )
