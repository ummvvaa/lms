"""Критерии приёмки Фазы 2: права по доменам и скрытие ярлыков."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from core.models import AuditLog


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def kymbat(make_user):
    """Директор экзаменов — домен `exam`."""
    return make_user("director_exam", "kymbat@school.kz", full_name="Кымбат")


@pytest.fixture
def asem(make_user):
    """Директор по поступлению — домен `admission`."""
    return make_user("director_admission", "asem@school.kz", full_name="Асем")


@pytest.fixture
def student_user(make_user, student):
    user = make_user("student", student.email, full_name=student.full_name)
    student.user = user
    student.save(update_fields=["user"])
    return user


# --- Критерий: чужой домен не пишется ----------------------------------


@pytest.mark.django_db
def test_exam_director_cannot_write_admission_field(api, kymbat, student):
    """Директор экзаменов получает 403 на поле домена поступления."""
    api.force_authenticate(kymbat)
    response = api.patch(f"/api/profiles/admission/{student.pk}/", {"status": "A"}, format="json")
    assert response.status_code == 403
    student.admission.refresh_from_db()
    assert student.admission.status == ""


@pytest.mark.django_db
def test_exam_director_can_write_own_domain(api, kymbat, student):
    api.force_authenticate(kymbat)
    response = api.patch(f"/api/profiles/exam/{student.pk}/", {"ielts_current": "6.5"}, format="json")
    assert response.status_code == 200, response.data
    student.exam.refresh_from_db()
    assert str(student.exam.ielts_current) == "6.5"

    log = AuditLog.objects.get(field_name="ielts_current")
    assert log.actor == kymbat
    assert log.domain_code == "exam"
    assert (log.old_value, log.new_value) == ("", "6.5")


@pytest.mark.django_db
def test_admission_director_can_write_status(api, asem, student):
    api.force_authenticate(asem)
    response = api.patch(f"/api/profiles/admission/{student.pk}/", {"status": "A"}, format="json")
    assert response.status_code == 200, response.data
    student.admission.refresh_from_db()
    assert student.admission.status == "A"


@pytest.mark.django_db
def test_director_reads_foreign_domain(api, kymbat, student):
    """Чужие поля видно, но менять нельзя."""
    student.admission.status = "B"
    student.admission.save()
    api.force_authenticate(kymbat)
    response = api.get(f"/api/profiles/admission/{student.pk}/")
    assert response.status_code == 200
    assert response.data["status"] == "B"


# --- Критерий: ученик не видит ярлыков (инвариант №7) ------------------


@pytest.mark.django_db
def test_student_response_has_no_internal_labels(api, student_user, student):
    """В ответе API для ученика нет behavior_status и admission_status."""
    student.behavior.status = "critical"
    student.behavior.save()
    student.admission.status = "C"
    student.admission.save()
    student.talent.portfolio_status = "weak"
    student.talent.save()

    api.force_authenticate(student_user)
    response = api.get("/api/students/me/")
    assert response.status_code == 200

    body = response.data
    assert "status" not in body["behavior"]
    assert "status" not in body["admission"]
    assert "portfolio_status" not in body["talent"]

    raw = str(body)
    for label in ("critical", "needs_supervision", "strong", "medium", "weak"):
        assert label not in raw, f"ярлык {label} утёк ученику"


@pytest.mark.django_db
def test_student_sees_non_label_fields(api, student_user, student):
    """Ярлыки скрыты, но полезные поля остаются."""
    student.exam.ielts_current = "6.5"
    student.exam.save()
    api.force_authenticate(student_user)
    response = api.get("/api/students/me/")
    assert response.data["exam"]["ielts_current"] == "6.5"
    assert response.data["behavior"]["attendance_percent"] is None


@pytest.mark.django_db
def test_student_cannot_see_other_students(api, student_user, student, group):
    from students.models import Student

    other = Student.objects.create(
        last_name="Другой",
        first_name="Ученик",
        email="other@school.kz",
        grade=11,
        group=group,
        graduation_year=2027,
    )
    api.force_authenticate(student_user)
    assert api.get(f"/api/students/{other.pk}/").status_code == 404
    listing = api.get("/api/students/")
    assert [row["id"] for row in listing.data["results"]] == [student.pk]


@pytest.mark.django_db
def test_student_cannot_write_anything(api, student_user, student):
    api.force_authenticate(student_user)
    response = api.patch(f"/api/profiles/exam/{student.pk}/", {"ielts_current": "9.0"}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_anonymous_gets_401(api, student):
    assert api.get("/api/students/").status_code in (401, 403)


# --- Метаданные доменов -------------------------------------------------


@pytest.mark.django_db
def test_domain_meta_marks_own_domain(api, kymbat):
    api.force_authenticate(kymbat)
    body = api.get("/api/meta/domains/").data
    assert body["my_domain"] == "exam"
    mine = [d for d in body["domains"] if d["is_mine"]]
    assert [d["code"] for d in mine] == ["exam"]
    assert {d["owner_name"] for d in body["domains"]} == {"Салтанат", "Асем", "Кымбат", "Арман", "Нурлыбек"}


@pytest.mark.django_db
def test_domain_meta_hides_labels_from_student(api, student_user):
    api.force_authenticate(student_user)
    body = api.get("/api/meta/domains/").data
    all_fields = [f["name"] for d in body["domains"] for m in d["models"] for f in m["fields"]]
    assert "portfolio_status" not in all_fields
    assert body["my_domain"] is None
