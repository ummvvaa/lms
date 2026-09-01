"""Приёмка фазы 48: внешний вид по образцу и найденное владельцем.

Часть проверок — по исходникам фронта: вид нечем проверить из pytest,
но три класса поломок этой фазы видны в тексте файлов и ловятся дешевле,
чем браузером. Остальное — обычные проверки поведения.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"


def sources(suffix: str = ".tsx") -> dict[Path, str]:
    return {
        path: path.read_text(encoding="utf-8")
        for path in FRONTEND.rglob(f"*{suffix}")
        if path.name != "schema.ts" and "node_modules" not in path.parts
    }


# --- Общий визуальный язык -------------------------------------------------


def test_visual_language_lives_in_one_set():
    """Крупная карточка, карточка-число и строка списка собраны один раз.

    Иначе через три фазы у каждого экрана будет своя карточка, своя
    строка и своя геометрия — ровно то состояние, из которого фаза
    выводила.
    """
    patterns = (FRONTEND / "components" / "patterns.tsx").read_text(encoding="utf-8")
    for name in ("Hero", "StatCard", "Row", "CatalogCard", "Segmented", "TipBar", "Dimmed"):
        assert f"export function {name}" in patterns, f"в наборе нет: {name}"

    # экраны берут детали оттуда, а не рисуют свои
    users = [path.name for path, text in sources().items() if "components/patterns" in text]
    assert len(users) >= 8, f"набор используют слишком мало экранов: {users}"


def test_student_home_kept_tasks_and_readiness():
    """Переделка вида не должна была унести работающие блоки.

    Первая сборка фазы собрала главную по образцу и потеряла две вещи:
    «задания на сегодня» (задачу отмечают прямо здесь, за это начисляется
    XP) и разбивку готовности по пяти доменам (C4 из аудита фазы 7 —
    домен без данных подписан, а не спрятан). Образец задавал характер,
    а не право удалять построенное.
    """
    home = (FRONTEND / "screens" / "dashboards" / "StudentHome.tsx").read_text(encoding="utf-8")
    assert "TodayPanel" in home, "с главной ученика пропали задания на сегодня"
    assert "ReadinessBlock" in home, "с главной ученика пропала разбивка готовности"

    ready = home.split("function ReadinessBlock")[1]
    assert "readiness.skipped" in ready, "домены без данных снова прячутся вместо подписи"

    today = (FRONTEND / "components" / "TodayPanel.tsx").read_text(encoding="utf-8")
    assert "useTaskStatus" in today, "задачу с главной больше не отметить"
    assert "streak_phrase" in today, "поддерживающая формулировка стрика пропала"


def test_our_own_503_is_not_mistaken_for_a_broken_connection():
    """503 с JSON — это наш ответ «раздел недоступен», а не обрыв связи.

    Профтест без ключа модели отвечает 503 и объясняет причину. Клиент
    считал любой 503 ответом прокси и показывал «Нет связи с сервером»,
    пряча то самое объяснение, ради которого код и выбран. Без тела JSON
    503 по-прежнему обрыв: так отвечает nginx.
    """
    client = (FRONTEND / "api" / "client.ts").read_text(encoding="utf-8")
    guard = client.split("function isGatewayFailure")[1].split("}")[0]
    assert "status === 502 || status === 504" in guard
    assert "status === 503) && body === null" in guard


def test_hero_graphics_are_vectors_without_characters():
    """Вместо персонажа — герб и геометрия, нарисованные кодом.

    Никаких картинок и персонажей: рисунок должен перекрашиваться вместе
    с темой, а в тёмной теме гаснуть.
    """
    patterns = (FRONTEND / "components" / "patterns.tsx").read_text(encoding="utf-8")
    assert "<svg" in patterns and "var(--hero-figure)" in patterns and "var(--hero-mark)" in patterns
    assert "<img" not in patterns, "в крупной карточке появилась картинка вместо векторов"

    tokens = (FRONTEND / "styles" / "tokens.css").read_text(encoding="utf-8")
    light, dark = tokens.split(":root[data-theme='dark']")
    for name in ("--hero-figure", "--hero-mark", "--on-hero"):
        assert name in light and name in dark, f"у {name} нет тёмного двойника"


def test_answer_option_is_not_a_registry_button():
    """Вариант ответа не красится классом поверх кнопки реестра.

    Правило реестра по двум атрибутам (`[data-slot][data-variant]`)
    перебивает наш класс по одному: выбор проходил, а на экране
    не менялось ничего — ученик решал, что вариант не выбирается вовсе.
    """
    for name in ("Quiz.tsx", "Prep.tsx"):
        text = (FRONTEND / "screens" / name).read_text(encoding="utf-8")
        # сам перебор вариантов: от `__options` до конца этого блока
        block = text.split("__options", 1)[1].split("</div>", 1)[0]
        assert "<Button" not in block, f"{name}: вариант ответа снова кнопка реестра"
        assert "aria-checked" in block, f"{name}: у варианта ответа нет состояния выбора"


def test_two_densities_got_smaller_but_kept_the_gap():
    """Обе шкалы стали плотнее, разница между ними осталась."""
    text = (FRONTEND / "styles" / "density.css").read_text(encoding="utf-8")
    dense, roomy = text.split("[data-density='roomy']")

    def value(block: str, name: str) -> float:
        found = re.search(rf"{name}:\s*([\d.]+)px", block)
        assert found, f"в наборе нет {name}"
        return float(found.group(1))

    # не мельче образца: подпись под числом читается без прищуривания
    assert value(dense, "--type-note") >= 11
    assert value(roomy, "--type-body") >= 14
    for name in ("--type-body", "--type-screen", "--pad-card", "--control-h"):
        assert value(dense, name) < value(roomy, name), f"{name}: разница плотностей потеряна"


def test_student_menu_is_split_into_three_groups():
    """Меню ученика разбито на три группы, а не идёт списком файлов."""
    nav = (FRONTEND / "layout" / "nav.ts").read_text(encoding="utf-8")
    student = nav.split("student: [", 1)[1].split("director_behavior:", 1)[0]
    for group in ("group: 'main'", "group: 'admission'", "group: 'work'"):
        assert group in student, f"у ученика нет группы {group}"


# --- План заводится сам (часть 4.1) ----------------------------------------


@pytest.fixture
def program(db):
    from universities.models import AdmissionRequirement, AdmissionRound, Program, University

    university = University.objects.create(name="Plan University", country="Канада")
    program = Program.objects.create(university=university, name="Data Science", level="bachelor")
    AdmissionRequirement.objects.create(program=program, min_ielts=6.5)
    AdmissionRound.objects.create(program=program, round_type="RD", deadline=dt.date(2027, 1, 15))
    return program


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def student_user(make_user, student):
    user = make_user("student", student.email)
    student.user = user
    student.save(update_fields=["user"])
    return user


@pytest.mark.django_db
def test_adding_a_university_creates_the_plan_and_its_tasks(api_client, student_user, student, program):
    """Ученик добавил программу — план и задачи появились без второй кнопки.

    До фазы 48 подтверждением было отдельное нажатие «Создать план»,
    а потом ещё одно — «Принять задачи». Ни того, ни другого человек
    не находил, и после выбора двух вузов у него не появлялось ничего.
    """
    from roadmap.models import ApplicationPlan, Task
    from students import calendar_feed

    api_client.force_authenticate(student_user)
    added = api_client.post("/api/catalog/add/", {"program": program.pk, "tier": "target"}, format="json")
    assert added.status_code == 201, added.data

    plan = ApplicationPlan.objects.filter(student=student, program=program).first()
    assert plan is not None, "план не завёлся при добавлении программы"
    assert plan.generation_status == "done"

    tasks = Task.objects.filter(plan=plan)
    assert tasks.count() > 0, "задачи собрались, но в план не попали"

    # видны в общем роадмапе — с пометкой вуза
    mine = api_client.get("/api/tasks/my/").data
    assert any(row["plan_university"] == "Plan University" for row in mine)

    # и в календаре: срок задачи подачи живёт в дедлайне раунда
    events = calendar_feed.state(student)["events"]
    assert any(event["kind"] == "task" for event in events), "задачи плана не дошли до календаря"


@pytest.mark.django_db
def test_removing_the_university_archives_the_plan(api_client, student_user, student, program):
    """Убрали программу — план и его задачи ушли в архив вместе с ней."""
    from roadmap.models import ApplicationPlan, Task
    from universities.models import StudentUniversity

    api_client.force_authenticate(student_user)
    api_client.post("/api/catalog/add/", {"program": program.pk, "tier": "target"}, format="json")
    plan = ApplicationPlan.objects.get(student=student, program=program)
    assert Task.objects.filter(plan=plan).count() > 0

    entry = StudentUniversity.objects.get(student=student, program=program)
    removed = api_client.delete(f"/api/catalog/remove/{entry.pk}/")
    assert removed.status_code == 204

    assert ApplicationPlan.objects.filter(student=student, program=program).count() == 0
    assert Task.objects.filter(plan=plan).count() == 0
    # но из базы ничего не пропало: мягкое удаление (инвариант №13)
    assert ApplicationPlan.all_objects.filter(pk=plan.pk).exists()
    assert Task.all_objects.filter(plan=plan).count() > 0


# --- Два экзамена (часть 4.2) ----------------------------------------------


@pytest.mark.django_db
def test_hidden_exams_disappear_everywhere_but_keep_their_rows(api_client, student_user):
    """Скрытый экзамен не появляется ни в подготовке, ни в целях, ни в квизе.

    Строки справочника при этом целы: понадобится ЕНТ — включается
    галочкой, без выката.
    """
    from directories.models import ExamKind

    assert ExamKind.objects.count() == 7, "строки скрытых экзаменов удалены, а должны были остаться"
    visible = set(ExamKind.objects.filter(is_active=True).values_list("name", flat=True))
    assert visible == {"SAT", "IELTS"}

    api_client.force_authenticate(student_user)
    exams = {row["exam_type"] for row in api_client.get("/api/prep/center/exams/").data["exams"]}
    assert exams == {"SAT", "IELTS"}

    quiz = api_client.get("/api/prep/quiz/").data
    assert {row["code"] for row in quiz["exams"]} == {"SAT", "IELTS"}

    # цели по экзаменам берут список из того же справочника
    meta = api_client.get("/api/meta/domains/").data
    fields = [
        field
        for domain in meta["domains"]
        for model in domain["models"]
        if model["label"] == "students.ExamGoal"
        for field in model["fields"]
        if field["name"] == "exam"
    ]
    assert fields, "поля экзамена в реестре не нашлось"
    assert {choice["title"] for choice in fields[0]["choices"]} == {"SAT", "IELTS"}


# --- Профтест кнопками (часть 3.9) -----------------------------------------


@pytest.mark.django_db
def test_career_questions_are_answered_by_options(api_client, student_user):
    """У каждого вопроса анкеты есть готовые варианты и вид «несколько».

    Шесть пустых текстовых полей ученик не заполняет: он закрывает экран,
    не начав.
    """
    from engagement.models import CareerQuestion

    questions = list(CareerQuestion.objects.filter(is_active=True))
    assert questions, "анкета пуста"
    assert all(question.options_list for question in questions), "есть вопрос без вариантов ответа"
    assert all(question.kind == "multi" for question in questions), "вопрос не принимает несколько вариантов"

    api_client.force_authenticate(student_user)
    payload = api_client.get("/api/career/").data
    assert all(row["options_list"] for row in payload["questions"])
