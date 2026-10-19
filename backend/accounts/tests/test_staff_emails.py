"""Почты сотрудников из файла школы: `staff_emails` (решение владельца, 19.10.2026).

Строки здесь вымышленные: настоящий файл школы в тесты не кладётся.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounts import staff_emails, states
from accounts.logins import address_of, find_user
from accounts.mailing import _skip_reason
from accounts.models import Role, User
from core.models import AuditLog
from students.models import Student

pytestmark = pytest.mark.django_db


def book(tmp_path, rows: list[tuple[str, str]]):
    """Книга в формате школы: «№, ФИО, Почта»."""
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Почты учителей"
    sheet.append(["№", "ФИО", "Почта"])
    for number, (full_name, email) in enumerate(rows, start=1):
        sheet.append([number, full_name, email])
    path = tmp_path / "emails.xlsx"
    workbook.save(path)
    return str(path)


def staff(full_name: str, *, login: str | None = None, email: str | None = None, role: str = Role.TEACHER, **extra):
    """Сотрудник, как его заводит лист «Сотрудники»: с логином или с почтой."""
    return User.objects.create_user(email=email, login=login, password=None, full_name=full_name, role=role, **extra)


def run(path: str, *, apply: bool = False) -> str:
    out = StringIO()
    call_command("staff_emails", path, *(["--apply"] if apply else []), stdout=out)
    return out.getvalue()


def test_fills_the_email_of_a_login_account_found_by_a_shorter_name(tmp_path):
    """В файле ФИО с отчеством, в LMS — два слова и логин: почта вписывается, логин живёт."""
    user = staff("Жумабаева Гульнара", login="gulnara.zhumabaeva")
    path = book(tmp_path, [("Жумабаева Гульнара Ермековна", "G.Zhumabaeva@bhs.kz")])

    text = run(path, apply=True)
    user.refresh_from_db()

    assert "Впишется почта (1)" in text
    assert user.email == "g.zhumabaeva@bhs.kz"
    assert user.login == "gulnara.zhumabaeva"
    assert find_user("gulnara.zhumabaeva") == user
    assert find_user("g.zhumabaeva@bhs.kz") == user
    entry = AuditLog.objects.get(model_label="accounts.User", object_id=str(user.pk), field_name="email")
    assert (entry.old_value, entry.new_value, entry.source) == ("", "g.zhumabaeva@bhs.kz", "import")


def test_typo_in_the_surname_still_matches(tmp_path):
    """«Билаловна Сурия» в LMS и «Билалова Сурия» в файле — один человек."""
    user = staff("Билаловна Сурия", login="suriya.bilalovna")
    result = staff_emails.plan(
        staff_emails.read(book(tmp_path, [("Билалова Сурия Ахметовна", "s.bilalova@bhs.kz")]))[0]
    )
    assert [item.user for item in result.fill] == [user]


def test_unsure_match_is_shown_and_not_applied(tmp_path):
    """Тёзки в LMS и совпадение ниже порога — в «не уверен», без записи."""
    staff("Ахметова Алия", login="aliya.akhmetova")
    staff("Ахметова Алия", login="aliya.akhmetova2")
    staff("Сериков Бекзат", login="bekzat.serikov")
    path = book(
        tmp_path,
        [("Ахметова Алия Бекзатовна", "a.akhmetova@bhs.kz"), ("Серикова Бекзада Муратовна", "b.serikova@bhs.kz")],
    )

    text = run(path, apply=True)

    assert "Не уверен / конфликт (2)" in text
    assert "несколько похожих" in text
    assert "кандидаты" in text
    assert not User.objects.filter(email__isnull=False).exclude(email="").exists()
    assert not AuditLog.objects.exists()


def test_other_email_in_lms_is_a_conflict_and_same_email_is_nothing(tmp_path):
    same = staff("Нурманова Айдана", email="a.nurmanova@bhs.kz")
    other = staff("Касымов Ерлан", email="erlan@bhs.kz")
    path = book(
        tmp_path,
        [("Нурманова Айдана Сериковна", "A.Nurmanova@bhs.kz"), ("Касымов Ерлан Болатович", "e.kasymov@bhs.kz")],
    )

    text = run(path, apply=True)

    assert "Уже есть (1)" in text and "Не уверен / конфликт (1)" in text
    assert "в LMS другая почта" in text
    same.refresh_from_db()
    other.refresh_from_db()
    assert (same.email, other.email) == ("a.nurmanova@bhs.kz", "erlan@bhs.kz")
    assert not AuditLog.objects.exists()


def test_student_email_and_duplicate_rows_are_conflicts(tmp_path, student):
    student.email = "pupil@bhs.kz"
    student.save(update_fields=["email"])
    one = staff("Омарова Динара", login="dinara.omarova")
    path = book(
        tmp_path,
        [
            ("Омарова Динара", "pupil@bhs.kz"),
            ("Омарова Динара", "d.omarova@bhs.kz"),
            ("Омарова Динара Ж.", "d.omarova@bhs.kz"),
        ],
    )
    result = staff_emails.plan(staff_emails.read(path)[0])
    assert [item.why for item in result.unsure] == [staff_emails.EMAIL_OF_STUDENT, staff_emails.EMAIL_TWICE]
    assert [item.user for item in result.fill] == [one]


def test_dry_run_writes_nothing(tmp_path):
    user = staff("Жумабаева Гульнара", login="gulnara.zhumabaeva")
    path = book(tmp_path, [("Жумабаева Гульнара", "g.zhumabaeva@bhs.kz"), ("Новый Учитель Иванович", "n@bhs.kz")])

    text = run(path)

    assert "Сухой прогон" in text and "Впишется почта (1)" in text and "Заведётся (1)" in text
    user.refresh_from_db()
    assert user.email is None
    assert User.objects.count() == 1
    assert not AuditLog.objects.exists()


def test_new_person_is_a_teacher_without_password_who_waits_for_an_invite(tmp_path):
    path = book(tmp_path, [("Бекова Сауле Талгатовна", "s.bekova@bhs.kz")])

    run(path, apply=True)

    user = User.objects.get(email="s.bekova@bhs.kz")
    assert (user.role, user.full_name, user.login, user.is_active) == (
        Role.TEACHER,
        "Бекова Сауле Талгатовна",
        None,
        True,
    )
    assert not user.has_usable_password() and user.must_change_password
    assert states.state_of(user) == states.NO_PASSWORD
    assert user.last_login is None
    assert (
        AuditLog.objects.get(model_label="accounts.User", object_id=str(user.pk), field_name="role").source == "import"
    )
    # «Выслать письма» её возьмёт: почта есть, причин пропуска нет
    assert address_of(user) == "s.bekova@bhs.kz"
    assert _skip_reason(user, now=timezone.now(), force=False) == ""


def test_second_run_changes_nothing(tmp_path):
    staff("Жумабаева Гульнара", login="gulnara.zhumabaeva")
    path = book(
        tmp_path, [("Жумабаева Гульнара Ермековна", "g.zhumabaeva@bhs.kz"), ("Бекова Сауле", "s.bekova@bhs.kz")]
    )

    run(path, apply=True)
    users, entries = User.objects.count(), AuditLog.objects.count()
    text = run(path, apply=True)

    assert "Уже есть (2)" in text and "Впишется почта (0)" in text and "Заведётся (0)" in text
    assert (User.objects.count(), AuditLog.objects.count()) == (users, entries)


def test_disabled_account_gets_the_email_and_is_marked(tmp_path):
    user = staff("Жумабаева Гульнара", login="gulnara.zhumabaeva", is_active=False)
    path = book(tmp_path, [("Жумабаева Гульнара", "g.zhumabaeva@bhs.kz")])

    text = run(path, apply=True)
    user.refresh_from_db()

    assert "доступ отключён" in text
    assert user.email == "g.zhumabaeva@bhs.kz"
    assert _skip_reason(user, now=timezone.now(), force=False) != ""


def test_students_are_never_candidates(tmp_path, student):
    """Ученик с тем же ФИО не находится: почты вписываются только сотрудникам."""
    student.last_name, student.first_name = "Жумабаева", "Гульнара"
    student.save(update_fields=["last_name", "first_name"])
    result = staff_emails.plan(staff_emails.read(book(tmp_path, [("Жумабаева Гульнара", "g@bhs.kz")]))[0])
    assert len(result.create) == 1 and not result.fill


def test_student_card_without_email_does_not_break_the_plan(tmp_path, student):
    """На проде у карточки ученика почта None, а не пустая строка: план не падает, почта вписывается."""
    Student.objects.filter(pk=student.pk).update(email=None)
    User.objects.filter(role=Role.STUDENT).update(email=None)
    user = staff("Жумабаева Гульнара", login="gulnara.zhumabaeva")

    result = staff_emails.plan(staff_emails.read(book(tmp_path, [("Жумабаева Гульнара", "g.zhumabaeva@bhs.kz")]))[0])

    assert [item.user for item in result.fill] == [user] and not result.unsure
