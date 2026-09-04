"""Фаза 53: права справочника правил обзвона и страж унаследованных прав.

Дефект D27: `CallRuleViewSet` наследовался от `HomeCueViewSet` и вместе
с ним получал аудиторию соседнего справочника. Карусель написана для
ученика, правила обзвона — нет: по ним директор школы решает, кому
звонить, и ученику нельзя видеть ни фразы, которыми школа описывает
его самого, ни пороги срабатывания (инвариант №7).

Здесь же страж, чтобы это не повторилось: маршрутизируемая вьюха не
наследуется от другой маршрутизируемой. Общий предок у двух живых
эндпойнтов молча раздаёт права и аудиторию — ровно так D27 и спрятался.
"""

from __future__ import annotations

import pytest
from django.urls import get_resolver
from rest_framework.test import APIClient
from rest_framework.viewsets import ViewSetMixin

from engagement.models import CallCondition, CallRule, CueCondition, CueTone, HomeCue

#: роли, которые не владеют доменом «Профиль и дисциплина»
STRANGERS = (
    "student",
    "director_admission",
    "director_exam",
    "director_talent",
    "director_sport",
    "admin",
)


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def saltanat(make_user):
    return make_user("director_behavior", "saltanat53@example.kz")


@pytest.fixture
def rule(db) -> CallRule:
    return CallRule.objects.create(
        code="phase53",
        condition=CallCondition.INACTIVE,
        reason="просел по пробным экзаменам",
        urgency="today",
        threshold=21,
    )


# --- D27: правила обзвона закрыты всем, кроме владельца домена --------------


@pytest.mark.parametrize("role", STRANGERS)
def test_call_rules_are_closed_to_everyone_but_the_owner(api, make_user, rule, role):
    """Ученику и соседним доменам — отказ, а не пустой список.

    Пустой список читается как «правил нет» и врёт о состоянии системы.
    """
    api.force_authenticate(make_user(role, f"{role}53@example.kz"))

    assert api.get("/api/call-rules/").status_code == 403
    assert api.get(f"/api/call-rules/{rule.pk}/").status_code == 403
    assert api.post("/api/call-rules/", {"code": "x", "reason": "y"}, format="json").status_code == 403
    assert api.patch(f"/api/call-rules/{rule.pk}/", {"threshold": 1}, format="json").status_code == 403
    assert api.delete(f"/api/call-rules/{rule.pk}/").status_code == 403


def test_call_rule_wording_never_reaches_a_stranger(api, make_user, rule):
    """Формулировки правила нет ни в списке, ни в карточке — ни у кого чужого."""
    for role in STRANGERS:
        api.force_authenticate(make_user(role, f"body-{role}53@example.kz"))
        for path in ("/api/call-rules/", f"/api/call-rules/{rule.pk}/"):
            body = api.get(path).content.decode()
            assert rule.reason not in body, f"{role} видит формулировку правила в {path}"
            assert str(rule.threshold) not in body, f"{role} видит порог правила в {path}"


def test_owner_still_reads_and_writes_the_directory(api, saltanat, rule):
    """У Салтанат ничего не изменилось: справочник её, и он открыт."""
    api.force_authenticate(saltanat)

    listing = api.get("/api/call-rules/")
    assert listing.status_code == 200
    assert any(row["code"] == "phase53" for row in listing.json()["results"])

    card = api.get(f"/api/call-rules/{rule.pk}/")
    assert card.status_code == 200
    assert card.json()["reason"] == rule.reason

    created = api.post(
        "/api/call-rules/",
        {"code": "phase53-new", "condition": CallCondition.ABSENCES, "reason": "пропуски", "urgency": "now"},
        format="json",
    )
    assert created.status_code == 201
    assert api.patch(f"/api/call-rules/{rule.pk}/", {"threshold": 14}, format="json").status_code == 200
    assert api.delete(f"/api/call-rules/{created.json()['id']}/").status_code in (200, 204)


def test_home_cues_stay_open_to_the_student(api, make_user, db):
    """Аудитория карусели не изменилась: сюжеты ученик по-прежнему читает.

    Правка D27 касается правил обзвона, а не соседнего справочника.
    """
    HomeCue.objects.create(
        code="phase53-cue",
        condition=CueCondition.NO_UNIVERSITIES,
        title="Добавьте вуз",
        description="Список пуст",
        action_label="Открыть каталог",
        action_path="/catalog",
        tone=CueTone.BRAND,
    )
    api.force_authenticate(make_user("student", "cue-student53@example.kz"))
    listing = api.get("/api/home-cues/")
    assert listing.status_code == 200
    assert any(row["code"] == "phase53-cue" for row in listing.json()["results"])


# --- Страж: маршрутизируемая вьюха не наследует права у соседней ------------


def _routed_viewsets() -> dict[type, list[str]]:
    """Классы вьюх, за которыми стоит живой маршрут, и сами маршруты."""
    found: dict[type, list[str]] = {}

    def walk(patterns, prefix: str) -> None:
        for entry in patterns:
            nested = getattr(entry, "url_patterns", None)
            if nested is not None:
                walk(nested, prefix + str(entry.pattern))
                continue
            cls = getattr(getattr(entry, "callback", None), "cls", None)
            if isinstance(cls, type) and issubclass(cls, ViewSetMixin):
                found.setdefault(cls, []).append(prefix + str(entry.pattern))

    walk(get_resolver().url_patterns, "")
    return found


def test_no_routed_viewset_inherits_from_another_routed_viewset():
    """Общий предок у двух живых эндпойнтов — источник дефектов вроде D27.

    Общая часть выносится в базовый класс без маршрута, а права и аудиторию
    каждый эндпойнт объявляет сам. Наследоваться у соседа нельзя: так права
    расходятся с реестром молча, и в интерфейсе это выглядит исправным.
    """
    routed = _routed_viewsets()
    guilty = [
        f"{cls.__module__}.{cls.__name__} наследует {parent.__name__} (маршрут {routed[parent][0]})"
        for cls in routed
        for parent in cls.__mro__[1:]
        if parent in routed
    ]
    assert guilty == [], "наследование прав у соседнего эндпойнта: " + "; ".join(guilty)
