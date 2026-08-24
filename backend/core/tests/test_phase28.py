"""Фаза 28: ссылка-приглашение руками и полная очистка архива.

Две вещи, из-за которых система буксовала в жизни: завести человека
без настроенной почты было нечем, а удалённое копилось в архиве навсегда.

Проверяем не тексты, а то, что нарушать нельзя: ссылка выдаётся только
администратору и только по нажатию, а журнал изменений переживает
даже безвозвратное удаление и продолжает читаться человеком.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.utils import timezone

from accounts.models import LinkPurpose, MagicLinkToken, Role, User
from core.archive import archive, purge, purge_batch, purge_batch_preview, purge_preview
from core.audit import apply_changes
from core.models import ArchiveEntry, AuditLog
from students.models import ExamProfile, Student, StudyGroup

CONSOLE = "django.core.mail.backends.console.EmailBackend"


@pytest.fixture
def admin(make_user):
    return make_user(Role.ADMIN, email="admin.phase28@example.kz")


@pytest.fixture
def group(db):
    return StudyGroup.objects.create(code="11B", grade=11)


@pytest.fixture
def learner(group):
    student = Student.objects.create(
        last_name="Ахметова",
        first_name="Алия",
        email="aliya.phase28@school.kz",
        grade=11,
        group=group,
        graduation_year=2027,
    )
    ExamProfile.objects.create(student=student)
    return student


# --- Ссылка-приглашение ----------------------------------------------------


@pytest.mark.django_db
@override_settings(EMAIL_BACKEND=CONSOLE, EMAIL_HOST="", FRONTEND_BASE_URL="https://school.example")
def test_new_user_comes_back_with_a_link_to_hand_over(client, admin):
    """Почта не настроена — ссылку администратор видит сразу на экране."""
    client.force_login(admin)

    body = client.post(
        "/api/users/",
        {"email": "newbie@school.kz", "full_name": "Данияр Оспанов", "role": Role.STUDENT},
        content_type="application/json",
    ).json()

    assert body["invite"]["link"].startswith("https://school.example/set-password?token=")
    assert body["invite"]["minutes"] > 0
    assert "newbie@school.kz" in body["invite"]["detail"]


@pytest.mark.django_db
@override_settings(FRONTEND_BASE_URL="https://school.example")
def test_admin_can_ask_for_a_fresh_link_later(client, admin, db):
    """Кнопка в списке выпускает новую ссылку — старая могла и протухнуть."""
    user = User.objects.create_user(email="later@school.kz", password=None, role=Role.STUDENT)
    client.force_login(admin)

    body = client.post(f"/api/users/{user.pk}/invite-link/").json()

    assert "set-password?token=" in body["link"]
    assert MagicLinkToken.objects.filter(email="later@school.kz", purpose=LinkPurpose.INVITE).count() == 1


@pytest.mark.django_db
def test_the_link_is_not_shown_in_the_list(client, admin, db):
    """В общем списке ссылки нет: оттуда она уедет в скриншот и в журнал."""
    User.objects.create_user(email="quiet@school.kz", password=None, role=Role.STUDENT)
    client.force_login(admin)

    rows = client.get("/api/users/").json()

    assert rows
    for row in rows:
        assert "invite" not in row
        assert "link" not in row
        assert "token" not in str(row)


@pytest.mark.django_db
def test_only_admin_gets_the_link(client, make_user, db):
    user = User.objects.create_user(email="target@school.kz", password=None, role=Role.STUDENT)
    director = make_user(Role.DIRECTOR_EXAM, email="kymbat.phase28@example.kz")
    client.force_login(director)

    assert client.post(f"/api/users/{user.pk}/invite-link/").status_code == 403


@pytest.mark.django_db
def test_disabled_account_gets_no_link(client, admin, db):
    """Отключённому доступ не открываем ссылкой в обход отключения."""
    user = User.objects.create_user(email="off@school.kz", password=None, role=Role.STUDENT)
    user.is_active = False
    user.save(update_fields=["is_active"])
    client.force_login(admin)

    response = client.post(f"/api/users/{user.pk}/invite-link/")
    assert response.status_code == 400
    assert "отключена" in response.json()["detail"]


@pytest.mark.django_db
@override_settings(FRONTEND_BASE_URL="https://school.example")
def test_link_from_the_screen_actually_sets_the_password(client, admin, db):
    """Полный путь: администратор скопировал ссылку — человек вошёл."""
    client.force_login(admin)
    created = client.post(
        "/api/users/", {"email": "walkthrough@school.kz", "full_name": "Асель Ким"}, content_type="application/json"
    ).json()

    token = created["invite"]["link"].split("token=")[1]
    client.logout()

    done = client.post(
        "/api/auth/password/set/",
        {"token": token, "new_password": "Асель!Осень2026"},
        content_type="application/json",
    )
    assert done.status_code == 200

    client.logout()
    entered = client.post(
        "/api/auth/login/",
        {"email": "walkthrough@school.kz", "password": "Асель!Осень2026"},
        content_type="application/json",
    )
    assert entered.status_code == 200
    assert entered.json()["must_change_password"] is False


@pytest.mark.django_db
def test_command_prints_a_link(db, capsys):
    from io import StringIO

    from django.core.management import call_command

    User.objects.create_user(email="cli@school.kz", password=None, role=Role.STUDENT)
    out = StringIO()
    call_command("invite_link", "cli@school.kz", stdout=out)

    assert "set-password?token=" in out.getvalue()


@pytest.mark.django_db
def test_command_refuses_for_an_unknown_email(db):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    with pytest.raises(CommandError) as error:
        call_command("invite_link", "nobody@school.kz")
    assert "нет" in str(error.value)


# --- Полное удаление из архива ---------------------------------------------


@pytest.mark.django_db
def test_purge_removes_the_record_but_keeps_the_journal(learner, admin):
    """Ученика нет ни в списках, ни в архиве — а журнал о нём читается.

    Инвариант №13 существует ради истории, а не ради самих строк:
    запись можно стереть, а память о правках — нельзя.
    """
    apply_changes(learner.exam, {"ielts_current": "7.0"}, actor=admin)
    entry = archive(learner, actor=admin)
    assert Student.all_objects.filter(pk=learner.pk).exists()

    result = purge(entry, actor=admin)

    assert result["purged"] >= 1
    assert not Student.all_objects.filter(pk=learner.pk).exists()
    entry.refresh_from_db()
    assert entry.is_purged

    row = AuditLog.objects.filter(field_name="ielts_current").first()
    assert row is not None
    assert row.object_deleted is True
    assert row.object_purged is True
    # имя видно: без него запись читалась бы как «students.ExamProfile#12»
    assert "Ахметова Алия" in row.object_title


@pytest.mark.django_db
def test_journal_of_a_purged_record_is_still_readable(client, learner, admin):
    """Карточки нет, а история читается — и показывает прежнее имя.

    Ради этого инвариант №13 и написан: журнал не должен ссылаться
    в пустоту, но и исчезать вместе с объектом ему нельзя.
    """
    apply_changes(learner.exam, {"ielts_current": "7.0"}, actor=admin)
    entry = archive(learner, actor=admin)
    purge(entry, actor=admin)
    client.force_login(admin)

    body = client.get(f"/api/archive/{entry.pk}/journal/").json()

    assert body["title"] == "Ахметова Алия"
    assert body["rows"], "журнал пуст — читать историю удалённого стало негде"
    row = next(r for r in body["rows"] if r["field_title"])
    assert "Ахметова Алия" in row["object_title"]
    assert row["new_display"]


@pytest.mark.django_db
def test_purge_preview_says_plainly_that_there_is_no_way_back(learner, admin):
    entry = archive(learner, actor=admin)
    preview = purge_preview(entry)

    assert preview["confirm_word"] == "УДАЛИТЬ"
    assert any("восстановить будет нельзя" in line for line in preview["consequences"])
    assert any("журнал" in line.lower() for line in preview["consequences"])


@pytest.mark.django_db
def test_restored_record_is_not_purged(learner, admin):
    """Восстановленное удалять из архива нечего — и незачем."""
    from core.archive import restore

    entry = archive(learner, actor=admin)
    restore(entry, actor=admin)

    result = purge(entry, actor=admin)
    assert result["purged"] == 0
    assert Student.objects.filter(pk=learner.pk).exists()


@pytest.mark.django_db
def test_user_account_is_never_purged(admin, make_user):
    """На учётной записи висит журнал правок — её удалять нельзя вовсе."""
    victim = make_user(Role.DIRECTOR_SPORT, email="victim.phase28@example.kz")
    entry = ArchiveEntry.objects.create(
        model_label="accounts.User", object_id=str(victim.pk), title=victim.email, kind_title="Учётная запись"
    )

    result = purge(entry, actor=admin)

    assert result["purged"] == 0
    assert User.objects.filter(pk=victim.pk).exists()
    assert "журнал" in result["detail"]


@pytest.mark.django_db
def test_api_demands_the_typed_word(client, learner, admin):
    entry = archive(learner, actor=admin)
    client.force_login(admin)

    refused = client.post(f"/api/archive/{entry.pk}/purge/", {"confirm": "да"}, content_type="application/json")
    assert refused.status_code == 400
    assert Student.all_objects.filter(pk=learner.pk).exists()

    done = client.post(f"/api/archive/{entry.pk}/purge/", {"confirm": "УДАЛИТЬ"}, content_type="application/json")
    assert done.status_code == 200
    assert not Student.all_objects.filter(pk=learner.pk).exists()


@pytest.mark.django_db
def test_only_admin_purges(client, learner, make_user, admin):
    entry = archive(learner, actor=admin)
    director = make_user(Role.DIRECTOR_BEHAVIOR, email="saltanat.phase28@example.kz")
    client.force_login(director)

    assert client.get(f"/api/archive/{entry.pk}/purge/").status_code == 403
    assert (
        client.post(
            f"/api/archive/{entry.pk}/purge/", {"confirm": "УДАЛИТЬ"}, content_type="application/json"
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_batch_cleanup_takes_only_what_is_older(learner, group, admin):
    """Свежие удаления массовая очистка не трогает."""
    old = archive(learner, actor=admin)
    ArchiveEntry.objects.filter(pk=old.pk).update(created_at=timezone.now() - timezone.timedelta(days=200))

    fresh_student = Student.objects.create(
        last_name="Сериков",
        first_name="Дамир",
        email="damir.phase28@school.kz",
        grade=11,
        group=group,
        graduation_year=2027,
    )
    archive(fresh_student, actor=admin)

    preview = purge_batch_preview(older_than_days=180)
    assert preview["entries"] == 1

    result = purge_batch(older_than_days=180, actor=admin)
    assert result["entries"] == 1
    assert not Student.all_objects.filter(pk=learner.pk).exists()
    assert Student.all_objects.filter(pk=fresh_student.pk).exists()


@pytest.mark.django_db
def test_batch_cleanup_needs_the_word_too(client, learner, admin):
    entry = archive(learner, actor=admin)
    ArchiveEntry.objects.filter(pk=entry.pk).update(created_at=timezone.now() - timezone.timedelta(days=400))
    client.force_login(admin)

    preview = client.get("/api/archive/cleanup/?days=90").json()
    assert preview["entries"] == 1
    assert preview["confirm_word"] == "УДАЛИТЬ"

    refused = client.post("/api/archive/cleanup/", {"days": 90}, content_type="application/json")
    assert refused.status_code == 400

    done = client.post(
        "/api/archive/cleanup/", {"days": 90, "confirm": "УДАЛИТЬ"}, content_type="application/json"
    ).json()
    assert done["entries"] == 1
    assert not Student.all_objects.filter(pk=learner.pk).exists()
