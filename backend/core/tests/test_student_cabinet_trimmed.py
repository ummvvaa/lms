"""Кабинет ученика без лишнего (решение владельца, 07.10.2026).

«Мой путь», план поступления, стипендии, роадмап, ресурсы и избранное
убраны из кабинета: пункта меню нет, адрес ведёт на главную. Маршруты
разделов остаются — задачи живут на главной, сотрудники читают данные.
«Мои вузы» — вкладка «Каталога вузов».
"""

from __future__ import annotations

import pytest

from core.parallels import HIDDEN_PATHS, student_screen
from core.tests.test_parallel_gate import _student
from engagement.cues import build
from engagement.models import HomeCue

HIDDEN = {"/journey", "/plan", "/scholarships", "/roadmap", "/resources", "/favorites", "/universities"}


def test_hidden_list_is_the_one_on_the_screen():
    from pathlib import Path

    assert HIDDEN_PATHS == HIDDEN
    nav = (Path(__file__).resolve().parents[3] / "frontend" / "src" / "layout" / "nav.ts").read_text()
    line = nav.split("export const STUDENT_HIDDEN = [")[1].split("]")[0]
    # «Мои вузы» на фронте — переход на вкладку каталога, а не «на главную»
    assert {item.strip().strip("'") for item in line.split(",")} == HIDDEN - {"/universities"}


@pytest.mark.django_db
def test_menu_of_eleventh_grade_has_no_hidden_screens_but_routes_work(make_user):
    client, _student_ = _student(11, make_user)
    sections = client.get("/api/auth/me/").json()["sections"]
    assert not HIDDEN & set(sections)
    assert {"/dashboard", "/catalog", "/selection", "/my-data"} <= set(sections)
    # задачи — на главной: маршруты роадмапа ученику открыты
    assert client.get("/api/tasks/my/").status_code == 200
    # замка у подбора нет — он открыт без условий
    locks = {row["path"] for row in client.get("/api/journey/locks/").json()["locks"]}
    assert "/selection" not in locks


@pytest.mark.django_db
def test_home_cue_leading_to_a_hidden_screen_is_not_shown(make_user):
    _client, student = _student(11, make_user)
    HomeCue.objects.update(is_active=False)
    cue = HomeCue.objects.filter(action_path__in=["/plan", "/scholarships"]).first()
    assert cue is not None, "сюжеты плана и стипендий посеяны миграциями"
    HomeCue.objects.filter(pk=cue.pk).update(is_active=True)
    assert all(student_screen(row["path"].split("?")[0]) for row in build(student))
    assert cue.code not in {row["code"] for row in build(student)}
