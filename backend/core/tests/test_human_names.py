"""Приёмка фазы 17: человек нигде не видит технического имени поля.

Тест обходит ответы API под всеми ролями и падает, если в тексте нашлась
строка, совпадающая с именем колонки модели. Имя колонки допустимо только
в служебных ключах, по которым фронт строит запрос обратно (`field`,
`model`, `name` в реестре доменов) — их список здесь явный и короткий.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.apps import apps
from django.db import models

from accounts.models import Role
from core.domains import DOMAINS, iter_field_specs
from core.labels import field_short, field_title, value_title
from core.models import AuditLog

#: ключи, значение которых по договорённости технический идентификатор:
#: фронт кладёт его обратно в запрос, человеку он не показывается
TECHNICAL_KEYS = {
    "name",  # реестр доменов: имя колонки, по которому строится запрос
    "field",  # предпросмотр импорта и батч: фронт кладёт его обратно в запрос
    "model",
    "model_label",
    "value",  # значение варианта в списке выбора
    "column",  # заголовок колонки в загруженном файле
    "type",  # вид колонки для виджета ввода: date, number, boolean
}

#: `field_name` в этот список намеренно не входит: ключ с таким именем
#: и был источником проблемы — «by_field: [{field_name: ielts_current}]»
#: в дайджесте. Тест обязан такое ловить.

#: приложения проекта — чужие модели (django.contrib) не считаем
OUR_APPS = {
    "accounts",
    "alumni",
    "core",
    "engagement",
    "prep",
    "roadmap",
    "students",
    "suggestions",
    "universities",
}


def _choice_values() -> set[str]:
    """Все значения перечислений: они омонимичны именам колонок.

    `domain_code = "sport"` и колонка `ReadinessSnapshot.sport` пишутся
    одинаково, но первое — код домена, а не имя поля. Сравнением строк
    их не различить, поэтому такие слова из проверки исключаются.
    """
    out: set[str] = {d.code for d in DOMAINS.values()}
    out |= {str(role) for role in Role.values}
    for model in apps.get_models():
        if model._meta.app_label not in OUR_APPS:
            continue
        for field in model._meta.get_fields():
            for raw, _title in getattr(field, "choices", None) or ():
                out.add(str(raw))
    return out


def model_field_names() -> set[str]:
    """Имена колонок всех наших моделей, кроме омонимов перечислений."""
    names: set[str] = set()
    for model in apps.get_models():
        if model._meta.app_label not in OUR_APPS:
            continue
        for field in model._meta.get_fields():
            if isinstance(field, models.Field):
                names.add(field.name)
    return names - _choice_values()


def walk(payload, names: set[str], path: str = "") -> list[str]:
    """Найти технические имена в человеческих местах ответа."""
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in TECHNICAL_KEYS:
                continue
            found += walk(value, names, f"{path}.{key}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            found += walk(item, names, f"{path}[{i}]")
    elif isinstance(payload, str) and payload in names:
        found.append(f"{path} = «{payload}»")
    return found


def test_the_guard_itself_catches_a_planted_name(db):
    """Проверка на проверку: обход обязан ловить имя колонки в тексте.

    Без этого зелёный тест ничего не значит — он мог бы просто не находить
    ничего никогда.
    """
    names = model_field_names()
    assert "ielts_current" in names
    assert walk({"headline": "ielts_current: 3"}, names) == []  # подстрока — не совпадение
    assert walk({"lines": ["ielts_current"]}, names)
    assert walk({"field": "ielts_current"}, names) == []  # служебный ключ
    # прежний дайджест отдавал именно это — проверка обязана падать на нём
    assert walk({"by_field": [{"field_name": "ielts_current", "n": 3}]}, names)


# --- Реестр -------------------------------------------------------------


def test_every_field_has_a_human_name():
    """У каждого поля реестра есть название и короткая подпись."""
    for _domain, model, spec in iter_field_specs():
        assert spec.title and spec.title != spec.name, f"{model.label}.{spec.name}"
        assert spec.short_title, f"{model.label}.{spec.name}"
        assert "_" not in spec.title, f"{model.label}.{spec.name}: имя переменной в подписи"
        assert "_" not in spec.short_title, f"{model.label}.{spec.name}"


def test_short_name_fits_a_column_header():
    """Короткая подпись должна влезать в шапку таблицы."""
    for _domain, model, spec in iter_field_specs():
        assert len(spec.short_title) <= 20, f"{model.label}.{spec.name}: {spec.short_title}"


def test_lookup_falls_back_outside_the_registry():
    """Поле вне пяти доменов тоже называется по-человечески."""
    assert field_title("students.Student", "first_name") == "Имя"
    assert field_short("students.Student", "email") == "Почта"
    # неизвестная модель не роняет обращение
    assert field_title("nope.Nope", "whatever") == "whatever"


def test_values_are_translated_too():
    """В журнале и сводке значения читаются словами, а не кодами."""
    assert value_title("students.BehaviorProfile", "status", "critical") != "critical"
    assert value_title("students.ExamProfile", "ielts_current", "6.5") == "6.5"
    assert value_title("students.Activity", "is_confirmed", "True") == "да"


# --- Ответы API ---------------------------------------------------------


ROLE_PAGES = {
    Role.DIRECTOR_EXAM: ["/api/digest/", "/api/meta/domains/", "/api/dashboards/exam/"],
    Role.DIRECTOR_ADMISSION: ["/api/digest/", "/api/dashboards/admission/", "/api/suggestions/"],
    Role.DIRECTOR_BEHAVIOR: ["/api/digest/", "/api/dashboards/behavior/", "/api/students/"],
    Role.DIRECTOR_TALENT: ["/api/digest/", "/api/dashboards/talent/"],
    Role.DIRECTOR_SPORT: ["/api/digest/", "/api/dashboards/sport/"],
    Role.ADMIN: ["/api/archive/", "/api/imports/", "/api/meta/domains/"],
    Role.STUDENT: ["/api/meta/domains/", "/api/getting-started/"],
}


@pytest.fixture
def touched_student(student, make_user):
    """Ученик с историей правок — чтобы дайджест и журнал были непустыми."""
    from core.audit import apply_changes

    author = make_user(Role.DIRECTOR_EXAM, email="exam.author@example.kz")
    apply_changes(student.exam, {"ielts_current": "6.5"}, actor=author)
    apply_changes(student.behavior, {"attendance_percent": 88, "status": "critical"}, actor=author)
    return student


@pytest.mark.django_db
@pytest.mark.parametrize("role", list(ROLE_PAGES))
def test_api_answers_contain_no_column_names(client, make_user, touched_student, role):
    """Ни в одном человеческом тексте ответа нет имени колонки."""
    user = make_user(role, email=f"probe.{role}@example.kz", sees_whole_school=(role == Role.DIRECTOR_BEHAVIOR))
    client.force_login(user)
    names = model_field_names()

    for path in ROLE_PAGES[role]:
        response = client.get(path)
        assert response.status_code in (200, 403), (path, response.status_code)
        if response.status_code != 200:
            continue
        leaks = walk(response.json(), names, path)
        assert not leaks, f"{path}: техническое имя поля в тексте ответа — {leaks}"


@pytest.mark.django_db
def test_student_card_history_reads_in_words(client, make_user, touched_student):
    """Журнал на карточке: название поля и значения — словами."""
    user = make_user(Role.DIRECTOR_EXAM, email="hist@example.kz")
    client.force_login(user)
    rows = client.get(f"/api/students/{touched_student.pk}/history/").json()

    assert rows, "история пуста — проверять нечего"
    titles = {row["field_title"] for row in rows}
    assert "Текущий балл IELTS" in titles
    for row in rows:
        assert "_" not in row["field_title"]
        assert row["source_title"] and "_" not in row["source_title"]

    status_row = next(row for row in rows if row["field_title"] == "Статус по дисциплине")
    assert status_row["new_display"] != "critical"


@pytest.mark.django_db
def test_digest_reads_without_a_developer_dictionary(client, make_user, touched_student):
    """Дайджест — готовые фразы, а не перечисление колонок."""
    user = make_user(Role.DIRECTOR_EXAM, email="digest@example.kz")
    client.force_login(user)
    data = client.get("/api/digest/").json()

    assert data["headline"] and "_" not in data["headline"]
    assert data["lines"], "сводка пуста при непустой истории"
    text = " ".join(data["lines"])
    assert "ielts_current" not in text
    assert "текущий балл ielts" in text.lower()
    assert "один ученик" in text.lower()


@pytest.mark.django_db
def test_digest_of_admission_speaks_about_deadlines(client, make_user, student):
    """Сводка Асем говорит про дедлайн и про то, что добавил ученик."""
    from universities.models import (
        AddedBy,
        AdmissionRound,
        ApplicationStatus,
        Program,
        RoundType,
        StudentUniversity,
        University,
    )

    university = University.objects.create(name="NYU", country="US")
    program = Program.objects.create(university=university, name="CS")
    deadline = dt.date.today() + dt.timedelta(days=5)
    admission_round = AdmissionRound.objects.create(program=program, round_type=RoundType.RD, deadline=deadline)
    StudentUniversity.objects.create(
        student=student,
        program=program,
        admission_round=admission_round,
        added_by=AddedBy.STUDENT,
        is_confirmed=False,
        application_status=ApplicationStatus.NOT_STARTED,
    )

    user = make_user(Role.DIRECTOR_ADMISSION, email="asem.digest@example.kz")
    client.force_login(user)
    lines = " ".join(client.get("/api/digest/").json()["lines"])

    assert "Через 5 дней дедлайн NYU" in lines
    assert "ждут подтверждения" in lines


@pytest.mark.django_db
def test_digest_is_quiet_when_nothing_happened(client, make_user):
    """Пустая сводка тоже читается по-человечески, а не нулями."""
    user = make_user(Role.DIRECTOR_SPORT, email="quiet@example.kz")
    client.force_login(user)
    data = client.get("/api/digest/").json()

    assert "правок не было" in data["headline"]
    assert data["lines"] == ["Ничего нового — можно заняться тем, что запланировали"]


@pytest.mark.django_db
def test_batch_conflict_names_the_field_in_words(client, make_user, student):
    """Отказ табличного сохранения называет поле так же, как таблица."""
    user = make_user(Role.DIRECTOR_EXAM, email="batch.names@example.kz")
    client.force_login(user)

    student.exam.ielts_current = 7
    student.exam.save()
    response = client.post(
        "/api/batch/save/",
        {
            "changes": [
                {
                    "student": student.pk,
                    "model": "students.ExamProfile",
                    "field": "ielts_current",
                    "value": "6.5",
                    "expected": "5.5",
                }
            ]
        },
        content_type="application/json",
    )
    conflict = response.json()["conflicts"][0]
    assert conflict["field_title"] == "Текущий балл IELTS"
    assert conflict["actual_display"] == "7.0"


@pytest.mark.django_db
def test_import_revert_report_names_fields_in_words(student, make_user):
    """Отчёт об отмене загрузки называет поле по-человечески."""
    from core.imports import revert_batch
    from core.models import ImportBatch

    actor = make_user(Role.DIRECTOR_EXAM, email="revert.names@example.kz")
    batch = ImportBatch.objects.create(actor=actor, file_name="scores.xlsx", kind=ImportBatch.Kind.STUDENTS)
    student.exam.ielts_current = 6
    student.exam.save()
    AuditLog.objects.create(
        model_label="students.ExamProfile",
        object_id=str(student.exam.pk),
        student_id=student.pk,
        field_name="ielts_current",
        domain_code="exam",
        old_value="",
        new_value="9.9",  # в базе сейчас другое — откат такое поле не трогает
        import_batch=batch,
    )

    report = revert_batch(batch, actor=actor)
    assert report["skipped"][0]["field_title"] == "Текущий балл IELTS"
    assert "field" not in report["skipped"][0]
