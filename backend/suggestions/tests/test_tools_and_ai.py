"""Инструменты модели, ограничения ИИ и приватность."""

from __future__ import annotations

import pytest
from django.test import override_settings

from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamProfile,
    SportProfile,
    Student,
    TalentProfile,
)
from suggestions import tools
from suggestions.tools import ToolContext, ToolDenied


def make(last: str, first: str, email: str, group) -> Student:
    s = Student.objects.create(
        last_name=last, first_name=first, email=email, grade=11, group=group, graduation_year=2027
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=s)
    return s


@pytest.fixture
def kymbat(make_user):
    return make_user("director_exam", "kymbat@school.kz", full_name="Кымбат")


@pytest.fixture
def context(kymbat):
    return ToolContext(actor=kymbat, role="director_exam")


# --- Права на инструменты ---


@pytest.mark.django_db
def test_tool_call_is_checked_against_role(context, group):
    """Инструмент чужой роли не выполнится, что бы ни попросила модель."""
    with pytest.raises(ToolDenied):
        tools.call("parse_certificate_stub", context)


@pytest.mark.django_db
def test_student_role_cannot_call_tools(make_user):
    context = ToolContext(actor=make_user("student", "s@school.kz"), role="student")
    with pytest.raises(ToolDenied):
        tools.call("find_student", context, query="Кто угодно")


@pytest.mark.django_db
def test_schemas_are_filtered_by_role():
    exam_tools = {t["name"] for t in tools.schemas_for("director_exam")}
    assert "propose_field_change" in exam_tools
    assert "find_student" in exam_tools


# --- Инструмент никогда не пишет в основные таблицы (инвариант №3) ---


@pytest.mark.django_db
def test_propose_does_not_touch_the_database(context, group):
    student = make("Ахметова", "Аружан", "a@school.kz", group)
    result = tools.call(
        "propose_field_change",
        context,
        student=student.pk,
        model="students.ExamProfile",
        field="ielts_current",
        value="7.5",
        confidence=0.95,
    )
    assert result["accepted"] is True
    assert len(context.rows) == 1

    student.exam.refresh_from_db()
    assert student.exam.ielts_current is None, "инструмент записал в основную таблицу"


@pytest.mark.django_db
def test_propose_refuses_foreign_domain(context, group):
    student = make("Ахметова", "Аружан", "a@school.kz", group)
    result = tools.call(
        "propose_field_change",
        context,
        student=student.pk,
        model="students.AdmissionProfile",
        field="status",
        value="A",
    )
    assert result["accepted"] is False
    assert context.rows == []


@pytest.mark.django_db
def test_find_student_records_ambiguity(context, group):
    make("Ахметова", "Аружан", "a1@school.kz", group)
    make("Ахметова", "Алия", "a2@school.kz", group)
    result = tools.call("find_student", context, query="Ахметова")
    assert result["is_ambiguous"]
    assert result["student"] is None
    assert context.ambiguities


# --- Минимизация персональных данных ---


@pytest.mark.django_db
def test_student_summary_sends_only_what_the_task_needs(context, group):
    """В модель уходят баллы, а не профиль целиком."""
    student = make("Ахметова", "Аружан", "a@school.kz", group)
    student.exam.ielts_current = "6.5"
    student.exam.save()
    student.behavior.status = "critical"
    student.behavior.remarks_count = 4
    student.behavior.save()

    payload = tools.call("get_student_summary", context, student=student.pk)
    assert payload["ielts"] == "6.5"
    # ни имени, ни почты, ни ярлыков дисциплины
    assert "full_name" not in payload
    assert "email" not in payload
    assert "critical" not in str(payload)


@pytest.mark.django_db
def test_requirements_tool_admits_when_data_is_missing(context, group):
    """Требований нет — так и говорим, а не выдумываем."""
    from universities.models import Program, University

    university = University.objects.create(name="U", country="C")
    program = Program.objects.create(university=university, name="CS")
    payload = tools.call("get_program_requirements", context, program=program.pk)
    assert payload["has_requirements"] is False
    assert "не заведены" in payload["detail"]


# --- Объяснение соответствия ---


@pytest.mark.django_db
def test_explanation_says_when_requirements_are_missing(group):
    from suggestions.explain import explain_student_program
    from universities.models import Program, University

    student = make("Ахметова", "Аружан", "a@school.kz", group)
    university = University.objects.create(name="U", country="C")
    program = Program.objects.create(university=university, name="CS")

    result = explain_student_program(student_id=student.pk, program_id=program.pk)
    assert result["has_requirements"] is False
    assert "не заведены" in result["text"]


@pytest.mark.django_db
def test_explanation_uses_only_registry_numbers(group):
    from suggestions.explain import explain_student_program
    from universities.models import AdmissionRequirement, Program, University

    student = make("Ахметова", "Аружан", "a@school.kz", group)
    student.exam.ielts_current = "6.0"
    student.exam.save()

    university = University.objects.create(name="U", country="C")
    program = Program.objects.create(university=university, name="CS")
    AdmissionRequirement.objects.create(program=program, min_ielts="6.5")

    result = explain_student_program(student_id=student.pk, program_id=program.pk)
    assert result["has_requirements"] is True
    assert "6.5" in result["text"]
    # никаких внутренних ярлыков в объяснении
    for label in ("critical", "weak", "A/B/C"):
        assert label not in result["text"]


# --- Ограничение по эссе ---


@pytest.mark.django_db
def test_essay_assist_only_asks_questions(group):
    """ИИ не пишет и не переписывает текст эссе."""
    from roadmap.models import Essay, EssayType
    from suggestions.essay_assist import ask_questions
    from suggestions.models import EssayAssistLog

    student = make("Ахметова", "Аружан", "a@school.kz", group)
    essay = Essay.objects.create(student=student, essay_type=EssayType.PERSONAL_STATEMENT, title="PS")

    result = ask_questions(essay_id=essay.pk, prompt="Хочу написать про олимпиаду по химии")
    assert result["ok"]
    assert "?" in result["questions"]

    # вся активность видна куратору
    log = EssayAssistLog.objects.get(essay=essay)
    assert log.prompt == "Хочу написать про олимпиаду по химии"
    assert log.questions == result["questions"]


@pytest.mark.django_db
def test_essay_system_prompt_forbids_writing():
    from suggestions.essay_assist import SYSTEM

    assert "запрещено" in SYSTEM.lower()
    assert "переписывать" in SYSTEM.lower()


# --- Журнал вызовов модели ---


@override_settings(LLM={"API_KEY": "", "BASE_URL": "https://example", "MODEL": "m", "TIMEOUT": 5, "NO_RETENTION": True})
def test_llm_is_optional():
    from suggestions.llm import LLMUnavailable, complete, is_configured

    assert is_configured() is False
    with pytest.raises(LLMUnavailable):
        complete(system="s", user="u", purpose="test")
