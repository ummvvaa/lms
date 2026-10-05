"""Кабинеты шести руководителей (фаза 49).

У каждого свой экран, а не один с подменой данных: у Кымбат сверху числа
по экзаменам и очередь баллов, у Асем первым горят дедлайны недели,
у Салтанат — кому позвонить сегодня, у Армана — материалы на проверке,
у Нурлыбека — календарь стартов, у администратора — реестр и то, что
требует его действий.

Общее у пятерых — очередь «Ждут вашего решения»: с фазы 37 данные о себе
вносит ученик, а директор подтверждает. У администратора её нет: ему
нечего подтверждать, у него список действий.

Считается агрегатами в базе, как и дашборды фазы 7: на 250 учениках это
несколько запросов, а не выборка всех строк в память.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Avg, Count, Exists, F, OuterRef, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from core import school_rules, stored_text
from core.dashboards import mock_drops
from core.parallels import admission_q, parallel_of
from core.phrasing import counted, tn
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    Competition,
    ExamGoal,
    ExamProfile,
    ParentContact,
    SportProfile,
    Student,
    StudyGroup,
)
from universities.models import AdmissionRound, StudentUniversity


def horizon_days() -> int:
    """На сколько дней вперёд смотрит «ближайшее» — экзамены, олимпиады, старты (настройка школы)."""
    return school_rules.value(school_rules.DEADLINE_HORIZON_DAYS)


def urgent_days() -> int:
    """Окно героя на дашборде Асем: дальше — уже не «горит», это видно в разделе «Дедлайны»."""
    return school_rules.value(school_rules.DEADLINE_SOON_DAYS)


def _active():
    return Student.objects.filter(is_active=True)


def _graduates():
    """Ученики с поступлением — 11 (`core.parallels`): их ведут Асем и Кымбат-экзамены."""
    return _active().filter(admission_q())


#: условие «у ученика поступление» для дочерних таблиц
GRADUATE = admission_q("student__")


def _short(student) -> str:
    """«Ахметова Алия» — фамилия и имя, без отчества: строка списка узкая."""
    return f"{student.last_name} {student.first_name}".strip()


def _initials(student) -> str:
    letters = [part[0] for part in (student.last_name, student.first_name) if part]
    return "".join(letters).upper()


# --- Очередь «Ждут вашего решения» ---------------------------------------


def pending_queue(role: str, group_ids: list[int] | None = None) -> dict:
    """Сколько слов ученика ждёт решения владельца домена.

    Сами строки очереди отдаёт `/suggestions/from-students/` — тот же
    список, что и на экране предложений с фазы 37. Здесь только число
    для карточки: второй источник той же очереди разошёлся бы с первым
    в понимании того, что считать ждущим решения.
    """
    from suggestions.student_queue import pending_for

    return {"total": len(pending_for(role, group_ids))}


# --- Куратор (фаза 60): заглушка точки входа ------------------------------


def curator_cabinet(user) -> dict:
    """Свои группы и число учеников — остальное появится в фазе 61.

    Считается по назначениям на сегодня, а не по текстовому полю группы:
    источник права один (инвариант №2).
    """
    from accounts.curators import active_assignments

    rows = active_assignments().filter(curator=user).select_related("group").order_by("group__code")
    groups = []
    for row in rows:
        count = row.group.students.filter(is_active=True).count()
        groups.append(
            {
                "id": row.group_id,
                "code": row.group.code,
                "parallel": row.group.parallel,
                "students": count,
                "since": row.since,
            }
        )
    group_ids = [g["id"] for g in groups]
    total = sum(g["students"] for g in groups)
    queue = pending_queue("curator", group_ids)
    return {
        "role": "curator",
        "title": _("Кабинет куратора"),
        "owner": _("{name} · куратор").format(name=user.full_name or user.email),
        "stats": [
            {
                "code": "groups",
                "label": _("Групп"),
                "value": len(groups),
                "note": _("назначены на сегодня"),
                "tone": "accent",
            },
            {"code": "students", "label": _("Учеников"), "value": total, "note": _("в ваших группах"), "tone": "info"},
            {"code": "queue", "label": _("Ждут решения"), "value": queue["total"], "note": "", "tone": "warn"},
        ],
        "groups": groups,
        "queue": queue,
    }


# --- Кымбат: экзамены ----------------------------------------------------


def exam_cabinet() -> dict:
    """Средние баллы школы, очередь баллов и целей, просевшие моки."""
    profiles = ExamProfile.objects.filter(GRADUATE, student__is_active=True)
    averages = profiles.aggregate(ielts=Avg("ielts_current"), sat=Avg("sat_current"))
    drops = mock_drops(limit=6)

    today = timezone.localdate()
    horizon = today + timedelta(days=horizon_days())
    upcoming = list(
        ExamGoal.objects.filter(GRADUATE, exam_date__gte=today, exam_date__lte=horizon, student__is_active=True)
        .values("exam_date", name=F("exam__name"))
        .annotate(students=Count("id"))
        .order_by("exam_date")[:6]
    )

    # Полоса диапазона открывает этих учеников в таблице, а не просто
    # подсвечивается: фильтр приходит вместе с числом, чтобы диапазон
    # и отбор не разошлись (то же правило, что у плиток фазы 8)
    ranges = [
        {
            "title": _("IELTS 7.5 и выше"),
            "count": profiles.filter(ielts_current__gte=7.5).count(),
            "filter": {"ielts_min": "7.5"},
        },
        {
            "title": "IELTS 6.5–7.0",
            "count": profiles.filter(ielts_current__gte=6.5, ielts_current__lt=7.5).count(),
            "filter": {"ielts_min": "6.5", "ielts_max": "7.5"},
        },
        {
            "title": "IELTS 5.5–6.0",
            "count": profiles.filter(ielts_current__gte=5.5, ielts_current__lt=6.5).count(),
            "filter": {"ielts_min": "5.5", "ielts_max": "6.5"},
        },
        {
            "title": _("IELTS ниже 5.5"),
            "count": profiles.filter(ielts_current__lt=5.5).count(),
            "filter": {"ielts_max": "5.5"},
        },
    ]

    has_goal = ExamGoal.objects.filter(student=OuterRef("pk"))
    without_goals = list(
        _graduates()
        .annotate(has_goal=Exists(has_goal))
        .filter(has_goal=False, group__isnull=False)
        .values(code=F("group__code"))
        .annotate(students=Count("id"))
        .order_by("code")[:8]
    )

    queue = pending_queue("director_exam")
    return {
        "role": "director_exam",
        "title": _("Экзамены"),
        "owner": _("Кымбат · академический директор"),
        "stats": [
            {
                "code": "ielts",
                "label": _("Средний IELTS"),
                "value": round(averages["ielts"], 1) if averages["ielts"] else None,
                "note": _("цель школы 6.5"),
                "tone": "info",
            },
            {
                "code": "sat",
                "label": _("Средний SAT"),
                "value": round(averages["sat"]) if averages["sat"] else None,
                "note": _("цель 1300"),
                "tone": "info",
            },
            # «Мок просел» плиткой здесь не стоит: то же число — в заголовке списка
            # просевших ниже, и там по каждому есть действие (фаза 80)
            {
                "code": "queue",
                "label": _("Ждут решения"),
                "value": queue["total"],
                "note": _("внесли ученики"),
                "tone": "warn",
            },
        ],
        "queue": queue,
        "drops": [
            {
                "student_id": row["student_id"],
                "student": f"{row['student__last_name']} {row['student__first_name']}",
                "exam": row["exam_type"],
                "previous": row["previous"],
                "latest": row["latest"],
                "delta": row["delta"],
            }
            for row in drops
        ],
        "upcoming": [{"title": row["name"], "date": row["exam_date"], "students": row["students"]} for row in upcoming],
        "ranges": ranges,
        "without_goals": without_goals,
    }


# --- Асем: поступление ---------------------------------------------------


def admission_cabinet() -> dict:
    """Дедлайны недели, баланс списков и справочник, который она ведёт."""
    from universities.models import Program, Scholarship, University

    students = _graduates()
    total = students.count()
    today = timezone.localdate()
    week = today + timedelta(days=7)

    week_rounds = (
        AdmissionRound.objects.filter(deadline__gte=today, deadline__lte=week)
        .annotate(
            applicants_count=Count(
                "applicants", filter=Q(applicants__student__is_active=True) & admission_q("applicants__student__")
            )
        )
        .filter(applicants_count__gt=0)
        .select_related("program__university")
        .order_by("deadline")
    )
    applying = sum(row.applicants_count for row in week_rounds)
    not_ready = StudentUniversity.objects.filter(
        GRADUATE,
        student__is_active=True,
        admission_round__deadline__gte=today,
        admission_round__deadline__lte=week,
    ).exclude(application_status="submitted")
    first = week_rounds.first()
    # герой дашборда стоит, только пока впереди есть дедлайн с подающими:
    # окно — настройка школы «Ближайшие сроки», неделя — его срочная часть (фаза 80)
    window_days = urgent_days()
    month_rounds = (
        AdmissionRound.objects.filter(deadline__gte=today, deadline__lte=today + timedelta(days=window_days))
        .annotate(
            applicants_count=Count(
                "applicants", filter=Q(applicants__student__is_active=True) & admission_q("applicants__student__")
            )
        )
        .filter(applicants_count__gt=0)
        .select_related("program__university")
        .order_by("deadline")
    )
    nearest = month_rounds.first()

    has_university = StudentUniversity.objects.filter(student=OuterRef("pk"))
    without_universities = students.annotate(has_u=Exists(has_university)).filter(has_u=False).count()
    from roadmap.models import ApplicationPlan

    has_plan = ApplicationPlan.objects.filter(student=OuterRef("pk"))
    without_plan = students.annotate(has_p=Exists(has_plan)).filter(has_p=False).count()

    match = _average_match()
    queue = pending_queue("director_admission")

    # баланс списков: только reach без safety, один вуз, сбалансирован
    tiers: dict[int, set[str]] = {}
    for row in StudentUniversity.objects.filter(GRADUATE, student__is_active=True).values_list("student_id", "tier"):
        tiers.setdefault(row[0], set()).add(row[1])
    counts: dict[int, int] = {}
    for student_id in StudentUniversity.objects.filter(GRADUATE, student__is_active=True).values_list(
        "student_id", flat=True
    ):
        counts[student_id] = counts.get(student_id, 0) + 1
    only_reach = sum(1 for sid, kinds in tiers.items() if "reach" in kinds and "safety" not in kinds)
    single = sum(1 for count in counts.values() if count == 1)
    balanced = sum(1 for sid, kinds in tiers.items() if {"reach", "safety"} <= kinds)

    # раунд «давно не сверяли» — настройка школы
    stale = today - timedelta(days=school_rules.value(school_rules.ROUND_STALE_DAYS))
    return {
        "role": "director_admission",
        "title": _("Поступление"),
        "owner": _("Асем · директор по поступлению"),
        "urgent": {
            "eyebrow": _("Дедлайны на этой неделе"),
            "applying": applying,
            "not_ready": not_ready.count(),
            "first": (
                {
                    "university": first.program.university.name,
                    "deadline": first.deadline,
                    "days": (first.deadline - today).days,
                }
                if first is not None
                else None
            ),
            # дедлайны ближайшего окна: без них героя на дашборде нет вовсе
            "window_days": window_days,
            "rounds": month_rounds.count(),
            "applicants": sum(row.applicants_count for row in month_rounds),
            "nearest": (
                {
                    "university": nearest.program.university.name,
                    "deadline": nearest.deadline,
                    "days": (nearest.deadline - today).days,
                }
                if nearest is not None
                else None
            ),
        },
        "stats": [
            {
                "code": "match",
                # процент пишется процентом: это соответствие требованиям,
                # а не шанс поступления (инвариант №11)
                "label": _("Среднее соответствие"),
                "value": f"{match}%" if match is not None else None,
                "note": _("по спискам"),
                "tone": "accent",
            },
            {
                "code": "no_universities",
                "label": _("Без вузов"),
                "value": without_universities,
                "note": _("из {total}").format(total=total),
                "tone": "bad",
            },
            {"code": "no_plan", "label": _("Без плана"), "value": without_plan, "note": "", "tone": "info"},
            {"code": "queue", "label": _("Ждут решения"), "value": queue["total"], "note": "", "tone": "warn"},
        ],
        "queue": queue,
        "balance": [
            {"title": _("Только reach, нет safety"), "count": only_reach, "tone": "bad", "chip": _("Риск")},
            {"title": _("Один вуз в списке"), "count": single, "tone": "warn", "chip": _("Мало")},
            {"title": _("Список сбалансирован"), "count": balanced, "tone": "good", "chip": _("Хорошо")},
        ],
        "directory": {
            "unverified_requirements": Program.objects.filter(requirement__is_verified=False).distinct().count(),
            "universities": University.objects.count(),
            "scholarships": Scholarship.objects.count(),
            "stale_rounds": AdmissionRound.objects.filter(Q(checked_at__isnull=True) | Q(checked_at__lt=stale)).count(),
        },
        "statuses_unset": AdmissionProfile.objects.filter(GRADUATE, student__is_active=True, status="").count(),
    }


def _average_match() -> int | None:
    """Среднее соответствие по спискам учеников.

    Механически от порогов требований, и называется соответствием, а не
    шансом (инвариант №11). Считается по последним ста двадцати строкам
    списков: на дашборде нужно среднее школы, а не полный перебор.
    """
    from universities.matching import match, match_rules

    rows = (
        StudentUniversity.objects.filter(GRADUATE, student__is_active=True)
        .select_related("student", "program__university", "program__requirement")
        .order_by("-id")[:120]
    )
    rules = match_rules()
    values = [
        result.percent for result in (match(row.student, row.program, rules) for row in rows) if result.has_requirements
    ]
    if not values:
        return None
    return round(sum(values) / len(values))


# --- Салтанат: школа -----------------------------------------------------


def call_list(limit: int = 8) -> list[dict]:
    """Кому позвонить сегодня: правила из справочника, а не из кода.

    Каждое правило говорит, что считать поводом («три пропуска подряд»),
    насколько это срочно и какой фразой это назвать. Телефон родителя —
    прямо в строке: иначе звонок откладывается до поиска контакта.
    """
    from engagement.models import CallCondition, CallRule

    rules = list(CallRule.objects.filter(is_active=True))
    if not rules:
        return []

    today = timezone.localdate()
    rows: dict[int, dict] = {}
    order = {"now": 0, "today": 1, "week": 2}

    def add(student, rule, detail: str) -> None:
        current = rows.get(student.pk)
        # причина — запись справочника: исходная формулировка переводится, своя — как введена
        title = stored_text.localize(rule.reason)
        reason = title if not detail else f"{title} · {detail}"
        if current is not None:
            if order[rule.urgency] < order[current["urgency"]]:
                current["urgency"] = rule.urgency
                current["urgency_title"] = rule.get_urgency_display()
            current["reasons"].append(reason)
            return
        contact = ParentContact.objects.filter(student=student).exclude(phone="").order_by("-is_primary", "id").first()
        rows[student.pk] = {
            "student_id": student.pk,
            "student": _short(student),
            "group": student.group.code if student.group_id else "",
            "urgency": rule.urgency,
            "urgency_title": rule.get_urgency_display(),
            "reasons": [reason],
            "contact": (
                {"name": contact.get_relation_display(), "phone": contact.phone} if contact is not None else None
            ),
        }

    for rule in rules:
        threshold = float(rule.threshold)
        if rule.condition == CallCondition.ABSENCES:
            found = BehaviorProfile.objects.filter(
                student__is_active=True, attendance_percent__isnull=False, attendance_percent__lt=threshold
            ).select_related("student", "student__group")
            for profile in found[:limit]:
                add(profile.student, rule, _("посещаемость {percent}%").format(percent=profile.attendance_percent))
        elif rule.condition == CallCondition.MOCK_DROP:
            for drop in mock_drops(limit=limit):
                if abs(drop["delta"]) < threshold:
                    continue
                student = Student.objects.select_related("group").filter(pk=drop["student_id"]).first()
                if student is not None:
                    add(student, rule, f"{drop['exam_type']} {drop['previous']} → {drop['latest']}")
        elif rule.condition == CallCondition.INACTIVE:
            edge = timezone.now() - timedelta(days=threshold)
            found = (
                _active()
                .select_related("group", "user")
                .filter(Q(user__last_login__lt=edge) | Q(user__last_login__isnull=True), user__isnull=False)
            )
            for student in found[:limit]:
                days = (timezone.now() - student.user.last_login).days if student.user.last_login else None
                add(
                    student,
                    rule,
                    (
                        tn(days, "{n} день без входа|{n} дня без входа|{n} дней без входа")
                        if days is not None
                        else _("не входил ни разу")
                    ),
                )
        elif rule.condition == CallCondition.MISSED_DEADLINE:
            missed = (
                StudentUniversity.objects.filter(
                    student__is_active=True,
                    admission_round__deadline__lt=today,
                )
                .exclude(application_status="submitted")
                .select_related("student", "student__group", "admission_round")
            )
            for row in missed[:limit]:
                add(row.student, rule, _("дедлайн {date}").format(date=f"{row.admission_round.deadline:%d.%m}"))
        elif rule.condition == CallCondition.NO_CONTACT:
            has_contact = ParentContact.objects.filter(student=OuterRef("pk"))
            found = _active().select_related("group").annotate(has_c=Exists(has_contact)).filter(has_c=False)
            for student in found[:limit]:
                add(student, rule, "")

    result = sorted(rows.values(), key=lambda row: (order[row["urgency"]], row["student"]))
    for row in result:
        row["reason"] = ", ".join(row.pop("reasons")[:2])
    return result[:limit]


def behavior_cabinet() -> dict:
    """Кому позвонить, группы плитками, очередь контактов и разговоры."""
    students = _active()
    total = students.count()
    calls = call_list()

    has_contact = ParentContact.objects.filter(student=OuterRef("pk"))
    without_contacts = students.annotate(has_c=Exists(has_contact)).filter(has_c=False).count()

    # «молчит» — не входил дольше срока из настроек школы
    edge = timezone.now() - timedelta(days=school_rules.value(school_rules.STUDENT_SILENT_DAYS))
    silent = students.filter(
        Q(user__last_login__lt=edge) | Q(user__last_login__isnull=True), user__isnull=False
    ).count()

    groups = list(
        StudyGroup.objects.filter(is_active=True)
        .annotate(
            students_count=Count("students", filter=Q(students__is_active=True), distinct=True),
            risk=Count(
                "students",
                filter=Q(students__is_active=True, students__behavior__attendance_percent__lt=80),
                distinct=True,
            ),
        )
        .values("id", "code", "students_count", "risk")
        .order_by("code")[:12]
    )

    supervision = BehaviorProfile.objects.filter(student__is_active=True, attendance_percent__lt=80).count()
    queue = pending_queue("director_behavior")
    return {
        "role": "director_behavior",
        "title": _("Школа"),
        "owner": _("Салтанат · директор школы"),
        "calls": calls,
        "stats": [
            {
                "code": "supervision",
                "label": _("Нужен контроль"),
                "value": supervision,
                "note": _("из {total}").format(total=total),
                "tone": "bad",
            },
            {
                "code": "no_contacts",
                "label": _("Без контактов родителей"),
                "value": without_contacts,
                "note": "",
                "tone": "warn",
            },
            {"code": "silent", "label": _("Не заходили месяц"), "value": silent, "note": "", "tone": "info"},
        ],
        "groups": groups,
        "queue": queue,
        "talks": _talks_week(),
    }


def _talks_week() -> dict:
    """Разговоры за неделю: записанные и вопросы, ждущие ответа."""
    from roadmap.models import TaskComment

    edge = timezone.now() - timedelta(days=7)
    written = TaskComment.objects.filter(created_at__gte=edge).count()
    waiting = TaskComment.objects.filter(created_at__gte=edge, author__role="student").count()
    return {"written": written, "waiting": waiting}


def _material_author(row) -> str:
    """Автор материала: ученик или сотрудник — у второго карточки ученика нет."""
    if row.author_id:
        return f"{row.author.last_name} {row.author.first_name}".strip()
    if row.staff_author_id:
        return row.staff_author.full_name or row.staff_author.email
    return "—"


# --- Арман: таланты ------------------------------------------------------


def talent_cabinet() -> dict:
    """Материалы на проверке, ближайшие олимпиады, олимпиадная группа."""
    from materials.models import MaterialStatus, StudyMaterial
    from students.models import Activity, TalentProfile

    pending = list(
        StudyMaterial.objects.filter(status=MaterialStatus.PENDING)
        .select_related("author", "staff_author", "subject")
        .order_by("created_at")[:6]
    )
    today = timezone.localdate()
    horizon = today + timedelta(days=horizon_days())
    olympiads = list(
        Activity.objects.filter(category="olympiad", date__gte=today, date__lte=horizon, student__is_active=True)
        .values("title", "date")
        .annotate(students=Count("id"))
        .order_by("date")[:6]
    )
    by_subject = list(
        # `order_by()` до `values`: сортировка модели (по дате) иначе входит
        # в группировку, и один предмет приходит несколькими строками (фаза 81)
        Activity.objects.filter(category="olympiad", student__is_active=True, subject__isnull=False)
        .order_by()
        .values(name=F("subject__name"))
        .annotate(students=Count("student_id", distinct=True))
        .order_by("-students")[:8]
    )

    group_size = _active().filter(in_olympiad_group=True).count()
    empty_portfolio = TalentProfile.objects.filter(student__is_active=True, portfolio_status="").count()
    queue = pending_queue("director_talent")
    return {
        "role": "director_talent",
        "title": _("Таланты"),
        "owner": _("Арман · директор талантов"),
        "stats": [
            {"code": "group", "label": _("В олимпиадной группе"), "value": group_size, "note": "", "tone": "accent"},
            {
                "code": "review",
                "label": _("Материалов на проверке"),
                "value": len(pending),
                "note": _("ваша основная работа"),
                "tone": "warn",
            },
            {
                "code": "library",
                "label": _("В библиотеке"),
                "value": StudyMaterial.objects.filter(status=MaterialStatus.APPROVED).count(),
                "note": _("материалов"),
                "tone": "info",
            },
            {
                "code": "empty",
                "label": _("Портфолио пустое"),
                "value": empty_portfolio,
                "note": _("из {total}").format(total=_active().count()),
                "tone": "bad",
            },
        ],
        "review": [
            {
                "id": row.pk,
                "title": row.title,
                "author": _material_author(row),
                "source": row.get_source_kind_display(),
                "files": row.files.count(),
                "rights_ok": row.rights_confirmed,
            }
            for row in pending
        ],
        "olympiads": [{"title": row["title"], "date": row["date"], "students": row["students"]} for row in olympiads],
        "by_subject": by_subject,
        "queue": queue,
    }


# --- Нурлыбек: спорт -----------------------------------------------------


def sport_cabinet() -> dict:
    """Календарь стартов, три числа, распределение по видам спорта."""
    today = timezone.localdate()
    horizon = today + timedelta(days=horizon_days())
    starts = list(
        Competition.objects.filter(student__is_active=True, date__gte=today, date__lte=horizon)
        .values("name", "date")
        .annotate(students=Count("student_id", distinct=True), applied=Count("id", filter=Q(has_certificate=True)))
        .order_by("date")[:8]
    )
    profiles = SportProfile.objects.filter(student__is_active=True, sport_type__isnull=False)
    by_sport = list(
        profiles.values(name=F("sport_type__name")).annotate(students=Count("id")).order_by("-students")[:8]
    )
    no_certificate = (
        Competition.objects.filter(student__is_active=True, has_certificate=False, date__lt=today).count() or 0
    )
    queue = pending_queue("director_sport")
    return {
        "role": "director_sport",
        "title": _("Спорт"),
        "owner": _("Нурлыбек · директор спорта"),
        "starts": [
            {
                "title": row["name"],
                "date": row["date"],
                "students": row["students"],
                # заявка считается поданной, когда у выступления есть отметка
                "applied": row["applied"] > 0,
            }
            for row in starts
        ],
        "stats": [
            {
                "code": "athletes",
                "label": _("Занимаются спортом"),
                "value": profiles.count(),
                "note": _("из {total}").format(total=_active().count()),
                "tone": "good",
            },
            {
                "code": "queue",
                "label": _("Ждут подтверждения"),
                "value": queue["total"],
                "note": _("выступлений"),
                "tone": "warn",
            },
            {
                "code": "no_certificate",
                "label": _("Без сертификата"),
                "value": no_certificate,
                "note": _("выступлений"),
                "tone": "bad",
            },
        ],
        "by_sport": by_sport,
        "queue": queue,
    }


# --- Администратор -------------------------------------------------------


def admin_cabinet() -> dict:
    """Реестр школы и то, что требует действий: приглашения, пароли, замки."""
    from accounts.models import LoginAttempt
    from core.models import ImportBatch
    from suggestions.models import LLMCall

    students = _active().select_related("group", "user").order_by("last_name", "first_name", "id")
    total = students.count()
    never = students.filter(Q(user__isnull=True) | Q(user__last_login__isnull=True)).count()

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_calls = LLMCall.objects.filter(created_at__gte=month_start)
    spent = float(month_calls.aggregate(total=Sum("cost"))["total"] or 0)
    calls_count = month_calls.count()

    locks = _locked_addresses()

    rows = []
    for student in students[:40]:
        user = student.user
        if user is None:
            status = {"code": "no_account", "title": _("Нет записи")}
        elif user.last_login is None:
            status = {"code": "never", "title": _("Не входил")}
        elif user.must_change_password:
            status = {"code": "temporary", "title": _("Пароль истёк")}
        else:
            status = {"code": "ok", "title": _("Вошёл")}
        rows.append(
            {
                "id": student.pk,
                "student": _short(student),
                "parallel": parallel_of(student),
                "group": student.group.code if student.group_id else "",
                "email": student.email,
                "status": status,
            }
        )

    # Кнопка в строке должна работать, а не подсвечиваться: вместе с числом
    # уходит и то, над чем действие выполнится, — почты для приглашения,
    # номера записей для нового пароля, адрес для снятия блокировки
    # приглашение письмом — тем, у кого есть почта; 8–10 без почты получают
    # пароль списком (раздача паролей) или ссылку от куратора
    without_account = list(
        students.filter(user__isnull=True, email__isnull=False).values_list("email", flat=True)[:100]
    )
    expired = list(students.filter(user__must_change_password=True).values_list("user_id", flat=True)[:100])
    actions = []
    if without_account:
        actions.append(
            {
                "code": "invite",
                "title": _("Приглашение не отправлено"),
                "note": counted(len(without_account), "ученик|ученика|учеников"),
                "action": _("Выслать"),
                "count": len(without_account),
                "emails": without_account,
            }
        )
    if expired:
        actions.append(
            {
                "code": "password",
                "title": _("Временный пароль истёк"),
                "note": counted(len(expired), "ученик|ученика|учеников"),
                "action": _("Выпустить"),
                "count": len(expired),
                "users": expired,
            }
        )
    for lock in locks:
        actions.append(
            {
                "code": "lock",
                "title": _("Блокировка входа"),
                "note": lock["value"],
                "action": _("Снять"),
                "count": 1,
                "scope": lock["scope"],
                "value": lock["value"],
            }
        )

    uploads = list(
        ImportBatch.objects.select_related("actor")
        .order_by("-created_at")[:5]
        .values("id", "file_name", "domain_code", "kind", "rows_created", "rows_updated", "status", "created_at")
    )
    return {
        "role": "admin",
        "title": _("Администрирование"),
        "owner": _("Администратор · реестр школы"),
        "stats": [
            {
                "code": "students",
                "label": _("Учеников"),
                "value": total,
                "note": tn(StudyGroup.objects.filter(is_active=True).count(), "{n} группа|{n} группы|{n} групп"),
                "tone": "accent",
            },
            {"code": "never", "label": _("Не входили ни разу"), "value": never, "note": "", "tone": "warn"},
            {
                "code": "spend",
                "label": _("Расходы ИИ за месяц"),
                "value": f"${spent:.2f}",
                "note": _("вызовов: {count}").format(count=calls_count),
                "tone": "info",
            },
            {"code": "locks", "label": _("Блокировок входа"), "value": len(locks), "note": "", "tone": "bad"},
        ],
        "registry": rows,
        "actions": actions,
        "uploads": uploads,
        "attempts": LoginAttempt.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=1), successful=False
        ).count(),
    }


def _locked_addresses() -> list[dict]:
    """Кому сейчас закрыт вход: считает тот же код, что и отказ на форме."""
    from accounts import passwords

    return [{"scope": lock.scope, "value": lock.value} for lock in passwords.current_locks()]


BUILDERS = {
    "director_exam": exam_cabinet,
    "director_admission": admission_cabinet,
    "director_behavior": behavior_cabinet,
    "director_talent": talent_cabinet,
    "director_sport": sport_cabinet,
    "admin": admin_cabinet,
}


def build(role: str, user=None) -> dict:
    """Кабинет роли. У ученика своя главная, сюда он не попадает.

    Кабинет куратора зависит от человека, а не только от роли: у каждого
    свои группы. Поэтому `user` — для него обязателен.
    """
    if role == "curator":
        return curator_cabinet(user) if user is not None else {}
    builder = BUILDERS.get(role)
    if builder is None:
        return {}
    return builder()
