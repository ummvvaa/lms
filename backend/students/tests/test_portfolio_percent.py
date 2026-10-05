"""Процент портфолио — одно число, посчитанное один раз (фаза 81).

Обход карточки ученика показал «6700 %» и «2000 %»: сервер отдаёт долю уже
в процентах (`portfolio._card`: `round(value * 100)`), экран ученика печатал её
как есть, а карточка у куратора умножала второй раз. Здесь закреплено, что
в процентах считает сервер, и что оба экрана берут число без своей арифметики.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from students.models import Student

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
SRC = ROOT / "frontend" / "src"


@pytest.fixture
def pupil(db) -> Student:
    return Student.objects.create(
        last_name="Процентов", first_name="Ученик", email="percent81@example.kz", graduation_year=2027
    )


@pytest.mark.django_db
def test_server_sends_percents_not_fractions(pupil):
    from students.portfolio import state

    payload = state(pupil)
    assert 0 <= payload["percent"] <= 100
    for section in payload["sections"]:
        assert 0 <= section["value"] <= 100, f"{section['code']}: доля вместо процентов"
        assert float(section["value"]) == int(section["value"]), "процент — целое число"


@pytest.mark.django_db
def test_section_weights_come_from_school_rules(pupil, set_rules):
    """Веса разделов — правила школы: заполнены только баллы — процент равен весу раздела «Академические»."""
    from decimal import Decimal

    from students.models import ExamProfile
    from students.portfolio import state

    ExamProfile.objects.create(student=pupil, gpa=Decimal("3.5"), ielts_current=Decimal("6.5"), sat_current=1300)
    pupil.refresh_from_db()
    assert state(pupil)["percent"] == 25
    set_rules(
        portfolio_w_profile=10,
        portfolio_w_academics=60,
        portfolio_w_achievements=10,
        portfolio_w_olympiads=5,
        portfolio_w_sport=5,
        portfolio_w_documents=10,
    )
    assert state(pupil)["percent"] == 60


@pytest.mark.django_db
def test_sixty_seven_from_the_server_stays_sixty_seven(pupil):
    """67 с сервера — «67 %» у обеих ролей: экран умножать не должен."""
    for screen in ("screens/MyData.tsx", "screens/curator/Card.tsx"):
        source = (SRC / screen).read_text("utf-8")
        # ищем вывод процента секции портфолио рядом со знаком «%»
        for line in source.splitlines():
            if "section.value" in line and "%" in line:
                assert "* 100" not in line, f"{screen}: процент умножается второй раз — {line.strip()}"


def test_neither_screen_multiplies_a_percent_by_hundred():
    """Страж на будущее: ни один экран не умножает на сто то, что пришло в процентах."""
    offenders = []
    for path in sorted(SRC.rglob("*.tsx")):
        for number, line in enumerate(path.read_text("utf-8").splitlines(), 1):
            if re.search(r"(percent|section\.value)\s*\*\s*100", line):
                offenders.append(f"{path.relative_to(SRC)}:{number}")
    assert not offenders, "процент умножается на сто: " + ", ".join(offenders)
