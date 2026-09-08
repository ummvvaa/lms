"""Фаза 61: кабинет куратора — корзины, задачи, резкий скачок, границы групп.

Правила корзин живут в одном месте (`students.attention`) и закрыты здесь
по одному тесту на правило: числа на главной, чипы над таблицей и блок
в карточке обязаны сходиться, а сойтись они могут только если считает
их один код.

Задачи ставятся существующей сущностью (`roadmap.Task`), а не второй
таблицей: ученик уже видит её в календаре, в панели «Сегодня» и на доске.
Здесь проверяется, что задача от куратора видна ученику как чужая
(«от куратора»), а имя куратора ему по-прежнему не показывается.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.curators import assign
from accounts.models import User
from directories.models import ExamKind
from roadmap.models import Task, TaskOrigin, TaskStatus
from students import attention
from students.models import (
    AdmissionProfile,
    BehaviorProfile,
    ExamAttempt,
    ExamGoal,
    ExamProfile,
    SportProfile,
    Student,
    StudyGroup,
    TalentProfile,
)

TODAY = timezone.localdate()
CURATOR_NAME = "Асель Ермекова"


def days(n: int) -> dt.date:
    return TODAY + dt.timedelta(days=n)


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def chicago(db) -> StudyGroup:
    return StudyGroup.objects.create(code="CHICAGO", grade=11)


@pytest.fixture
def tokyo(db) -> StudyGroup:
    return StudyGroup.objects.create(code="TOKYO", grade=11)


@pytest.fixture
def boston(db) -> StudyGroup:
    """Группа чужого куратора — граница всех проверок."""
    return StudyGroup.objects.create(code="BOSTON", grade=10)


def make_student(group: StudyGroup, last_name: str, email: str) -> Student:
    student = Student.objects.create(
        last_name=last_name, first_name="Ученик", email=email, grade=11, group=group, graduation_year=2027
    )
    for model in (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile):
        model.objects.create(student=student)
    return student


@pytest.fixture
def admin(make_user) -> User:
    return make_user("admin", "admin61@example.kz", full_name="Администратор")


@pytest.fixture
def curator(make_user, chicago, tokyo, admin) -> User:
    user = make_user("curator", "curator61@example.kz", full_name=CURATOR_NAME)
    assign(group=chicago, curator=user, since=days(-30), actor=admin)
    assign(group=tokyo, curator=user, since=days(-30), actor=admin)
    return user


@pytest.fixture
def as_curator(api, curator) -> APIClient:
    api.force_login(curator)
    return api


@pytest.fixture
def ielts(db) -> ExamKind:
    return ExamKind.objects.get_or_create(name="IELTS", defaults={"max_score": 9})[0]


@pytest.fixture
def sat(db) -> ExamKind:
    return ExamKind.objects.get_or_create(name="SAT", defaults={"max_score": 1600})[0]


def student_with(group, *, name, email, ielts_kind=None, sat_kind=None, **kwargs) -> Student:
    """Ученик с целями, баллами и пробником — заготовка под правила корзин."""
    student = make_student(group, name, email)
    profile = student.exam
    for field in ("ielts_current", "sat_current", "ielts_target", "sat_target"):
        if field in kwargs:
            setattr(profile, field, kwargs[field])
    profile.save()
    if kwargs.get("ielts_exam_date") and ielts_kind:
        ExamGoal.objects.create(
            student=student,
            exam=ielts_kind,
            target_score=kwargs.get("ielts_goal_score"),
            exam_date=kwargs["ielts_exam_date"],
        )
    if kwargs.get("sat_exam_date") and sat_kind:
        ExamGoal.objects.create(
            student=student,
            exam=sat_kind,
            target_score=kwargs.get("sat_goal_score"),
            exam_date=kwargs["sat_exam_date"],
        )
    if kwargs.get("mock_date"):
        ExamAttempt.objects.create(
            student=student,
            exam_type="IELTS",
            attempt_format="mock",
            date=kwargs["mock_date"],
            total_score=kwargs.get("mock_score", 6),
        )
    return student


# --- Корзины: по тесту на правило ---------------------------------------------


@pytest.mark.django_db
def test_bucket_nogoal_only_when_neither_goal_is_set(chicago):
    """Без цели — когда нет ни IELTS, ни SAT. Одной цели достаточно, чтобы выйти."""
    empty = student_with(chicago, name="Безцелев", email="nogoal61@example.kz")
    ielts_only = student_with(chicago, name="Цельев", email="ielts61@example.kz", ielts_target=7)
    sat_only = student_with(chicago, name="Сатов", email="sat61@example.kz", sat_target=1400)

    assert "nogoal" in attention.buckets_of(empty)
    assert "nogoal" not in attention.buckets_of(ielts_only)
    assert "nogoal" not in attention.buckets_of(sat_only)


@pytest.mark.django_db
def test_bucket_nomock_counts_from_the_threshold(chicago, settings):
    """Пробника не было или он старше порога — граница ровно на числе настроек."""
    limit = settings.CURATOR_RULES["MOCK_STALE_DAYS"]
    never = student_with(chicago, name="Небылов", email="nomock61@example.kz")
    fresh = student_with(chicago, name="Свежев", email="fresh61@example.kz", mock_date=days(-limit + 1))
    stale = student_with(chicago, name="Староев", email="stale61@example.kz", mock_date=days(-limit - 1))

    assert "nomock" in attention.buckets_of(never)
    assert "nomock" not in attention.buckets_of(fresh)
    assert "nomock" in attention.buckets_of(stale)


@pytest.mark.django_db
def test_bucket_far_needs_both_the_gap_and_the_near_exam(chicago, ielts, sat, settings):
    """Далеко от цели — только если и отставание большое, и экзамен скоро."""
    gap = settings.CURATOR_RULES["IELTS_GAP"]
    soon = settings.CURATOR_RULES["EXAM_SOON_DAYS"]

    far = student_with(
        chicago,
        name="Отставов",
        email="far61@example.kz",
        ielts_kind=ielts,
        ielts_current=5.5,
        ielts_goal_score=7,
        ielts_exam_date=days(soon - 10),
    )
    # то же отставание, но экзамен нескоро
    later = student_with(
        chicago,
        name="Успеев",
        email="later61@example.kz",
        ielts_kind=ielts,
        ielts_current=5.5,
        ielts_goal_score=7,
        ielts_exam_date=days(soon + 10),
    )
    # экзамен скоро, но до цели меньше порога
    close = student_with(
        chicago,
        name="Близков",
        email="close61@example.kz",
        ielts_kind=ielts,
        ielts_current=7 - gap + 0.5,
        ielts_goal_score=7,
        ielts_exam_date=days(10),
    )
    assert "far" in attention.buckets_of(far)
    assert "far" not in attention.buckets_of(later)
    assert "far" not in attention.buckets_of(close)


@pytest.mark.django_db
def test_bucket_far_uses_its_own_threshold_for_sat(chicago, sat, settings):
    """У SAT свой порог: 90 баллов отставания — ещё не корзина, 150 — уже да."""
    gap = settings.CURATOR_RULES["SAT_GAP"]
    small = student_with(
        chicago,
        name="Малов",
        email="satsmall61@example.kz",
        sat_kind=sat,
        sat_current=1400 - gap + 10,
        sat_goal_score=1400,
        sat_exam_date=days(20),
    )
    big = student_with(
        chicago,
        name="Большов",
        email="satbig61@example.kz",
        sat_kind=sat,
        sat_current=1400 - gap - 50,
        sat_goal_score=1400,
        sat_exam_date=days(20),
    )
    assert "far" not in attention.buckets_of(small)
    assert "far" in attention.buckets_of(big)


@pytest.mark.django_db
def test_bucket_rejected_clears_when_the_student_submits_again(chicago, make_user):
    """Отклонено и не перевнесено: новое предложение выводит из корзины."""
    from suggestions.models import Suggestion, SuggestionChange, SuggestionStatus

    student = student_with(chicago, name="Отклонов", email="rejected61@example.kz")
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])

    def propose(status: str) -> Suggestion:
        suggestion = Suggestion.objects.create(
            role="student", domain_code="exam", status=status, author=user, source_type="student"
        )
        SuggestionChange.objects.create(
            suggestion=suggestion,
            student=student,
            model_label="students.ExamProfile",
            field_name="ielts_current",
            old_value="",
            new_value="7.0",
        )
        return suggestion

    propose(SuggestionStatus.REJECTED)
    assert "rejected" in attention.buckets_of(student)

    propose(SuggestionStatus.PENDING)
    assert "rejected" not in attention.buckets_of(student)


@pytest.mark.django_db
def test_buckets_never_reach_across_group_borders(as_curator, chicago, boston, ielts):
    """Корзины считаются только по своим группам — чужой ученик в них не попадает."""
    mine = student_with(chicago, name="Свойков", email="own61@example.kz")
    student_with(boston, name="Чужаков", email="alien61@example.kz")

    body = as_curator.get("/api/curator/students/").json()
    assert [row["id"] for row in body["results"]] == [mine.pk]
    counts = {row["code"]: row["count"] for row in body["buckets"]}
    assert counts["nogoal"] == 1, "чужой ученик без цели не должен попадать в счётчик"


@pytest.mark.django_db
def test_the_same_numbers_on_the_home_screen_in_chips_and_in_the_card(as_curator, chicago, ielts):
    """Главная, чипы таблицы и карточка показывают одно и то же число."""
    student = student_with(chicago, name="Одинаков", email="same61@example.kz")

    home = as_curator.get("/api/curator/overview/").json()
    table = as_curator.get("/api/curator/students/").json()
    card = as_curator.get(f"/api/curator/students/{student.pk}/").json()

    home_counts = {row["code"]: row["count"] for row in home["buckets"]}
    chip_counts = {row["code"]: row["count"] for row in table["buckets"]}
    assert home_counts == chip_counts
    assert home_counts["nogoal"] == 1
    assert {row["code"] for row in card["buckets"]} == set(table["results"][0]["buckets"])


@pytest.mark.django_db
def test_group_switch_narrows_everything(as_curator, chicago, tokyo):
    """Переключатель группы сужает и список, и корзины, и числа главной."""
    student_with(chicago, name="Чикагов", email="chi61@example.kz")
    student_with(tokyo, name="Токиев", email="tok61@example.kz")

    both = as_curator.get("/api/curator/students/").json()
    assert len(both["results"]) == 2

    one = as_curator.get("/api/curator/students/?group=CHICAGO").json()
    assert [row["group"] for row in one["results"]] == ["CHICAGO"]

    home = as_curator.get("/api/curator/overview/?group=CHICAGO").json()
    assert home["students_total"] == 1

    # чужой код группы не открывает чужих учеников
    alien = as_curator.get("/api/curator/students/?group=BOSTON").json()
    assert alien["results"] == []


# --- Резкий скачок -------------------------------------------------------------


@pytest.mark.django_db
def test_sharp_jump_thresholds(settings):
    """Пороги скачка свои у каждого экзамена и берутся из настроек."""
    jump_ielts = settings.CURATOR_RULES["IELTS_JUMP"]
    jump_sat = settings.CURATOR_RULES["SAT_JUMP"]

    assert attention.sharp_jump("students.ExamProfile", "ielts_current", "5.5", str(5.5 + jump_ielts))
    assert not attention.sharp_jump("students.ExamProfile", "ielts_current", "5.5", str(5.5 + jump_ielts - 0.5))
    assert attention.sharp_jump("students.ExamProfile", "sat_current", "1200", str(1200 + jump_sat))
    assert not attention.sharp_jump("students.ExamProfile", "sat_current", "1200", str(1200 + jump_sat - 10))
    # не балл — не скачок, что бы там ни поменялось
    assert not attention.sharp_jump("students.AdmissionProfile", "target_country", "США", "Канада")
    assert not attention.sharp_jump("students.ExamProfile", "ielts_current", "", "7.0")


@pytest.mark.django_db
def test_queue_row_carries_the_sharp_jump_flag(as_curator, chicago, make_user):
    """Признак приходит строкой очереди с сервера, а не считается на экране."""
    from suggestions.models import Suggestion, SuggestionChange, SuggestionStatus

    student = student_with(chicago, name="Скачков", email="jump61@example.kz", ielts_current=5.5)
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])

    suggestion = Suggestion.objects.create(
        role="student", domain_code="exam", status=SuggestionStatus.PENDING, author=user, source_type="student"
    )
    SuggestionChange.objects.create(
        suggestion=suggestion,
        student=student,
        model_label="students.ExamProfile",
        field_name="ielts_current",
        old_value="5.5",
        new_value="8.0",
    )

    rows = as_curator.get("/api/suggestions/from-students/").json()["results"]
    assert len(rows) == 1 and rows[0]["sharp_jump"] is True


# --- Задачи ----------------------------------------------------------------------


@pytest.mark.django_db
def test_task_to_one_student(as_curator, chicago, curator):
    """Задача одному: попадает ученику, знает автора и его роль."""
    student = student_with(chicago, name="Задачин", email="task61@example.kz")
    made = as_curator.post(
        "/api/curator/tasks/",
        {"student": student.pk, "title": "Загрузить транскрипт", "due_date": str(days(5))},
        format="json",
    )
    assert made.status_code == 201 and made.json()["created"] == 1

    task = Task.objects.get(student=student)
    assert task.title == "Загрузить транскрипт" and task.due_date == days(5)
    assert task.author == curator and task.author_role == "curator"
    assert task.origin == TaskOrigin.CURATOR and task.origin_title == "От куратора"


@pytest.mark.django_db
def test_task_to_a_group_creates_one_per_student(as_curator, chicago, tokyo):
    """Задача группе — по одной на каждого: закрывает её каждый сам."""
    first = student_with(chicago, name="Первов", email="g1-61@example.kz")
    second = student_with(chicago, name="Второв", email="g2-61@example.kz")
    other = student_with(tokyo, name="Соседов", email="g3-61@example.kz")

    made = as_curator.post("/api/curator/tasks/", {"group": "CHICAGO", "title": "Записаться на пробник"}, format="json")
    assert made.status_code == 201 and made.json()["created"] == 2
    assert set(made.json()["students"]) == {first.pk, second.pk}
    assert Task.objects.filter(student=other).count() == 0
    # закрытие одной не трогает вторую
    mine = Task.objects.get(student=first)
    as_curator.post(f"/api/curator/tasks/{mine.pk}/status/", {"status": "done"}, format="json")
    assert Task.objects.get(student=second).status == TaskStatus.TODO


@pytest.mark.django_db
def test_task_needs_a_title_and_a_real_student(as_curator, chicago, boston):
    """Пустой текст — 400; чужой ученик — 404, как и везде."""
    mine = student_with(chicago, name="Свойков", email="own-task61@example.kz")
    alien = student_with(boston, name="Чужаков", email="alien-task61@example.kz")

    empty = as_curator.post("/api/curator/tasks/", {"student": mine.pk, "title": "   "}, format="json")
    assert empty.status_code == 400

    foreign = as_curator.post("/api/curator/tasks/", {"student": alien.pk, "title": "Что-то"}, format="json")
    assert foreign.status_code == 404
    assert Task.objects.filter(student=alien).count() == 0

    alien_group = as_curator.post("/api/curator/tasks/", {"group": "BOSTON", "title": "Что-то"}, format="json")
    assert alien_group.status_code == 404


@pytest.mark.django_db
def test_curator_closes_cancels_and_reopens(as_curator, chicago, curator):
    """Закрыть, отменить и вернуть — тем же кодом, что двигает задачу ученик."""
    student = student_with(chicago, name="Статусов", email="status61@example.kz")
    as_curator.post("/api/curator/tasks/", {"student": student.pk, "title": "Собрать документы"}, format="json")
    task = Task.objects.get(student=student)

    done = as_curator.post(f"/api/curator/tasks/{task.pk}/status/", {"status": "done"}, format="json")
    assert done.status_code == 200
    task.refresh_from_db()
    assert task.status == TaskStatus.DONE and task.closed_by == curator and task.completed_at is not None

    as_curator.post(f"/api/curator/tasks/{task.pk}/status/", {"status": "todo"}, format="json")
    task.refresh_from_db()
    assert task.status == TaskStatus.TODO and task.closed_by is None and task.completed_at is None

    as_curator.post(f"/api/curator/tasks/{task.pk}/status/", {"status": "cancelled"}, format="json")
    task.refresh_from_db()
    assert task.status == TaskStatus.CANCELLED and task.completed_at is None

    bad = as_curator.post(f"/api/curator/tasks/{task.pk}/status/", {"status": "review"}, format="json")
    assert bad.status_code == 400


@pytest.mark.django_db
def test_cancelled_task_gives_no_xp_and_leaves_the_student_alone(as_curator, chicago, make_user):
    """Отменённая задача не «сделана»: XP нет, в календаре и «Сегодня» её нет."""
    from engagement.models import XPEvent

    student = student_with(chicago, name="Отменов", email="cancel61@example.kz")
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    as_curator.post(
        "/api/curator/tasks/",
        {"student": student.pk, "title": "Уже не нужно", "due_date": str(days(3))},
        format="json",
    )
    task = Task.objects.get(student=student)
    as_curator.post(f"/api/curator/tasks/{task.pk}/status/", {"status": "cancelled"}, format="json")

    assert not XPEvent.objects.filter(student=student).exists()

    client = APIClient()
    client.force_login(user)
    events = client.get("/api/calendar/").json()
    assert all("Уже не нужно" not in str(row) for row in events.get("events", []))


@pytest.mark.django_db
def test_student_sees_the_task_as_the_curators_not_as_own(as_curator, chicago, make_user, curator):
    """Ученик видит задачу и её происхождение, но не имя куратора (фаза 60)."""
    student = student_with(chicago, name="Видев", email="sees61@example.kz")
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    as_curator.post(
        "/api/curator/tasks/",
        {"student": student.pk, "title": "Поставить цель по SAT", "due_date": str(days(4))},
        format="json",
    )

    client = APIClient()
    client.force_login(user)
    rows = client.get("/api/tasks/my/").json()
    assert len(rows) == 1
    assert rows[0]["origin"] == "curator" and rows[0]["origin_title"] == "От куратора"

    for path in ("/api/tasks/my/", "/api/calendar/", "/api/game/me/"):
        body = client.get(path).content.decode()
        assert CURATOR_NAME not in body, path
        assert "curator61@example.kz" not in body, path

    # и закрыть свою задачу ученик по-прежнему может сам
    task = Task.objects.get(student=student)
    moved = client.post(f"/api/tasks/{task.pk}/status/", {"status": "done"}, format="json")
    assert moved.status_code == 200
    task.refresh_from_db()
    assert task.status == TaskStatus.DONE and task.closed_by == user


@pytest.mark.django_db
def test_student_never_sees_someone_elses_task(as_curator, chicago, make_user):
    """Задача соседа не появляется ни в списке, ни поштучно."""
    mine = student_with(chicago, name="Мойков", email="mine61@example.kz")
    other = student_with(chicago, name="Другов", email="other61@example.kz")
    user = make_user("student", mine.email)
    mine.user = user
    mine.save(update_fields=["user"])

    as_curator.post("/api/curator/tasks/", {"student": other.pk, "title": "Чужая задача"}, format="json")
    foreign = Task.objects.get(student=other)

    client = APIClient()
    client.force_login(user)
    assert client.get("/api/tasks/my/").json() == []
    assert client.get(f"/api/tasks/{foreign.pk}/").status_code == 404


@pytest.mark.django_db
def test_task_filters_and_overdue_flag(as_curator, chicago):
    """Фильтры экрана задач и просроченность считает сервер."""
    student = student_with(chicago, name="Фильтров", email="filter61@example.kz")
    as_curator.post(
        "/api/curator/tasks/",
        {"student": student.pk, "title": "Просроченная", "due_date": str(days(-3))},
        format="json",
    )
    as_curator.post(
        "/api/curator/tasks/", {"student": student.pk, "title": "Свежая", "due_date": str(days(3))}, format="json"
    )
    late = Task.objects.get(title="Просроченная")

    body = as_curator.get("/api/curator/tasks/?filter=late").json()
    assert [row["id"] for row in body["results"]] == [late.pk]
    assert body["results"][0]["is_overdue"] is True
    assert body["counts"]["open"] == 2 and body["counts"]["late"] == 1

    as_curator.post(f"/api/curator/tasks/{late.pk}/status/", {"status": "cancelled"}, format="json")
    after = as_curator.get("/api/curator/tasks/?filter=cancelled").json()
    assert [row["id"] for row in after["results"]] == [late.pk]
    assert after["counts"]["late"] == 0


# --- Карточка, поиск, выгрузка ---------------------------------------------------


@pytest.mark.django_db
def test_card_gathers_five_tabs_and_refuses_a_foreign_student(as_curator, chicago, boston, ielts):
    """Карточка отдаёт всё для пяти вкладок; чужая — 404, не 403."""
    student = student_with(
        chicago,
        name="Карточкин",
        email="card61@example.kz",
        ielts_kind=ielts,
        ielts_current=6.5,
        ielts_goal_score=7.5,
        ielts_exam_date=days(30),
        mock_date=days(-10),
    )
    alien = student_with(boston, name="Чужаков", email="alien-card61@example.kz")

    body = as_curator.get(f"/api/curator/students/{student.pk}/").json()
    assert body["full_name"] == student.full_name and body["group"] == "CHICAGO"
    assert body["exams"]["ielts_current"] == 6.5 and body["exams"]["ielts_target"] == 7.5
    assert body["exams"]["mocks_total"] == 1 and len(body["mocks"]) == 1
    for key in ("universities", "portfolio", "contacts", "buckets", "queue", "tasks"):
        assert key in body, key

    assert as_curator.get(f"/api/curator/students/{alien.pk}/").status_code == 404


@pytest.mark.django_db
def test_search_finds_only_own_students(as_curator, chicago, boston):
    """Поиск в шапке сузился до своих групп (фаза 61 вернула его куратору)."""
    student_with(chicago, name="Уникальнов", email="uniq61@example.kz")
    student_with(boston, name="Уникальсон", email="uniq2-61@example.kz")

    body = as_curator.get("/api/search/?q=Уникаль").json()
    students = next((g for g in body["groups"] if g["code"] == "students"), {"rows": []})
    assert [row["title"] for row in students["rows"]] == ["Уникальнов Ученик"]
    # справочник вузов куратору закрыт — и в поиске его нет: находка,
    # ведущая на закрытый экран, это ссылка в никуда
    assert [group["code"] for group in body["groups"]] == ["students"]


@pytest.mark.django_db
def test_students_export_is_a_real_workbook(as_curator, chicago):
    """Выгрузка отдаёт книгу XLSX с шапкой и строками — общим кодом выгрузки."""
    from io import BytesIO

    from openpyxl import load_workbook

    student_with(chicago, name="Выгрузов", email="xls61@example.kz", ielts_current=6.5, ielts_target=7.5)
    response = as_curator.get("/api/curator/students/export/")

    assert response.status_code == 200
    assert "spreadsheetml" in response["Content-Type"]
    assert "attachment" in response["Content-Disposition"]

    page = load_workbook(BytesIO(response.getvalue())).active
    rows = list(page.values)
    assert rows[0] == ("Ученик", "Группа", "Класс", "IELTS", "SAT", "Последний пробник", "Документы", "Статус")
    assert rows[1][0] == "Выгрузов Ученик" and rows[1][3] == "6.5 → 7.5"


@pytest.mark.django_db
def test_cabinet_is_closed_to_everyone_but_the_curator(api, make_user, chicago):
    """Кабинет куратора — только куратору: директору и администратору 403."""
    student_with(chicago, name="Ничейнов", email="nobody61@example.kz")
    for role in ("director_exam", "admin", "director_behavior"):
        api.force_login(make_user(role, f"{role}-61@example.kz"))
        for path in ("/api/curator/overview/", "/api/curator/students/", "/api/curator/tasks/"):
            assert api.get(path).status_code == 403, (role, path)


@pytest.mark.django_db
def test_group_curator_text_field_is_gone(as_curator, api, admin, chicago):
    """Текстового поля «куратор» у группы больше нет — ни в ответе, ни в записи."""
    api.force_login(admin)
    body = api.get(f"/api/groups/{chicago.pk}/").json()
    assert "curator" not in body
    assert "curator_hint" not in body
    assert body["curator_user"]["full_name"] == CURATOR_NAME

    refused = api.patch(f"/api/groups/{chicago.pk}/", {"curator": "Кто-то"}, format="json")
    assert refused.status_code == 400
    assert not any(field.name == "curator" for field in StudyGroup._meta.get_fields())
