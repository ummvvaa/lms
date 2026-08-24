"""Фаза 27: живой провайдер, поиск по белому списку, учёт расходов.

Настоящего провайдера здесь нет — вместо него подменяется HTTP-слой:
проверяем то, что уходит в запросе и что делается с ответом. Качество
формулировок не проверяем, проверяем границы: за белый список поиск
выйти не может, факт без ссылки не принимается, а без ключа каждая
операция продолжает работать правилами.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import override_settings

from accounts.models import Role
from suggestions import websearch
from suggestions.budget import cost_of
from suggestions.models import LLMCall
from suggestions.providers import AnthropicProvider, LLMUnavailable
from universities.models import Program, University

LIVE = {
    "PROVIDER": "anthropic",
    "API_KEY": "test-key",
    "BASE_URL": "https://api.example",
    "MODEL": "claude-sonnet-5",
    "TIMEOUT": 5,
    "RETRIES": 0,
    "RETRY_DELAY": 0,
    "NO_RETENTION": True,
    "SEARCH": True,
    "SEARCH_MAX_USES": 5,
}


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload, self.status_code = payload, status_code

    def json(self) -> dict:
        return self.payload


def answer(*, parsed=None, searched: list[str] | None = None, searches: int = 0) -> dict:
    """Ответ провайдера в том виде, в каком его отдаёт Messages API."""
    content: list[dict] = []
    if searched is not None:
        content.append(
            {
                "type": "web_search_tool_result",
                "content": [{"type": "web_search_result", "url": url, "title": "стр."} for url in searched],
            }
        )
    if parsed is not None:
        content.append({"type": "tool_use", "name": "result", "input": parsed})
    return {
        "id": "msg_1",
        "model": "claude-sonnet-5",
        "content": content,
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 200,
            "server_tool_use": {"web_search_requests": searches},
        },
    }


@pytest.fixture
def catalog(db):
    """Вуз с доменом и одной программой — по нему и ходит поиск."""
    university = University.objects.create(
        name="University of Toronto", country="Канада", website="https://www.utoronto.ca", domain="utoronto.ca"
    )
    program = Program.objects.create(university=university, name="Computer Science", level="bachelor")
    return university, program


@pytest.fixture
def sent(monkeypatch):
    """Перехватить HTTP-запрос к провайдеру и подсунуть ответ."""
    box: dict = {}

    def install(payload: dict, status_code: int = 200):
        def fake_post(url, json=None, headers=None, timeout=None):
            box["url"], box["json"], box["headers"] = url, json, headers
            return FakeResponse(payload, status_code)

        import requests

        monkeypatch.setattr(requests, "post", fake_post)
        return box

    return install


@pytest.fixture
def asem(make_user):
    return make_user(Role.DIRECTOR_ADMISSION, email="asem.phase27@example.kz")


# --- Белый список ----------------------------------------------------------


@pytest.mark.django_db
def test_search_tool_carries_only_whitelisted_domains(catalog):
    """В запрос уходит список доменов: сайты справочника и Common App."""
    tool = websearch.tool()
    assert tool is not None
    assert tool["type"] == websearch.TOOL_TYPE
    domains = tool["allowed_domains"]
    assert "utoronto.ca" in domains
    assert "commonapp.org" in domains
    # ни форумов, ни агрегаторов, ни «звёздочки»
    assert all(not d.startswith("*") for d in domains)
    assert not {"reddit.com", "quora.com", "collegeconfidential.com"} & set(domains)


@pytest.mark.django_db
def test_search_for_one_university_stays_on_its_own_site(catalog):
    """Требования одного вуза на сайте другого не написаны."""
    university, _program = catalog
    University.objects.create(name="Другой", country="Канада", domain="other.example")

    domains = websearch.domains_for_university(university)
    assert "utoronto.ca" in domains
    assert "commonapp.org" in domains
    assert "other.example" not in domains


@pytest.mark.django_db
def test_search_is_not_offered_when_the_whitelist_is_empty(db):
    """Пустой справочник — не повод искать по всему интернету."""
    assert websearch.tool([]) is None


@pytest.mark.django_db
@override_settings(LLM={**LIVE, "SEARCH": False})
def test_search_can_be_turned_off_entirely(catalog):
    assert websearch.tool() is None


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_request_to_the_provider_contains_the_whitelist(catalog, sent, asem):
    """Ограничение стоит в самом запросе, а не в тексте промпта."""
    from suggestions.extraction import parse_university

    box = sent(
        answer(
            parsed={"name": "University of Toronto", "country": "Канада", "programs": []},
            searched=["https://www.utoronto.ca/admissions"],
            searches=2,
        )
    )
    parse_university(text="University of Toronto", actor=asem, role=Role.DIRECTOR_ADMISSION)

    tools = box["json"]["tools"]
    search = next(t for t in tools if t.get("type") == websearch.TOOL_TYPE)
    assert "utoronto.ca" in search["allowed_domains"]
    assert box["json"]["tool_choice"] == {"type": "auto"}
    assert box["headers"]["x-api-key"] == "test-key"
    assert box["url"] == "https://api.example/v1/messages"


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_answer_citing_a_forum_is_thrown_away(catalog, sent, asem):
    """Если провайдер всё-таки принёс форум — ответ не используется целиком.

    `allowed_domains` — обещание чужой стороны. Дедлайн с форума стоит
    ученику года, поэтому обещание мы проверяем сами.
    """
    from suggestions.extraction import NeedsModel, parse_university

    sent(
        answer(
            parsed={"name": "University of Toronto", "programs": []},
            searched=["https://www.collegeconfidential.com/threads/utoronto"],
            searches=1,
        )
    )
    with pytest.raises(NeedsModel):
        parse_university(text="University of Toronto", actor=asem, role=Role.DIRECTOR_ADMISSION)

    call = LLMCall.objects.latest("created_at")
    assert call.is_ok is False
    assert "белый список" in call.error


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_source_outside_the_whitelist_is_dropped_from_the_rows(catalog, sent, asem):
    """Ссылку с форума нельзя ни сохранить, ни показать как подтверждение."""
    from suggestions.extraction import parse_university

    sent(
        answer(
            parsed={
                "name": "University of Toronto",
                "domain": "utoronto.ca",
                "programs": [
                    {
                        "name": "Computer Science",
                        "min_ielts": "6.5",
                        "source_url": "https://forum.example/thread/1",
                        "quote": "говорят, 6.5",
                    }
                ],
            },
            searched=["https://www.utoronto.ca/admissions"],
            searches=1,
        )
    )
    result = parse_university(text="University of Toronto", actor=asem, role=Role.DIRECTOR_ADMISSION)

    assert result["ok"] is True
    assert result["dropped_sources"] == ["https://forum.example/thread/1"]
    from suggestions.models import SuggestionChange

    refs = SuggestionChange.objects.values_list("source_ref", flat=True)
    assert all("forum.example" not in (ref or "") for ref in refs)


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_fact_from_the_official_site_keeps_link_quote_and_date(catalog, sent, asem):
    """Каждый факт из интернета хранит ссылку, дату и фрагмент-источник."""
    from suggestions.extraction import parse_university
    from suggestions.models import SuggestionChange

    sent(
        answer(
            parsed={
                "name": "University of Toronto",
                "domain": "utoronto.ca",
                "programs": [
                    {
                        "name": "Computer Science",
                        "min_ielts": "6.5",
                        "deadline": "2027-01-15",
                        "round_type": "RD",
                        "source_url": "https://www.utoronto.ca/admissions/requirements",
                        "quote": "IELTS: minimum overall score of 6.5",
                        "checked_at": "2026-08-24",
                    }
                ],
            },
            searched=["https://www.utoronto.ca/admissions/requirements"],
            searches=1,
        )
    )
    parse_university(text="University of Toronto", actor=asem, role=Role.DIRECTOR_ADMISSION)

    row = SuggestionChange.objects.filter(field_name="min_ielts").first()
    assert row is not None
    assert "utoronto.ca/admissions/requirements" in row.source_ref
    assert "2026-08-24" in row.source_ref
    assert "6.5" in row.source_quote


# --- Учёт расходов ---------------------------------------------------------


def test_search_costs_money_and_lands_in_the_bill():
    """Поиск оплачивается запросами, а не токенами."""
    with override_settings(LLM_PRICES={"default": {"input": "3", "output": "15"}}, LLM_PRICE_SEARCH_PER_1000="10"):
        without = cost_of(model="claude-sonnet-5", tokens_in=1000, tokens_out=200)
        with_search = cost_of(model="claude-sonnet-5", tokens_in=1000, tokens_out=200, searches=2)
    assert with_search - without == Decimal("0.02")


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_searches_are_recorded_in_the_call_log(catalog, sent, asem):
    from suggestions.extraction import parse_university

    sent(answer(parsed={"name": "University of Toronto", "programs": []}, searched=[], searches=3))
    parse_university(text="University of Toronto", actor=asem, role=Role.DIRECTOR_ADMISSION)

    call = LLMCall.objects.latest("created_at")
    assert call.searches == 3
    assert call.cost > 0


# --- Сверка требований -----------------------------------------------------


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_requirements_check_makes_a_suggestion_with_the_source(catalog, sent, asem):
    """Расхождение уходит предложением со ссылкой и цитатой, а не в базу."""
    from suggestions.models import SuggestionChange
    from suggestions.verify_requirements import verify
    from universities.models import AdmissionRequirement

    _university, program = catalog
    AdmissionRequirement.objects.create(program=program, min_ielts=Decimal("6.0"))

    sent(
        answer(
            parsed={
                "found": True,
                "min_ielts": "6.5",
                "source_url": "https://www.utoronto.ca/admissions/english",
                "quote": "overall 6.5 with no band below 6.0",
                "checked_at": "2026-08-24",
            },
            searched=["https://www.utoronto.ca/admissions/english"],
            searches=1,
        )
    )
    result = verify(program_id=program.pk, actor=asem, role=Role.DIRECTOR_ADMISSION)

    assert result["ok"] and result["changed"] == 1
    row = SuggestionChange.objects.get(field_name="min_ielts")
    assert "utoronto.ca" in row.source_ref
    assert "6.5" in row.source_quote
    # в справочник ничего не записалось (инвариант №3)
    assert AdmissionRequirement.objects.get(program=program).min_ielts == Decimal("6.0")


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_requirements_check_refuses_without_a_known_domain(db, sent, asem):
    """Нет домена — сверять нечем: по форумам мы не ходим."""
    from suggestions.verify_requirements import CannotVerify, verify

    university = University.objects.create(name="Без сайта", country="Казахстан")
    program = Program.objects.create(university=university, name="Экономика", level="bachelor")

    with pytest.raises(CannotVerify) as error:
        verify(program_id=program.pk, actor=asem, role=Role.DIRECTOR_ADMISSION)
    assert "домен" in str(error.value)


@pytest.mark.django_db
@override_settings(LLM={**LIVE, "API_KEY": ""})
def test_requirements_check_says_plainly_that_the_model_is_off(catalog, asem):
    """Без ключа сверка не притворяется работающей."""
    from suggestions.verify_requirements import CannotVerify, verify

    _university, program = catalog
    with pytest.raises(CannotVerify) as error:
        verify(program_id=program.pk, actor=asem, role=Role.DIRECTOR_ADMISSION)
    assert "модель" in str(error.value).lower()


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_requirements_check_keeps_silence_when_the_site_says_nothing(catalog, sent, asem):
    """Пустой порог значит «требования нет», а не ноль."""
    from suggestions.models import Suggestion
    from suggestions.verify_requirements import verify

    _university, program = catalog
    sent(answer(parsed={"found": False}, searched=["https://www.utoronto.ca/"], searches=1))
    result = verify(program_id=program.pk, actor=asem, role=Role.DIRECTOR_ADMISSION)

    assert result["found"] is False
    assert Suggestion.objects.count() == 0


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_numbers_without_a_source_are_not_accepted(catalog, sent, asem):
    """Число без ссылки на официальный сайт — это просто число."""
    from suggestions.models import Suggestion
    from suggestions.verify_requirements import verify

    _university, program = catalog
    sent(answer(parsed={"found": True, "min_ielts": "6.5"}, searched=[], searches=0))
    result = verify(program_id=program.pk, actor=asem, role=Role.DIRECTOR_ADMISSION)

    assert result["ok"] is False
    assert Suggestion.objects.count() == 0


# --- Запрос к провайдеру ---------------------------------------------------


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_structured_answer_is_still_demanded_without_search(sent):
    """Без поиска ответ требуем сразу — лишнего хода модели не нужно."""
    provider = AnthropicProvider()
    box = sent(answer(parsed={"name": "Вуз"}))
    provider.complete(system="s", user="u", schema={"type": "object"})

    assert box["json"]["tool_choice"] == {"type": "tool", "name": "result"}
    assert box["json"]["messages"][0]["content"][-1]["text"] == "u"


@pytest.mark.django_db
@override_settings(LLM=LIVE)
def test_temporary_failures_are_retried_and_permanent_ones_are_not(monkeypatch):
    """429 повторяем, 400 — нет: на ошибке в запросе три вызова вместо одного."""
    import requests

    calls = {"n": 0}

    def flaky(url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        return FakeResponse({"error": "boom"}, 400)

    monkeypatch.setattr(requests, "post", flaky)
    with pytest.raises(LLMUnavailable):
        AnthropicProvider().complete(system="s", user="u")
    assert calls["n"] == 1


# --- Без ключа --------------------------------------------------------------


@pytest.mark.django_db
@override_settings(LLM={**LIVE, "API_KEY": ""})
def test_every_operation_survives_without_a_key(catalog, asem):
    """Без ключа операции отвечают правилами и ничего не роняют."""
    from suggestions import operations

    for outcome in (
        operations.week_changes(actor=asem, role=Role.DIRECTOR_ADMISSION),
        operations.focus_today(actor=asem, role=Role.DIRECTOR_ADMISSION),
        operations.explain_list(student_ids=[], actor=asem, role=Role.DIRECTOR_ADMISSION),
    ):
        payload = outcome.as_dict()
        assert payload["offline"] is True
        assert payload["text"] or payload["lines"] or payload["detail"]


@pytest.mark.django_db
@override_settings(LLM={**LIVE, "API_KEY": ""})
def test_assistant_free_text_refuses_honestly_without_a_key(asem):
    from suggestions import assistant

    payload = assistant.free_text(text="что делать?", actor=asem, role=Role.DIRECTOR_ADMISSION)
    assert "не подключена" in payload["text"]
    assert payload["suggestion"] is None


@pytest.mark.django_db
@override_settings(LLM={**LIVE, "API_KEY": ""})
def test_check_command_runs_and_reports_every_operation(catalog, asem):
    """`check_llm` проходит все операции и без ключа не падает."""
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("check_llm", offline=True, stdout=out)
    text = out.getvalue()
    for name in ("разбор вуза", "сверка требований", "дайджест", "помощник: свободный ввод"):
        assert name in text
    assert "Не отработали" not in text
