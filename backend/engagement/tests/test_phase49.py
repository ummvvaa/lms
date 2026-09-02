"""Фаза 49: карусель незакрытых мест, правила обзвона, кабинеты, эссе.

Главное здесь — что карусель и список обзвона живут справочником, а не
кодом, и что кабинет каждой роли отвечает своим. Плюс дефект, ради
которого фаза начиналась: эссе создавалось только двумя типами из девяти.
"""

from __future__ import annotations

import datetime as dt

import pytest
from rest_framework.test import APIClient

from engagement.cues import build as build_cues
from engagement.models import CallCondition, CallRule, CueCondition, CueTone, HomeCue


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
def saltanat(make_user):
    return make_user("director_behavior", "saltanat@example.kz")


# --- Карусель: сюжеты из справочника ---------------------------------------


def test_cue_rules_are_seeded_and_cover_the_named_conditions(db):
    """Стартовые правила посеяны миграцией: без них карусель пуста с первого дня."""
    codes = set(HomeCue.objects.values_list("condition", flat=True))
    for condition in (
        CueCondition.PORTFOLIO_GAP,
        CueCondition.EXAM_GOAL_GAP,
        CueCondition.SCHOLARSHIP_DEADLINE,
        CueCondition.PLAN_IDLE,
    ):
        assert condition in codes, f"нет сюжета для условия {condition}"


def test_cue_says_the_words_of_the_directory_and_the_number_of_the_code(student):
    """Слова берутся из справочника, живое число подставляет код."""
    HomeCue.objects.all().delete()
    HomeCue.objects.create(
        code="own",
        condition=CueCondition.PORTFOLIO_GAP,
        title="Свой заголовок школы",
        description="Своё описание",
        action_label="Своя кнопка",
        action_path="/my-data",
        tone=CueTone.TEAL,
    )
    cues = build_cues(student)
    assert len(cues) == 1
    cue = cues[0]
    assert cue["title"] == "Свой заголовок школы"
    assert cue["action"] == "Своя кнопка" and cue["path"] == "/my-data"
    assert cue["tone"] == "teal"
    # надпись над заголовком — с числом: в справочнике ему взяться неоткуда
    assert "%" in cue["eyebrow"]


def test_cue_disappears_when_the_place_is_closed(student, monkeypatch):
    """Место закрыто — сюжета нет. Пустая карусель на главной не рисуется."""
    HomeCue.objects.all().delete()
    HomeCue.objects.create(
        code="portfolio",
        condition=CueCondition.PORTFOLIO_GAP,
        title="Портфолио",
        action_label="Открыть",
        action_path="/my-data",
    )
    assert build_cues(student), "у пустого портфолио сюжет обязан быть"

    import students.portfolio as portfolio

    monkeypatch.setattr(portfolio, "state", lambda _s: {"percent": 100})
    assert build_cues(student) == []


def test_hidden_cue_never_reaches_the_student(student):
    """Снятая галочка «Показывать» убирает сюжет, а не прячет его на экране."""
    HomeCue.objects.all().delete()
    HomeCue.objects.create(
        code="off",
        condition=CueCondition.PORTFOLIO_GAP,
        title="Скрытый",
        action_label="Открыть",
        action_path="/my-data",
        is_active=False,
    )
    assert build_cues(student) == []


def test_cues_endpoint_is_for_the_student(api, student_user, saltanat):
    """Карусель — экран ученика: сотруднику здесь показывать нечего."""
    api.force_authenticate(saltanat)
    assert api.get("/api/home/cues/").status_code == 403
    api.force_authenticate(student_user)
    assert api.get("/api/home/cues/").status_code == 200


def test_cue_directory_is_kept_by_the_school_director(api, saltanat, make_user):
    """Справочник сюжетов ведёт директор школы, чужой домен его не правит."""
    api.force_authenticate(saltanat)
    created = api.post(
        "/api/home-cues/",
        {
            "code": "new-one",
            "condition": CueCondition.NO_UNIVERSITIES,
            "title": "Список вузов пуст",
            "action_label": "Открыть каталог",
            "action_path": "/catalog",
            "tone": CueTone.INDIGO,
        },
        format="json",
    )
    assert created.status_code == 201, created.data

    api.force_authenticate(make_user("director_sport", "sport@example.kz"))
    refused = api.post(
        "/api/home-cues/",
        {
            "code": "not-mine",
            "condition": CueCondition.NO_UNIVERSITIES,
            "title": "Чужое",
            "action_label": "Открыть",
            "action_path": "/catalog",
        },
        format="json",
    )
    assert refused.status_code == 403


# --- Кому позвонить сегодня -------------------------------------------------


def test_call_list_follows_the_rule_and_its_threshold(student):
    """Список собирается по правилу справочника, а порог — школы."""
    from core.cabinets import call_list
    from students.models import BehaviorProfile

    CallRule.objects.all().delete()
    BehaviorProfile.objects.filter(student=student).update(attendance_percent=70)

    rule = CallRule.objects.create(
        code="attendance",
        condition=CallCondition.ABSENCES,
        reason="низкая посещаемость",
        urgency="now",
        threshold=80,
    )
    rows = call_list()
    assert rows and rows[0]["student"].startswith("Тестов")
    assert "низкая посещаемость" in rows[0]["reason"]
    assert rows[0]["urgency"] == "now"

    # порог опустили — правило перестало срабатывать
    rule.threshold = 60
    rule.save(update_fields=["threshold"])
    assert call_list() == []


def test_call_list_is_empty_without_rules(student):
    """Правил нет — список пуст, а не собран по зашитым в код условиям."""
    from core.cabinets import call_list
    from students.models import BehaviorProfile

    BehaviorProfile.objects.filter(student=student).update(attendance_percent=10)
    CallRule.objects.all().delete()
    assert call_list() == []


def test_call_rule_directory_belongs_to_the_school_director(api, saltanat, make_user):
    """Правила обзвона ведёт директор школы."""
    api.force_authenticate(make_user("director_exam", "exam@example.kz"))
    refused = api.post(
        "/api/call-rules/",
        {"code": "x", "condition": CallCondition.INACTIVE, "reason": "не заходил", "urgency": "today"},
        format="json",
    )
    assert refused.status_code == 403

    api.force_authenticate(saltanat)
    created = api.post(
        "/api/call-rules/",
        {"code": "x", "condition": CallCondition.INACTIVE, "reason": "не заходил", "urgency": "today"},
        format="json",
    )
    assert created.status_code == 201, created.data


# --- Кабинеты ---------------------------------------------------------------


@pytest.mark.parametrize(
    "role,keys",
    [
        ("director_exam", ("drops", "ranges", "without_goals")),
        ("director_admission", ("urgent", "balance", "directory")),
        ("director_behavior", ("calls", "groups", "talks")),
        ("director_talent", ("review", "olympiads", "by_subject")),
        ("director_sport", ("starts", "by_sport")),
        ("admin", ("registry", "actions", "uploads")),
    ],
)
def test_each_cabinet_answers_with_its_own(db, role, keys):
    """У каждого кабинета своё содержимое, а не общий набор с подменой."""
    from core.cabinets import build

    data = build(role)
    assert data["stats"], f"{role}: кабинет без чисел"
    for key in keys:
        assert key in data, f"{role}: в кабинете нет «{key}»"


def test_admin_has_no_confirmation_queue(db):
    """Администратору подтверждать нечего: очереди у него нет."""
    from core.cabinets import build

    assert "queue" not in build("admin")


def test_cabinet_endpoint_is_closed_to_the_student(api, student_user, saltanat):
    """У ученика своя главная: кабинет руководителя ему не отвечает."""
    api.force_authenticate(student_user)
    assert api.get("/api/cabinet/").status_code == 403
    api.force_authenticate(saltanat)
    assert api.get("/api/cabinet/").status_code == 200


def test_admin_actions_carry_what_they_act_on(db, student):
    """Кнопка в строке знает, над чем она сработает: почты, номера, адрес."""
    from core.cabinets import build

    rows = {row["code"]: row for row in build("admin")["actions"]}
    assert "invite" in rows, "ученик без учётной записи — это работа администратора"
    assert student.email in rows["invite"]["emails"]


# --- Дефект фазы: эссе всех девяти типов ------------------------------------


@pytest.mark.django_db
def test_essay_is_created_for_every_document_type(api, student_user):
    """Эссе заводится любым типом справочника, а вид выводит сервер.

    До фазы 49 фронт слал в поле `essay_type` код типа документа, а туда
    помещались только четыре значения — семь типов из девяти отбивались
    четырёхсотой.
    """
    from roadmap.models import EssayDocType

    api.force_authenticate(student_user)
    types = EssayDocType.objects.all()
    assert types.count() >= 9, "справочник типов не посеян — проверка ничего не значит"
    for doc_type in types:
        response = api.post(
            "/api/essays/",
            {"doc_type": doc_type.pk, "title": f"Эссе {doc_type.name}"},
            format="json",
        )
        assert response.status_code == 201, f"{doc_type.code}: {response.status_code} {response.data}"
        assert response.data["essay_type"], "вид эссе обязан выводиться из типа документа"


@pytest.mark.django_db
def test_essay_type_follows_the_document_type(student):
    """Соответствие вида и типа документа живёт в одном месте."""
    from roadmap.models import Essay, EssayDocType, EssayType

    motivation = EssayDocType.objects.get(code="motivation_letter")
    essay = Essay.objects.create(student=student, doc_type=motivation, title="Письмо")
    assert essay.essay_type == EssayType.MOTIVATION

    free = EssayDocType.objects.get(code="free_form")
    other = Essay.objects.create(student=student, doc_type=free, title="Свободное")
    assert other.essay_type == EssayType.OTHER


# --- Календарь сотрудника ---------------------------------------------------


def test_staff_calendar_counts_students_and_hides_personal_tasks(student, group):
    """Директор видит школьные события с числом сдающих, а не чужие задачи."""
    from directories.models import ExamKind
    from students.calendar_feed import staff_state
    from students.models import ExamGoal

    kind, _ = ExamKind.objects.get_or_create(name="IELTS")
    ExamGoal.objects.create(student=student, exam=kind, exam_date=dt.date.today() + dt.timedelta(days=10))

    state = staff_state()
    exams = [event for event in state["events"] if event["kind"] == "exam"]
    assert exams and exams[0]["students"] == 1
    assert all(event["kind"] != "task" for event in state["events"])
