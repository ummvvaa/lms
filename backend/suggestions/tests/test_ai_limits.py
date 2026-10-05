"""Ограничения ИИ: объяснение только по справочнику, эссе без переписывания, модель необязательна."""

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


def make(last: str, first: str, email: str, group) -> Student:
    s = Student.objects.create(last_name=last, first_name=first, email=email, group=group, graduation_year=2027)
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=s)
    return s


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


@pytest.mark.django_db  # месячный лимит — настройка школы, читается из базы
@override_settings(LLM={"API_KEY": "", "BASE_URL": "https://example", "MODEL": "m", "TIMEOUT": 5, "NO_RETENTION": True})
def test_llm_is_optional():
    from suggestions.llm import LLMUnavailable, complete, is_configured

    assert is_configured() is False
    with pytest.raises(LLMUnavailable):
        complete(system="s", user="u", purpose="test")
