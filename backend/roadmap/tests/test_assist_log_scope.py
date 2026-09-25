"""Переписка с помощником по эссе видна только в границах видимости.

`essay_assist_log` отбивала лишь чужого ученика; сотрудник с границей
видимости читал переписку по любому эссе школы. Куратору маршрут закрыт
шлюзом, поэтому правило проверяется вызовом вьюхи напрямую.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from accounts.curators import assign
from accounts.tests.test_phase60 import _student
from roadmap import views
from roadmap.models import Essay
from students.models import StudyGroup

MONTH_AGO = dt.timedelta(days=30)


def _log(user, essay_id: int):
    request = APIRequestFactory().get(f"/api/essays/{essay_id}/assist-log/")
    force_authenticate(request, user=user)
    return views.essay_assist_log(request, pk=essay_id)


@pytest.mark.django_db
def test_assist_log_respects_the_curator_boundary(make_user):
    admin = make_user("admin", "admin-log@example.kz")
    curator = make_user("curator", "curator-log@example.kz", full_name="Куратор Границы")
    own_group = StudyGroup.objects.create(code="OWN", grade=11)
    own = _student("own-log@example.kz", own_group, "Свой")
    assign(group=own_group, curator=curator, since=timezone.localdate() - MONTH_AGO, actor=admin)
    alien = _student("alien-log@example.kz", StudyGroup.objects.create(code="ALIEN", grade=11), "Чужой")
    own_essay = Essay.objects.create(student=own, title="Своё эссе")
    alien_essay = Essay.objects.create(student=alien, title="Чужое эссе")

    assert _log(curator, own_essay.pk).status_code == 200
    assert _log(curator, alien_essay.pk).status_code == 404
    assert _log(make_user("director_admission", "asem-log@example.kz"), alien_essay.pk).status_code == 200

    # через шлюз куратору маршрут закрыт целиком
    client = APIClient()
    client.force_login(curator)
    assert client.get(f"/api/essays/{own_essay.pk}/assist-log/").status_code == 403
