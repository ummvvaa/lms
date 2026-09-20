"""Класс не существует — только группы.

Школа ведёт только выпускников: у каждого ученика и каждой группы класс один,
и делится поток по группам. Поэтому класс нигде не выбирается, не фильтруется
и не показывается: ни поля в форме, ни фильтра, ни колонки, ни подписи «11 класс».
В реестре он остаётся (`students.models.SCHOOL_GRADE`), но приходит сам.

Страж обходит исходники фронта так же, как страж словарей: любая строка
интерфейса со словом «класс» — падение. Слова «одноклассник» и «классификация»
классом не являются и перечислены явно.
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
def test_the_api_neither_filters_nor_asks_for_the_class(make_user):
    """Сервер: фильтра по классу нет, группа и ученик заводятся без него — встаёт 11."""
    from students.models import SCHOOL_GRADE, Student, StudyGroup
    from students.views import StudentFilter, StudyGroupViewSet

    assert "grade" not in StudentFilter.base_filters
    assert "grade" not in StudyGroupViewSet.filterset_fields

    from rest_framework.test import APIClient

    api = APIClient()
    api.force_authenticate(make_user("admin", "no-class-admin@example.kz"))
    made = api.post("/api/groups/", {"code": "OSLO"}, format="json")
    assert made.status_code == 201, made.data
    assert StudyGroup.objects.get(code="OSLO").grade == SCHOOL_GRADE

    student = api.post(
        "/api/students/",
        {"last_name": "Безклассов", "first_name": "Ученик", "email": "no-class@example.kz", "graduation_year": 2027},
        format="json",
    )
    assert student.status_code == 201, student.data
    assert Student.objects.get(email="no-class@example.kz").grade == SCHOOL_GRADE


def test_task_template_has_neither_class_nor_cohort():
    from roadmap.models import TaskTemplate

    names = {field.name for field in TaskTemplate._meta.get_fields()}
    assert not {"grade", "graduation_year"} & names
    assert "groups" in names
