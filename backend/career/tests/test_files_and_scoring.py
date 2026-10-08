"""Файл теста и ключ: разбор книги, подсчёт баллов, границы полосок."""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from career import files
from career.models import CareerTest
from career.scoring import bounds, label_for

pytestmark = pytest.mark.django_db


def test_example_file_parses_whole(example_bytes):
    parsed = files.parse(example_bytes)
    assert parsed.ok, parsed.errors
    assert parsed.title.startswith("Карта интересов")
    assert len(parsed.items) == 144 and len(parsed.scales) == 24 and len(parsed.options) == 5
    assert len(parsed.ranges) == 6 and parsed.threshold == 1
    # ключ по столбцам бланка: 1, 25, 49 … — биология; 24, 48 … — экология
    by_number = {item.number: item.scale for item in parsed.items}
    assert by_number[1] == by_number[25] == by_number[121] == "bio"
    assert by_number[24] == by_number[144] == "eco"
    assert not parsed.warnings


def test_template_parses_too():
    parsed = files.parse(files.template())
    assert parsed.ok, parsed.errors
    assert len(parsed.items) == 2


def _book(**sheets) -> bytes:
    book = Workbook()
    first = True
    for name, rows in sheets.items():
        sheet = book.active if first else book.create_sheet()
        sheet.title = name
        first = False
        for row in rows:
            sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_errors_name_sheet_and_row():
    data = _book(
        **{
            "Тест": [["Название", "Проба"], ["Порог для разбора", "много"]],
            "Ответы": [["Подпись", "Баллы"], ["да", 1], ["нет", "x"]],
            "Шкалы": [["Код", "Название"], ["a", "Альфа"], ["a", "Дубль"]],
            "Вопросы": [
                ["Номер", "Текст", "Шкала"],
                [1, "Первый", "a"],
                [1, "Повтор", "a"],
                [3, "Чужая", "zzz"],
                ["", "Без номера", "a"],
            ],
            "Интерпретация": [["Шкала", "От", "До", "Подпись"], ["", 5, 1, "наоборот"]],
        }
    )
    parsed = files.parse(data)
    assert not parsed.ok
    text = "\n".join(parsed.errors)
    assert "целое число" in text and "лист «Ответы», строка 3" in text
    assert "код шкалы «a» повторяется" in text
    assert "номер 1 повторяется" in text
    assert "шкалы «zzz» нет" in text
    assert "«От» больше «До»" in text
    assert "ни одного вопроса" not in text


def test_not_a_workbook_is_one_error():
    parsed = files.parse(b"not a workbook")
    assert parsed.errors == ["Файл не читается как книга xlsx"]


def test_missing_sheets_are_named():
    parsed = files.parse(_book(**{"Тест": [["Название", "Проба"]]}))
    assert parsed.errors == ["Нет листов: «Шкалы», «Вопросы»"]


def test_choice_questions_carry_their_own_scales():
    data = _book(
        **{
            "Тест": [["Название", "Пары"]],
            "Шкалы": [["Код", "Название"], ["p", "Люди"], ["t", "Техника"]],
            "Вопросы": [
                [
                    "Номер",
                    "Текст",
                    "Шкала",
                    "Знак",
                    "Вариант 1",
                    "Шкала 1",
                    "Баллы 1",
                    "Вариант 2",
                    "Шкала 2",
                    "Баллы 2",
                ],
                [1, "Что ближе", "", "", "ухаживать за животными", "p", "", "чинить приборы", "t", 1],
                [2, "Без вариантов и без ответов", "p", "", "", "", "", "", "", ""],
            ],
        }
    )
    parsed = files.parse(data)
    assert "нужны хотя бы два варианта ответа" in "\n".join(parsed.errors)
    data = _book(
        **{
            "Тест": [["Название", "Пары"]],
            "Шкалы": [["Код", "Название"], ["p", "Люди"], ["t", "Техника"]],
            "Вопросы": [
                ["Номер", "Текст", "Вариант 1", "Шкала 1", "Вариант 2", "Шкала 2"],
                [1, "Что ближе", "ухаживать за животными", "p", "чинить приборы", "t"],
            ],
        }
    )
    parsed = files.parse(data)
    assert parsed.ok, parsed.errors
    assert [c.scale for c in parsed.items[0].choices] == ["p", "t"] and parsed.items[0].choices[0].value == 1


def test_scores_follow_the_key_and_ranges(karta, pupils):
    """Все «++» по биологии и все «−−» по физике дают 12 и −12 с подписями."""
    from career.models import CareerAttempt, CareerAttemptAnswer
    from career.scoring import finish

    attempt = CareerAttempt.objects.create(test=karta, student=pupils["aliya"])
    options = {o.label: o for o in karta.options.all()}
    for item in karta.items.select_related("scale"):
        label = {"bio": "++", "phys": "−−", "chem": "+"}.get(item.scale.code, "0")
        CareerAttemptAnswer.objects.create(attempt=attempt, item=item, option=options[label])
    finish(attempt)
    attempt.refresh_from_db()
    rows = {row.scale.code: row for row in attempt.scores.select_related("scale")}
    assert rows["bio"].score == 12 and rows["bio"].label == "ярко выраженный интерес"
    assert rows["phys"].score == -12 and rows["phys"].label == "активно отрицается"
    assert rows["chem"].score == 6 and rows["chem"].label == "выраженный интерес"
    assert rows["math"].score == 0 and rows["math"].label == "не определён"
    assert attempt.is_done and attempt.finished_at is not None
    limits = bounds(CareerTest.objects.get(pk=karta.pk))
    assert set(limits.values()) == {(-12, 12)}


def test_label_prefers_the_scale_own_range():
    class R:
        def __init__(self, scale_id, low, high, label):
            self.scale_id, self.low, self.high, self.label = scale_id, low, high, label

    ranges = [R(None, 0, 10, "общий"), R(7, 0, 10, "свой")]
    assert label_for(ranges, 7, 5) == "свой"
    assert label_for(ranges, 8, 5) == "общий"
    assert label_for(ranges, 8, 50) == ""
