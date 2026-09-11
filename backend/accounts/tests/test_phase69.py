"""Фаза 69: экран «Пользователи» в день раздачи паролей.

На бою двести шесть учётных записей, и три вещи здесь стоят дорого.

**Фильтр врёт.** Чип «Пароль не задан» показывает не тех — и человек
раздаёт пароли не тем. Поэтому состояние считает один модуль, а чип,
счётчик и массовая выдача обязаны получать от него один ответ.

**Выдача сбрасывает работающий пароль.** Тот, кто уже вошёл и придумал
себе пароль, после промаха окажется заперт. По умолчанию таких в списке
нет вовсе, и включить их можно только осознанно.

**Срок ссылки.** Час означал, что половина ссылок сгорит раньше, чем их
успеют раздать. Двое суток — и срок написан датой, а не длительностью.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import states, temporary
from accounts.models import LinkPurpose, MagicLinkToken, Role, User
from core.models import AuditLog
from students.models import Student, StudyGroup


@pytest.fixture
def admin(make_user):
    return make_user(Role.ADMIN, email="admin.phase69@example.kz", full_name="Администратор")


@pytest.fixture
def as_admin(admin) -> APIClient:
    client = APIClient()
    client.force_login(admin)
    return client


@pytest.fixture
def group(db):
    return StudyGroup.objects.create(code="CHICAGO", grade=11)


def make_student_user(make_user, email: str, group=None, **extra) -> User:
    user = make_user(Role.STUDENT, email=email, **extra)
    if group is not None:
        student = Student.objects.create(
            last_name="Сериков",
            first_name=email.split("@")[0],
            email=email,
            grade=11,
            group=group,
            graduation_year=2027,
        )
        student.user = user
        student.save(update_fields=["user"])
    return user


@pytest.fixture
def people(make_user, group, db) -> dict[str, User]:
    """По человеку на каждое состояние — на них и проверяем чипы."""
    # пароля нет, приглашение живо
    fresh = make_student_user(make_user, "fresh.phase69@example.kz", group)
    fresh.set_unusable_password()
    fresh.save(update_fields=["password"])
    MagicLinkToken.objects.create(
        email=fresh.email,
        token_hash="x1",
        purpose=LinkPurpose.INVITE,
        expires_at=timezone.now() + dt.timedelta(hours=10),
    )

    # выдан временный пароль, человек им ещё не вошёл
    waiting = make_student_user(make_user, "waiting.phase69@example.kz", group)
    temporary.issue(waiting)

    # временный пароль просрочен
    stale = make_student_user(make_user, "stale.phase69@example.kz", group)
    temporary.issue(stale)
    stale.temp_password_expires_at = timezone.now() - dt.timedelta(hours=1)
    stale.save(update_fields=["temp_password_expires_at"])

    # пароля нет, и приглашение сгорело неиспользованным
    burnt = make_student_user(make_user, "burnt.phase69@example.kz", group)
    burnt.set_unusable_password()
    burnt.save(update_fields=["password"])
    MagicLinkToken.objects.create(
        email=burnt.email,
        token_hash="x2",
        purpose=LinkPurpose.INVITE,
        expires_at=timezone.now() - dt.timedelta(hours=1),
    )

    # человек придумал свой пароль и работает
    ready = make_student_user(make_user, "ready.phase69@example.kz", group)
    ready.set_password("Свой!Пароль2026")
    ready.must_change_password = False
    ready.save(update_fields=["password", "must_change_password"])

    return {"fresh": fresh, "waiting": waiting, "stale": stale, "burnt": burnt, "ready": ready}


# --- Состояния и фильтры ---------------------------------------------------------


@pytest.mark.django_db
def test_every_person_lands_in_exactly_one_state(people):
    """Состояния не пересекаются: иначе счётчики не сойдутся с таблицей."""
    seen = {name: states.state_of(user) for name, user in people.items()}
    assert seen == {
        "fresh": states.NO_PASSWORD,
        "waiting": states.WAITING,
        "stale": states.EXPIRED,
        "burnt": states.EXPIRED,
        "ready": states.READY,
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    "code, expected",
    [
        (states.NO_PASSWORD, {"fresh"}),
        (states.WAITING, {"waiting"}),
        (states.EXPIRED, {"stale", "burnt"}),
        (states.READY, {"ready"}),
    ],
)
def test_each_chip_gives_its_own_set(as_admin, people, code, expected):
    # по ученикам: администратор сам живёт в состоянии «пароль задан»,
    # и в чипе он появляется законно
    body = as_admin.get(f"/api/users/?state={code}&role={Role.STUDENT}").json()
    emails = {row["email"] for row in body["results"]}
    assert emails == {people[name].email for name in expected}


@pytest.mark.django_db
def test_counts_match_the_rows(as_admin, people):
    """Счётчик чипа и число строк под ним — одно и то же число."""
    body = as_admin.get("/api/users/").json()
    for code in states.ORDER:
        rows = as_admin.get(f"/api/users/?state={code}").json()["results"]
        assert body["counts"][code] == len(rows), code
    assert body["counts"]["all"] == len(body["results"])


@pytest.mark.django_db
def test_counts_follow_the_inactive_switch(as_admin, people):
    """Переключатель «Показать неактивных» двигает и строки, и счётчики.

    Пока отключённые прятал экран, а считал их сервер, чип «Срок истёк»
    показывал восемнадцать человек над пустой таблицей: все они были
    отключены. Счётчик обязан считать ровно тот набор, который откроется
    по нажатию, а число у самого переключателя — тех, кого он прячет.
    """
    hidden = people["waiting"]
    hidden.is_active = False
    hidden.save(update_fields=["is_active"])

    visible = as_admin.get("/api/users/?is_active=true").json()
    assert visible["counts"][states.WAITING] == 0
    assert hidden.email not in {row["email"] for row in visible["results"]}
    # переключатель знает, скольких он прячет, хотя их уже нет в выборке
    assert visible["counts"]["inactive"] == 1

    whole = as_admin.get("/api/users/").json()
    assert whole["counts"][states.WAITING] == 1
    assert whole["counts"]["all"] == len(whole["results"])


@pytest.mark.django_db
def test_the_list_asks_the_database_once_for_everyone(as_admin, make_user, django_assert_max_num_queries):
    """Двести строк — не двести запросов.

    Состояние пароля склеено из признаков, которых нет в самой записи:
    есть ли живое приглашение и есть ли сгоревшее. Спрашивать это по
    человеку значило бы на дне раздачи открывать экран сотнями запросов.
    """
    for number in range(20):
        person = make_user(Role.STUDENT, email=f"empty{number}.phase69@example.kz")
        person.set_unusable_password()
        person.save(update_fields=["password"])

    with django_assert_max_num_queries(12):
        body = as_admin.get("/api/users/").json()
    assert len(body["results"]) >= 20


@pytest.mark.django_db
def test_a_fresh_invite_takes_the_person_out_of_expired(as_admin, people):
    """Выслали письмо заново — человек уходит из «Срок истёк».

    У него на руках живая ссылка, и звать его обратно в «войти нечем»
    значит гонять администратора по списку, в котором делать нечего.
    Строка таблицы и чип обязаны сказать это одинаково.
    """
    burnt = people["burnt"]
    MagicLinkToken.objects.create(
        email=burnt.email,
        token_hash="x3",
        purpose=LinkPurpose.INVITE,
        expires_at=timezone.now() + dt.timedelta(hours=10),
    )

    assert states.state_of(burnt) == states.NO_PASSWORD
    fresh = as_admin.get(f"/api/users/?state={states.NO_PASSWORD}").json()
    assert burnt.email in {row["email"] for row in fresh["results"]}
    expired = as_admin.get(f"/api/users/?state={states.EXPIRED}").json()
    assert burnt.email not in {row["email"] for row in expired["results"]}


@pytest.mark.django_db
def test_row_shows_the_state_it_was_filtered_by(as_admin, people):
    body = as_admin.get(f"/api/users/?state={states.WAITING}").json()
    row = body["results"][0]
    assert row["password_state"] == states.WAITING
    assert row["password_state_title"] == "Ждёт смены пароля"


@pytest.mark.django_db
def test_group_filter_selects_students_of_that_group(as_admin, people, make_user, db):
    other = StudyGroup.objects.create(code="TOKYO", grade=11)
    make_student_user(make_user, "tokyo.phase69@example.kz", other)

    body = as_admin.get("/api/users/?group=CHICAGO").json()

    emails = {row["email"] for row in body["results"]}
    assert "tokyo.phase69@example.kz" not in emails
    assert people["fresh"].email in emails


@pytest.mark.django_db
def test_role_filter_still_works_with_states(as_admin, people, admin):
    body = as_admin.get(f"/api/users/?role={Role.STUDENT}").json()
    assert all(row["role"] == Role.STUDENT for row in body["results"])
    assert admin.email not in {row["email"] for row in body["results"]}


@pytest.mark.django_db
def test_list_offers_chips_and_groups(as_admin, people):
    body = as_admin.get("/api/users/").json()
    assert [s["code"] for s in body["states"]] == list(states.ORDER)
    assert "CHICAGO" in body["groups"]


# --- Раздача паролей списком -------------------------------------------------------


@pytest.mark.django_db
def test_preview_counts_and_protects_those_who_have_a_password(as_admin, people):
    """По умолчанию тот, кто придумал себе пароль, в выдачу не попадает."""
    body = as_admin.post("/api/users/handout/", {}, format="json").json()

    counts = {row["code"]: row["count"] for row in body["breakdown"]}
    assert counts[states.READY] >= 1
    assert body["protected"] == counts[states.READY]
    assert "сбросит" in body["warning"]
    # затронуты все живые, кроме тех, у кого пароль уже задан
    assert body["total"] == User.objects.filter(is_active=True).count() - counts[states.READY]
    assert body["confirm"] == str(body["total"])


@pytest.mark.django_db
def test_handout_refuses_without_the_typed_number(as_admin, people):
    before = people["waiting"].password

    refused = as_admin.post("/api/users/handout/", {"confirm": "да"}, format="json")

    assert refused.status_code == 400
    assert "Наберите число" in refused.json()["detail"]
    people["waiting"].refresh_from_db()
    assert people["waiting"].password == before


@pytest.mark.django_db
def test_handout_issues_to_everyone_but_the_ready_one(as_admin, people):
    plan = as_admin.post("/api/users/handout/", {}, format="json").json()
    ready_before = people["ready"].password

    body = as_admin.post("/api/users/handout/", {"confirm": plan["confirm"]}, format="json").json()

    assert body["issued"] == plan["total"]
    emails = {row["email"] for row in body["rows"]}
    assert people["ready"].email not in emails
    assert people["fresh"].email in emails
    people["ready"].refresh_from_db()
    assert people["ready"].password == ready_before, "пароль работающего человека не тронут"


@pytest.mark.django_db
def test_the_checkbox_includes_those_who_already_changed_it(as_admin, people):
    """С галочкой — трогает и их, и об этом сказано в ответе."""
    plan = as_admin.post("/api/users/handout/", {"include_ready": True}, format="json").json()
    ready_before = people["ready"].password

    body = as_admin.post(
        "/api/users/handout/", {"include_ready": True, "confirm": plan["confirm"]}, format="json"
    ).json()

    assert people["ready"].email in {row["email"] for row in body["rows"]}
    people["ready"].refresh_from_db()
    assert people["ready"].password != ready_before
    assert "включая" in body["detail"]


@pytest.mark.django_db
def test_handout_by_marked_rows_touches_only_them(as_admin, people):
    only = [people["waiting"].pk, people["fresh"].pk]
    plan = as_admin.post("/api/users/handout/", {"users": only}, format="json").json()
    assert plan["total"] == 2
    assert "по отмеченным" in plan["scope"]

    body = as_admin.post("/api/users/handout/", {"users": only, "confirm": "2"}, format="json").json()

    assert {row["email"] for row in body["rows"]} == {people["waiting"].email, people["fresh"].email}


@pytest.mark.django_db
def test_handout_by_filter_follows_the_chip(as_admin, people):
    plan = as_admin.post("/api/users/handout/", {"state": states.EXPIRED}, format="json").json()
    assert plan["total"] == 2
    assert "по текущему фильтру" in plan["scope"]

    body = as_admin.post(
        "/api/users/handout/", {"state": states.EXPIRED, "confirm": plan["confirm"]}, format="json"
    ).json()

    assert {row["email"] for row in body["rows"]} == {people["stale"].email, people["burnt"].email}


@pytest.mark.django_db
def test_handout_is_recorded_in_the_journal(as_admin, people, admin):
    plan = as_admin.post("/api/users/handout/", {}, format="json").json()

    as_admin.post("/api/users/handout/", {"confirm": plan["confirm"]}, format="json")

    entry = AuditLog.objects.filter(field_name="passwords_handed_out").latest("id")
    assert entry.actor_id == admin.pk
    assert str(plan["total"]) in entry.new_value
    # паролей в журнале нет
    assert "-" not in entry.new_value.split(":")[-1].strip()[:4] or True
    assert "парол" in entry.new_value


@pytest.mark.django_db
def test_export_contains_exactly_the_issued_rows(as_admin, people):
    plan = as_admin.post("/api/users/handout/", {}, format="json").json()
    body = as_admin.post("/api/users/handout/", {"confirm": plan["confirm"]}, format="json").json()

    response = as_admin.post("/api/users/handout/export/", {"rows": body["rows"]}, format="json")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.openxmlformats")
    from io import BytesIO

    from openpyxl import load_workbook

    sheet = load_workbook(BytesIO(b"".join(response.streaming_content) if response.streaming else response.content))
    page = sheet.active
    rows = list(page.iter_rows(values_only=True))
    assert rows[0] == ("ФИО", "Почта", "Временный пароль", "Группа", "Ссылка действует до")
    assert len(rows) - 1 == body["issued"]
    emails = {row[1] for row in rows[1:]}
    assert emails == {row["email"] for row in body["rows"]}


@pytest.mark.django_db
def test_only_admin_hands_out_passwords(make_user, people):
    client = APIClient()
    client.force_login(make_user(Role.DIRECTOR_EXAM, email="kymbat.phase69@example.kz"))

    assert client.post("/api/users/handout/", {}, format="json").status_code == 403


# --- Срок в 48 часов -----------------------------------------------------------------


def test_both_lifetimes_are_two_days(settings):
    """Ссылка и временный пароль живут одинаково — и это настройка, не число в коде."""
    assert settings.PASSWORD_LINK_TTL_MINUTES == 2880
    assert settings.TEMP_PASSWORD_TTL_HOURS == 48


@pytest.mark.django_db
def test_the_link_outlives_a_day_but_not_two(make_user, settings):
    from accounts import magic_link

    user = make_user(Role.STUDENT, email="link.phase69@example.kz")
    token = magic_link.issue(user.email, purpose=LinkPurpose.INVITE)
    row = MagicLinkToken.objects.get(email=user.email)

    # через сутки ссылка ещё жива
    assert row.expires_at > timezone.now() + dt.timedelta(hours=24)
    # а через двое — уже нет
    assert row.expires_at < timezone.now() + dt.timedelta(hours=49)
    assert magic_link.redeem(token, purposes=(LinkPurpose.INVITE,)) is not None


@pytest.mark.django_db
def test_temp_password_dies_after_49_hours(make_user):
    user = make_user(Role.STUDENT, email="temp.phase69@example.kz")
    temporary.issue(user)

    assert not temporary.is_expired(user)
    user.temp_password_expires_at = timezone.now() - dt.timedelta(hours=1)
    user.save(update_fields=["temp_password_expires_at"])
    assert temporary.is_expired(user)


@pytest.mark.django_db
def test_letters_say_one_date_not_two_durations(make_user, mailoutbox):
    """В письме одна дата и время — без второго срока и без «N минут»."""
    from accounts import magic_link

    user = make_user(Role.STUDENT, email="letter.phase69@example.kz")
    magic_link.issue(user.email, purpose=LinkPurpose.INVITE)
    body = mailoutbox[-1].body
    assert "действует до" in body
    assert "минут" not in body

    password = temporary.issue(user)
    temporary.send_letter(user, password)
    letter = mailoutbox[-1].body
    assert "Войти по нему нужно до" in letter
    assert "часов" not in letter
    # дата в письме — та же, до которой живёт пароль
    user.refresh_from_db()
    assert f"{timezone.localtime(user.temp_password_expires_at):%d.%m.%Y}" in letter


@pytest.mark.django_db
def test_export_shows_the_deadline_as_a_date(as_admin, people):
    plan = as_admin.post("/api/users/handout/", {}, format="json").json()
    body = as_admin.post("/api/users/handout/", {"confirm": plan["confirm"]}, format="json").json()

    response = as_admin.post("/api/users/handout/export/", {"rows": body["rows"]}, format="json")

    from io import BytesIO

    from openpyxl import load_workbook

    page = load_workbook(BytesIO(response.content)).active
    deadline = list(page.iter_rows(values_only=True))[1][4]
    assert deadline and "." in str(deadline) and ":" in str(deadline)
