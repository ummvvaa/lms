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
def test_a_repeated_sync_updates_the_one_suggestion_of_the_university(toronto, make_user):
    """D47: нерешённое расхождение назавтра не заводит второе предложение.

    У вуза одно висящее предложение сверки. Повторная сверка обновляет его
    строки: сайт сменил дату — в том же предложении стоит новая.
    """
    make_user("director_admission", "asem@school.kz", full_name="Асем")
    other_round = AdmissionRound.objects.create(
        program=toronto.program, round_type="ED", deadline=date(2026, 11, 5), source_url=toronto.source_url
    )

    from universities.tasks import sync_deadlines

    with patch("universities.sync.fetch", return_value=PAGE):
        first = sync_deadlines()
        second = sync_deadlines()

    assert first["suggestions"] == second["suggestions"]
    assert Suggestion.objects.filter(source_type="web_sync").count() == 1
    suggestion = Suggestion.objects.get()
    # два раунда одного вуза — одно предложение, по строке на раунд
    assert sorted(suggestion.changes.values_list("object_id", flat=True)) == sorted(
        [str(toronto.pk), str(other_round.pk)]
    )
    assert "University of Toronto" in suggestion.source_ref

    moved = PAGE.replace("January 15, 2027", "January 10, 2027")
    with patch("universities.sync.fetch", return_value=moved):
        third = sync_deadlines()
    assert third["suggestions"] == first["suggestions"]
    assert suggestion.changes.get(object_id=str(toronto.pk)).new_value == "2027-01-10"
    assert Suggestion.objects.count() == 1


@pytest.mark.django_db
def test_each_university_gets_its_own_suggestion(toronto, make_user):
    make_user("director_admission", "asem@school.kz", full_name="Асем")
    mcgill = University.objects.create(name="McGill", country="Канада", domain="mcgill.ca", website="https://mcgill.ca")
    AdmissionRound.objects.create(
        program=Program.objects.create(university=mcgill, name="Physics"),
        round_type="RD",
        deadline=date(2027, 2, 1),
        source_url="https://mcgill.ca/apply",
    )

    from universities.tasks import sync_deadlines

    with patch("universities.sync.fetch", return_value=PAGE):
        result = sync_deadlines()

    assert len(result["suggestions"]) == 2
    assert Suggestion.objects.filter(source_type="web_sync", status="pending").count() == 2


@pytest.mark.django_db
def test_a_suggestion_closes_itself_when_the_site_and_the_directory_agree(toronto, make_user):
    """Дедлайн поправили руками — висящая сверка закрывается сама, решать в ней нечего."""
    make_user("director_admission", "asem@school.kz", full_name="Асем")

    from universities.tasks import SYNC_RESOLVED_ITSELF, sync_deadlines

    with patch("universities.sync.fetch", return_value=PAGE):
        sync_deadlines()
        toronto.deadline = date(2027, 1, 15)
        toronto.save(update_fields=["deadline"])
        result = sync_deadlines()

    assert result["closed"] == 1 and result["suggestions"] == []
    suggestion = Suggestion.objects.get()
    assert (suggestion.status, suggestion.reject_reason) == ("rejected", SYNC_RESOLVED_ITSELF)
    assert suggestion.resolved_at is not None


@pytest.mark.django_db
def test_the_sync_writes_its_date_without_a_suggestion(toronto, make_user):
    """Дата последней сверки — служебная отметка: пишется сразу, предложением не становится."""
    make_user("director_admission", "asem@school.kz")
    toronto.deadline = date(2027, 1, 15)
    toronto.save(update_fields=["deadline"])

    from universities.tasks import sync_deadlines

    with patch("universities.sync.fetch", return_value=PAGE):
        sync_deadlines()

    toronto.refresh_from_db()
    assert toronto.checked_at is not None
    assert not Suggestion.objects.exists()


@pytest.mark.django_db
def test_old_nightly_suggestions_are_closed_by_the_migration(toronto, make_user):
    """Шестнадцать одинаковых предложений, накопленных до правки, закрыты как устаревшие."""
    import importlib

    from django.apps import apps as django_apps

    asem = make_user("director_admission", "asem@school.kz")
    nightly = [
        Suggestion.objects.create(
            author=asem,
            role=asem.role,
            domain_code="admission",
            source_type="web_sync",
            command="sync_deadlines",
            status="pending",
        )
        for _ in range(3)
    ]
    by_button = Suggestion.objects.create(
        author=asem,
        role=asem.role,
        domain_code="admission",
        source_type="web_sync",
        command="verify_requirements",
        status="pending",
    )

    migration = importlib.import_module("suggestions.migrations.0012_close_stale_sync_suggestions")
    migration.close_stale(django_apps, None)

    for row in nightly:
        row.refresh_from_db()
        assert (row.status, row.reject_reason) == ("rejected", "Устарело: заменено новой сверкой")
        assert row.resolved_at is not None
    by_button.refresh_from_db()
    assert by_button.status == "pending"


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
