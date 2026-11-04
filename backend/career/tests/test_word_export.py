"""Разборы профтеста в Word (решение владельца, 04.11.2026).

Выгружают только учитель профориентации и администратор; в файл идут все
готовые разборы ученика, версия профориентолога с правками; один ученик на
языке разбора — файл сразу. Журнал помнит, кто, кого и на каком языке
выгрузил, — без текстов разбора.
"""

from __future__ import annotations

import io

import pytest
from docx import Document

from accounts.models import Role
from career import word
from career.models import AnalysisStatus, CareerAnalysis
from career.tests.conftest import FakeProvider, activate, answer_all, login
from core.models import AuditLog

pytestmark = pytest.mark.django_db

PROFILE = [{"scale": "Биология", "meaning": "Самый сильный интерес теста."}]


def _directions(n: int = 2) -> list[dict]:
    return [
        {
            "title": f"Биотехнологии {i}",
            "title_abroad": f"Biotechnology {i}",
            "scales": ["Биология"],
            "reasoning": "Интерес к биологии — самый высокий в тесте, 12 из 12.",
            "professions": "биотехнолог, генетик",
            "exams": "IELTS: сейчас 6.0, порог 6.5 — не хватает 0.5\nSAT: пороги — по программам в каталоге",
            "subjects": "SAT Math — для первого курса\nбиология — профильный предмет",
            "next_steps": ["олимпиада по биологии в 10 классе", "летняя школа", "проект"],
        }
        for i in range(1, n + 1)
    ]


def _pass(student, test):
    client = login(student.user)
    attempt = client.post(f"/api/career/my/tests/{test.pk}/start/").json()["id"]
    answer_all(client, attempt, lambda n: {1: "++", 2: "−−", 17: "+"}.get((n - 1) % 24 + 1, "0"))
    client.post(f"/api/career/my/attempts/{attempt}/finish/")


@pytest.fixture
def analysed(karta, teacher, boston, riga, pupils, fake) -> CareerAnalysis:
    """Готовый разбор Алии на русском."""
    activate(karta, [{"group": boston.pk}, {"group": riga.pk}], by=teacher)
    _pass(pupils["aliya"], karta)
    fake(FakeProvider({"summary": "Сильнее всего — биология.", "profile": PROFILE, "directions": _directions()}))
    response = login(teacher).post(
        "/api/career/analyses/",
        {"group": boston.pk, "tests": [karta.pk], "students": [pupils["aliya"].pk]},
        format="json",
    )
    assert response.status_code == 202, response.content
    row = CareerAnalysis.objects.get(student=pupils["aliya"])
    assert row.status == AnalysisStatus.DONE, row.error
    return row


def _word(client, student, language: str = "ru"):
    return client.get(f"/api/career/students/{student.pk}/word/?language={language}")


def _document(payload: bytes):
    return Document(io.BytesIO(payload))


def test_one_student_in_the_analysis_language_is_downloaded_at_once(analysed, teacher, pupils):
    response = _word(login(teacher), pupils["aliya"])
    assert response.status_code == 200, response.content
    assert response["Content-Type"] == word.DOCX_TYPE
    assert "filename*=UTF-8''%D0%90%D1%85%D0%BC%D0%B5%D1%82%D0%BE%D0%B2%D0%B0_" in response["Content-Disposition"]
    document = _document(response.content)
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    assert "Общий вывод" in headings and "Профиль интересов" in headings and "Направления" in headings
    assert "Общая картина по всем тестам" not in headings, "разбор один — общей картины нет"
    assert "1. Биотехнологии 1" in headings
    text = "\n".join(p.text for p in document.paragraphs)
    assert "Сильнее всего — биология." in text and "Biotechnology 1" in text
    # шапка: герб, ФИО, группа, параллель, кто выгрузил
    head = document.tables[0].rows[0].cells
    assert head[0]._tc.xpath(".//pic:pic"), "в шапке герб школы"
    assert "Ахметова Алия" in head[1].text and "BOSTON" in head[1].text and "11 класс" in head[1].text
    assert "Жанар Профориентатор" in head[1].text
    # профиль: строка на каждую шкалу теста, сильная выделена
    table = document.tables[1]
    assert [cell.text for cell in table.rows[0].cells] == ["Шкала", "Балл", "Диапазон", "Что значит"]
    rows = {row.cells[0].text: row for row in table.rows[1:]}
    assert len(rows) == analysed.scales.count() == 24
    assert rows["Биология"].cells[1].text == "12 из 12"
    assert rows["Биология"].cells[3].text == "Самый сильный интерес теста."
    assert rows["Биология"].cells[0]._tc.xpath(".//w:shd"), "сильная шкала выделена"
    assert not rows["Физика"].cells[0]._tc.xpath(".//w:shd")


def test_teacher_edits_go_into_the_file_as_on_screen(analysed, teacher, pupils):
    client = login(teacher)
    direction = analysed.directions.first()
    client.patch(
        f"/api/career/analyses/{analysed.pk}/",
        {"summary": "Правка профориентолога.", "directions": [{"id": direction.pk, "title": "Генетика"}]},
        format="json",
    )
    text = "\n".join(p.text for p in _document(_word(client, pupils["aliya"]).content).paragraphs)
    assert "Правка профориентолога." in text and "1. Генетика" in text
    assert "Сильнее всего — биология." not in text


def test_only_ready_analyses_go_into_the_file(analysed, teacher, pupils):
    CareerAnalysis.objects.filter(pk=analysed.pk).update(status=AnalysisStatus.FAILED)
    response = _word(login(teacher), pupils["aliya"])
    assert response.status_code == 400 and "нет готового разбора" in response.json()["detail"]


def test_other_language_asks_to_prepare_the_file(analysed, teacher, pupils):
    response = _word(login(teacher), pupils["aliya"], "kk")
    assert response.status_code == 409 and response.json()["prepare"] is True


@pytest.mark.parametrize("who", ["curator", "asem", "kymbat", "other_teacher"])
def test_only_career_teacher_and_admin_export(request, analysed, pupils, who):
    response = _word(login(request.getfixturevalue(who)), pupils["aliya"])
    assert response.status_code == 403


def test_student_cannot_export_even_own_analysis(analysed, pupils):
    assert _word(login(pupils["aliya"].user), pupils["aliya"]).status_code == 403


def test_admin_exports_any_group(analysed, admin, pupils):
    assert _word(login(admin), pupils["aliya"]).status_code == 200


def test_career_teacher_of_another_group_gets_404(analysed, pupils, make_user, career_subject, riga):
    from academics.cohorts import group_cohort
    from academics.models import Course, TeacherProfile

    user = make_user(Role.TEACHER, "riga.career@example.kz", full_name="Только Рига")
    TeacherProfile.objects.create(user=user).subjects.set([career_subject])
    Course.objects.create(subject=career_subject, teacher=user, cohort=group_cohort(riga))
    assert _word(login(user), pupils["aliya"]).status_code == 404


def test_journal_says_who_exported_whom_and_in_what_language(analysed, teacher, pupils):
    _word(login(teacher), pupils["aliya"])
    entry = AuditLog.objects.get(field_name="career_export")
    assert entry.actor == teacher and entry.student_id == pupils["aliya"].pk
    assert "ru" in entry.new_value
    assert "биология" not in entry.new_value.lower(), "текста разбора в журнале нет"


def test_file_name_has_no_characters_that_break_windows():
    class Pupil:
        last_name, first_name = 'Ахметова: "Алия"', "Мария / Анна"

    assert word.file_name(Pupil()) == "Ахметова_Алия_Мария_Анна_профтест.docx"
