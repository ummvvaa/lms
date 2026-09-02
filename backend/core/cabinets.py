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

from core.dashboards import mock_drops
from core.phrasing import counted
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

#: сколько дней вперёд смотрит «ближайшее» — экзамены, олимпиады, старты
HORIZON_DAYS = 60


def _active():
    return Student.objects.filter(is_active=True)


def _short(student) -> str:
    """«Ахметова Алия» — фамилия и имя, без отчества: строка списка узкая."""
    return f"{student.last_name} {student.first_name}".strip()


def _initials(student) -> str:
    letters = [part[0] for part in (student.last_name, student.first_name) if part]
    return "".join(letters).upper()


# --- Очередь «Ждут вашего решения» ---------------------------------------


def pending_queue(role: str) -> dict:
    """Сколько слов ученика ждёт решения владельца домена.

    Сами строки очереди отдаёт `/suggestions/from-students/` — тот же
    список, что и на экране предложений с фазы 37. Здесь только число
    для карточки: второй источник той же очереди разошёлся бы с первым
    в понимании того, что считать ждущим решения.
    """
    from suggestions.student_queue import pending_for

    return {"total": len(pending_for(role))}


# --- Кымбат: экзамены ----------------------------------------------------


def exam_cabinet() -> dict:
    """Средние баллы школы, очередь баллов и целей, просевшие моки."""
    profiles = ExamProfile.objects.filter(student__is_active=True)
    averages = profiles.aggregate(ielts=Avg("ielts_current"), sat=Avg("sat_current"))
    drops = mock_drops(limit=6)

    today = timezone.localdate()
    horizon = today + timedelta(days=HORIZON_DAYS)
    upcoming = list(
        ExamGoal.objects.filter(exam_date__gte=today, exam_date__lte=horizon, student__is_active=True)
        .values("exam_date", name=F("exam__name"))
        .annotate(students=Count("id"))
        .order_by("exam_date")[:6]
    )

    # Полоса диапазона открывает этих учеников в таблице, а не просто
    # подсвечивается: фильтр приходит вместе с числом, чтобы диапазон
    # и отбор не разошлись (то же правило, что у плиток фазы 8)
    ranges = [
        {
            "title": "IELTS 7.5 и выше",
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
            "title": "IELTS ниже 5.5",
            "count": profiles.filter(ielts_current__lt=5.5).count(),
            "filter": {"ielts_max": "5.5"},
        },
    ]

    has_goal = ExamGoal.objects.filter(student=OuterRef("pk"))
    without_goals = list(
        _active()
        .annotate(has_goal=Exists(has_goal))
        .filter(has_goal=False, group__isnull=False)
        .values(code=F("group__code"))
        .annotate(students=Count("id"))
        .order_by("code")[:8]
    )

    queue = pending_queue("director_exam")
    return {
        "role": "director_exam",
        "title": "Экзамены",
        "owner": "Кымбат · академический директор",
        "stats": [
            {
                "code": "ielts",
                "label": "Средний IELTS",
                "value": round(averages["ielts"], 1) if averages["ielts"] else None,
                "note": "цель школы 6.5",
                "tone": "teal",
            },
            {
                "code": "sat",
                "label": "Средний SAT",
                "value": round(averages["sat"]) if averages["sat"] else None,
                "note": "цель 1300",
                "tone": "indigo",
            },
            {
                "code": "drops",
                "label": "Мок просел",
                "value": len(drops),
                "note": "с прошлого раза",
                "tone": "risk",
            },
            {
                "code": "queue",
                "label": "Ждут решения",
                "value": queue["total"],
                "note": "внесли ученики",
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

    students = _active()
    total = students.count()
    today = timezone.localdate()
    week = today + timedelta(days=7)

    week_rounds = (
        AdmissionRound.objects.filter(deadline__gte=today, deadline__lte=week)
        .annotate(applicants_count=Count("applicants", filter=Q(applicants__student__is_active=True)))
        .filter(applicants_count__gt=0)
        .select_related("program__university")
        .order_by("deadline")
    )
    applying = sum(row.applicants_count for row in week_rounds)
    not_ready = StudentUniversity.objects.filter(
        student__is_active=True,
        admission_round__deadline__gte=today,
        admission_round__deadline__lte=week,
    ).exclude(application_status="submitted")
    first = week_rounds.first()

    has_university = StudentUniversity.objects.filter(student=OuterRef("pk"))
    without_universities = students.annotate(has_u=Exists(has_university)).filter(has_u=False).count()
    from roadmap.models import ApplicationPlan

    has_plan = ApplicationPlan.objects.filter(student=OuterRef("pk"))
    without_plan = students.annotate(has_p=Exists(has_plan)).filter(has_p=False).count()

    match = _average_match()
    queue = pending_queue("director_admission")

    # баланс списков: только reach без safety, один вуз, сбалансирован
    tiers: dict[int, set[str]] = {}
    for row in StudentUniversity.objects.filter(student__is_active=True).values_list("student_id", "tier"):
        tiers.setdefault(row[0], set()).add(row[1])
    counts: dict[int, int] = {}
    for student_id in StudentUniversity.objects.filter(student__is_active=True).values_list("student_id", flat=True):
        counts[student_id] = counts.get(student_id, 0) + 1
    only_reach = sum(1 for sid, kinds in tiers.items() if "reach" in kinds and "safety" not in kinds)
    single = sum(1 for count in counts.values() if count == 1)
    balanced = sum(1 for sid, kinds in tiers.items() if {"reach", "safety"} <= kinds)

    stale = today - timedelta(days=30)
    return {
        "role": "director_admission",
        "title": "Поступление",
        "owner": "Асем · директор по поступлению",
        "urgent": {
            "eyebrow": "Дедлайны на этой неделе",
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
        },
        "stats": [
            {
                "code": "match",
                # процент пишется процентом: это соответствие требованиям,
                # а не шанс поступления (инвариант №11)
                "label": "Среднее соответствие",
                "value": f"{match}%" if match is not None else None,
                "note": "по спискам",
                "tone": "brand",
            },
            {
                "code": "no_universities",
                "label": "Без вузов",
                "value": without_universities,
                "note": f"из {total}",
                "tone": "risk",
            },
            {"code": "no_plan", "label": "Без плана", "value": without_plan, "note": "", "tone": "indigo"},
            {"code": "queue", "label": "Ждут решения", "value": queue["total"], "note": "", "tone": "warn"},
        ],
        "queue": queue,
        "balance": [
            {"title": "Только reach, нет safety", "count": only_reach, "tone": "risk", "chip": "Риск"},
            {"title": "Один вуз в списке", "count": single, "tone": "warn", "chip": "Мало"},
            {"title": "Список сбалансирован", "count": balanced, "tone": "ok", "chip": "Хорошо"},
        ],
        "directory": {
            "unverified_requirements": Program.objects.filter(requirement__is_verified=False).distinct().count(),
            "universities": University.objects.count(),
            "scholarships": Scholarship.objects.count(),
            "stale_rounds": AdmissionRound.objects.filter(Q(checked_at__isnull=True) | Q(checked_at__lt=stale)).count(),
        },
        "statuses_unset": AdmissionProfile.objects.filter(student__is_active=True, status="").count(),
    }


def _average_match() -> int | None:
    """Среднее соответствие по спискам учеников.

    Механически от порогов требований, и называется соответствием, а не
    шансом (инвариант №11). Считается по последним ста двадцати строкам
    списков: на дашборде нужно среднее школы, а не полный перебор.
    """
    from universities.matching import match

    rows = (
        StudentUniversity.objects.filter(student__is_active=True)
        .select_related("student", "program__university", "program__requirement")
        .order_by("-id")[:120]
    )
    values = [result.percent for result in (match(row.student, row.program) for row in rows) if result.has_requirements]
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
        reason = rule.reason if not detail else f"{rule.reason} · {detail}"
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
                add(profile.student, rule, f"посещаемость {profile.attendance_percent}%")
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
                add(student, rule, f"{days} дн. без входа" if days is not None else "не входил ни разу")
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
                add(row.student, rule, f"дедлайн {row.admission_round.deadline:%d.%m}")
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

    edge = timezone.now() - timedelta(days=30)
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
        "title": "Школа",
        "owner": "Салтанат · директор школы",
        "calls": calls,
        "stats": [
            {
                "code": "supervision",
                "label": "Нужен контроль",
                "value": supervision,
                "note": f"из {total}",
                "tone": "risk",
            },
            {
                "code": "no_contacts",
                "label": "Без контактов родителей",
                "value": without_contacts,
                "note": "",
                "tone": "warn",
            },
            {"code": "silent", "label": "Не заходили месяц", "value": silent, "note": "", "tone": "indigo"},
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
    horizon = today + timedelta(days=HORIZON_DAYS)
    olympiads = list(
        Activity.objects.filter(category="olympiad", date__gte=today, date__lte=horizon, student__is_active=True)
        .values("title", "date")
        .annotate(students=Count("id"))
        .order_by("date")[:6]
    )
    by_subject = list(
        Activity.objects.filter(category="olympiad", student__is_active=True, subject__isnull=False)
        .values(name=F("subject__name"))
        .annotate(students=Count("student_id", distinct=True))
        .order_by("-students")[:8]
    )

    group_size = _active().filter(in_olympiad_group=True).count()
    empty_portfolio = TalentProfile.objects.filter(student__is_active=True, portfolio_status="").count()
    queue = pending_queue("director_talent")
    return {
        "role": "director_talent",
        "title": "Таланты",
        "owner": "Арман · директор талантов",
        "stats": [
            {"code": "group", "label": "В олимпиадной группе", "value": group_size, "note": "", "tone": "brand"},
            {
                "code": "review",
                "label": "Материалов на проверке",
                "value": len(pending),
                "note": "ваша основная работа",
                "tone": "warn",
            },
            {
                "code": "library",
                "label": "В библиотеке",
                "value": StudyMaterial.objects.filter(status=MaterialStatus.APPROVED).count(),
                "note": "материалов",
                "tone": "teal",
            },
            {
                "code": "empty",
                "label": "Портфолио пустое",
                "value": empty_portfolio,
                "note": f"из {_active().count()}",
                "tone": "risk",
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
    horizon = today + timedelta(days=HORIZON_DAYS)
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
        "title": "Спорт",
        "owner": "Нурлыбек · директор спорта",
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
                "label": "Занимаются спортом",
                "value": profiles.count(),
                "note": f"из {_active().count()}",
                "tone": "ok",
            },
            {
                "code": "queue",
                "label": "Ждут подтверждения",
                "value": queue["total"],
                "note": "выступлений",
                "tone": "warn",
            },
            {
                "code": "no_certificate",
                "label": "Без сертификата",
                "value": no_certificate,
                "note": "выступлений",
                "tone": "risk",
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
            status = {"code": "no_account", "title": "Нет записи"}
        elif user.last_login is None:
            status = {"code": "never", "title": "Не входил"}
        elif user.must_change_password:
            status = {"code": "temporary", "title": "Пароль истёк"}
        else:
            status = {"code": "ok", "title": "Вошёл"}
        rows.append(
            {
                "id": student.pk,
                "student": _short(student),
                "grade": student.grade,
                "group": student.group.code if student.group_id else "",
                "email": student.email,
                "status": status,
            }
        )

    # Кнопка в строке должна работать, а не подсвечиваться: вместе с числом
    # уходит и то, над чем действие выполнится, — почты для приглашения,
    # номера записей для нового пароля, адрес для снятия блокировки
    without_account = list(students.filter(user__isnull=True).values_list("email", flat=True)[:100])
    expired = list(students.filter(user__must_change_password=True).values_list("user_id", flat=True)[:100])
    actions = []
    if without_account:
        actions.append(
            {
                "code": "invite",
                "title": "Приглашение не отправлено",
                "note": counted(len(without_account), ("ученик", "ученика", "учеников")),
                "action": "Выслать",
                "count": len(without_account),
                "emails": without_account,
            }
        )
    if expired:
        actions.append(
            {
                "code": "password",
                "title": "Временный пароль истёк",
                "note": counted(len(expired), ("ученик", "ученика", "учеников")),
                "action": "Выпустить",
                "count": len(expired),
                "users": expired,
            }
        )
    for lock in locks:
        actions.append(
            {
                "code": "lock",
                "title": "Блокировка входа",
                "note": lock["value"],
                "action": "Снять",
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
        "title": "Администрирование",
        "owner": "Администратор · реестр школы",
        "stats": [
            {
                "code": "students",
                "label": "Учеников",
                "value": total,
                "note": f"{StudyGroup.objects.filter(is_active=True).count()} групп",
                "tone": "brand",
            },
            {"code": "never", "label": "Не входили ни разу", "value": never, "note": "", "tone": "warn"},
            {
                "code": "spend",
                "label": "Расходы ИИ за месяц",
                "value": f"${spent:.2f}",
                "note": f"вызовов: {calls_count}",
                "tone": "teal",
            },
            {"code": "locks", "label": "Блокировок входа", "value": len(locks), "note": "", "tone": "risk"},
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


def build(role: str) -> dict:
    """Кабинет роли. У ученика своя главная, сюда он не попадает."""
    builder = BUILDERS.get(role)
    if builder is None:
        return {}
    return builder()
