"""Разбор профтеста под поступление за рубеж (решения владельца, 03.11 и 04.11.2026).

Модель знает, что школа в Казахстане готовит к зарубежным вузам, и получает
баллы и вузы ученика; разбор подробный, объём частей задан в SYSTEM; профиля
интересов по каждой шкале нет (06.11.2026); направлений два–пять, каждое на сильной
шкале (верхний диапазон теста), направление только из средних шкал отбрасывается;
профессии и программы — с объяснением «почему подходит», программа только из
каталога; цифры порогов — только из требований программ каталога; ученику 8–10
класса программы уходят ориентиром. Старые разборы открываются как есть, без
профиля, с пометкой «по старым правилам» у правил ниже третьих.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from career import analysis
from career.models import (
    AnalysisStatus,
    CareerAnalysis,
    CareerAnalysisDirection,
    CareerAnalysisScale,
    CareerAttempt,
    CareerAttemptScore,
    CareerDirectionItem,
    ItemKind,
)
from career.payloads import analysis_dict
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


def _directions(n: int, scales: tuple[str, ...] = ("Биология",)) -> list[dict]:
    return [
        {
            "title": f"Направление {i}",
            "title_abroad": f"Major {i}",
            "scales": list(scales),
            "reasoning": "Интерес к биологии — самый высокий в тесте, 12 из 12",
            "professions": [
                {
                    "title": "Биотехнолог",
                    "description": "Создаёт лекарства и материалы; подходит при биологии 12 из 12.",
                },
                {"title": "Генетик", "description": "Изучает наследственность. " * 20},
            ],
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


def test_system_asks_for_detail_and_sets_the_volume_of_every_part():
    system = analysis.SYSTEM
    assert "Пиши подробно и по делу" in system
    assert "общий вывод — пять–восемь предложений: сильные и средние шкалы" in system
    assert "одной фразой списком" in system and "без разбора каждой" in system
    assert "профиль интересов" not in system.casefold(), "профиля по каждой шкале больше нет (06.11.2026)"
    assert "«почему подходит» — четыре–шесть предложений" in system
    assert "профессии — три–пять, у каждой одна–две фразы" in system
    assert "программы каталога — у каждой две–три фразы" in system
    assert "ничего\n  не додумывай о вузе, стране, рейтинге" in system
    assert "«что сдавать для поступления» — по каждому экзамену отдельно" in system
    assert "сколько не хватает или что порог уже пройден" in system
    assert "«что подтянуть в школе» — каждый предмет с новой строки и с объяснением, зачем" in system
    assert "«что сделать уже сейчас» — три–пять конкретных шагов" in system
    assert "направлений — от двух до пяти" in system
    assert "понятно для ученика и родителя" in system and "но не коротко" in system
    assert "одно направление" not in system and "можно присмотреться: физика" not in system
    assert "profile" not in analysis.RESULT_SCHEMA["properties"]
    assert analysis.RESULT_SCHEMA["required"] == ["summary", "directions"]
    direction = analysis.RESULT_SCHEMA["properties"]["directions"]["items"]["properties"]
    assert direction["professions"]["items"]["required"] == ["title", "description"]
    assert direction["programs"]["items"]["required"] == ["id", "why"]
    assert analysis.MAX_TOKENS >= 12000, "подробный ответ не должен обрываться по max_tokens"
    student = analysis.STUDENT_SYSTEM
    assert "сохрани подробность" in student and "не короче исходной" in student
    assert "профил" not in student and "profile" not in analysis.STUDENT_SCHEMA["properties"]


def test_one_strong_scale_gives_two_to_five_directions(aliya_passed, karta, teacher, boston, fake):
    # «Карта интересов»: верхний диапазон 8…12 — только биология (12); юриспруденция 6 — средняя
    provider = fake(FakeProvider({"summary": "Сильнее всего — биология.", "directions": _directions(6)}))
    login(teacher).post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    prompt = provider.calls[0]["user"]
    strong = prompt.split("Сильные шкалы — верхний диапазон теста")[1].split("Средние шкалы")[0]
    middle = prompt.split("Средние шкалы — выше порога разбора (1)")[1].split("Слабые и отвергаемые")[0]
    low = prompt.split("Слабые и отвергаемые шкалы — ниже порога разбора (1):")[1]
    assert "- Биология: 12 из 12 — ярко выраженный интерес" in strong and "Юриспруденция" not in strong
    assert "- Юриспруденция: 6 из 12 — выраженный интерес" in middle
    assert "- Физика: -12 из 12 — активно отрицается" in low
    assert "Назови от двух до пяти направлений" in prompt and "Профиль интересов" not in prompt
    assert "одна сильная шкала может дать несколько направлений" in prompt
    row = CareerAnalysis.objects.get()
    assert row.status == AnalysisStatus.DONE and row.rules == analysis.RULES == 4
    assert row.directions.count() == 5, "одна сильная шкала — несколько направлений, не больше пяти"
    first = row.directions.first()
    assert first.title_abroad == "Major 1"
    assert first.next_steps == "олимпиада по биологии\nлетняя школа\nпроект в лаборатории"
    assert first.professions == "", "профессии списком — строками, не строкой"
    jobs = list(first.items.filter(kind=ItemKind.PROFESSION).values_list("title", "text"))
    assert jobs[0] == ("Биотехнолог", "Создаёт лекарства и материалы; подходит при биологии 12 из 12.")
    assert len(jobs[1][1]) > 300, "длинный текст не режется"


def test_direction_only_from_a_middle_scale_is_dropped(aliya_passed, karta, teacher, boston, fake):
    law = _directions(1, ("Юриспруденция",))[0] | {"title": "Право"}
    mixed = _directions(1, ("биология", "Юриспруденция"))[0] | {"title": "Биоэтика и право"}
    bare = _directions(1, ())[0] | {"title": "Без опоры"}
    biology = _directions(1)[0] | {"title": "Биотехнологии"}
    fake(FakeProvider({"summary": "Биология и право.", "directions": [law, mixed, bare, biology]}))
    login(teacher).post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    row = CareerAnalysis.objects.get()
    titles = list(row.directions.values_list("title", flat=True))
    assert titles == ["Биоэтика и право", "Биотехнологии"], "средняя шкала дополняет, но сама направления не даёт"
    assert list(row.directions.values_list("order", flat=True)) == [1, 2]


def test_only_middle_directions_leave_the_analysis_failed(aliya_passed, karta, teacher, boston, fake):
    fake(FakeProvider({"summary": "Право.", "directions": _directions(2, ("Юриспруденция",))}))
    login(teacher).post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    row = CareerAnalysis.objects.get()
    assert row.status == AnalysisStatus.FAILED and row.directions.count() == 0
    assert "без направлений" in row.error


def test_answer_without_profile_is_accepted_and_no_profile_is_shown(aliya_passed, karta, teacher, boston, fake):
    fake(FakeProvider({"summary": "Биология.", "directions": _directions(2)}))
    login(teacher).post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    row = CareerAnalysis.objects.get()
    assert row.status == AnalysisStatus.DONE and row.directions.count() == 2
    assert row.scales.count() == 0, "строк профиля новый разбор не заводит"
    body = login(teacher).get(f"/api/career/analyses/{row.pk}/").json()
    assert "profile" not in body
    jobs = body["directions"][0]["profession_items"]
    assert [job["title"] for job in jobs] == ["Биотехнолог", "Генетик"] and jobs[0]["text"].startswith("Создаёт")


def test_programs_come_with_why_and_foreign_numbers_are_dropped(aliya_passed, karta, teacher, boston, fake):
    leeds = _program("Biology", "University of Leeds", "Великобритания", min_ielts=Decimal("6.5"))
    asu = _program("Business", "Arizona State University", "США")
    picks = [
        {"id": leeds.pk, "why": "Биология 12 из 12 — ядро программы. Порог IELTS 6.5."},
        {"id": 999999, "why": "программы нет в каталоге"},
        {"id": leeds.pk, "why": "повтор"},
        asu.pk,  # прежний вид ответа — номер без объяснения
    ]
    provider = fake(FakeProvider({"summary": "Биология.", "directions": [{**_directions(1)[0], "programs": picks}]}))
    login(teacher).post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    assert f"- id={leeds.pk}: Biology · University of Leeds (Великобритания)" in provider.calls[0]["user"]
    direction = CareerAnalysis.objects.get().directions.get()
    rows = list(direction.items.filter(kind=ItemKind.PROGRAM))
    assert [(r.program_id, r.text) for r in rows] == [
        (leeds.pk, "Биология 12 из 12 — ядро программы. Порог IELTS 6.5."),
        (asu.pk, ""),
    ], "номер не из списка и повтор отброшены"
    assert [r.order for r in direction.items.all()] == [1, 2, 3, 4], "порядок общий: профессии, затем программы"
    assert direction.programs.count() == 0, "у нового разбора программы — строками с объяснением"
    body = login(teacher).get(f"/api/career/analyses/{direction.analysis_id}/").json()
    first = body["directions"][0]["programs"][0]
    assert (first["name"], first["university"], first["country"]) == (
        "Biology",
        "University of Leeds",
        "Великобритания",
    )
    assert first["why"].startswith("Биология 12 из 12") and first["item"] == rows[0].pk


def test_teacher_edits_professions_and_program_why(aliya_passed, karta, teacher, boston, fake):
    leeds = _program("Biology", "University of Leeds", "Великобритания")
    fake(
        FakeProvider(
            {"summary": "Биология.", "directions": [{**_directions(1)[0], "programs": [{"id": leeds.pk, "why": "x"}]}]}
        )
    )
    client = login(teacher)
    client.post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    direction = CareerAnalysis.objects.get().directions.get()
    job = direction.items.get(kind=ItemKind.PROFESSION, order=1)
    program = direction.items.get(kind=ItemKind.PROGRAM)
    response = client.patch(
        f"/api/career/analyses/{direction.analysis_id}/",
        {
            "directions": [
                {
                    "id": direction.pk,
                    "items": [
                        {"id": job.pk, "title": " Биоинженер ", "text": " Правка учителя "},
                        {"id": program.pk, "title": "не меняется", "text": "Связь с биологией."},
                    ],
                }
            ]
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    job.refresh_from_db()
    program.refresh_from_db()
    assert (job.title, job.text) == ("Биоинженер", "Правка учителя")
    assert (program.title, program.text) == ("", "Связь с биологией.")
    assert response.json()["edited_at"]
    empty = client.patch(
        f"/api/career/analyses/{direction.analysis_id}/",
        {"directions": [{"id": direction.pk, "items": [{"id": job.pk, "title": " "}]}]},
        format="json",
    )
    assert empty.status_code == 400


def test_student_version_keeps_the_detail_without_profile(aliya_passed, karta, teacher, boston, fake):
    fake(FakeProvider({"summary": "Биология.", "directions": _directions(2)}))
    login(teacher).post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    row = CareerAnalysis.objects.get()
    provider = fake(
        FakeProvider(
            {
                "summary": "У тебя самый сильный интерес — биология.",
                "directions": [{"order": 1, "why": "Тебе подходит, потому что…"}],
            }
        )
    )
    analysis.write_student_version(row, actor=teacher)
    prompt = provider.calls[0]["user"]
    assert "Профиль интересов" not in prompt and "Шкала 1" not in prompt
    assert "Профессии: Биотехнолог, Генетик" in prompt and "Что сдавать для поступления:" in prompt
    row.refresh_from_db()
    assert row.summary_student.startswith("У тебя")
    mine = analysis_dict(row, for_student=True)
    assert "profile" not in mine and mine["directions"][0]["reasoning"] == "Тебе подходит, потому что…"
    # профессии одни на обе версии: без обращения и без третьего лица
    assert mine["directions"][0]["profession_items"][0]["title"] == "Биотехнолог"


def test_several_top_scales_give_at_most_five_directions(aliya_passed, karta, teacher, boston, fake):
    for title in ("Юриспруденция", "Химия", "Медицина"):
        _weaken(aliya_passed, title, 9, "ярко выраженный интерес")
    fake(FakeProvider({"summary": "Биология, право, химия, медицина.", "directions": _directions(7)}))
    login(teacher).post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    assert CareerAnalysis.objects.get().directions.count() == 5


def test_test_without_ranges_counts_every_scale_above_threshold(aliya_passed, karta, teacher, boston, fake):
    karta.ranges.all().delete()
    provider = fake(FakeProvider({"summary": "Биология и право.", "directions": _directions(3, ("Юриспруденция",))}))
    login(teacher).post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    prompt = provider.calls[0]["user"]
    strong = prompt.split("Сильные шкалы — верхний диапазон теста")[1].split("Слабые и отвергаемые")[0]
    assert "Средние шкалы" not in prompt and "- Юриспруденция: 6 из 12" in strong
    assert CareerAnalysis.objects.get().directions.count() == 3, "без диапазонов сильна любая шкала выше порога"


def test_range_boundaries_count_own_scale_ranges_first():
    class R:
        def __init__(self, scale_id, low, high):
            self.scale_id, self.low, self.high = scale_id, low, high

    common = [R(None, 8, 12), R(None, 5, 7), R(None, 1, 4)]
    assert analysis.is_strong(common, 1, 12) and analysis.is_strong(common, 1, 8)
    assert not analysis.is_strong(common, 1, 6), "второй диапазон направления не даёт"
    assert not analysis.is_strong(common, 1, 4)
    assert analysis.is_strong(common, 1, 13), "выше верхней границы — тоже верхний"
    own = [*common, R(1, 10, 12), R(1, 7, 9), R(1, 0, 6)]
    assert not analysis.is_strong(own, 1, 9) and analysis.is_strong(own, 1, 10) and analysis.is_strong(own, 2, 9)
    assert analysis.is_strong([], 1, 1), "у теста без диапазонов сильна любая шкала выше порога"


def test_without_strong_scales_there_are_no_directions_and_an_honest_summary(
    aliya_passed, karta, teacher, boston, fake
):
    for title in ("Биология", "Юриспруденция"):
        _weaken(aliya_passed, title, 2, "интерес выражен слабо")
    honest = "Ярко выраженных интересов тест пока не показал; можно присмотреться к биологии."
    provider = fake(FakeProvider({"summary": honest, "directions": _directions(2)}))
    login(teacher).post("/api/career/analyses/", {"group": boston.pk, "tests": [karta.pk]}, format="json")
    prompt = provider.calls[0]["user"]
    assert "Сильных шкал нет: направлений не давай; общий вывод напиши так же подробно" in prompt
    row = CareerAnalysis.objects.get()
    assert row.status == AnalysisStatus.DONE and row.summary == honest
    assert row.directions.count() == 0 and row.scales.count() == 0


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
        FakeProvider(
            {
                "summary": "Биология.",
                "directions": [{**_directions(1)[0], "programs": [{"id": program.pk, "why": "y"}]}],
            }
        )
    )
    response = login(teacher).post("/api/career/analyses/", {"group": riga.pk, "tests": [karta.pk]}, format="json")
    assert response.status_code == 202, response.content
    prompt = provider.calls[0]["user"]
    assert "9 класс" in prompt and "До 11 класса, когда подаются документы в вузы, — 2 года" in prompt
    assert "ориентир на будущее, а не выбор" in prompt and f"id={program.pk}: Biology" in prompt
    row = CareerAnalysis.objects.get(attempts=attempt)
    assert list(row.directions.get().items.filter(kind=ItemKind.PROGRAM).values_list("program", flat=True)) == [
        program.pk
    ]


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
    assert body["legacy"] is True and body["summary"] == "Старый вывод" and "profile" not in body
    direction = body["directions"][0]
    assert direction["subjects"] == "русский язык, литература"
    assert direction["title_abroad"] == "" and direction["next_steps"] == ""
    assert body["group_id"] == pupils["aliya"].group_id
    listing = login(teacher).get(f"/api/career/students/{pupils['aliya'].pk}/").json()
    assert listing["analyses"][0]["legacy"] is True


def test_short_analysis_of_the_top_range_rules_opens_marked_old(aliya_passed, teacher, pupils):
    row = _old_analysis(pupils["aliya"], aliya_passed)
    CareerAnalysis.objects.filter(pk=row.pk).update(rules=2)
    body = login(teacher).get(f"/api/career/analyses/{row.pk}/").json()
    assert body["legacy"] is True and len(body["directions"]) == 1


def test_detailed_analysis_with_profile_opens_without_it(aliya_passed, karta, teacher, pupils):
    """Разбор 04.11.2026 (правила 3): профиль в базе остаётся, на экран и в ответ не идёт;
    профессии строкой, программы связью без объяснения; пометки «по старым правилам» нет."""
    row = _old_analysis(pupils["aliya"], aliya_passed)
    CareerAnalysis.objects.filter(pk=row.pk).update(rules=3)
    CareerAnalysisScale.objects.create(
        analysis=row, order=1, test_title=karta.title, title="Физика", score=-12, top=12, meaning="отвергается"
    )
    direction = row.directions.get()
    direction.professions = "биолог, эколог"
    direction.save()
    leeds = _program("Biology", "University of Leeds", "Великобритания")
    direction.programs.set([leeds])
    body = login(teacher).get(f"/api/career/analyses/{row.pk}/").json()
    assert body["legacy"] is False and "profile" not in body
    item = body["directions"][0]
    assert item["professions"] == "биолог, эколог" and item["profession_items"] == []
    assert item["programs"] == [
        {
            "id": leeds.pk,
            "item": None,
            "name": "Biology",
            "university": "University of Leeds",
            "country": "Великобритания",
            "level_title": "Бакалавриат",
            "why": "",
        }
    ]
    assert CareerAnalysisScale.objects.filter(analysis=row).count() == 1, "строки профиля не удаляются"
    assert not CareerDirectionItem.objects.exists()


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
    assert fresh.rules == 2


PROFILE = [("career", "0005_interest_profile")]


def test_profile_migration_only_adds(db, pupils):
    executor = MigrationExecutor(connection)
    executor.migrate(AFTER)
    old = executor.loader.project_state(AFTER).apps
    Analysis = old.get_model("career", "CareerAnalysis")
    Direction = old.get_model("career", "CareerAnalysisDirection")
    row = Analysis.objects.create(student_id=pupils["aliya"].pk, fingerprint="1", status="done", summary="вывод")
    Direction.objects.create(analysis=row, order=1, title="Право", reasoning="коротко")
    connection.check_constraints()
    executor = MigrationExecutor(connection)
    executor.migrate(PROFILE)
    new = executor.loader.project_state(PROFILE).apps
    Analysis = new.get_model("career", "CareerAnalysis")
    kept = Analysis.objects.get(pk=row.pk)
    assert (kept.rules, kept.summary) == (2, "вывод")
    assert new.get_model("career", "CareerAnalysisDirection").objects.get(analysis=kept).reasoning == "коротко"
    assert new.get_model("career", "CareerAnalysisScale").objects.filter(analysis=kept).count() == 0
    assert Analysis.objects.create(student_id=pupils["aliya"].pk, fingerprint="2").rules == 3
