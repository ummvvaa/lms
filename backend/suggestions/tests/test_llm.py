"""Подключение модели: провайдер, лимит расходов, обезличивание, операции.

Настоящего провайдера здесь нет: он подменяется поддельным. Проверяем не
качество формулировок, а то, что нарушать нельзя — границы доменов,
инварианты и поведение без ключа.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import Role
from core.domains import Source
from directories.models import OlympiadSubject
from suggestions import budget, operations
from suggestions.budget import BudgetExceeded, cost_of, spent_this_month
from suggestions.models import LLMCall, SuggestionChange
from suggestions.providers import Completion, LLMUnavailable, NullProvider, Usage
from universities.models import AdmissionRequirement, Program, University


class FakeProvider:
    """Провайдер, который отвечает заранее заданным."""

    name = "fake"

    def __init__(self, *, content: str = "", parsed=None, tokens=(100, 50), fail: bool = False) -> None:
        self.content, self.parsed, self.tokens, self.fail = content, parsed, tokens, fail
        self.calls: list[dict] = []

    def is_configured(self) -> bool:
        return True

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise LLMUnavailable("провайдер вернул 503")
        return Completion(
            content=self.content,
            parsed=self.parsed,
            model="fake-1",
            external_id="msg_1",
            usage=Usage(*self.tokens),
            raw={"id": "msg_1"},
        )


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def kymbat(make_user):
    return make_user(Role.DIRECTOR_EXAM, email="kymbat.llm@example.kz")


@pytest.fixture
def asem(make_user):
    return make_user(Role.DIRECTOR_ADMISSION, email="asem.llm@example.kz")


@pytest.fixture
def fake(monkeypatch):
    """Подменить провайдера на поддельный."""

    def install(provider):
        monkeypatch.setattr("suggestions.providers.get_provider", lambda: provider)
        monkeypatch.setattr("suggestions.llm.get_provider", lambda: provider)
        return provider

    return install


# --- Провайдер за интерфейсом ---------------------------------------------


@pytest.mark.django_db
def test_without_a_key_everything_keeps_working_on_rules(fake, student, kymbat):
    """Ключа нет — разбор идёт правилами, ошибок наружу нет."""
    fake(NullProvider())
    from suggestions.parsers import rows_for_suggestion

    student.last_name, student.first_name = "Ахметова", "Аружан"
    student.save(update_fields=["last_name", "first_name"])

    rows, _ambiguities = rows_for_suggestion("Ахметова Аружан — 6.5", actor=kymbat, role=kymbat.role)
    assert rows and rows[0]["field"] == "ielts_current"
    assert LLMCall.objects.count() == 0, "без ключа вызовов быть не должно"


@pytest.mark.django_db
def test_a_call_is_logged_with_tokens_and_cost(fake, kymbat):
    """Каждый вызов записан: кто, операция, токены, деньги."""
    provider = fake(FakeProvider(content="Готово", tokens=(1000, 500)))
    from suggestions.llm import complete

    complete(system="s", user="u", purpose="week_changes", actor=kymbat, role=kymbat.role)

    call = LLMCall.objects.get()
    assert call.actor == kymbat and call.role == Role.DIRECTOR_EXAM
    assert call.purpose == "week_changes" and call.provider == "fake"
    assert call.tokens_in == 1000 and call.tokens_out == 500
    assert call.cost > 0
    assert call.is_ok is True
    assert provider.calls


@pytest.mark.django_db
def test_a_failed_call_is_logged_too(fake, kymbat):
    """Сбой провайдера тоже попадает в журнал — иначе счёт не сойдётся."""
    fake(FakeProvider(fail=True))
    from suggestions.llm import complete

    with pytest.raises(LLMUnavailable):
        complete(system="s", user="u", purpose="digest", actor=kymbat, role=kymbat.role)

    call = LLMCall.objects.get()
    assert call.is_ok is False and "503" in call.error


def test_retries_only_on_temporary_failures(monkeypatch):
    """Повторяем перегрузку, не повторяем отказ по существу."""
    from suggestions import providers

    monkeypatch.setattr(providers.time, "sleep", lambda _s: None)
    attempts = {"n": 0}

    class Response:
        def __init__(self, code):
            self.status_code = code

        def json(self):
            return {"error": "boom"} if self.status_code >= 400 else {"content": []}

    def flaky():
        attempts["n"] += 1
        return Response(529 if attempts["n"] == 1 else 200)

    with override_settings(LLM={**providers.settings.LLM, "RETRIES": 2, "RETRY_DELAY": 0}):
        providers._with_retries(flaky)
    assert attempts["n"] == 2, "перегрузку надо повторить"

    attempts["n"] = 0
    with override_settings(LLM={**providers.settings.LLM, "RETRIES": 2, "RETRY_DELAY": 0}):
        with pytest.raises(LLMUnavailable):
            providers._with_retries(lambda: Response(400))
    assert attempts["n"] == 0


# --- Лимит расходов --------------------------------------------------------


def test_cost_is_counted_by_the_price_list():
    with override_settings(LLM_PRICES={"default": {"input": "3", "output": "15"}}):
        assert cost_of(model="any", tokens_in=1_000_000, tokens_out=0) == Decimal("3.00000")
        assert cost_of(model="any", tokens_in=0, tokens_out=1_000_000) == Decimal("15.00000")


@pytest.mark.django_db
def test_exhausted_limit_turns_operations_off_with_a_readable_message(fake, kymbat):
    """Лимит выбран — операции отключаются, и это сказано словами."""
    fake(FakeProvider(content="ответ"))
    LLMCall.objects.create(purpose="digest", model="fake-1", cost=Decimal("12.5"))

    with override_settings(LLM_MONTHLY_LIMIT="10"):
        assert spent_this_month() == Decimal("12.5")
        with pytest.raises(BudgetExceeded) as error:
            budget.check_available()
        assert "Месячный лимит расходов" in str(error.value)
        assert "Разбор и объяснения продолжают работать правилами" in str(error.value)

        from suggestions.llm import is_available, status

        assert is_available() is False
        assert status()["available"] is False


@pytest.mark.django_db
def test_operations_fall_back_to_rules_when_the_limit_is_out(fake, kymbat, student):
    """Та же операция без модели отвечает правилами и не показывает ошибку."""
    fake(FakeProvider(content="красиво написанный текст"))
    LLMCall.objects.create(purpose="digest", model="fake-1", cost=Decimal("99"))

    with override_settings(LLM_MONTHLY_LIMIT="10"):
        outcome = operations.explain_list(student_ids=[student.pk], actor=kymbat, role=kymbat.role)

    assert outcome.offline is True
    assert "красиво" not in outcome.text
    assert student.full_name in outcome.text


@pytest.mark.django_db
def test_the_operation_endpoint_answers_402_when_the_limit_is_out(api, kymbat):
    LLMCall.objects.create(purpose="digest", model="fake-1", cost=Decimal("99"))
    api.force_authenticate(kymbat)
    with override_settings(LLM_MONTHLY_LIMIT="10"):
        answer = api.post("/api/commands/run/", {"code": "focus_today"}, format="json")
    assert answer.status_code == 402
    assert "лимит" in answer.json()["detail"].lower()


@pytest.mark.django_db
def test_spend_report_is_for_the_admin_only(api, kymbat, make_user):
    LLMCall.objects.create(purpose="digest", model="fake-1", role=Role.DIRECTOR_EXAM, cost=Decimal("1.5"))
    api.force_authenticate(kymbat)
    assert api.get("/api/llm/spend/").status_code == 403

    api.force_authenticate(make_user(Role.ADMIN, email="admin.spend@example.kz"))
    report = api.get("/api/llm/spend/").json()
    assert report["calls"] == 1
    assert report["by_purpose"][0]["purpose_title"] == "Дайджест на сегодня"
    assert "_" not in report["detail"]


# --- Персональные данные ---------------------------------------------------


@pytest.mark.django_db
def test_names_do_not_leave_the_server(fake, kymbat, student):
    """В модель уходят номера, имена подставляются обратно здесь."""
    provider = fake(FakeProvider(content="ученик 1 отстаёт по баллам"))
    student.last_name, student.first_name = "Ахметова", "Аружан"
    student.save(update_fields=["last_name", "first_name"])

    outcome = operations.explain_list(student_ids=[student.pk], actor=kymbat, role=kymbat.role)

    sent = provider.calls[0]["user"]
    assert "Ахметова" not in sent and "Аружан" not in sent
    assert "ученик 1" in sent
    assert "Ахметова Аружан отстаёт по баллам" == outcome.text
    assert outcome.offline is False


@pytest.mark.django_db
def test_only_the_fields_of_the_operation_are_sent(fake, kymbat, student):
    """Профиль целиком не отправляется: только то, что нужно операции."""
    provider = fake(FakeProvider(content="план"))
    student.exam.ielts_current = 6
    student.exam.teacher = "Секретный Преподаватель"
    student.exam.save()
    student.behavior.comment = "Личное замечание куратора"
    student.behavior.save()

    operations.prep_plan(student_id=student.pk, actor=kymbat, role=kymbat.role)

    sent = provider.calls[0]["user"]
    assert "IELTS сейчас" in sent
    assert "Секретный Преподаватель" not in sent
    assert "Личное замечание" not in sent


# --- Операции пишут только в предложения -----------------------------------


@pytest.mark.django_db
def test_bulk_tasks_go_through_a_suggestion_not_into_the_table(fake, kymbat, student):
    """Массовая постановка задач ничего не пишет сама (инвариант №3)."""
    from roadmap.models import Task

    fake(FakeProvider(parsed={"title": "Собрать рекомендательные письма", "days": 10}))
    outcome = operations.bulk_tasks(student_ids=[student.pk], wish="нужны рекомендации", actor=kymbat, role=kymbat.role)

    assert outcome.suggestion is not None
    assert Task.objects.count() == 0, "до применения человеком задач быть не должно"

    from suggestions.engine import apply_suggestion
    from suggestions.models import Suggestion

    suggestion = Suggestion.objects.get(pk=outcome.suggestion)
    ids = list(suggestion.changes.values_list("pk", flat=True))
    apply_suggestion(suggestion, actor=kymbat, change_ids=ids)

    task = Task.objects.get()
    assert task.title == "Собрать рекомендательные письма"
    assert task.student_id == student.pk


@pytest.mark.django_db
def test_a_foreign_domain_row_is_dropped_even_if_the_model_asks(kymbat):
    """Предложение с полем чужого домена отбрасывается кодом, не промптом."""
    from suggestions.engine import create_suggestion

    _suggestion, rejected = create_suggestion(
        author=kymbat,
        role=Role.DIRECTOR_EXAM,
        domain_code="exam",
        source_type="manual",
        rows=[{"model": "students.BehaviorProfile", "field": "attendance_percent", "value": 50, "student": None}],
    )
    assert rejected and "ведёт домен" in rejected[0]["reason"]


@pytest.mark.django_db
def test_parsed_university_lands_unverified_and_only_after_a_human(fake, asem):
    """Разобранный вуз заводится плашкой «не подтверждено» (инвариант №14)."""
    from suggestions.engine import apply_suggestion
    from suggestions.extraction import parse_university
    from suggestions.models import Suggestion

    fake(
        FakeProvider(
            parsed={
                "name": "University of Toronto",
                "country": "Канада",
                "website": "https://utoronto.ca",
                "domain": "utoronto.ca",
                "programs": [
                    {"name": "Computer Science", "level": "bachelor", "min_ielts": "6.5", "deadline": "2027-01-15"}
                ],
            }
        )
    )
    answer = parse_university(text="University of Toronto", actor=asem, role=asem.role)
    assert answer["ok"] is True
    assert University.objects.count() == 0, "до применения справочник не трогаем (инвариант №3)"

    suggestion = Suggestion.objects.get(pk=answer["suggestion"])
    apply_suggestion(suggestion, actor=asem, change_ids=list(suggestion.changes.values_list("pk", flat=True)))

    university = University.objects.get(name="University of Toronto")
    assert university.data_source == "ai"
    assert university.is_verified is False

    program = Program.objects.get(university=university)
    assert program.name == "Computer Science"
    assert program.is_verified is False
    assert AdmissionRequirement.objects.get(program=program).min_ielts == Decimal("6.5")
    assert program.rounds.get().deadline.isoformat() == "2027-01-15"


@pytest.mark.django_db
def test_parsed_certificate_becomes_a_proposal(fake, make_user, student):
    """Фото грамоты превращается в предложение, а не в запись."""
    from students.models import Competition
    from suggestions.extraction import parse_certificate

    nurlybek = make_user(Role.DIRECTOR_SPORT, email="nur.llm@example.kz")
    fake(
        FakeProvider(
            parsed={"name": "Городская спартакиада", "date": "2026-05-12", "result": "2 место", "confidence": 0.8}
        )
    )

    answer = parse_certificate(
        payload=b"\x89PNG\r\n\x1a\n",
        media_type="image/png",
        student_id=student.pk,
        actor=nurlybek,
        role=nurlybek.role,
    )
    assert answer["ok"] is True
    assert Competition.objects.count() == 0

    from suggestions.engine import apply_suggestion
    from suggestions.models import Suggestion

    suggestion = Suggestion.objects.get(pk=answer["suggestion"])
    apply_suggestion(suggestion, actor=nurlybek, change_ids=list(suggestion.changes.values_list("pk", flat=True)))

    competition = Competition.objects.get()
    assert competition.name == "Городская спартакиада"
    assert competition.has_certificate is True


@pytest.mark.django_db
def test_image_parsing_says_so_when_the_model_is_off(fake, make_user, student):
    """Без модели распознавание невозможно — говорим прямо."""
    from suggestions.extraction import NeedsModel, parse_certificate

    fake(NullProvider())
    kymbat = make_user(Role.DIRECTOR_EXAM, email="kym.image@example.kz")
    with pytest.raises(NeedsModel) as error:
        parse_certificate(
            payload=b"\x89PNG", media_type="image/png", student_id=student.pk, actor=kymbat, role=kymbat.role
        )
    assert "заведите запись руками" in str(error.value)


@pytest.mark.django_db
def test_parsed_activity_uses_only_subjects_from_the_directory(fake, make_user, student):
    """Предмет берётся из справочника: выдуманный молча не заводится."""
    from suggestions.extraction import parse_activity

    OlympiadSubject.objects.create(name="Физика")
    arman = make_user(Role.DIRECTOR_TALENT, email="arman.llm@example.kz")
    fake(
        FakeProvider(
            parsed={
                "category": "olympiad",
                "subject": "Астрофизика",  # такого предмета в справочнике нет
                "title": "Областная олимпиада",
                "strength": "сильный результат",
            }
        )
    )
    answer = parse_activity(text="занял второе место", student_id=student.pk, actor=arman, role=arman.role)

    rows = SuggestionChange.objects.filter(suggestion_id=answer["suggestion"])
    assert not rows.filter(field_name="subject").exists()
    assert OlympiadSubject.objects.count() == 1


# --- Подбор вузов ----------------------------------------------------------


@pytest.mark.django_db
def test_the_picker_never_names_a_university_outside_the_catalog(fake, student):
    """Инвариант №10 держится кодом: id вне справочника отбрасывается."""
    from universities.picker import pick

    university = University.objects.create(name="Nazarbayev University", country="Казахстан")
    program = Program.objects.create(university=university, name="Computer Science")
    AdmissionRequirement.objects.create(program=program, min_ielts=Decimal("6.0"))

    fake(
        FakeProvider(
            parsed={
                "picks": [
                    {"id": 999999, "why": "Гарвард отличный вуз"},
                    {"id": program.pk, "why": "подходит по баллам"},
                ],
                "note": "",
            }
        )
    )
    result = pick(student=student, text="Казахстан, информатика")
    names = [row.card["university_name"] for row in result.picks]
    assert names == ["Nazarbayev University"]
    assert "Гарвард" not in " ".join(row.why for row in result.picks)


# --- Инварианты в тексте ---------------------------------------------------


def test_the_prompt_forbids_promising_chances():
    """В правилах для модели прямо запрещено обещать вероятность."""
    assert "вероятность" in operations.RULES
    assert "соответствие требованиям" in operations.RULES


@pytest.mark.django_db
def test_xp_is_never_given_for_a_model_operation():
    """Инвариант №12: среди видов XP нет ни одного про баллы или ИИ."""
    from engagement.models import XPKind

    words = ("ielts", "sat", "gpa", "балл", "score", "ai", "модел")
    for kind in XPKind.values:
        assert not any(word in kind.lower() for word in words), kind


@pytest.mark.django_db
def test_applied_model_proposal_is_recorded_as_ai_in_the_journal(fake, kymbat, student):
    """Применённая правка от модели помечена источником `ai` (инвариант №9)."""
    from core.models import AuditLog
    from suggestions.engine import apply_suggestion, create_suggestion
    from suggestions.models import Suggestion

    fake(FakeProvider())
    suggestion, _ = create_suggestion(
        author=kymbat,
        role=Role.DIRECTOR_EXAM,
        domain_code="exam",
        source_type="paste",
        rows=[{"student": student.pk, "model": "students.ExamProfile", "field": "ielts_current", "value": "6.5"}],
    )
    suggestion = Suggestion.objects.get(pk=suggestion.pk)
    apply_suggestion(suggestion, actor=kymbat, change_ids=list(suggestion.changes.values_list("pk", flat=True)))

    entry = AuditLog.objects.get(field_name="ielts_current")
    assert entry.source == Source.AI
    assert entry.suggestion_id == suggestion.pk


# --- Приёмка фазы ----------------------------------------------------------


@pytest.mark.django_db
def test_with_a_key_pasted_text_becomes_a_suggestion_and_applies(fake, kymbat, student):
    """С ключом: вставили текст с баллами → предложение → применили."""
    from suggestions.engine import apply_suggestion, create_suggestion
    from suggestions.models import Suggestion
    from suggestions.parsers import rows_for_suggestion

    student.last_name, student.first_name = "Сериков", "Дамир"
    student.save(update_fields=["last_name", "first_name"])

    # правила такую строку не разбирают: имя и число не разделены тире
    provider = fake(
        FakeProvider(
            parsed={"rows": [{"name": "Сериков Дамир", "field": "sat_current", "value": "1320", "quote": "исходник"}]}
        )
    )
    rows, _ambiguities = rows_for_suggestion(
        "вчера Сериков Дамир написал сат на 1320, наконец-то", actor=kymbat, role=kymbat.role
    )
    assert provider.calls, "модель должна была получить неразобранное"
    assert rows and rows[0]["field"] == "sat_current"

    suggestion, _rejected = create_suggestion(
        author=kymbat, role=kymbat.role, domain_code="exam", source_type="paste", rows=rows
    )
    suggestion = Suggestion.objects.get(pk=suggestion.pk)
    apply_suggestion(suggestion, actor=kymbat, change_ids=list(suggestion.changes.values_list("pk", flat=True)))

    student.exam.refresh_from_db()
    assert student.exam.sat_current == 1320


@pytest.mark.django_db
def test_without_a_key_the_same_paste_works_on_rules(fake, kymbat, student):
    """Без ключа тот же разбор идёт правилами и не показывает ошибок."""
    from suggestions.parsers import rows_for_suggestion

    fake(NullProvider())
    student.last_name, student.first_name = "Сериков", "Дамир"
    student.save(update_fields=["last_name", "first_name"])

    rows, ambiguities = rows_for_suggestion("Сериков Дамир — 1320", actor=kymbat, role=kymbat.role)
    assert rows and rows[0]["value"] == 1320
    assert ambiguities == []


def test_every_offered_command_has_a_panel_on_the_front():
    """Кнопка без обработчика — дефект, и список сверяется здесь.

    Фронт разбирает коды в `Assistant.tsx` и `AiPanels.tsx`. Если сюда
    добавили команду, а туда панель — нет, тест упадёт и напомнит.
    """
    from suggestions.commands import COMMANDS

    handled = {
        # старые панели помощника
        "paste_as_is",
        "parse_mock",
        "upload_file",
        "digest",
        "explain_match",
        "check_balance",
        # панели операций с моделью (`AiPanels.tsx`, константа AI_PANELS)
        "explain_list",
        "week_changes",
        "focus_today",
        "bulk_tasks",
        "prep_plan",
        "gap_to_tasks",
        "parent_letter",
        "parse_university",
        "verify_requirements",
        "parse_activity",
        "parse_certificate",
        "parse_score_screenshot",
    }
    offered = {command.code for command in COMMANDS}
    assert offered <= handled, f"нет панели для: {sorted(offered - handled)}"


@pytest.mark.django_db
def test_boolean_survives_the_round_trip():
    """«да» из журнала читается обратно как булево.

    На этом ломались и откат импорта, и создание записи предложением:
    `to_text` пишет «да», а обратно значение не принималось.
    """
    from core.audit import coerce, to_text
    from students.models import Competition

    row = Competition(name="Спартакиада", has_certificate=True)
    assert to_text(row.has_certificate) == "да"
    assert coerce(row, "has_certificate", "да") is True
    assert coerce(row, "has_certificate", "нет") is False

    with pytest.raises(Exception, match="нужно «да» или «нет»"):
        coerce(row, "has_certificate", "может быть")
