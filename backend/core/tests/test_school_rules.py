"""Правила школы — настройки администратора, а не константы (решение владельца, 30.09.2026).

Экран «Настройки школы»: текущее значение, значение по умолчанию, проверка
границ, «Сбросить». Правка — строкой журнала «кто, когда, было → стало»,
значение действует со следующего запроса без перезапуска.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import Role
from core import school_rules
from core.models import AuditLog, SchoolRule

pytestmark = pytest.mark.django_db


def client_of(user) -> APIClient:
    api = APIClient()
    api.force_login(user)
    return api


@pytest.fixture
def admin(make_user):
    return make_user(Role.ADMIN, "rules.admin@example.kz", full_name="Администратор Правил")


def test_defaults_are_listed_with_bounds(admin):
    body = client_of(admin).get("/api/school-rules/").json()
    rules = {row["code"]: row for row in body["rules"]}
    assert rules["attendance_below"]["value"] == rules["attendance_below"]["default"] == 85
    assert rules["quarter_grade_below"]["value"] == 4
    assert rules["fo_only_below"]["value"] == 60
    assert rules["no_grades_days"]["value"] == 14
    assert (rules["attendance_below"]["minimum"], rules["attendance_below"]["maximum"]) == (0, 100)
    assert (rules["no_grades_days"]["minimum"], rules["no_grades_days"]["maximum"]) == (1, 90)
    assert all(row["is_default"] for row in body["rules"])
    assert body["history"] == []


@pytest.mark.parametrize(
    "role",
    [
        Role.DIRECTOR_BEHAVIOR,
        Role.DIRECTOR_ADMISSION,
        Role.DIRECTOR_EXAM,
        Role.DIRECTOR_TALENT,
        Role.DIRECTOR_SPORT,
        Role.CURATOR,
        Role.TEACHER,
        Role.STUDENT,
    ],
)
def test_only_the_admin_reads_and_changes_rules(role, make_user):
    api = client_of(make_user(role, f"rules.{role}@example.kz"))
    assert api.get("/api/school-rules/").status_code in (403, 404)
    assert api.patch("/api/school-rules/attendance_below/", {"value": 70}, format="json").status_code in (403, 404)
    assert api.post("/api/school-rules/attendance_below/reset/").status_code in (403, 404)
    assert school_rules.value(school_rules.ATTENDANCE_BELOW) == 85


@pytest.mark.parametrize(
    ("code", "value"),
    [
        ("attendance_below", 101),
        ("attendance_below", -1),
        ("attendance_below", "восемьдесят"),
        ("attendance_below", 80.5),
        ("no_grades_days", 0),
        ("no_grades_days", 91),
        ("quarter_grade_below", 6),
        ("fo_only_below", ""),
    ],
)
def test_values_outside_the_bounds_are_refused(admin, code, value):
    response = client_of(admin).patch(f"/api/school-rules/{code}/", {"value": value}, format="json")
    assert response.status_code == 400
    assert response.json()["detail"]
    assert not SchoolRule.objects.exists()
    assert not AuditLog.objects.filter(model_label=school_rules.AUDIT_LABEL).exists()


def test_unknown_rule_is_not_found(admin):
    assert client_of(admin).patch("/api/school-rules/nope/", {"value": 1}, format="json").status_code == 404


def test_change_and_reset_are_logged_who_when_was_became(admin):
    api = client_of(admin)
    body = api.patch("/api/school-rules/attendance_below/", {"value": 70}, format="json").json()
    rule = next(row for row in body["rules"] if row["code"] == "attendance_below")
    assert rule["value"] == 70 and rule["is_default"] is False
    assert body["history"][0]["old_value"] == "85" and body["history"][0]["new_value"] == "70"
    assert body["history"][0]["actor"] == "Администратор Правил"

    # то же значение — записи нет
    api.patch("/api/school-rules/attendance_below/", {"value": "70"}, format="json")
    assert AuditLog.objects.filter(model_label=school_rules.AUDIT_LABEL).count() == 1

    body = api.post("/api/school-rules/attendance_below/reset/").json()
    rule = next(row for row in body["rules"] if row["code"] == "attendance_below")
    assert rule["value"] == 85 and rule["is_default"] is True
    entries = list(AuditLog.objects.filter(model_label=school_rules.AUDIT_LABEL).order_by("id"))
    assert [(e.old_value, e.new_value) for e in entries] == [("85", "70"), ("70", "85")]
    assert all(e.actor_id == admin.pk and e.domain_code == "settings" and e.source == "manual" for e in entries)
    assert not SchoolRule.objects.exists()


def test_new_value_works_at_once_without_restart(admin, make_user):
    """Порог посещаемости поменяли — «Риски» Салтанат считают по новому со следующего запроса."""
    saltanat = client_of(make_user(Role.DIRECTOR_BEHAVIOR, "rules.saltanat@example.kz"))
    assert saltanat.get("/api/acad/risks/").json()["threshold"] == 85
    client_of(admin).patch("/api/school-rules/attendance_below/", {"value": 60}, format="json")
    assert saltanat.get("/api/acad/risks/").json()["threshold"] == 60


def test_attendance_threshold_is_not_a_constant_anymore():
    """Порог не читается ни из настроек сервера, ни из окружения."""
    from pathlib import Path

    from django.conf import settings

    assert "RISK_ATTENDANCE_BELOW" not in settings.ACADEMICS_RULES
    root = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
    for example in ("deploy/.env.example", "deploy/.env.prod.example"):
        assert "RISK_ATTENDANCE_BELOW" not in (root / example).read_text(encoding="utf-8")


def test_yes_no_rule_and_lesson_length_are_settings_too(admin):
    """«Уважительная снижает процент» — да/нет с журналом; длина урока — число в границах."""
    api = client_of(admin)
    rules = {row["code"]: row for row in api.get("/api/school-rules/").json()["rules"]}
    assert rules["excused_lowers_attendance"]["kind"] == "bool" and rules["excused_lowers_attendance"]["value"] == 1
    assert rules["lesson_minutes_default"]["value"] == 40

    assert (
        api.patch("/api/school-rules/excused_lowers_attendance/", {"value": "может"}, format="json").status_code == 400
    )
    body = api.patch("/api/school-rules/excused_lowers_attendance/", {"value": "нет"}, format="json").json()
    assert body["history"][0]["old_value"] == "да" and body["history"][0]["new_value"] == "нет"
    assert school_rules.value(school_rules.EXCUSED_LOWERS_ATTENDANCE) == 0
    api.post("/api/school-rules/excused_lowers_attendance/reset/")
    assert school_rules.value(school_rules.EXCUSED_LOWERS_ATTENDANCE) == 1

    assert api.patch("/api/school-rules/lesson_minutes_default/", {"value": 5}, format="json").status_code == 400
    assert api.patch("/api/school-rules/lesson_minutes_default/", {"value": 45}, format="json").status_code == 200
    assert school_rules.value(school_rules.LESSON_MINUTES_DEFAULT) == 45


# --- Разделы экрана и дробные правила (05.10.2026) ----------------------------


def test_every_rule_sits_in_a_listed_section(admin):
    """Экран делится на разделы: у каждого правила — раздел из списка, пустых разделов нет."""
    body = client_of(admin).get("/api/school-rules/").json()
    codes = [section["code"] for section in body["sections"]]
    assert codes == [section.code for section in school_rules.SECTIONS]
    assert all(section["title"] and section["note"] for section in body["sections"])
    used = {row["section"] for row in body["rules"]}
    assert used == set(codes)
    assert len({rule.code for rule in school_rules.RULES}) == len(school_rules.RULES)


#: Умолчания равны тому, что было зашито в коде и `.env` до переноса: после выката
#: поведение прода не меняется, пока администратор сам не поменял правило
FORMER_CONSTANTS = {
    "day_absent_min": 2,
    "day_absent_share": 60,
    "unmarked_remind_minutes": 10,
    "assistant_attendance_days": 30,
    "profile_stale_days": 14,
    "finals_window_days": 6,
    "empty_journal_days": 14,
    "unmarked_lessons_days": 7,
    "mock_stale_days": 30,
    "exam_soon_days": 60,
    "ielts_gap": 1.0,
    "sat_gap": 100,
    "ielts_jump": 1.5,
    "sat_jump": 150,
    "queue_gap_share": 20,
    "document_expiring_days": 60,
    "document_notice_days": 14,
    "curator_task_soon_days": 2,
    "deadline_close_days": 7,
    "deadline_near_days": 14,
    "deadline_soon_days": 30,
    "deadline_horizon_days": 60,
    "deadline_dashboard_days": 120,
    "deadline_tight_days": 3,
    "student_silent_days": 30,
    "round_stale_days": 30,
    "plan_idle_days": 7,
    "remind_exam_days": 14,
    "remind_deadline_days": 14,
    "remind_task_days": 3,
    "remind_exam_task_days": 30,
    "remind_scholarship_days": 21,
    "documents_task_days": 7,
    "next_mock_days": 21,
    "material_file_mb": 15,
    "material_max_files": 10,
    "prep_audio_mb": 20,
    "practice_size": 10,
    "practice_weak_share": 60,
    "llm_monthly_limit": 0,
}


def test_defaults_equal_the_former_constants():
    values = school_rules.values()
    assert {code: values[code] for code in FORMER_CONSTANTS} == FORMER_CONSTANTS
    for code, default in FORMER_CONSTANTS.items():
        rule = school_rules.BY_CODE[code]
        assert rule.minimum <= default <= rule.maximum


def test_decimal_rule_keeps_tenths_and_reads_a_comma(admin):
    """Балл IELTS — дробный: запятая и точка читаются одинаково, шаг — половина балла."""
    api = client_of(admin)
    rule = next(row for row in api.get("/api/school-rules/").json()["rules"] if row["code"] == "ielts_jump")
    assert (rule["kind"], rule["value"], rule["step"], rule["minimum"]) == ("decimal", 1.5, 0.5, 0.5)

    body = api.patch("/api/school-rules/ielts_jump/", {"value": "2,5"}, format="json").json()
    rule = next(row for row in body["rules"] if row["code"] == "ielts_jump")
    assert rule["value"] == 2.5 and rule["is_default"] is False
    assert SchoolRule.objects.get(code="ielts_jump").value == 25
    assert school_rules.value(school_rules.IELTS_JUMP) == 2.5
    assert (body["history"][0]["old_value"], body["history"][0]["new_value"]) == ("1.5", "2.5")
    assert body["history"][0]["section"] == "curator"

    # то же значение точкой — правки нет
    api.patch("/api/school-rules/ielts_jump/", {"value": 2.5}, format="json")
    assert AuditLog.objects.filter(model_label=school_rules.AUDIT_LABEL).count() == 1

    for wrong in ("2.3", "0", "9.5", "1.55", "полтора"):
        assert api.patch("/api/school-rules/ielts_jump/", {"value": wrong}, format="json").status_code == 400
    assert school_rules.value(school_rules.IELTS_JUMP) == 2.5

    api.post("/api/school-rules/ielts_jump/reset/")
    assert school_rules.value(school_rules.IELTS_JUMP) == 1.5
