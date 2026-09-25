"""Подбор и каталог под конкретного ученика — только в границах видимости.

`_student_for` брал ученика по id из `Student.objects`, и куратор через
открытый ему каталог читал проценты соответствия, GPA, IELTS и SAT ученика
чужой группы. Правило проекта одно: чужая куратору группа — 404, как во
всех выборках `core.scope`. Остальные ручки подбора куратору закрывает
шлюз (403), но ученика они теперь тоже берут через область видимости —
третья роль с границей получит то же правило без правок здесь.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.curators import assign
from accounts.tests.test_phase60 import _student
from students.models import StudyGroup

MONTH_AGO = dt.timedelta(days=30)

#: ручки, которые берут ученика через `_student_for`
STAFF_READS = (
    "/api/match/my-universities/",
    "/api/match/open-programs/",
    "/api/match/list-balance/",
    "/api/match/at-goal/",
    "/api/catalog/",
)
#: из них куратору открыт только каталог
CURATOR_READS = ("/api/catalog/",)


@pytest.fixture
def admin(make_user):
    return make_user("admin", "admin-scope@example.kz")


@pytest.fixture
def curator(make_user, admin):
    """Куратор одной группы с одним учеником; рядом — чужая группа с учеником."""
    user = make_user("curator", "curator-scope@example.kz", full_name="Куратор Границы")
    own_group = StudyGroup.objects.create(code="OWN", grade=11)
    own = _student("own-scope@example.kz", own_group, "Свой")
    assign(group=own_group, curator=user, since=timezone.localdate() - MONTH_AGO, actor=admin)
    alien_group = StudyGroup.objects.create(code="ALIEN", grade=11)
    alien = _student("alien-scope@example.kz", alien_group, "Чужой")
    client = APIClient()
    client.force_login(user)
    return client, own, alien


@pytest.mark.django_db
def test_curator_reads_the_catalog_only_for_own_students(curator):
    client, own, alien = curator
    for path in CURATOR_READS:
        assert client.get(f"{path}?student={own.pk}").status_code == 200, path
        assert client.get(f"{path}?student={alien.pk}").status_code == 404, path
    # подбор куратору закрыт шлюзом целиком — и для своего ученика тоже
    for path in set(STAFF_READS) - set(CURATOR_READS):
        assert client.get(f"{path}?student={own.pk}").status_code == 403, path


@pytest.mark.django_db
def test_curator_cannot_pick_for_an_alien_student(curator):
    client, own, alien = curator
    pick = {"student": alien.pk, "text": "информатика в Европе"}
    assert client.post("/api/catalog/pick/", pick, format="json").status_code in (403, 404)
    assert client.post("/api/catalog/pick/", pick, format="json").status_code != 200


@pytest.mark.django_db
def test_director_still_reads_any_student(make_user, curator):
    """Директор видит всю школу: граница — только у куратора и ученика."""
    _, own, alien = curator
    client = APIClient()
    client.force_login(make_user("director_admission", "asem-scope@example.kz"))
    for path in STAFF_READS:
        assert client.get(f"{path}?student={alien.pk}").status_code == 200, path
    deltas = {"ielts_delta": 0.5, "sat_delta": 0, "gpa_delta": 0}
    assert client.post("/api/match/what-if/", {"student": alien.pk, **deltas}, format="json").status_code == 200
