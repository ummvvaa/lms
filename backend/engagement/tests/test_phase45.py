"""Фаза 45, часть 2: профтест.

Проверяем ровно то, ради чего он устроен именно так:

* без ключа модели раздел говорит «недоступен», а не показывает пустой
  результат;
* в разборе не может появиться программа мимо справочника (инвариант №10);
* согласие с направлением уходит предложением директору, а не пишется
  в профиль (инвариант №1, механика фазы 37);
* вопросы — справочник директора школы, а не константы в коде.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from engagement.models import CareerDirection, CareerQuestion, CareerRun
from suggestions.models import Suggestion, SuggestionStatus
from suggestions.providers import Completion, LLMUnavailable, Usage
from universities.models import Program, University


class FakeProvider:
    """Провайдер, отвечающий заранее заданным разбором."""

    name = "fake"

    def __init__(self, parsed=None, *, fail: bool = False) -> None:
        self.parsed, self.fail = parsed, fail
        self.calls: list[dict] = []

    def is_configured(self) -> bool:
        return True

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise LLMUnavailable("провайдер вернул 503")
        return Completion(
            content="",
            parsed=self.parsed,
            model="fake-1",
            external_id="msg_1",
            usage=Usage(100, 50),
            raw={"id": "msg_1"},
        )


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def student_user(make_user, student):
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    return user


@pytest.fixture
def program(db) -> Program:
    university = University.objects.create(name="Career University", country="Канада")
    return Program.objects.create(university=university, name="Computer Science", level="bachelor")


@pytest.fixture
def fake(monkeypatch):
    def install(provider):
        monkeypatch.setattr("suggestions.providers.get_provider", lambda: provider)
        monkeypatch.setattr("suggestions.llm.get_provider", lambda: provider)
        return provider

    return install


def answers_payload() -> dict:
    return {
        "answers": [
            {"question": question.code, "value": "математика"}
            for question in CareerQuestion.objects.filter(is_active=True)
        ]
    }


# --- Анкета как справочник --------------------------------------------------


@pytest.mark.django_db
def test_six_questions_are_seeded(db):
    """Стартовая анкета посеяна миграцией — дальше её ведёт школа."""
    assert CareerQuestion.objects.count() >= 6
    choice = CareerQuestion.objects.get(code="what_matters")
    assert choice.kind == "choice"
    assert "Доход" in choice.options_list


@pytest.mark.django_db
def test_school_director_keeps_the_questions(api, make_user):
    api.force_authenticate(make_user("director_behavior"))
    made = api.post(
        "/api/career-questions/", {"code": "probe_q", "text": "Проверочный вопрос", "kind": "text"}, format="json"
    )
    assert made.status_code == 201, made.data
    assert api.patch(f"/api/career-questions/{made.data['id']}/", {"hint": "подсказка"}).status_code == 200
    assert api.delete(f"/api/career-questions/{made.data['id']}/").status_code == 204


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["director_admission", "director_exam", "admin", "student"])
def test_others_do_not_keep_the_questions(api, make_user, role):
    api.force_authenticate(make_user(role))
    assert api.get("/api/career-questions/").status_code == 200
    assert api.post("/api/career-questions/", {"code": "x", "text": "X"}, format="json").status_code == 403


@pytest.mark.django_db
def test_answered_question_is_hidden_not_deleted(api, make_user, student, student_user, fake, program):
    """Вопрос с ответами не удаляется: иначе прошлый разбор станет нечитаемым."""
    fake(FakeProvider({"summary": "", "directions": [{"title": "Инженерия", "why": "по ответам"}]}))
    api.force_authenticate(student_user)
    api.post("/api/career/run/", answers_payload(), format="json")

    question = CareerQuestion.objects.filter(is_active=True).first()
    api.force_authenticate(make_user("director_behavior"))
    answer = api.delete(f"/api/career-questions/{question.pk}/")
    assert answer.status_code == 400
    assert "Показывать в анкете" in answer.data["detail"]


# --- Без модели -------------------------------------------------------------


@pytest.mark.django_db
def test_without_a_key_the_test_says_it_is_unavailable(api, student_user):
    """Ключа нет — раздел говорит об этом прямо, а не показывает пустое."""
    state = api if api.force_authenticate(student_user) is None else api
    data = state.get("/api/career/").data
    assert data["available"] is False
    assert "не подключена" in data["detail"]

    answer = state.post("/api/career/run/", answers_payload(), format="json")
    assert answer.status_code == 503
    assert answer.data["available"] is False


@pytest.mark.django_db
def test_provider_failure_marks_the_run_and_explains(api, student_user, fake):
    fake(FakeProvider(fail=True))
    api.force_authenticate(student_user)
    answer = api.post("/api/career/run/", answers_payload(), format="json")
    assert answer.status_code == 503
    run = CareerRun.objects.get()
    assert run.status == "failed"
    assert run.error


# --- Разбор -----------------------------------------------------------------


@pytest.mark.django_db
def test_analysis_stores_answers_and_directions_as_rows(api, student_user, student, fake, program):
    """Ответы и направления — строками, а не одним текстом (инварианты №5, №6)."""
    fake(
        FakeProvider(
            {
                "summary": "Вам подходят технические направления",
                "directions": [
                    {
                        "title": "Информатика",
                        "why": "любите математику и решаете задачи",
                        "subjects": "математика, физика",
                        "exams": "SAT, IELTS",
                        "programs": [program.pk],
                    }
                ],
            }
        )
    )
    api.force_authenticate(student_user)
    answer = api.post("/api/career/run/", answers_payload(), format="json")
    assert answer.status_code == 201, answer.data

    run = CareerRun.objects.get(student=student)
    assert run.answers.count() == CareerQuestion.objects.filter(is_active=True).count()
    direction = run.directions.get()
    assert direction.title == "Информатика"
    assert list(direction.programs.all()) == [program]
    assert answer.data["directions"][0]["programs"][0]["university"] == "Career University"


@pytest.mark.django_db
def test_program_outside_the_directory_is_dropped(api, student_user, fake, program):
    """Инвариант №10: номер, которого нет в справочнике, не сохраняется."""
    fake(
        FakeProvider(
            {
                "directions": [
                    {"title": "Медицина", "why": "по ответам", "programs": [program.pk, 999_999]},
                ]
            }
        )
    )
    api.force_authenticate(student_user)
    api.post("/api/career/run/", answers_payload(), format="json")
    direction = CareerDirection.objects.get()
    assert list(direction.programs.values_list("pk", flat=True)) == [program.pk]


@pytest.mark.django_db
def test_empty_analysis_is_called_empty(api, student_user, fake):
    fake(FakeProvider({"directions": []}))
    api.force_authenticate(student_user)
    answer = api.post("/api/career/run/", answers_payload(), format="json")
    assert answer.status_code == 503
    assert "пустой разбор" in answer.data["detail"]


@pytest.mark.django_db
def test_history_of_runs_stays(api, student_user, fake):
    fake(FakeProvider({"directions": [{"title": "Инженерия", "why": "по ответам"}]}))
    api.force_authenticate(student_user)
    api.post("/api/career/run/", answers_payload(), format="json")
    api.post("/api/career/run/", answers_payload(), format="json")
    assert api.get("/api/career/").data["runs"].__len__() == 2


# --- Согласие с направлением ------------------------------------------------


@pytest.mark.django_db
def test_agreement_goes_as_a_proposal_not_into_the_profile(api, student_user, student, fake):
    """Ученик соглашается — направление уходит предложением директору."""
    fake(FakeProvider({"directions": [{"title": "Computer Science", "why": "по ответам"}]}))
    api.force_authenticate(student_user)
    api.post("/api/career/run/", answers_payload(), format="json")
    direction = CareerDirection.objects.get()

    answer = api.post(f"/api/career/directions/{direction.pk}/agree/")
    assert answer.status_code == 200 and answer.data["ok"] is True

    suggestion = Suggestion.objects.get(pk=answer.data["suggestion"])
    assert suggestion.status == SuggestionStatus.PENDING
    assert suggestion.domain_code == "admission"
    change = suggestion.changes.get()
    assert change.field_name == "target_major"
    assert change.new_value == "Computer Science"
    # в профиль до решения директора ничего не записано
    student.admission.refresh_from_db()
    assert student.admission.target_major != "Computer Science"

    # второй раз то же направление не отправляется
    again = api.post(f"/api/career/directions/{direction.pk}/agree/")
    assert again.data["ok"] is False


@pytest.mark.django_db
def test_foreign_direction_is_not_visible(api, make_user, student_user, fake, group):
    """Чужой разбор не открывается: это кабинет ученика."""
    from students.models import AdmissionProfile, Student

    fake(FakeProvider({"directions": [{"title": "Инженерия", "why": "по ответам"}]}))
    api.force_authenticate(student_user)
    api.post("/api/career/run/", answers_payload(), format="json")
    direction = CareerDirection.objects.get()

    other = Student.objects.create(
        last_name="Второй",
        first_name="Ученик",
        email="other.career@example.kz",
        grade=11,
        group=group,
        graduation_year=2027,
    )
    AdmissionProfile.objects.create(student=other)
    other_user = make_user("student", other.email)
    other.user = other_user
    other.save(update_fields=["user"])

    api.force_authenticate(other_user)
    assert api.post(f"/api/career/directions/{direction.pk}/agree/").status_code == 404


@pytest.mark.django_db
def test_career_is_a_student_screen(api, make_user):
    api.force_authenticate(make_user("director_behavior"))
    assert api.get("/api/career/").status_code == 403
    assert api.post("/api/career/run/", {"answers": []}, format="json").status_code == 403
