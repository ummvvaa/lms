"""Комментарии домена дисциплины и талантов ученику не показываются.

«Комментарий куратора» и «Комментарий по талантам» пишут о ученике, а не
для него — как заметки куратора. Поля были описаны в реестре без
`internal_label`, и `/api/students/me/` отдавал их ученику вместе
с карточкой. Инвариант №7: внутреннее ученику не показывается никогда,
даже в сыром JSON.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from students.models import BehaviorProfile, TalentProfile

BEHAVIOR_SECRET = "Опаздывает, мать просила звонить только после шести"
TALENT_SECRET = "Портфолио слабое, на олимпиаду не тянет"


@pytest.fixture
def commented(student):
    BehaviorProfile.objects.filter(student=student).update(comment=BEHAVIOR_SECRET)
    TalentProfile.objects.filter(student=student).update(comment=TALENT_SECRET)
    return student


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_student_never_reads_the_comments(make_user, commented):
    user = make_user("student", commented.email)
    commented.user = user
    commented.save(update_fields=["user"])
    client = _client(user)

    for path in ("/api/students/me/", f"/api/students/{commented.pk}/", "/api/meta/domains/"):
        response = client.get(path)
        assert response.status_code == 200, path
        body = response.content.decode()
        assert BEHAVIOR_SECRET not in body and TALENT_SECRET not in body, path
        assert '"comment"' not in body, path


@pytest.mark.django_db
def test_staff_still_read_the_comments(make_user, commented):
    for role in ("director_behavior", "director_talent", "admin"):
        client = _client(make_user(role, f"{role}-comments@example.kz"))
        body = client.get(f"/api/students/{commented.pk}/").content.decode()
        assert BEHAVIOR_SECRET in body and TALENT_SECRET in body, role
