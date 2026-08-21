"""Движок соответствия: проходит / не хватает, и на сколько."""

from __future__ import annotations

import io

import pytest
from rest_framework.test import APIClient

from universities.matching import match, match_student_list, open_programs, what_if
from universities.models import (
    AdmissionRequirement,
    Program,
    StudentUniversity,
    University,
)


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def asem(make_user):
    return make_user("director_admission", "asem@school.kz", full_name="Асем")


@pytest.fixture
def programs(db):
    """Три программы с разными порогами."""
    made = {}
    for name, country, ielts, sat, gpa in [
        ("Computer Science", "Канада", "6.5", 1300, "3.30"),
        ("Economics", "США", "7.0", 1400, "3.50"),
        ("Graphic Design", "Нидерланды", "6.0", None, None),
    ]:
        university = University.objects.create(name=f"Университет {name}", country=country, domain=f"{name[:3]}.edu")
        program = Program.objects.create(university=university, name=name)
        AdmissionRequirement.objects.create(
            program=program, min_ielts=ielts, min_sat=sat, min_gpa=gpa, source_url="https://example.edu/admission"
        )
        made[name] = program
    # программа без заведённых требований
    bare_university = University.objects.create(name="Университет без требований", country="Турция")
    made["bare"] = Program.objects.create(university=bare_university, name="Architecture")
    return made


def fresh(program: Program) -> Program:
    """Перечитать программу: `program.requirement` кэшируется после первого доступа."""
    return Program.objects.select_related("university", "requirement").get(pk=program.pk)


@pytest.fixture
def ielts_six(student):
    """Ученик с IELTS 6.0 — из критерия приёмки."""
    student.exam.ielts_current = "6.0"
    student.exam.sat_current = 1240
    student.exam.gpa = "3.40"
    student.exam.save()
    return student


# --- Критерий приёмки: IELTS 6.0 — что открыто, что закрыто и на сколько ---


@pytest.mark.django_db
def test_open_and_closed_programs_for_ielts_six(ielts_six, programs):
    results = {m.program_name: m for m in open_programs(ielts_six)}

    design = results["Graphic Design"]
    assert design.is_open, design.summary()

    cs = results["Computer Science"]
    assert not cs.is_open
    assert cs.summary() == "Не хватает 0.5 IELTS и 60 SAT"

    economics = results["Economics"]
    assert not economics.is_open
    gaps = {c.code: c.gap for c in economics.unmet}
    assert gaps["ielts"] == 1.0
    assert gaps["sat"] == 160
    assert gaps["gpa"] == pytest.approx(0.1)


@pytest.mark.django_db
def test_summary_phrase_matches_the_brief(ielts_six, programs):
    """Формулировка ровно та, что в задании: «не хватает 0.5 IELTS и 60 SAT»."""
    result = match(ielts_six, programs["Computer Science"])
    assert result.summary() == "Не хватает 0.5 IELTS и 60 SAT"


@pytest.mark.django_db
def test_gap_rounds_up_to_the_exam_step(student, programs):
    """IELTS ходит по 0.5, SAT — по 10: разрыв округляется вверх до шага."""
    student.exam.ielts_current = "6.4"
    student.exam.sat_current = 1295
    student.exam.gpa = "4.0"
    student.exam.save()
    result = match(student, programs["Computer Science"])
    gaps = {c.code: c.gap for c in result.unmet}
    assert gaps["ielts"] == 0.5  # 0.1 округляется вверх до полшага
    assert gaps["sat"] == 10  # 5 округляется вверх до десятка


@pytest.mark.django_db
def test_missing_requirements_say_so_instead_of_guessing(ielts_six, programs):
    """Требований нет — так и говорим, а не выдумываем вердикт."""
    result = match(ielts_six, programs["bare"])
    assert result.status == "unknown"
    assert not result.is_open
    assert "не заведены" in result.summary()


@pytest.mark.django_db
def test_no_data_is_not_the_same_as_failing(student, programs):
    """У ученика нет баллов — это «нет данных», а не «не проходит»."""
    result = match(student, programs["Computer Science"])
    ielts = next(c for c in result.criteria if c.code == "ielts")
    assert ielts.is_unknown
    assert "нет данных" in ielts.phrase()


@pytest.mark.django_db
def test_official_attempt_beats_profile_value(student, programs):
    """Официальная сдача из истории попыток точнее поля профиля."""
    from students.models import ExamAttempt

    student.exam.ielts_current = "5.5"
    student.exam.gpa = "4.0"
    student.exam.sat_current = 1600
    student.exam.save()
    ExamAttempt.objects.create(
        student=student, exam_type="IELTS", attempt_format="official", date="2026-06-01", total_score="7.0"
    )
    result = match(student, programs["Computer Science"])
    ielts = next(c for c in result.criteria if c.code == "ielts")
    assert ielts.current == 7.0
    assert ielts.is_met


# --- Что откроется, если поднять баллы ---


@pytest.mark.django_db
def test_what_if_shows_newly_unlocked_programs(ielts_six, programs):
    """Поднимаем IELTS на 0.5 и SAT на 60 — открывается Computer Science."""
    result = what_if(ielts_six, ielts_delta=0.5, sat_delta=60)
    assert result["open_after"] > result["open_before"]
    assert "Computer Science" in [row["program_name"] for row in result["unlocked"]]


@pytest.mark.django_db
def test_what_if_does_not_save_anything(ielts_six, programs):
    what_if(ielts_six, ielts_delta=2.0, sat_delta=300)
    ielts_six.exam.refresh_from_db()
    assert str(ielts_six.exam.ielts_current) == "6.0"
    assert ielts_six.exam.sat_current == 1240


# --- Список вузов ученика и API ---


@pytest.mark.django_db
def test_student_sees_gaps_without_labels(api, make_user, ielts_six, programs):
    """Экран «Мои вузы»: конкретный разрыв, никаких внутренних ярлыков."""
    StudentUniversity.objects.create(student=ielts_six, program=programs["Computer Science"], tier="reach")
    StudentUniversity.objects.create(student=ielts_six, program=programs["Graphic Design"], tier="safety")

    user = make_user("student", ielts_six.email)
    ielts_six.user = user
    ielts_six.save(update_fields=["user"])
    api.force_authenticate(user)

    body = api.get("/api/match/my-universities/").data
    assert len(body) == 2
    summaries = {row["program_name"]: row["summary"] for row in body}
    assert "не хватает" in summaries["Computer Science"].lower()
    assert "проходите" in summaries["Graphic Design"].lower()

    raw = str(body)
    for label in ("reach", "critical", "weak", "strong"):
        assert label not in raw, f"ярлык {label} утёк ученику"


@pytest.mark.django_db
def test_match_student_list_uses_own_universities(ielts_six, programs):
    StudentUniversity.objects.create(student=ielts_six, program=programs["Economics"], tier="reach")
    results = match_student_list(ielts_six)
    assert [m.program_name for m in results] == ["Economics"]


# --- Импорт требований ---


def xlsx_like_csv(text: str, name: str = "requirements.csv"):
    buffer = io.BytesIO(text.encode("utf-8"))
    buffer.name = name
    return buffer


@pytest.mark.django_db
def test_import_requirements_from_file(api, asem):
    api.force_authenticate(asem)
    mapping = (
        '{"Вуз":"university","Программа":"program","IELTS":"min_ielts",'
        '"SAT":"min_sat","GPA":"min_gpa","Портфолио":"portfolio_required"}'
    )
    response = api.post(
        "/api/requirements/import/",
        {
            "file": xlsx_like_csv(
                "Вуз,Программа,IELTS,SAT,GPA,Портфолио\n"
                "University of Toronto,Computer Science,6.5,1300,3.3,нет\n"
                "TU Delft,Architecture,6.0,,,да\n"
            ),
            "mapping": mapping,
        },
        format="multipart",
    )
    assert response.status_code == 200, response.data
    assert response.data["created"] == 2
    assert response.data["errors"] == []

    requirement = AdmissionRequirement.objects.get(program__name="Computer Science")
    assert str(requirement.min_ielts) == "6.5"
    assert requirement.min_sat == 1300
    assert requirement.checked_at is not None

    delft = AdmissionRequirement.objects.get(program__name="Architecture")
    assert delft.portfolio_required is True
    assert delft.min_sat is None  # пустой порог — «требования нет», а не ноль


@pytest.mark.django_db
def test_import_requirements_is_idempotent(api, asem):
    api.force_authenticate(asem)
    payload = lambda: {  # noqa: E731
        "file": xlsx_like_csv("Вуз,Программа,IELTS\nUniversity of Toronto,Computer Science,6.5\n"),
        "mapping": '{"Вуз":"university","Программа":"program","IELTS":"min_ielts"}',
    }
    api.post("/api/requirements/import/", payload(), format="multipart")
    second = api.post("/api/requirements/import/", payload(), format="multipart")
    assert second.data["created"] == 0
    assert second.data["unchanged"] == 1
    assert AdmissionRequirement.objects.count() == 1


@pytest.mark.django_db
def test_only_admission_director_imports_requirements(api, make_user):
    api.force_authenticate(make_user("director_exam", "kymbat@school.kz"))
    response = api.post(
        "/api/requirements/import/",
        {"file": xlsx_like_csv("Вуз,Программа\nX,Y\n")},
        format="multipart",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_exam_director_cannot_edit_requirements(api, make_user, programs):
    """Требования — домен поступления (инвариант №1)."""
    requirement = AdmissionRequirement.objects.get(program=programs["Computer Science"])
    api.force_authenticate(make_user("director_exam", "kymbat2@school.kz"))
    response = api.patch(f"/api/requirements/{requirement.pk}/", {"min_ielts": "5.0"}, format="json")
    assert response.status_code == 403
    requirement.refresh_from_db()
    assert str(requirement.min_ielts) == "6.5"


# --- Альтернативные экзамены ---


@pytest.mark.django_db
def test_ielts_and_toefl_are_alternatives(student, programs):
    """Сдан IELTS — TOEFL не требуется, и наоборот."""
    requirement = AdmissionRequirement.objects.get(program=programs["Computer Science"])
    requirement.min_toefl = 89
    requirement.save()

    student.exam.ielts_current = "7.0"
    student.exam.sat_current = 1400
    student.exam.gpa = "3.5"
    student.exam.save()

    result = match(student, fresh(programs["Computer Science"]))
    assert result.is_open, result.summary()
    assert "TOEFL" not in result.summary()


@pytest.mark.django_db
def test_toefl_alone_also_satisfies_english(student, programs):
    from students.models import ExamAttempt

    requirement = AdmissionRequirement.objects.get(program=programs["Computer Science"])
    requirement.min_toefl = 89
    requirement.save()

    ExamAttempt.objects.create(
        student=student, exam_type="TOEFL", attempt_format="official", date="2026-06-01", total_score=100
    )
    student.exam.sat_current = 1400
    student.exam.gpa = "3.5"
    student.exam.save()

    result = match(student, fresh(programs["Computer Science"]))
    assert result.is_open, result.summary()


@pytest.mark.django_db
def test_only_the_taken_exam_is_reported_as_gap(student, programs):
    """Ученик сдавал IELTS: недобор показываем по нему, а не по TOEFL."""
    requirement = AdmissionRequirement.objects.get(program=programs["Computer Science"])
    requirement.min_toefl = 89
    requirement.save()

    student.exam.ielts_current = "6.0"
    student.exam.sat_current = 1400
    student.exam.gpa = "3.5"
    student.exam.save()

    result = match(student, fresh(programs["Computer Science"]))
    assert result.summary() == "Не хватает 0.5 IELTS"


@pytest.mark.django_db
def test_no_english_data_at_all_is_reported_once(student, programs):
    requirement = AdmissionRequirement.objects.get(program=programs["Computer Science"])
    requirement.min_toefl = 89
    requirement.save()

    student.exam.sat_current = 1400
    student.exam.gpa = "3.5"
    student.exam.save()

    result = match(student, fresh(programs["Computer Science"]))
    english = [c for c in result.unmet if c.group == "english"]
    assert len(english) == 1, "английский должен упоминаться один раз, а не дважды"


@pytest.mark.django_db
def test_sat_and_act_are_alternatives(student, programs):
    from students.models import ExamAttempt

    requirement = AdmissionRequirement.objects.get(program=programs["Computer Science"])
    requirement.min_act = 28
    requirement.save()

    student.exam.ielts_current = "7.0"
    student.exam.gpa = "3.5"
    student.exam.save()
    ExamAttempt.objects.create(
        student=student, exam_type="ACT", attempt_format="official", date="2026-06-01", total_score=30
    )

    result = match(student, fresh(programs["Computer Science"]))
    assert result.is_open, result.summary()


@pytest.mark.django_db
def test_portfolio_gap_reads_naturally(student, programs):
    """«Не хватает 1 портфолио» — бессмыслица; фраза должна быть человеческой."""
    requirement = AdmissionRequirement.objects.get(program=programs["Graphic Design"])
    requirement.portfolio_required = True
    requirement.save()

    student.exam.ielts_current = "7.0"
    student.exam.save()

    result = match(student, fresh(programs["Graphic Design"]))
    assert result.summary() == "Не хватает работ в портфолио"
