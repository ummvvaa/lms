"""Класса нет — есть параллель, и только у группы.

Школа ведёт 8–11 параллели (поступление — только у 11). Параллель задаёт
администратор группе; ученику она не выбирается, не вводится и не
показывается отдельным полем — его параллель берётся из группы
(`core.parallels.parallel_of`). Фильтр по параллели допустим только
в списках сотрудников.

Слово «класс» в интерфейсе по-прежнему не встречается: страж обходит
исходники фронта так же, как страж словарей. Слова «одноклассник»
и «классификация» классом не являются и перечислены явно.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.tests.test_i18n import FRONTEND, cyrillic_literals

#: слова, в которых «класс» — не школьный класс
NOT_A_GRADE = re.compile(r"одноклассни|классифи|классическ", re.I)
THE_WORD = re.compile(r"класс", re.I)
#: имена полей, которыми класс уходил бы на сервер из формы или фильтра
GRADE_KEYS = re.compile(r"""(name:\s*'grade'|\bgrade:\s|[?&]grade=|'grade'\s*,|setGrade|graduation_year',\s*label)""")


def sources() -> list[Path]:
    return [
        path
        for path in sorted(FRONTEND.rglob("*.ts*"))
        if "i18n" not in path.parts and not path.name.endswith(("schema.ts", ".d.ts"))
    ]


def test_no_interface_string_mentions_the_class():
    found = []
    for path in sources():
        for text in cyrillic_literals(path.read_text(encoding="utf-8")):
            if THE_WORD.search(NOT_A_GRADE.sub("", text)):
                found.append(f"{path.relative_to(FRONTEND)}: {text}")
    assert not found, "класс в интерфейсе:\n" + "\n".join(found)


def test_no_form_or_filter_sends_the_class():
    """Ни одна форма и ни один фильтр не отправляют класс: тип ответа сервера — не форма."""
    found = []
    for path in sources():
        if path.name == "hooks.ts" or path.parts[-2] == "api":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if GRADE_KEYS.search(line) and "grade: number" not in line:
                found.append(f"{path.relative_to(FRONTEND)}:{number}: {line.strip()}")
    assert not found, "класс уходит из формы или фильтра:\n" + "\n".join(found)


@pytest.mark.django_db
def test_parallel_lives_only_on_the_group(make_user):
    """Сервер: у ученика нет ни класса, ни параллели; группа без параллели — 11,
    с параллелью — какой задали. Фильтр по параллели — у списков сотрудников."""
    from rest_framework.test import APIClient

    from students.models import Student, StudyGroup
    from students.views import StudentFilter, StudyGroupViewSet

    names = {field.name for field in Student._meta.get_fields()}
    assert not {"grade", "parallel"} & names
    assert "grade" not in StudentFilter.base_filters
    assert "parallel" in StudentFilter.base_filters
    assert "parallel" in StudyGroupViewSet.filterset_fields

    api = APIClient()
    api.force_authenticate(make_user("admin", "no-class-admin@example.kz"))
    assert api.post("/api/groups/", {"code": "OSLO"}, format="json").status_code == 201
    assert StudyGroup.objects.get(code="OSLO").parallel == 11
    assert api.post("/api/groups/", {"code": "LISBON", "parallel": 9}, format="json").status_code == 201
    lisbon = StudyGroup.objects.get(code="LISBON")
    assert lisbon.parallel == 9
    assert api.post("/api/groups/", {"code": "RIGA", "parallel": 7}, format="json").status_code == 400

    made = api.post(
        "/api/students/",
        {"last_name": "Безклассов", "first_name": "Ученик", "group": lisbon.pk, "graduation_year": 2029, "grade": 5},
        format="json",
    )
    assert made.status_code == 201, made.data
    assert made.data["email"] is None
    assert Student.objects.get(last_name="Безклассов").group == lisbon

    listed = api.get("/api/students/", {"parallel": 9})
    assert [row["full_name"] for row in listed.data["results"]] == ["Безклассов Ученик"]


def test_task_template_has_neither_class_nor_cohort():
    from roadmap.models import TaskTemplate

    names = {field.name for field in TaskTemplate._meta.get_fields()}
    assert not {"grade", "graduation_year"} & names
    assert "groups" in names
