"""Календарь ученика: СОР и СОЧ — подсвеченные дни, а не события.

Уроки живут в «Расписании» (решение владельца, 28.09.2026): в ленте
событий и в «ближайшем» их нет, день с работой подписан «предмет — вид».
"""

from __future__ import annotations

from academics.models import Lesson
from students import calendar_feed


def test_sor_goes_to_highlighted_days_not_to_events(lesson, pupils, calendar):
    Lesson.objects.filter(pk=lesson.pk).update(kind="sor", number=2, max_score=20)
    aliya = pupils["aliya"]
    state = calendar_feed.state(aliya)

    assert all(event["kind"] != "assessment" for event in state["events"])
    assert state["nearest"] is None or state["nearest"]["kind"] != "assessment"
    days = state["assessment_days"]
    assert [row["date"] for row in days] == [lesson.date.isoformat()]
    # подпись «предмет — вид работы»; «СОР 2» не рвётся посередине
    assert days[0]["title"] == "Алгебра — СОР 2"
    assert days[0]["short"].endswith("— СОР 2")


def test_ordinary_lesson_is_not_in_the_calendar_at_all(lesson, pupils, calendar):
    state = calendar_feed.state(pupils["aliya"])
    assert state["assessment_days"] == []
    assert all(event["kind"] != "assessment" for event in state["events"])
