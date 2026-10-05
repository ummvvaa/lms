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
    # формулы (задача 2): веса, планки и границы соответствия, потолок списка вузов
    "match_w_gpa": 30,
    "match_w_english": 30,
    "match_w_standardized": 25,
    "match_w_portfolio": 15,
    "match_floor_gpa": 2.0,
    "match_floor_ielts": 5.0,
    "match_floor_toefl": 45,
    "match_floor_sat": 800,
    "match_floor_act": 12,
    "match_tier_safety": 90,
    "match_tier_match": 70,
    "match_tier_reach": 45,
    "student_list_limit": 15,
    # готовность: веса доменов, планки, цели, баллы внутри поступления и спорта
    "readiness_w_exam": 35,
    "readiness_w_admission": 25,
    "readiness_w_talent": 20,
    "readiness_w_behavior": 10,
    "readiness_w_sport": 10,
    "readiness_ielts_floor": 4.0,
    "readiness_sat_floor": 800,
    "readiness_target_universities": 3,
    "readiness_talent_target": 8,
    "readiness_sport_competitions": 3,
    "readiness_points_list": 25,
    "readiness_points_common_app": 25,
    "readiness_points_account": 10,
    "readiness_points_ready": 40,
    "readiness_points_competitions": 60,
    "readiness_points_certificate": 25,
    "readiness_points_leadership": 15,
    # портфолио: веса разделов
    "portfolio_w_profile": 20,
    "portfolio_w_academics": 25,
    "portfolio_w_achievements": 20,
    "portfolio_w_olympiads": 10,
    "portfolio_w_sport": 10,
    "portfolio_w_documents": 15,
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


# --- Правила ушли из кода и окружения (05.10.2026) ----------------------------

#: имена настроек сервера, в которых правила жили раньше: в коде их быть не должно
FORMER_SETTINGS = (
    "CURATOR_RULES",
    "REMIND_EXAM_DAYS",
    "REMIND_DEADLINE_DAYS",
    "REMIND_TASK_DAYS",
    "REMIND_EXAM_TASK_DAYS",
    "REMIND_SCHOLARSHIP_DAYS",
    "SCHOLARSHIP_SOON_DAYS",
    "MATERIAL_MAX_FILE_MB",
    "MATERIAL_MAX_FILES",
    "LLM_MONTHLY_LIMIT",
    "SUGGESTION_CONFIDENCE_THRESHOLD",
    "DAY_MIN_ABSENT",
    "DAY_SHARE",
    "MATCH_WEIGHTS",
    "MATCH_FLOORS",
    "MATCH_TIERS",
    "STUDENT_LIST_LIMIT",
    "READINESS_WEIGHTS",
    "READINESS_BASELINES",
    "READINESS_ADMISSION",
    "READINESS_TALENT_TARGET",
    "READINESS_SPORT",
    "PORTFOLIO_WEIGHTS",
)


def _sources():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]
    for path in backend.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        yield path, path.read_text(encoding="utf-8")


def test_every_rule_is_read_by_the_code():
    """Правило на экране, которое код не читает, — рычаг, не подключённый ни к чему."""
    text = "\n".join(body for path, body in _sources() if path.name != "school_rules.py")
    names = {
        name: value
        for name, value in vars(school_rules).items()
        if name.isupper() and isinstance(value, str) and value in school_rules.BY_CODE
    }
    assert set(names.values()) == set(school_rules.BY_CODE), "у правила нет константы с кодом"
    unused = sorted(name for name in names if f"school_rules.{name}" not in text)
    assert not unused, f"правила, которые код не читает: {unused}"


def test_former_settings_and_env_names_are_gone():
    """Перенесённое правило не читается ни из настроек сервера, ни из окружения."""
    from pathlib import Path

    from django.conf import settings

    for name in FORMER_SETTINGS:
        assert not hasattr(settings, name), f"настройка {name} осталась в settings"
    hits = [
        f"{path.name}: {name}"
        for path, body in _sources()
        if path.name != "school_rules.py"
        for name in (*FORMER_SETTINGS, *school_rules.FORMER_ENV)
        # имя правила в реестре совпадает с прежним именем настройки — ищем обращение к настройке
        if f'"{name}"' in body or f"settings.{name}" in body
    ]
    assert not hits, f"прежние имена в коде: {hits}"
    root = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
    for example in ("deploy/.env.example", "deploy/.env.prod.example"):
        body = (root / example).read_text(encoding="utf-8")
        left = [name for name in school_rules.FORMER_ENV if f"{name}=" in body]
        assert not left, f"{example}: остались {left}"


def test_preflight_names_a_rule_left_in_the_environment(monkeypatch):
    """Переменная прежнего правила в окружении молча ничего не делает — preflight её называет."""
    from core.management.commands.preflight import _former_env_check

    for name in school_rules.FORMER_ENV:
        monkeypatch.delenv(name, raising=False)
    assert _former_env_check().ok
    monkeypatch.setenv("CURATOR_SAT_GAP", "200")
    check = _former_env_check()
    assert not check.ok and check.warn and "CURATOR_SAT_GAP" in check.detail


# --- Группы правил: веса с суммой 100 и границы по убыванию (задача 2) ----------


def test_groups_are_listed_and_their_defaults_hold_the_condition(admin):
    """Группа приходит с экраном: её правила по порядку; умолчания проходят её же проверку."""
    body = client_of(admin).get("/api/school-rules/").json()
    groups = {group["code"]: group for group in body["groups"]}
    assert set(groups) == {group.code for group in school_rules.GROUPS}
    rules = {row["code"]: row for row in body["rules"]}
    for group in school_rules.GROUPS:
        members = school_rules.members_of(group.code)
        assert members, f"в группе {group.code} нет правил"
        assert groups[group.code]["rules"] == [rule.code for rule in members]
        assert all(rule.section == group.section for rule in members)
        assert all(rules[rule.code]["group"] == group.code for rule in members)
        school_rules.check_group(group, {rule.code: rule.default for rule in members})
    assert groups["match_weights"]["check"] == "sum" and groups["match_weights"]["total"] == 100
    assert groups["match_tiers"]["check"] == "descending"


WEIGHTS = {"match_w_gpa": 40, "match_w_english": 30, "match_w_standardized": 20, "match_w_portfolio": 10}


def test_group_is_saved_whole_and_each_change_is_logged(admin):
    api = client_of(admin)
    body = api.patch("/api/school-rule-groups/match_weights/", {"values": WEIGHTS}, format="json").json()
    rules = {row["code"]: row for row in body["rules"]}
    assert {code: rules[code]["value"] for code in WEIGHTS} == WEIGHTS
    assert school_rules.values()["match_w_gpa"] == 40
    # в журнале — только то, что изменилось: английский остался 30
    logged = {row["code"]: (row["old_value"], row["new_value"]) for row in body["history"]}
    assert logged == {
        "match_w_gpa": ("30", "40"),
        "match_w_standardized": ("25", "20"),
        "match_w_portfolio": ("15", "10"),
    }
    assert all(row["section"] == "match" and row["actor"] == "Администратор Правил" for row in body["history"])

    body = api.post("/api/school-rule-groups/match_weights/reset/").json()
    rules = {row["code"]: row for row in body["rules"]}
    assert all(rules[code]["is_default"] for code in WEIGHTS)
    assert not SchoolRule.objects.exists()
    assert AuditLog.objects.filter(model_label=school_rules.AUDIT_LABEL).count() == 6


@pytest.mark.parametrize(
    "values",
    [
        {**WEIGHTS, "match_w_gpa": 35},  # сумма 95
        {**WEIGHTS, "match_w_gpa": 45},  # сумма 105
        {"match_w_gpa": 100},  # не все правила группы
        {**WEIGHTS, "match_floor_sat": 800},  # чужое правило
        {**WEIGHTS, "match_w_gpa": 140, "match_w_english": -70},  # сумма 100, но мимо границ
        None,
    ],
)
def test_group_with_a_wrong_sum_is_refused_whole(admin, values):
    response = client_of(admin).patch("/api/school-rule-groups/match_weights/", {"values": values}, format="json")
    assert response.status_code == 400 and response.json()["detail"]
    assert not SchoolRule.objects.exists()
    assert not AuditLog.objects.filter(model_label=school_rules.AUDIT_LABEL).exists()


def test_wrong_sum_is_named_in_the_refusal(admin):
    response = client_of(admin).patch(
        "/api/school-rule-groups/match_weights/", {"values": {**WEIGHTS, "match_w_gpa": 35}}, format="json"
    )
    assert "100" in response.json()["detail"] and "95" in response.json()["detail"]


def test_tiers_must_go_down(admin):
    """Границы категорий — по убыванию: иначе категория между ними пропадает."""
    api = client_of(admin)
    for wrong in (
        {"match_tier_safety": 70, "match_tier_match": 70, "match_tier_reach": 45},
        {"match_tier_safety": 90, "match_tier_match": 40, "match_tier_reach": 45},
    ):
        assert api.patch("/api/school-rule-groups/match_tiers/", {"values": wrong}, format="json").status_code == 400
    good = {"match_tier_safety": 95, "match_tier_match": 80, "match_tier_reach": 60}
    assert api.patch("/api/school-rule-groups/match_tiers/", {"values": good}, format="json").status_code == 200
    assert school_rules.values()["match_tier_match"] == 80


def test_a_rule_of_a_group_is_not_changed_alone(admin):
    """Вес по одному не правится и не сбрасывается: сумма перестала бы быть 100."""
    api = client_of(admin)
    assert api.patch("/api/school-rules/match_w_gpa/", {"value": 40}, format="json").status_code == 400
    assert api.post("/api/school-rules/match_w_gpa/reset/").status_code == 400
    assert api.patch("/api/school-rule-groups/nope/", {"values": {}}, format="json").status_code == 404
    assert api.post("/api/school-rule-groups/nope/reset/").status_code == 404
    assert not SchoolRule.objects.exists()


@pytest.mark.parametrize("role", [Role.DIRECTOR_ADMISSION, Role.CURATOR, Role.TEACHER, Role.STUDENT])
def test_only_the_admin_saves_a_group(role, make_user):
    api = client_of(make_user(role, f"groups.{role}@example.kz"))
    assert api.patch("/api/school-rule-groups/match_weights/", {"values": WEIGHTS}, format="json").status_code in (
        403,
        404,
    )
    assert api.post("/api/school-rule-groups/match_weights/reset/").status_code in (403, 404)
    assert school_rules.values()["match_w_gpa"] == 30


def test_match_formula_reads_the_rules_once_per_list(student):
    """Цикл по программам читает правила школы один раз, а не на каждую программу."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from universities.matching import open_programs
    from universities.models import AdmissionRequirement, Program, University

    university = University.objects.create(name="Rules U", country="США")
    for index in range(5):
        program = Program.objects.create(university=university, name=f"Program {index}", level="bachelor")
        AdmissionRequirement.objects.create(program=program, min_sat=1200)
    with CaptureQueriesContext(connection) as queries:
        results = open_programs(student)
    assert len(results) == 5
    assert sum("core_schoolrule" in query["sql"] for query in queries.captured_queries) == 1


def test_bar_tone_follows_the_match_boundary(student, set_rules):
    """Цвет полоски позиции считает сервер от границы match — числа во фронте нет."""
    from decimal import Decimal

    from universities.matching import match
    from universities.models import AdmissionRequirement, Program, University

    student.exam.sat_current = 1250
    student.exam.save()
    program = Program.objects.create(
        university=University.objects.create(name="Tone U", country="США"), name="Tone", level="bachelor"
    )
    AdmissionRequirement.objects.create(program=program, min_sat=1400, min_gpa=Decimal("1.0"))
    # SAT: (1250 − 800) / (1400 − 800) = 75 %
    row = {item["code"]: item for item in match(student, program).breakdown()}["standardized"]
    assert (row["percent"], row["tone"]) == (75, "accent")
    set_rules(match_tier_safety=95, match_tier_match=80, match_tier_reach=45)
    row = {item["code"]: item for item in match(student, program).breakdown()}["standardized"]
    assert (row["percent"], row["tone"]) == (75, "bad")
