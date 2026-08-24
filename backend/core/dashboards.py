"""Данные пяти дашбордов и сводного.

Считаются агрегатами в базе — на 250 учениках это один-два запроса,
а не выборка всех строк в память.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Avg, Count, F, Q
from django.utils import timezone

from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamProfile,
    SportProfile,
    Student,
    StudyGroup,
    TalentProfile,
)
from universities.models import AdmissionRound, StudentUniversity


def _active():
    return Student.objects.filter(is_active=True)


def _bucket(qs, **conditions) -> int:
    return qs.filter(**conditions).count()


def behavior_dashboard() -> dict:
    """Салтанат: заполненность профилей, светофор, риски по посещаемости."""
    students = _active()
    total = students.count()
    profiles = BehaviorProfile.objects.filter(student__is_active=True)

    filled = profiles.filter(attendance_percent__isnull=False, homework_percent__isnull=False).count()
    traffic = {row["status"] or "unset": row["n"] for row in profiles.values("status").annotate(n=Count("id"))}

    worst_attendance = list(
        profiles.filter(attendance_percent__isnull=False)
        .order_by("attendance_percent")
        .values("student_id", "student__last_name", "student__first_name", "attendance_percent", "remarks_count")[:20]
    )
    worst_homework = list(
        profiles.filter(homework_percent__isnull=False)
        .order_by("homework_percent")
        .values("student_id", "student__last_name", "student__first_name", "homework_percent")[:20]
    )

    groups = list(
        StudyGroup.objects.filter(is_active=True)
        .annotate(
            students_count=Count("students", filter=Q(students__is_active=True), distinct=True),
            critical=Count(
                "students", filter=Q(students__behavior__status="critical", students__is_active=True), distinct=True
            ),
            filled=Count(
                "students",
                filter=Q(students__behavior__attendance_percent__isnull=False, students__is_active=True),
                distinct=True,
            ),
        )
        .values("code", "grade", "students_count", "critical", "filled")
        .order_by("code")
    )

    return {
        "total": total,
        "filled": filled,
        "traffic": traffic,
        "worst_attendance": worst_attendance,
        "worst_homework": worst_homework,
        "groups": groups,
    }


def admission_dashboard() -> dict:
    """Асем: счётчик слотов, распределение A/B/C, дедлайны, списки без Common App."""
    students = _active()
    total = students.count()
    profiles = AdmissionProfile.objects.filter(student__is_active=True)

    slots = StudentUniversity.objects.filter(student__is_active=True).count()
    statuses = {row["status"] or "unset": row["n"] for row in profiles.values("status").annotate(n=Count("id"))}

    with_three = students.annotate(n=Count("universities")).filter(n__gte=3).count()

    today = timezone.localdate()
    horizon = today + timedelta(days=120)
    deadlines = list(
        AdmissionRound.objects.filter(deadline__gte=today, deadline__lte=horizon)
        .annotate(applicants_count=Count("applicants", filter=Q(applicants__student__is_active=True)))
        .filter(applicants_count__gt=0)
        .values(
            "id",
            "deadline",
            "round_type",
            "applicants_count",
            university=F("program__university__name"),
            country=F("program__university__country"),
            program_name=F("program__name"),
        )
        .order_by("deadline")[:40]
    )

    popular = list(
        StudentUniversity.objects.filter(student__is_active=True)
        .values(name=F("program__university__name"))
        .annotate(n=Count("id"))
        .order_by("-n")[:8]
    )

    no_common_app = list(
        profiles.filter(has_common_app=False).values(
            "student_id", "student__last_name", "student__first_name", "status"
        )[:50]
    )
    no_account = list(
        profiles.filter(has_application_account=False).values(
            "student_id", "student__last_name", "student__first_name"
        )[:50]
    )

    return {
        "total": total,
        "slots": slots,
        "slots_target": total * 3,
        "statuses": statuses,
        "with_three_universities": with_three,
        "deadlines": deadlines,
        "popular": popular,
        "no_common_app": no_common_app,
        "no_application_account": no_account,
    }


def exam_dashboard() -> dict:
    """Кымбат: матрица шести корзин, кандидаты в TOP-30, падения моков."""
    profiles = ExamProfile.objects.filter(student__is_active=True)

    buckets = {
        "ielts_low": _bucket(profiles, ielts_current__lt=6),
        "ielts_mid": _bucket(profiles, ielts_current__gte=6, ielts_current__lt=7.5),
        "ielts_high": _bucket(profiles, ielts_current__gte=7.5),
        "sat_low": _bucket(profiles, sat_current__lt=1200),
        "sat_mid": _bucket(profiles, sat_current__gte=1200, sat_current__lt=1500),
        "sat_high": _bucket(profiles, sat_current__gte=1500),
    }

    top_ielts = list(
        profiles.filter(ielts_current__gte=6.5)
        .order_by("-ielts_current")
        .values("student_id", "student__last_name", "student__first_name", "ielts_current", "ielts_target")[:30]
    )
    top_sat = list(
        profiles.filter(sat_current__gte=1350)
        .order_by("-sat_current")
        .values("student_id", "student__last_name", "student__first_name", "sat_current", "sat_target")[:30]
    )

    return {
        "buckets": buckets,
        "top_ielts": top_ielts,
        "top_sat": top_sat,
        "mock_drops": mock_drops(),
        "averages": profiles.aggregate(ielts=Avg("ielts_current"), sat=Avg("sat_current")),
    }


def mock_drops(limit: int = 20) -> list[dict]:
    """Ученики, у которых последний мок хуже предыдущего.

    История моков лежит строками в `ExamAttempt` (инвариант №5), поэтому
    падение видно по двум последним попыткам, а не по одному полю.
    """
    from students.models import ExamAttempt

    attempts = (
        ExamAttempt.objects.filter(student__is_active=True, attempt_format="mock", total_score__isnull=False)
        .select_related("student")
        .order_by("student_id", "exam_type", "-date")
    )

    seen: dict[tuple[int, str], list] = {}
    for attempt in attempts:
        seen.setdefault((attempt.student_id, attempt.exam_type), []).append(attempt)

    drops = []
    for (student_id, exam_type), rows in seen.items():
        if len(rows) < 2:
            continue
        latest, previous = rows[0], rows[1]
        delta = float(latest.total_score) - float(previous.total_score)
        if delta < 0:
            drops.append(
                {
                    "student_id": student_id,
                    "student__last_name": latest.student.last_name,
                    "student__first_name": latest.student.first_name,
                    "exam_type": exam_type,
                    "latest": float(latest.total_score),
                    "previous": float(previous.total_score),
                    "delta": round(delta, 1),
                    "date": latest.date,
                }
            )
    return sorted(drops, key=lambda x: x["delta"])[:limit]


def talent_dashboard() -> dict:
    """Арман: распределение портфолио, разбивка по шести трекам, отсчёт до 1 ноября."""
    from students.models import Activity

    profiles = TalentProfile.objects.filter(student__is_active=True)
    portfolio = {
        row["portfolio_status"] or "unset": row["n"]
        for row in profiles.values("portfolio_status").annotate(n=Count("id"))
    }
    tracks = {row["main_track"] or "unset": row["n"] for row in profiles.values("main_track").annotate(n=Count("id"))}

    today = timezone.localdate()
    cutoff = today.replace(month=11, day=1)
    if cutoff < today:
        cutoff = cutoff.replace(year=today.year + 1)

    no_track = list(
        profiles.filter(main_track="").values(
            "student_id", "student__last_name", "student__first_name", "portfolio_status"
        )[:50]
    )
    weak = list(
        profiles.filter(portfolio_status="weak").values("student_id", "student__last_name", "student__first_name")[:50]
    )

    return {
        "portfolio": portfolio,
        "tracks": tracks,
        "days_to_november": (cutoff - today).days,
        "deadline": cutoff,
        "no_track": no_track,
        "weak_portfolio": weak,
        "categories": {
            row["category"]: row["n"]
            for row in Activity.objects.filter(student__is_active=True).values("category").annotate(n=Count("id"))
        },
    }


def sport_dashboard() -> dict:
    """Нурлыбек: перспективные спортсмены, календарь соревнований, сертификаты."""
    from students.models import Competition

    # название вида спорта достаём одним запросом: `sport_kind` больше
    # не текст, а ссылка на справочник (фаза 18)
    profiles = (
        SportProfile.objects.filter(student__is_active=True)
        .exclude(sport_type__isnull=True)
        .annotate(sport_name=F("sport_type__name"))
    )
    strong = list(
        profiles.filter(level__in=("regional", "national", "international")).values(
            "student_id", "student__last_name", "student__first_name", "sport_name", "level", "rank"
        )[:50]
    )

    with_certificate = set(
        Competition.objects.filter(student__is_active=True, has_certificate=True).values_list("student_id", flat=True)
    )
    no_certificate = [
        row
        for row in profiles.values("student_id", "student__last_name", "student__first_name", "level", "sport_name")
        if row["student_id"] not in with_certificate
    ][:50]

    today = timezone.localdate()
    calendar = list(
        Competition.objects.filter(student__is_active=True, date__gte=today)
        .values("name", "date")
        .annotate(participants=Count("id"))
        .order_by("date")[:30]
    )

    return {
        "athletes": profiles.count(),
        "strong": strong,
        "no_certificate": no_certificate,
        "calendar": calendar,
        "leaders": profiles.exclude(leadership_role="").count(),
    }


def school_overview() -> dict:
    """Сводный вид директора школы: вся школа в нескольких цифрах."""
    from core.readiness import compute

    students = list(
        _active()
        .select_related("behavior", "admission", "exam", "talent", "sport")
        .prefetch_related("universities", "activities", "competitions")
    )
    total = len(students)
    scores = [compute(s).score for s in students] if students else []

    exam = ExamProfile.objects.filter(student__is_active=True).aggregate(
        ielts=Avg("ielts_current"), sat=Avg("sat_current")
    )

    return {
        "total": total,
        "average_readiness": round(sum(scores) / len(scores)) if scores else 0,
        "average_ielts": round(float(exam["ielts"]), 1) if exam["ielts"] else None,
        "average_sat": round(float(exam["sat"])) if exam["sat"] else None,
        "ready_to_apply": AdmissionProfile.objects.filter(student__is_active=True, status="A").count(),
        "at_risk": BehaviorProfile.objects.filter(student__is_active=True, status="critical").count(),
        "domains": {
            "behavior": BehaviorProfile.objects.filter(student__is_active=True, status="can_execute").count(),
            "admission": AdmissionProfile.objects.filter(student__is_active=True, status="A").count(),
            "exam": ExamProfile.objects.filter(student__is_active=True, ielts_current__gte=6.5).count(),
            "talent": TalentProfile.objects.filter(student__is_active=True)
            .exclude(portfolio_status="weak")
            .exclude(portfolio_status="")
            .count(),
            "sport": SportProfile.objects.filter(student__is_active=True).exclude(sport_type__isnull=True).count(),
        },
    }


DASHBOARDS = {
    "behavior": behavior_dashboard,
    "admission": admission_dashboard,
    "exam": exam_dashboard,
    "talent": talent_dashboard,
    "sport": sport_dashboard,
}
