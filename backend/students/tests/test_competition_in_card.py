"""Соревнование: «показывать в карточке ученика».

Школьный турнир и чемпионат страны весят для заявки по-разному, и решает это
человек. Отмеченные соревнования видны в карточке ученика у всех ролей и в CV;
неотмеченные — только на вкладке «Портфолио» (ученик, куратор группы)
и у директора спорта. Ставят отметку Нурлыбек и куратор своей группы; ученик
её не ставит, не предлагает и в ответах не видит.
"""

# ruff: noqa: F811 — фикстуры двух групп импортированы по имени
from __future__ import annotations

import pytest

from core.domains import can_student_propose, can_write
from students import portfolio
from students.models import Competition
from students.tests.test_admission_import_and_credentials import (  # noqa: F401 — фикстуры двух групп и куратора одной из них
    admin,
    asem,
    boston,
    chicago,
    curator,
    klass,
    kymbat,
    login,
    stranger,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def nurlybek(make_user):
    return make_user("director_sport", "nurlybek-card@example.kz", full_name="Нурлыбек")


@pytest.fixture
def two_rows(klass):
    student = klass[0]
    shown = Competition.objects.create(student=student, name="Чемпионат РК по плаванию", show_in_card=True)
    hidden = Competition.objects.create(student=student, name="Школьный турнир")
    return student, shown, hidden


def names(user, student) -> list[str]:
    answer = login(user).get(f"/api/competitions/?student={student.pk}")
    assert answer.status_code == 200, answer.content
    return sorted(row["name"] for row in answer.data["results"])


def test_new_competition_is_not_shown_by_default(klass):
    assert Competition.objects.create(student=klass[0], name="Турнир").show_in_card is False


def test_the_card_of_other_directors_shows_only_the_marked(two_rows, asem, kymbat, nurlybek, curator, admin):
    student, shown, hidden = two_rows
    for user in (asem, kymbat):
        assert names(user, student) == [shown.name], user.role
    for user in (nurlybek, curator, admin, student.user):
        assert names(user, student) == sorted([shown.name, hidden.name]), user.role
    # прямой адрес неотмеченного чужому директору тоже закрыт
    assert login(asem).get(f"/api/competitions/{hidden.pk}/").status_code == 404


def test_cv_lists_only_the_marked(two_rows):
    student, shown, hidden = two_rows
    html = portfolio.cv_html(student)
    assert shown.name in html
    assert hidden.name not in html


def test_the_sport_director_and_the_curator_of_the_group_set_the_mark(two_rows, nurlybek, curator, stranger):
    student, _shown, hidden = two_rows
    assert (
        login(curator).patch(f"/api/competitions/{hidden.pk}/", {"show_in_card": True}, format="json").status_code
        == 200
    )
    hidden.refresh_from_db()
    assert hidden.show_in_card is True
    assert (
        login(nurlybek).patch(f"/api/competitions/{hidden.pk}/", {"show_in_card": False}, format="json").status_code
        == 200
    )
    hidden.refresh_from_db()
    assert hidden.show_in_card is False

    foreign = Competition.objects.create(student=stranger, name="Чужой турнир")
    assert (
        login(curator).patch(f"/api/competitions/{foreign.pk}/", {"show_in_card": True}, format="json").status_code
        == 404
    )


def test_other_directors_and_the_student_do_not_set_it(two_rows, asem):
    student, shown, _hidden = two_rows
    assert (
        login(asem).patch(f"/api/competitions/{shown.pk}/", {"show_in_card": False}, format="json").status_code == 403
    )
    assert (
        login(student.user).patch(f"/api/competitions/{shown.pk}/", {"show_in_card": False}, format="json").status_code
        == 403
    )
    shown.refresh_from_db()
    assert shown.show_in_card is True
    assert not can_student_propose("students.Competition", "show_in_card")
    assert not can_write("student", "students.Competition", "show_in_card")


def test_the_student_does_not_see_the_mark(two_rows):
    student, _shown, _hidden = two_rows
    answer = login(student.user).get(f"/api/competitions/?student={student.pk}")
    assert all("show_in_card" not in row for row in answer.data["results"])
