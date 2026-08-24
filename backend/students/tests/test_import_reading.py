"""Фаза 29: разбор загружаемого файла и объяснение обычными словами.

Проверяем не формулировки, а то, из-за чего загрузка портит данные:
колонка чужого домена должна быть названа чужой, значение вне шкалы —
найдено с настоящим номером строки, а выбор человека — сильнее выбора
модели. Без ключа тот же экран обязан работать и говорить, что режим
упрощённый.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from accounts.models import Role
from students.import_reading import STUDENT_KEY, read, rules_mapping
from students.models import ExamProfile, Student, StudyGroup

LIVE_LLM = {
    "PROVIDER": "anthropic",
    "API_KEY": "test-key",
    "BASE_URL": "https://api.example",
    "MODEL": "claude-sonnet-5",
    "TIMEOUT": 5,
    "RETRIES": 0,
    "RETRY_DELAY": 0,
    "NO_RETENTION": True,
    "SEARCH": False,
    "SEARCH_MAX_USES": 0,
}

HEADER = ["Почта", "IELTS текущий", "Специальность", "Примечание"]
ROWS = [
    ["one@school.kz", "7.0", "Computer Science", "хорошо идёт"],
    ["two@school.kz", "12.5", "Экономика", ""],
    ["three@school.kz", "6.5", "Право", "переведён"],
]


class _Reply:
    def __init__(self, text: str = "", parsed=None) -> None:
        content = []
        if text:
            content.append({"type": "text", "text": text})
        if parsed is not None:
            content.append({"type": "tool_use", "name": "result", "input": parsed})
        self.payload = {
            "id": "msg_1",
            "model": "claude-sonnet-5",
            "content": content,
            "usage": {"input_tokens": 200, "output_tokens": 60},
        }
        self.status_code = 200

    def json(self) -> dict:
        return self.payload


@pytest.fixture
def model(monkeypatch):
    """Подменить провайдера: текст на объяснение, структуру на сопоставление."""
    box: dict = {"sent": []}

    def install(*, text: str = "", parsed=None):
        def fake_post(url, json=None, headers=None, timeout=None):
            box["sent"].append(json)
            # запрос со схемой — это сопоставление колонок, без неё — объяснение
            return _Reply(parsed=parsed) if json.get("tools") else _Reply(text=text)

        import requests

        monkeypatch.setattr(requests, "post", fake_post)
        return box

    return install


@pytest.fixture
def people(db):
    group = StudyGroup.objects.create(code="11R", grade=11)
    for name, email in (("Один", "one@school.kz"), ("Два", "two@school.kz")):
        student = Student.objects.create(
            last_name="Читаев", first_name=name, email=email, grade=11, group=group, graduation_year=2027
        )
        ExamProfile.objects.create(student=student)
    return group


# --- Сопоставление правилами ----------------------------------------------


@pytest.mark.django_db
def test_rules_find_the_student_key_and_own_field():
    columns = {c.title: c for c in rules_mapping(HEADER, Role.DIRECTOR_EXAM)}

    assert columns["Почта"].target == STUDENT_KEY
    assert columns["IELTS текущий"].target == "students.ExamProfile.ielts_current"


@pytest.mark.django_db
def test_foreign_domain_column_is_named_as_foreign():
    """«Специальность» ведёт другой директор — это надо сказать словами."""
    columns = {c.title: c for c in rules_mapping(HEADER, Role.DIRECTOR_EXAM)}
    column = columns["Специальность"]

    assert column.target == ""
    assert column.skip_reason == "foreign_domain"
    assert column.foreign_domain == "Поступление"


@pytest.mark.django_db
def test_unknown_column_is_not_guessed():
    columns = {c.title: c for c in rules_mapping(HEADER, Role.DIRECTOR_EXAM)}

    assert columns["Примечание"].skip_reason == "unknown"
    assert columns["Примечание"].target == ""


# --- Проверки значений -----------------------------------------------------


@pytest.mark.django_db
def test_value_out_of_range_is_found_with_the_real_row_number(people):
    """IELTS 12.5 во второй строке файла — это строка 3 вместе с заголовком."""
    reading = read(header=HEADER, rows=ROWS, role=Role.DIRECTOR_EXAM)

    out_of_range = [w for w in reading.warnings if w["kind"] == "out_of_range"]
    assert out_of_range, reading.warnings
    warning = out_of_range[0]
    assert warning["rows"] == [3]
    assert "9" in warning["text"]
    assert "строке 3" in warning["text"]


@pytest.mark.django_db
def test_duplicate_student_rows_are_found(people):
    rows = [*ROWS, ["one@school.kz", "7.5", "", ""]]
    reading = read(header=HEADER, rows=rows, role=Role.DIRECTOR_EXAM)

    duplicates = [w for w in reading.warnings if w["kind"] == "duplicates"]
    assert duplicates and duplicates[0]["rows"] == [5]


@pytest.mark.django_db
def test_mixed_date_formats_in_one_column_are_called_out(people):
    header = ["Почта", "Дата следующего пробного экзамена"]
    rows = [["one@school.kz", "2027-01-15"], ["two@school.kz", "15.01.2027"]]

    reading = read(header=header, rows=rows, role=Role.DIRECTOR_EXAM)

    mixed = [w for w in reading.warnings if w["kind"] == "mixed_dates"]
    assert mixed, reading.warnings
    assert "форматы дат" in mixed[0]["text"]


@pytest.mark.django_db
def test_rows_are_counted_and_missing_students_named(people):
    reading = read(header=HEADER, rows=ROWS, role=Role.DIRECTOR_EXAM)

    assert reading.total_rows == 3
    assert reading.matched == 2
    assert reading.unmatched == ["three@school.kz"]


# --- Объяснение ------------------------------------------------------------


@pytest.mark.django_db
def test_without_a_key_the_screen_still_works_and_says_it_is_simple(people):
    reading = read(header=HEADER, rows=ROWS, role=Role.DIRECTOR_EXAM)
    payload = reading.as_dict()

    assert payload["offline"] is True
    assert "упрощённ" in payload["note"].lower()
    # сухой текст всё равно называет обе проблемы
    assert "Специальность" in payload["text"]
    assert "строке 3" in payload["text"]


@pytest.mark.django_db
@override_settings(LLM=LIVE_LLM)
def test_with_a_key_the_model_writes_the_explanation(people, model):
    box = model(text="В файле 3 строки. Загружу текущий IELTS, «Специальность» пропущу.")

    reading = read(header=HEADER, rows=ROWS, role=Role.DIRECTOR_EXAM)
    payload = reading.as_dict()

    assert payload["offline"] is False
    assert "В файле 3 строки" in payload["text"]
    # в модель ушли только заголовки, факты и три строки-образца
    sent = str(box["sent"])
    assert "Читаев" not in sent, "имя ученика ушло в модель"
    assert "ученик 1" in sent


@pytest.mark.django_db
@override_settings(LLM=LIVE_LLM)
def test_model_may_suggest_a_column_but_only_from_its_own_domain(people, model):
    """Предложение модели — предложение: чужое поле она подставить не может."""
    model(
        parsed={
            "columns": [
                {"title": "Примечание", "target": "students.ExamProfile.notes"},
                {"title": "Специальность", "target": "students.AdmissionProfile.target_major"},
            ]
        }
    )

    reading = read(header=HEADER, rows=ROWS, role=Role.DIRECTOR_EXAM)
    columns = {c.title: c for c in reading.columns}

    # чужое поле осталось пропущенным, как бы модель его ни называла
    assert columns["Специальность"].target == ""
    assert columns["Специальность"].skip_reason == "foreign_domain"


@pytest.mark.django_db
def test_manual_mapping_wins_over_the_model(people):
    """Директор переназначил колонку — грузим то, что выбрал он."""
    reading = read(
        header=HEADER,
        rows=ROWS,
        role=Role.DIRECTOR_EXAM,
        mapping={"Почта": STUDENT_KEY, "Примечание": "students.ExamProfile.ielts_target"},
    )
    columns = {c.title: c for c in reading.columns}

    assert columns["Примечание"].target == "students.ExamProfile.ielts_target"
    assert columns["IELTS текущий"].skip_reason == "unknown"
    assert reading.mapping["Примечание"] == "students.ExamProfile.ielts_target"


@pytest.mark.django_db
def test_preview_endpoint_returns_the_reading(client, make_user, people):
    """Экран получает разбор первым же запросом, ещё до сопоставления."""
    import io

    class FakeUpload(io.BytesIO):
        name = "ballы.csv"

    director = make_user(Role.DIRECTOR_EXAM, email="kymbat.reading@example.kz")
    client.force_login(director)
    body = "Почта,IELTS текущий,Специальность\none@school.kz,7.0,CS\ntwo@school.kz,12.5,Экономика\n"

    response = client.post("/api/import/preview/", {"file": FakeUpload(body.encode())})

    assert response.status_code == 200
    reading = response.json()["reading"]
    assert reading["total_rows"] == 2
    assert reading["text"]
    titles = {column["title"]: column for column in reading["columns"]}
    assert titles["Специальность"]["skip_reason"] == "foreign_domain"
    assert any(w["kind"] == "out_of_range" for w in reading["warnings"])
