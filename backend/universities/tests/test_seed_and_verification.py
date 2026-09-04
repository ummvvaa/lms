"""Фаза 13: обнуление базы, стартовый справочник и признак «не подтверждено».

Инвариант №14 проверяется буквально: непроверенная запись обязана
приходить ученику вместе с текстом плашки, а снимать признак вправе
только директор по поступлению.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from accounts.models import Role, User
from accounts.passwords import set_password
from core.models import AuditLog
from students.models import AdmissionProfile, ExamProfile, Student
from universities.models import (
    AdmissionRequirement,
    AdmissionRound,
    CatalogSource,
    Program,
    StudentUniversity,
    University,
)
from universities.seed_catalog import SEED, SeedInUse, create_seed, drop_seed, seed_blockers, upcoming

PASSWORD = "Справочник!Проверка2026"


@pytest.fixture
def director(db) -> User:
    user = User.objects.create_user(email="seed.admission@school.kz", password=None, role=Role.DIRECTOR_ADMISSION)
    set_password(user, PASSWORD)
    return user


@pytest.fixture
def exam_director(db) -> User:
    user = User.objects.create_user(email="seed.exam@school.kz", password=None, role=Role.DIRECTOR_EXAM)
    set_password(user, PASSWORD)
    return user


def login(user: User) -> APIClient:
    client = APIClient()
    client.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
    return client


@pytest.fixture
def learner(db) -> Student:
    user = User.objects.create_user(email="seed.student@school.kz", password=None, role=Role.STUDENT)
    set_password(user, PASSWORD)
    person = Student.objects.create(
        last_name="Ким",
        first_name="Дана",
        email="seed.student@school.kz",
        grade=11,
        graduation_year=2027,
        user=user,
    )
    ExamProfile.objects.create(student=person, ielts_current=Decimal("6.5"), gpa=Decimal("3.6"))
    AdmissionProfile.objects.create(student=person)
    return person


# --- стартовый справочник -------------------------------------------------


@pytest.mark.django_db
def test_seed_creates_twenty_unverified_universities():
    created = create_seed()

    assert created["universities"] == 20 == len(SEED)
    assert University.objects.count() == 20
    # ни одной подтверждённой записи: это заготовка, а не проверенные данные
    assert University.objects.filter(is_verified=True).count() == 0
    assert Program.objects.filter(is_verified=True).count() == 0
    assert AdmissionRequirement.objects.filter(is_verified=True).count() == 0
    assert AdmissionRound.objects.filter(is_verified=True).count() == 0
    assert all(u.data_source == CatalogSource.SEED for u in University.objects.all())
    # у каждого вуза две-три программы
    for university in University.objects.all():
        assert 2 <= university.programs.count() <= 3


@pytest.mark.django_db
def test_seed_deadlines_are_not_expired():
    create_seed()
    assert AdmissionRound.objects.filter(deadline__lt=date.today()).count() == 0


def test_upcoming_moves_past_date_to_next_year():
    today = date(2026, 6, 1)
    assert upcoming(1, 15, today=today) == date(2027, 1, 15)
    assert upcoming(7, 15, today=today) == date(2026, 7, 15)


@pytest.mark.django_db
def test_drop_seed_keeps_records_entered_by_school():
    own = University.objects.create(name="Nazarbayev University", country="Казахстан")
    create_seed()
    assert University.objects.count() == 21

    drop_seed()

    assert University.objects.count() == 1
    assert University.objects.first() == own


@pytest.mark.django_db
def test_seed_does_not_overwrite_university_entered_by_school():
    University.objects.create(name="University of Toronto", country="Канада", website="https://school.example")
    create_seed()

    toronto = University.objects.get(name="University of Toronto")
    assert toronto.data_source == CatalogSource.SCHOOL
    assert toronto.is_verified is True


@pytest.mark.django_db
def test_drop_seed_refuses_while_students_hold_programs(learner):
    create_seed()
    program = Program.objects.filter(data_source=CatalogSource.SEED).first()
    StudentUniversity.objects.create(student=learner, program=program)

    with pytest.raises(SeedInUse):
        drop_seed()
    assert University.objects.count() == 20

    stats = drop_seed(force=True)
    assert stats["student_links"] == 1
    assert University.objects.count() == 0


# --- признак «не подтверждено» -------------------------------------------


@pytest.mark.django_db
def test_student_sees_unverified_note_on_catalog_card(learner):
    create_seed()

    payload = login(learner.user).get("/api/catalog/").data
    assert payload["count"] > 0
    card = payload["results"][0]
    assert card["is_verified"] is False
    assert card["verification_note"] == "Данные не подтверждены, проверьте на сайте вуза"
    # плашка идёт рядом с процентом, а не вместо него
    assert "percent" in card


@pytest.mark.django_db
def test_only_admission_director_removes_the_mark(director, exam_director):
    create_seed()
    university = University.objects.first()

    denied = login(exam_director).post(
        "/api/catalog/verify/", {"kind": "university", "id": university.pk, "verified": True}, format="json"
    )
    assert denied.status_code == 403
    university.refresh_from_db()
    assert university.is_verified is False

    allowed = login(director).post(
        "/api/catalog/verify/", {"kind": "university", "id": university.pk, "verified": True}, format="json"
    )
    assert allowed.status_code == 200
    university.refresh_from_db()
    assert university.is_verified is True


@pytest.mark.django_db
def test_verifying_university_covers_its_programs_and_deadlines(director):
    create_seed()
    university = University.objects.first()

    login(director).post(
        "/api/catalog/verify/", {"kind": "university", "id": university.pk, "verified": True}, format="json"
    )

    assert Program.objects.filter(university=university, is_verified=False).count() == 0
    assert AdmissionRequirement.objects.filter(program__university=university, is_verified=False).count() == 0
    assert AdmissionRound.objects.filter(program__university=university, is_verified=False).count() == 0
    # у остальных вузов плашка на месте
    assert University.objects.filter(is_verified=False).count() == 19


@pytest.mark.django_db
def test_verification_is_written_to_audit(director):
    create_seed()
    university = University.objects.first()

    login(director).post(
        "/api/catalog/verify/", {"kind": "university", "id": university.pk, "verified": True}, format="json"
    )

    entry = AuditLog.objects.filter(model_label="universities.University", field_name="is_verified").first()
    assert entry is not None
    assert entry.actor == director
    assert entry.new_value == "да"


@pytest.mark.django_db
def test_seed_drop_endpoint_reports_conflict_before_force(director, learner):
    create_seed()
    StudentUniversity.objects.create(student=learner, program=Program.objects.first())
    client = login(director)

    conflict = client.delete("/api/catalog/seed/")
    assert conflict.status_code == 409
    assert conflict.data["need_force"] is True
    assert University.objects.count() == 20

    forced = client.delete("/api/catalog/seed/?force=1")
    assert forced.status_code == 200
    assert University.objects.count() == 0


# --- обнуление ------------------------------------------------------------


@pytest.fixture
def debug_on(settings):
    """Обнуление проверяется как в контуре разработки: при DEBUG=False
    команда отказывает целиком (фаза 56), и это стережёт свой тест."""
    settings.DEBUG = True


@pytest.mark.usefixtures("debug_on")
@pytest.mark.django_db
def test_reset_all_empties_students_and_catalog_but_keeps_users(learner, director):
    create_seed()
    StudentUniversity.objects.create(student=learner, program=Program.objects.first())
    users_before = User.objects.count()

    call_command("reset_data", "--all", confirm="УДАЛИТЬ ДАННЫЕ", stdout=StringIO())

    assert Student.objects.count() == 0
    assert University.objects.count() == 0
    assert Program.objects.count() == 0
    assert User.objects.count() == users_before


@pytest.mark.usefixtures("debug_on")
@pytest.mark.django_db
def test_reset_all_leaves_nothing_behind(learner):
    """`--all` значит всё: архив, банк заданий и справочники школы (фаза 22).

    Обычный менеджер прячет архив — и ученик, убранный в архив до очистки,
    переживал «полное» обнуление. Банк заданий и справочники не чистились вовсе.
    """
    from django.utils import timezone

    from directories.models import OlympiadSubject, SportType
    from prep.models import MockExam, MockSection, Question, QuestionOption

    # архивный ученик: `objects` его не видит, а база — видит
    learner.archived_at = timezone.now()
    learner.save(update_fields=["archived_at"])

    question = Question.objects.create(exam_type="IELTS", section="reading", topic="Skimming", text="Вопрос")
    QuestionOption.objects.create(question=question, letter="A", text="Вариант", is_correct=True)
    mock = MockExam.objects.create(exam_type="IELTS", title="Пробный")
    MockSection.objects.create(mock=mock, section="reading", question_count=1, order=1)
    OlympiadSubject.objects.create(name="Математика")
    SportType.objects.create(name="Футбол")

    call_command("reset_data", "--all", confirm="УДАЛИТЬ ДАННЫЕ", stdout=StringIO())

    assert Student.all_objects.count() == 0
    assert Question.objects.count() == 0
    assert MockExam.objects.count() == 0
    assert OlympiadSubject.objects.count() == 0
    assert SportType.objects.count() == 0


@pytest.mark.usefixtures("debug_on")
@pytest.mark.django_db
def test_reset_all_clears_the_library_and_its_notifications(learner):
    """`--all` не спотыкается о библиотеку и не оставляет её следов (фаза 26).

    Подборка материалов принадлежит сотруднику, а не ученику: удаление
    учеников её не трогало, а ссылка на предмет (PROTECT) роняла очистку
    справочников. Уведомления вели на карточки, которых уже нет.
    """
    from core.models import Notification
    from directories.models import OlympiadSubject
    from materials.models import (
        CollectionItem,
        MaterialCollection,
        MaterialRequest,
        SourceKind,
        StudyMaterial,
    )

    subject = OlympiadSubject.objects.create(name="Физика")
    material = StudyMaterial.objects.create(
        author=learner,
        subject=subject,
        topic="Механика",
        title="Разбор",
        source_kind=SourceKind.OWN_ANALYSIS,
        rights_confirmed=True,
    )
    collection = MaterialCollection.objects.create(name="К республике", subject=subject)
    CollectionItem.objects.create(collection=collection, material=material, position=1)
    MaterialRequest.objects.create(author=learner, subject=subject, topic="Оптика")
    Notification.objects.create(
        recipient=User.objects.create_user(email="arman.reset@school.kz", password=None, role=Role.DIRECTOR_TALENT),
        kind=Notification.Kind.MATERIAL_PENDING,
        text="Материал ждёт проверки",
        link=f"/materials/{material.pk}",
    )

    call_command("reset_data", "--all", confirm="УДАЛИТЬ ДАННЫЕ", stdout=StringIO())

    assert StudyMaterial.all_objects.count() == 0
    assert MaterialRequest.all_objects.count() == 0
    assert MaterialCollection.objects.count() == 0
    assert CollectionItem.objects.count() == 0
    assert OlympiadSubject.objects.count() == 0
    assert Notification.objects.count() == 0


@pytest.mark.usefixtures("debug_on")
@pytest.mark.django_db
def test_reset_plan_counts_archived_rows_too(learner, capsys):
    """План удаления считает и архивные записи — иначе он врёт числами."""
    from django.utils import timezone

    learner.archived_at = timezone.now()
    learner.save(update_fields=["archived_at"])

    out = StringIO()
    call_command("reset_data", "--all", confirm="УДАЛИТЬ ДАННЫЕ", stdout=out)

    assert "Ученики: 1" in out.getvalue()


@pytest.mark.usefixtures("debug_on")
@pytest.mark.django_db
def test_reset_requires_the_exact_phrase(learner):
    with pytest.raises(CommandError):
        call_command("reset_data", "--students", confirm="удалить", stdout=StringIO())
    assert Student.objects.count() == 1


@pytest.mark.usefixtures("debug_on")
@pytest.mark.django_db
def test_reset_marks_audit_entries_as_pointing_at_deleted_objects(learner):
    from core.audit import apply_changes

    apply_changes(learner.exam, {"ielts_current": Decimal("7.0")})
    assert AuditLog.objects.filter(object_deleted=False).count() > 0

    call_command("reset_data", "--students", confirm="УДАЛИТЬ ДАННЫЕ", stdout=StringIO())

    assert AuditLog.objects.count() > 0
    assert AuditLog.objects.filter(object_deleted=False).count() == 0


@pytest.mark.usefixtures("debug_on")
@pytest.mark.django_db
def test_reset_catalog_alone_refuses_while_students_hold_programs(learner):
    create_seed()
    StudentUniversity.objects.create(student=learner, program=Program.objects.first())

    with pytest.raises(CommandError):
        call_command("reset_data", "--catalog", confirm="УДАЛИТЬ ДАННЫЕ", stdout=StringIO())
    assert University.objects.count() == 20


@pytest.mark.django_db
def test_drop_keeps_university_where_school_added_its_own_program():
    """Школа завела свою программу под вузом заготовки — вуз остаётся ей."""
    create_seed()
    university = University.objects.get(name="University of Toronto")
    own = Program.objects.create(university=university, name="Своя программа школы")

    stats = drop_seed()

    assert stats["kept_universities"] == 1
    university.refresh_from_db()
    assert university.data_source == CatalogSource.SCHOOL
    assert Program.objects.filter(pk=own.pk).exists()
    assert Program.objects.filter(university=university, data_source=CatalogSource.SEED).count() == 0
    assert University.objects.count() == 1


@pytest.mark.django_db
def test_drop_keeps_the_generic_check_for_records_with_history(learner):
    """Заготовку не сносит запись с историей, которая на неё ссылается.

    Сейчас таких моделей нет — каталог выпускников убран в фазе 29, —
    но правило остаётся общим: любая будущая связь с `PROTECT` на
    программу заготовки остановит удаление, а не уронит его 500-й.
    """
    create_seed()
    assert seed_blockers() == []


# --- Фаза 52: заготовка не досеивается в бою вслепую ------------------------


@pytest.mark.django_db
def test_seed_universities_refuses_on_filled_catalog_in_production(settings):
    """В бою на непустом справочнике команда останавливается.

    На вузах висят дедлайны раундов (инвариант №4): лишняя запись
    разъехалась бы сроками сразу у всех учеников.
    """
    settings.DEBUG = False
    call_command("seed_universities", stdout=StringIO())
    before = University.objects.count()
    assert before

    with pytest.raises(CommandError) as refusal:
        call_command("seed_universities", stdout=StringIO())

    assert "--force" in str(refusal.value)
    assert University.objects.count() == before


@pytest.mark.django_db
def test_seed_universities_runs_in_production_on_empty_catalog(settings):
    """Пустой справочник команда наполняет и в бою: каталог нужен с первого дня."""
    settings.DEBUG = False
    assert not University.objects.exists()

    call_command("seed_universities", stdout=StringIO())

    assert University.objects.exists()


@pytest.mark.django_db
def test_seed_universities_force_does_not_duplicate(settings):
    """`--force` снимает отказ, но вуз заводится по названию и не двоится."""
    settings.DEBUG = False
    call_command("seed_universities", stdout=StringIO())
    before = University.objects.count()

    call_command("seed_universities", "--force", stdout=StringIO())

    assert University.objects.count() == before
