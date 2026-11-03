"""Разбор профтеста под поступление за рубеж (решение владельца, 03.11.2026).

Модель знает, что школа в Казахстане готовит к зарубежным вузам, и получает
баллы и вузы ученика; направления — только по двум верхним диапазонам теста
и не больше трёх; цифры порогов — только из требований программ каталога;
ученику 8–10 класса программы уходят ориентиром. Старые разборы открываются
как есть, с пометкой «по старым правилам».
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from career import analysis
from career.models import AnalysisStatus, CareerAnalysis, CareerAnalysisDirection, CareerAttempt, CareerAttemptScore
from career.tests.conftest import FakeProvider, activate, answer_all, login
from students.models import AttemptFormat, ExamAttempt, ExamType
from universities.models import AdmissionRequirement, Program, StudentUniversity, University

pytestmark = pytest.mark.django_db

LOCAL_EXAMS = ("ОГЭ", "ЕНТ", "ЕГЭ")


def _pass(student, test) -> CareerAttempt:
    """Биология 12, юриспруденция 6, физика −12 — как у Алии в основных проверках."""
    client = login(student.user)
    attempt = client.post(f"/api/career/my/tests/{test.pk}/start/").json()["id"]
    answer_all(client, attempt, lambda n: {1: "++", 2: "−−", 17: "+"}.get((n - 1) % 24 + 1, "0"))
    client.post(f"/api/career/my/attempts/{attempt}/finish/")
    return CareerAttempt.objects.get(pk=attempt)


@pytest.fixture
def aliya_passed(karta, teacher, boston, riga, pupils) -> CareerAttempt:
    activate(karta, [{"group": boston.pk}, {"group": riga.pk}], by=teacher)
    return _pass(pupils["aliya"], karta)


def _weaken(attempt: CareerAttempt, title: str, score: int, label: str) -> None:
    CareerAttemptScore.objects.filter(attempt=attempt, scale__title=title).update(score=score, label=label)


def _program(name: str, university: str, country: str, **limits) -> Program:
    uni, _created = University.objects.get_or_create(name=university, defaults={"country": country})
    program = Program.objects.create(university=uni, name=name)
    if limits:
        AdmissionRequirement.objects.create(program=program, **limits)
    return program


def _directions(n: int) -> list[dict]:
    return [
        {
            "title": f"Направление {i}",
            "title_abroad": f"Major {i}",
            "reasoning": "Интерес к биологии — самый высокий в тесте, 12 из 12",
            "professions": "биотехнолог, " * 40,
            "exams": "IELTS или TOEFL; SAT — важнее Math",
            "subjects": "SAT Math, General English, биология",
            "next_steps": ["олимпиада по биологии", "летняя школа", "проект в лаборатории"],
        }
        for i in range(1, n + 1)
    ]


def test_prompt_knows_the_school_prepares_for_abroad_and_carries_the_student(
    aliya_passed, karta, teacher, boston, pupils, fake
):
    student = pupils["aliya"]
    student.exam.ielts_current, student.exam.ielts_target = Decimal("6.0"), Decimal("7.0")
    student.exam.sat_current = 1250
    student.exam.save()
    ExamAttempt.objects.create(
        student=student,
        exam_type=ExamType.IELTS,
        attempt_format=AttemptFormat.MOCK,
        date=dt.date(2026, 10, 12),
        total_score=Decimal("6.5"),
    )
    program = _program("Biology", "University of Leeds", "Великобритания")
    StudentUniversity.objects.create(student=student, program=program)
    provider = fake(FakeProvider({"summary": "Интересы — биология и право.", "directions": _directions(1)}))
    response = login(teacher).post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    assert response.status_code == 202, response.content
    call = provider.calls[0]
    system, prompt = call["system"], call["user"]
    assert "Казахстан" in system and "зарубежные вузы" in system and "IELTS или TOEFL" in system
    for word in LOCAL_EXAMS:
        # местные экзамены названы только в запрете
        assert word not in prompt
        assert system.count(word) == 1 and "не упоминай никогда" in system
    assert "Назови от трёх до пяти" not in prompt and "от трёх до пяти" not in system
    assert "11 класс" in prompt and "документы в вузы подаются в этом учебном году" in prompt
    assert "- IELTS: сейчас 6, цель 7" in prompt and "- SAT: сейчас 1250" in prompt
    assert "- Mock Test IELTS: 6.5 (10.2026)" in prompt
    assert "Biology · University of Leeds" in prompt and "Страны: Великобритания" in prompt
    assert "Ахметова" not in prompt and "Алия" not in prompt
    # предметы подготовки — из перечня школы, не школьная программа
    assert "EEP — English Exam Preparation" in prompt and "Профориентация" in prompt
    # программа из списка ученика — первой в каталоге
    catalog = prompt.split("Программы каталога школы")[1]
    assert catalog.splitlines()[1].startswith(f"- id={program.pk}: Biology")


def test_directions_only_from_two_top_ranges_and_at_most_three(aliya_passed, karta, teacher, boston, pupils, fake):
    # «Карта интересов»: верхние диапазоны 8…12 и 5…7; 1…4 — «интерес выражен слабо»
    _weaken(aliya_passed, "Юриспруденция", 3, "интерес выражен слабо")
    provider = fake(FakeProvider({"summary": "Сильнее всего — биология.", "directions": _directions(5)}))
    login(teacher).post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    prompt = provider.calls[0]["user"]
    strong, weak = prompt.split("Шкалы ниже — без направлений")
    assert "- Биология: 12 из 12 — ярко выраженный интерес" in strong.split("Сильные шкалы")[1]
    assert "- Юриспруденция: 3 из 12 — интерес выражен слабо" in weak
    assert "Юриспруденция" not in strong
    assert f"от одного до {analysis.MAX_DIRECTIONS} направлений" in prompt
    row = CareerAnalysis.objects.get()
    assert row.status == AnalysisStatus.DONE and row.rules == analysis.RULES
    assert row.directions.count() == 3, "больше трёх направлений не сохраняется"
    first = row.directions.first()
    assert first.title_abroad == "Major 1"
    assert first.next_steps == "олимпиада по биологии\nлетняя школа\nпроект в лаборатории"
    assert len(first.professions) > 300, "длинный текст не режется"


def test_range_boundaries_count_own_scale_ranges_first():
    class R:
        def __init__(self, scale_id, low, high):
            self.scale_id, self.low, self.high = scale_id, low, high

    common = [R(None, 8, 12), R(None, 5, 7), R(None, 1, 4)]
    assert analysis.is_strong(common, 1, 5) and analysis.is_strong(common, 1, 12)
    assert not analysis.is_strong(common, 1, 4)
    own = [*common, R(1, 10, 12), R(1, 7, 9), R(1, 0, 6)]
    assert not analysis.is_strong(own, 1, 6) and analysis.is_strong(own, 2, 6)
    assert analysis.is_strong([], 1, 1), "у теста без диапазонов сильна любая шкала выше порога"


def test_without_strong_scales_there_are_no_directions_and_an_honest_summary(
    aliya_passed, karta, teacher, boston, fake
):
    for title in ("Биология", "Юриспруденция"):
        _weaken(aliya_passed, title, 2, "интерес выражен слабо")
    honest = "Ярко выраженных интересов тест пока не показал; можно присмотреться к биологии."
    provider = fake(FakeProvider({"summary": honest, "directions": _directions(2)}))
    login(teacher).post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    assert "Сильных шкал нет: направлений не давай" in provider.calls[0]["user"]
    row = CareerAnalysis.objects.get()
    assert row.status == AnalysisStatus.DONE and row.summary == honest
    assert row.directions.count() == 0


def test_thresholds_come_only_from_catalog_requirements(aliya_passed, karta, teacher, boston, pupils, fake):
    student = pupils["aliya"]
    attempts = [aliya_passed]
    # каталог пуст — цифр порогов модель не получает и не должна называть
    empty = analysis._prompt(student, attempts, analysis._candidates(student))
    assert "Программ в каталоге школы пока нет" in empty
    assert "Порогов в каталоге нет: экзамены назови без цифр" in empty and "пороги — по программам в каталоге" in empty
    assert "пороги:" not in empty and "Цифры порогов — только из списка" not in empty
    # программа без требований — тоже без цифр
    _program("Law", "King's College London", "Великобритания")
    bare = analysis._prompt(student, attempts, analysis._candidates(student))
    assert "Law · King's College London (Великобритания) · Бакалавриат · порогов в каталоге нет" in bare
    assert "Порогов в каталоге нет" in bare
    # порог — из требований программы, ровно как в каталоге
    _program("Biology", "University of Leeds", "Великобритания", min_ielts=Decimal("6.5"), min_sat=1300)
    full = analysis._prompt(student, attempts, analysis._candidates(student))
    assert "· пороги: IELTS 6.5, SAT 1300" in full and "Цифры порогов — только из списка программ" in full
    assert "Порогов в каталоге нет" not in full


def test_junior_gets_catalog_programs_as_a_guide(karta, teacher, riga, boston, pupils, fake):
    activate(karta, [{"group": boston.pk}, {"group": riga.pk}], by=teacher)
    attempt = _pass(pupils["nurai"], karta)
    program = _program("Biology", "University of Leeds", "Великобритания", min_ielts=Decimal("6.5"))
    provider = fake(
        FakeProvider({"summary": "Биология.", "directions": [{**_directions(1)[0], "programs": [program.pk]}]})
    )
    response = login(teacher).post("/api/career/analyses/", {"group": riga.pk, "tests": [karta.pk]}, format="json")
    assert response.status_code == 202, response.content
    prompt = provider.calls[0]["user"]
    assert "9 класс" in prompt and "До 11 класса, когда подаются документы в вузы, — 2 года" in prompt
    assert "ориентир на будущее, а не выбор" in prompt and f"id={program.pk}: Biology" in prompt
    row = CareerAnalysis.objects.get(attempts=attempt)
    assert list(row.directions.get().programs.all()) == [program]


def _old_analysis(student, attempt) -> CareerAnalysis:
    row = CareerAnalysis.objects.create(
        student=student, fingerprint=str(attempt.pk), status=AnalysisStatus.DONE, summary="Старый вывод", rules=1
    )
    row.attempts.set([attempt])
    CareerAnalysisDirection.objects.create(
        analysis=row, order=1, title="Филология", reasoning="высокий интерес", subjects="русский язык, литература"
    )
    return row


def test_old_analysis_opens_as_is_marked_old(aliya_passed, teacher, pupils):
    row = _old_analysis(pupils["aliya"], aliya_passed)
    body = login(teacher).get(f"/api/career/analyses/{row.pk}/").json()
    assert body["legacy"] is True and body["summary"] == "Старый вывод"
    direction = body["directions"][0]
    assert direction["subjects"] == "русский язык, литература"
    assert direction["title_abroad"] == "" and direction["next_steps"] == ""
    assert body["group_id"] == pupils["aliya"].group_id
    listing = login(teacher).get(f"/api/career/students/{pupils['aliya'].pk}/").json()
    assert listing["analyses"][0]["legacy"] is True


def test_teacher_edits_new_fields_without_cutting(aliya_passed, karta, teacher, boston, fake):
    fake(FakeProvider({"summary": "Биология.", "directions": _directions(1)}))
    client = login(teacher)
    client.post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    row = CareerAnalysis.objects.get()
    direction = row.directions.get()
    long_exams = "IELTS 6.5 — до порога программ каталога не хватает 0.5. " * 10
    response = client.patch(
        f"/api/career/analyses/{row.pk}/",
        {"directions": [{"id": direction.pk, "title_abroad": "Biology", "exams": long_exams, "next_steps": "шаг"}]},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["legacy"] is False
    direction.refresh_from_db()
    assert direction.title_abroad == "Biology" and direction.exams == long_exams.strip()
    assert direction.next_steps == "шаг"


# --- миграция ---------------------------------------------------------------------------

BEFORE = [("career", "0003_analysis_job_and_cancelled")]
AFTER = [("career", "0004_abroad_rules")]


def test_migration_keeps_old_analyses_and_marks_them_old(db, pupils):
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    old = executor.loader.project_state(BEFORE).apps
    Analysis = old.get_model("career", "CareerAnalysis")
    Direction = old.get_model("career", "CareerAnalysisDirection")
    row = Analysis.objects.create(student_id=pupils["aliya"].pk, fingerprint="1", status="done", summary="вывод")
    text = "п" * 300
    Direction.objects.create(analysis=row, order=1, title="Право", professions=text, subjects=text, exams=text)
    connection.check_constraints()
    executor = MigrationExecutor(connection)
    executor.migrate(AFTER)
    new = executor.loader.project_state(AFTER).apps
    Analysis = new.get_model("career", "CareerAnalysis")
    Direction = new.get_model("career", "CareerAnalysisDirection")
    kept = Analysis.objects.get(pk=row.pk)
    assert kept.rules == 1 and kept.summary == "вывод"
    direction = Direction.objects.get(analysis=kept)
    assert (direction.professions, direction.subjects, direction.exams) == (text, text, text)
    assert direction.title_abroad == "" and direction.next_steps == ""
    fresh = Analysis.objects.create(student_id=pupils["aliya"].pk, fingerprint="2")
    assert fresh.rules == analysis.RULES
