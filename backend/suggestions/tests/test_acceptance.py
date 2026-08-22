"""Критерий приёмки Фазы 5 целиком, как его описал заказчик.

Директор экзаменов вставляет кусок переписки с баллами восьми учеников
и получает предпросмотр, где двое помечены как неоднозначные. Принимает
шесть из восьми — применяются только они. Откат возвращает прежние значения.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from core.models import AuditLog
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamProfile,
    SportProfile,
    Student,
    TalentProfile,
)
from suggestions.engine import apply_suggestion, create_suggestion, revert_suggestion
from suggestions.parsers import rows_for_suggestion


def make(last: str, first: str, email: str, group) -> Student:
    s = Student.objects.create(
        last_name=last, first_name=first, email=email, grade=11, group=group, graduation_year=2027
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=s)
    return s


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def kymbat(make_user):
    return make_user("director_exam", "kymbat@school.kz", full_name="Кымбат")


@pytest.fixture
def school(db, group):
    """Восемь учеников, среди них две однофамилицы Ахметовы."""
    return {
        "aruzhan": make("Ахметова", "Аружан", "aruzhan@school.kz", group),
        "aliya": make("Ахметова", "Алия", "aliya@school.kz", group),
        "damir": make("Сериков", "Дамир", "damir@school.kz", group),
        "alikhan": make("Абдрахманов", "Алихан", "alikhan@school.kz", group),
        "zhanna": make("Тлеубаева", "Жанна", "zhanna@school.kz", group),
        "madina": make("Оспанова", "Мадина", "madina@school.kz", group),
        "arsen": make("Калиев", "Арсен", "arsen@school.kz", group),
        "diana": make("Рахимова", "Диана", "diana@school.kz", group),
    }


#: Кусок переписки — ровно так, как его пришлют в мессенджере.
PASTE = """Кымбат, вот результаты последнего мока:
Сериков Дамир — 1320
Абдрахманов Алихан: 1280
Тлеубаева Жанна — 1450
Оспанова Мадина - 1190
Калиев Арсен — 1360
Рахимова Диана: 1240
Ахметова — 1300
Ахметова А. — 1220
"""


@pytest.mark.django_db
def test_paste_eight_students_two_are_ambiguous(school):
    """Двое помечены как неоднозначные: обе Ахметовы не различимы по строке."""
    rows, ambiguities = rows_for_suggestion(PASTE)

    assert len(ambiguities) == 2, [a["query"] for a in ambiguities]
    assert {a["query"] for a in ambiguities} == {"Ахметова", "Ахметова А"}
    assert all(a["is_ambiguous"] for a in ambiguities)
    # по каждой неоднозначности показаны кандидаты — «нашлось двое, выберите»
    for ambiguity in ambiguities:
        assert len(ambiguity["candidates"]) >= 2

    # остальные шесть разобрались однозначно
    assert len(rows) == 6
    assert {r["field"] for r in rows} == {"sat_current"}


@pytest.mark.django_db
def test_accepting_six_applies_only_six_and_revert_restores(kymbat, school):
    # у одного ученика уже есть балл — проверим, что откат вернёт именно его
    school["damir"].exam.sat_current = 1100
    school["damir"].exam.save()

    rows, ambiguities = rows_for_suggestion(PASTE)
    suggestion, rejected = create_suggestion(
        author=kymbat,
        role="director_exam",
        domain_code="exam",
        source_type="paste",
        command="paste_as_is",
        rows=rows,
    )
    assert rejected == []
    assert suggestion.changes.count() == 6
    assert len(ambiguities) == 2

    # ничего ещё не применено — база не тронута
    school["damir"].exam.refresh_from_db()
    assert school["damir"].exam.sat_current == 1100

    ids = list(suggestion.changes.values_list("pk", flat=True))
    result = apply_suggestion(suggestion, actor=kymbat, change_ids=ids)
    assert result["applied"] == 6
    assert result["conflicts"] == []

    school["damir"].exam.refresh_from_db()
    school["zhanna"].exam.refresh_from_db()
    assert school["damir"].exam.sat_current == 1320
    assert school["zhanna"].exam.sat_current == 1450

    # обе Ахметовы не тронуты: их строки в предложение не попали
    for key in ("aruzhan", "aliya"):
        school[key].exam.refresh_from_db()
        assert school[key].exam.sat_current is None

    # откат возвращает прежние значения
    revert = revert_suggestion(suggestion, actor=kymbat)
    assert revert["reverted"] == 6

    school["damir"].exam.refresh_from_db()
    assert school["damir"].exam.sat_current == 1100
    school["zhanna"].exam.refresh_from_db()
    assert school["zhanna"].exam.sat_current is None


@pytest.mark.django_db
def test_full_flow_through_api(api, kymbat, school, settings):
    """Тот же путь через HTTP: вставка, предпросмотр, частичное принятие, откат."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    api.force_authenticate(kymbat)

    response = api.post("/api/commands/paste/", {"text": PASTE}, format="json")
    assert response.status_code == 202
    task_id = response.data["task"]

    state = api.get(f"/api/tasks/status/{task_id}/").data
    assert state["state"] == "SUCCESS"
    payload = state["result"]
    assert payload["rows"] == 6
    assert len(payload["ambiguities"]) == 2

    suggestion_id = payload["suggestion"]
    preview = api.get(f"/api/suggestions/{suggestion_id}/").data
    assert len(preview["changes"]) == 6
    # сомнительное сверху: строки отсортированы по возрастанию уверенности
    confidences = [float(c["confidence"]) for c in preview["changes"]]
    assert confidences == sorted(confidences)

    chosen = [c["id"] for c in preview["changes"][:4]]
    applied = api.post(f"/api/suggestions/{suggestion_id}/apply/", {"changes": chosen}, format="json").data
    assert applied["applied"] == 4
    assert applied["status"] == "partially_applied"

    # в аудите ровно четыре записи со ссылкой на предложение
    logs = AuditLog.objects.filter(suggestion_id=suggestion_id)
    assert logs.count() == 4
    assert all(log.source == "ai" for log in logs)

    reverted = api.post(f"/api/suggestions/{suggestion_id}/revert/", {}, format="json").data
    assert reverted["reverted"] == 4
    assert AuditLog.objects.filter(suggestion_id=suggestion_id).count() == 8


@pytest.mark.django_db
def test_resolving_ambiguity_adds_the_row_human_chose(api, kymbat, school):
    """«Нашлось двое, выберите» — человек указал Аружан."""
    rows, _ = rows_for_suggestion(PASTE)
    suggestion, _ = create_suggestion(
        author=kymbat, role="director_exam", domain_code="exam", source_type="paste", rows=rows
    )

    api.force_authenticate(kymbat)
    response = api.post(
        f"/api/suggestions/{suggestion.pk}/resolve-ambiguity/",
        {
            "query": "Ахметова",
            "student": school["aruzhan"].pk,
            "model": "students.ExamProfile",
            "field": "sat_current",
            "value": 1300,
            "source_quote": "Ахметова — 1300",
        },
        format="json",
    )
    assert response.status_code == 201
    assert float(response.data["confidence"]) == 1.0

    change_id = response.data["id"]
    api.post(f"/api/suggestions/{suggestion.pk}/apply/", {"changes": [change_id]}, format="json")

    school["aruzhan"].exam.refresh_from_db()
    school["aliya"].exam.refresh_from_db()
    assert school["aruzhan"].exam.sat_current == 1300
    assert school["aliya"].exam.sat_current is None


@pytest.mark.django_db
def test_ambiguity_resolution_still_checks_domain(api, kymbat, school):
    suggestion, _ = create_suggestion(
        author=kymbat, role="director_exam", domain_code="exam", source_type="paste", rows=[]
    )
    api.force_authenticate(kymbat)
    response = api.post(
        f"/api/suggestions/{suggestion.pk}/resolve-ambiguity/",
        {
            "query": "Ахметова",
            "student": school["aruzhan"].pk,
            "model": "students.AdmissionProfile",
            "field": "status",
            "value": "A",
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_director_sees_only_own_domain_suggestions(api, kymbat, make_user, school):
    create_suggestion(author=kymbat, role="director_exam", domain_code="exam", source_type="paste", rows=[])
    asem = make_user("director_admission", "asem@school.kz")
    create_suggestion(author=asem, role="director_admission", domain_code="admission", source_type="paste", rows=[])

    api.force_authenticate(kymbat)
    body = api.get("/api/suggestions/").data
    assert {row["domain_code"] for row in body["results"]} == {"exam"}


@pytest.mark.django_db
def test_student_gets_no_suggestions(api, make_user, school):
    student = school["aruzhan"]
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    api.force_authenticate(user)
    assert api.get("/api/suggestions/").data["results"] == []
    assert api.post("/api/commands/paste/", {"text": PASTE}, format="json").status_code == 403


@pytest.mark.django_db
def test_commands_are_filtered_by_role(api, kymbat, make_user):
    api.force_authenticate(kymbat)
    exam_commands = {c["code"] for c in api.get("/api/commands/").data["commands"]}
    assert "parse_mock" in exam_commands
    assert "check_balance" not in exam_commands  # это кнопка Асем

    api.force_authenticate(make_user("director_admission", "asem@school.kz"))
    admission_commands = {c["code"] for c in api.get("/api/commands/").data["commands"]}
    assert "check_balance" in admission_commands
    assert "parse_mock" not in admission_commands


@pytest.mark.django_db
def test_every_offered_command_is_actually_built(api, kymbat, make_user):
    """Фаза 8, дефект B4: кнопка без обработчика — дефект, а не обещание.

    Реестр не должен предлагать действия, которых нет: раньше из двенадцати
    кнопок работала одна, остальные были нарисованы карточками без клика.
    """
    from suggestions.commands import COMMANDS, NOT_BUILT_YET

    offered = {c.code for c in COMMANDS}
    assert offered & set(NOT_BUILT_YET) == set()

    for role, user in (
        ("director_exam", kymbat),
        ("director_admission", make_user("director_admission", "a@school.kz")),
    ):
        api.force_authenticate(user)
        for command in api.get("/api/commands/").data["commands"]:
            assert command["code"] not in NOT_BUILT_YET, f"{role}: {command['code']} предлагается, но не построен"
