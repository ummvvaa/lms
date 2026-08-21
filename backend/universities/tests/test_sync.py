"""Фоновая сверка дедлайнов: белый список, источник, предложение."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from suggestions.models import Suggestion
from universities import sync
from universities.models import AdmissionRound, Program, University

PAGE = """
<html><body>
<h1>Apply to Computer Science</h1>
<p>The Early Decision deadline is November 1, 2026 for all first-year applicants.</p>
<p>Regular Decision applications are due January 15, 2027.</p>
<script>var x = "March 3, 2020";</script>
</body></html>
"""


@pytest.fixture
def toronto(db):
    university = University.objects.create(
        name="University of Toronto", country="Канада", domain="utoronto.ca", website="https://utoronto.ca/apply"
    )
    program = Program.objects.create(university=university, name="Computer Science")
    return AdmissionRound.objects.create(
        program=program,
        round_type="RD",
        deadline=date(2027, 1, 20),  # в справочнике старая дата
        source_url="https://admissions.utoronto.ca/apply",
    )


# --- Белый список ---


@pytest.mark.django_db
def test_university_domain_is_allowed(toronto):
    assert sync.is_allowed("https://admissions.utoronto.ca/apply") is True
    assert sync.is_allowed("https://utoronto.ca/apply") is True


@pytest.mark.django_db
def test_common_app_is_allowed(toronto):
    assert sync.is_allowed("https://apply.commonapp.org/deadlines") is True


@pytest.mark.django_db
def test_forums_and_aggregators_are_refused(toronto):
    """Никаких форумов и агрегаторов — там числа живут своей жизнью."""
    for url in (
        "https://reddit.com/r/ApplyingToCollege",
        "https://forum.example.com/toronto-deadlines",
        "https://collegeconfidential.com/utoronto",
        "https://utoronto.ca.evil.com/apply",
    ):
        assert sync.is_allowed(url) is False, url


@pytest.mark.django_db
def test_fetch_refuses_non_whitelisted_host(toronto):
    with pytest.raises(sync.NotWhitelisted):
        sync.fetch("https://reddit.com/r/ApplyingToCollege")


@pytest.mark.django_db
def test_check_round_refuses_foreign_source(toronto):
    result = sync.check_round(toronto, url="https://forum.example.com/deadlines")
    assert result["ok"] is False
    assert "не в белом списке" in result["reason"]


# --- Извлечение фактов ---


def test_extract_facts_keeps_source_quote():
    facts = sync.extract_facts(sync.strip_html(PAGE), "https://utoronto.ca/apply")
    by_round = {f.round_type: f for f in facts}

    assert by_round["ED"].deadline == date(2026, 11, 1)
    assert by_round["RD"].deadline == date(2027, 1, 15)
    # каждый факт несёт ссылку и фрагмент, по которым его можно проверить
    for fact in facts:
        assert fact.source_url == "https://utoronto.ca/apply"
        assert fact.quote
        assert str(fact.deadline.year) in fact.quote


def test_script_contents_are_ignored():
    text = sync.strip_html(PAGE)
    assert "March 3, 2020" not in text


def test_parses_several_date_formats():
    assert sync.parse_date("due 15 January 2027") == date(2027, 1, 15)
    assert sync.parse_date("due 2027-01-15") == date(2027, 1, 15)
    assert sync.parse_date("due Jan 15, 2027") == date(2027, 1, 15)
    assert sync.parse_date("нет даты") is None


# --- Расхождение уходит в предложение ---


@pytest.mark.django_db
def test_sync_creates_suggestion_with_source(toronto, make_user):
    """Критерий приёмки: задача находит изменившийся дедлайн и создаёт
    предложение со ссылкой на источник."""
    make_user("director_admission", "asem@school.kz", full_name="Асем")

    from universities.tasks import sync_deadlines

    with patch("universities.sync.fetch", return_value=PAGE):
        result = sync_deadlines()

    assert result["checked"] == 1
    assert result["changes"] == 1

    suggestion = Suggestion.objects.get(pk=result["suggestion"])
    assert suggestion.source_type == "web_sync"
    assert suggestion.domain_code == "admission"

    change = suggestion.changes.get()
    assert change.field_name == "deadline"
    assert change.old_value == "2027-01-20"
    assert change.new_value == "2027-01-15"
    # без источника поле не меняется — ссылка и фрагмент обязательны
    assert change.source_ref.startswith("https://admissions.utoronto.ca")
    assert "January 15, 2027" in change.source_quote

    # сама база не тронута: применяет человек
    toronto.refresh_from_db()
    assert toronto.deadline == date(2027, 1, 20)


@pytest.mark.django_db
def test_applying_sync_suggestion_moves_the_deadline(toronto, make_user):
    asem = make_user("director_admission", "asem@school.kz", full_name="Асем")

    from suggestions.engine import apply_suggestion
    from universities.tasks import sync_deadlines

    with patch("universities.sync.fetch", return_value=PAGE):
        result = sync_deadlines()

    suggestion = Suggestion.objects.get(pk=result["suggestion"])
    applied = apply_suggestion(suggestion, actor=asem, change_ids=list(suggestion.changes.values_list("pk", flat=True)))
    assert applied["applied"] == 1

    toronto.refresh_from_db()
    assert toronto.deadline == date(2027, 1, 15)

    # изменение доменного поля попало в журнал с указанием источника
    from core.models import AuditLog

    log = AuditLog.objects.get(field_name="deadline")
    assert log.suggestion_id == suggestion.pk
    assert log.actor == asem


@pytest.mark.django_db
def test_matching_deadline_produces_no_suggestion(toronto, make_user):
    """Дедлайн совпал — беспокоить директора не о чем."""
    make_user("director_admission", "asem@school.kz")
    toronto.deadline = date(2027, 1, 15)
    toronto.save(update_fields=["deadline"])

    from universities.tasks import sync_deadlines

    with patch("universities.sync.fetch", return_value=PAGE):
        result = sync_deadlines()

    assert result["changes"] == 0
    assert result["suggestion"] is None


@pytest.mark.django_db
def test_check_round_records_when_it_looked(toronto):
    assert toronto.checked_at is None
    with patch("universities.sync.fetch", return_value=PAGE):
        sync.check_round(toronto)
    toronto.refresh_from_db()
    assert toronto.checked_at is not None


@pytest.mark.django_db
def test_www_prefix_is_stripped_not_characters():
    """`lstrip("www.")` срезал бы первые буквы у wisconsin.edu."""
    assert sync.host_of("https://www.utoronto.ca/apply") == "utoronto.ca"
    assert sync.host_of("https://wisconsin.edu/apply") == "wisconsin.edu"
    assert sync.host_of("https://web.mit.edu/apply") == "web.mit.edu"


@pytest.mark.django_db
def test_domain_starting_with_w_is_allowed(db):
    """Вуз, чей домен начинается с «w», должен проходить белый список."""
    University.objects.create(name="Wisconsin", country="США", domain="wisconsin.edu")
    assert sync.is_allowed("https://wisconsin.edu/admissions") is True
    assert sync.is_allowed("https://www.wisconsin.edu/admissions") is True
