"""Разборы профтеста в Word (решение владельца, 04.11.2026).

Выгружают только учитель профориентации и администратор; в файл идут все
готовые разборы ученика, версия профориентолога с правками; профиля интересов
по каждой шкале в файле нет, профессии и программы — с объяснением (06.11.2026);
один ученик на языке разбора — файл сразу. Журнал помнит, кто, кого и на каком языке
выгрузил, — без текстов разбора.
"""

from __future__ import annotations

import io

import pytest
from docx import Document

from accounts.models import Role
from career import word
from career.models import AnalysisStatus, CareerAnalysis
from career.tests.conftest import FakeProvider, activate, answer_all, login
from core.models import AuditLog

pytestmark = pytest.mark.django_db

#: прежний вид ответа с профилем — профиль принимается молча и никуда не идёт
PROFILE = [{"scale": "Биология", "meaning": "Самый сильный интерес теста."}]


def _directions(n: int = 2, programs: list | None = None) -> list[dict]:
    return [
        {
            "title": f"Биотехнологии {i}",
            "title_abroad": f"Biotechnology {i}",
            "scales": ["Биология"],
            "reasoning": "Интерес к биологии — самый высокий в тесте, 12 из 12.",
            "professions": [
                {"title": "Биотехнолог", "description": "Создаёт лекарства и материалы из живых клеток."},
                {"title": "Генетик", "description": "Изучает наследственность."},
            ],
            "programs": programs or [],
            "exams": "IELTS: сейчас 6.0, порог 6.5 — не хватает 0.5\nSAT: пороги — по программам в каталоге",
            "subjects": "SAT Math — для первого курса\nбиология — профильный предмет",
            "next_steps": ["олимпиада по биологии в 10 классе", "летняя школа", "проект"],
        }
        for i in range(1, n + 1)
    ]


def _pass(student, test):
    client = login(student.user)
    attempt = client.post(f"/api/career/my/tests/{test.pk}/start/").json()["id"]
    answer_all(client, attempt, lambda n: {1: "++", 2: "−−", 17: "+"}.get((n - 1) % 24 + 1, "0"))
    client.post(f"/api/career/my/attempts/{attempt}/finish/")


@pytest.fixture
def analysed(karta, teacher, boston, riga, pupils, fake) -> CareerAnalysis:
    """Готовый разбор Алии на русском."""
    from universities.models import Program, University

    activate(karta, [{"group": boston.pk}, {"group": riga.pk}], by=teacher)
    _pass(pupils["aliya"], karta)
    leeds = Program.objects.create(
        university=University.objects.create(name="University of Leeds", country="Великобритания"), name="Biology"
    )
    why = [{"id": leeds.pk, "why": "Биология 12 из 12 — ядро программы."}]
    fake(FakeProvider({"summary": "Сильнее всего — биология.", "profile": PROFILE, "directions": _directions(2, why)}))
    response = login(teacher).post(
        "/api/career/analyses/",
        {"group": boston.pk, "tests": [karta.pk], "students": [pupils["aliya"].pk]},
        format="json",
    )
    assert response.status_code == 202, response.content
    row = CareerAnalysis.objects.get(student=pupils["aliya"])
    assert row.status == AnalysisStatus.DONE, row.error
    return row


def _word(client, student, language: str = "ru"):
    return client.get(f"/api/career/students/{student.pk}/word/?language={language}")


def _document(payload: bytes):
    return Document(io.BytesIO(payload))


def test_one_student_in_the_analysis_language_is_downloaded_at_once(analysed, teacher, pupils):
    response = _word(login(teacher), pupils["aliya"])
    assert response.status_code == 200, response.content
    assert response["Content-Type"] == word.DOCX_TYPE
    assert "filename*=UTF-8''%D0%90%D1%85%D0%BC%D0%B5%D1%82%D0%BE%D0%B2%D0%B0_" in response["Content-Disposition"]
    document = _document(response.content)
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    assert "Общий вывод" in headings and "Направления" in headings
    assert "Профиль интересов" not in headings, "профиля по каждой шкале в файле нет (06.11.2026)"
    assert "Общая картина по всем тестам" not in headings, "разбор один — общей картины нет"
    assert "1. Биотехнологии 1" in headings
    text = "\n".join(p.text for p in document.paragraphs)
    assert "Сильнее всего — биология." in text and "Biotechnology 1" in text
    # шапка: герб, ФИО, группа, параллель, кто выгрузил
    head = document.tables[0].rows[0].cells
    assert head[0]._tc.xpath(".//pic:pic"), "в шапке герб школы"
    assert "Ахметова Алия" in head[1].text and "BOSTON" in head[1].text and "11 класс" in head[1].text
    assert "Жанар Профориентатор" in head[1].text
    assert len(document.tables) == 1, "в файле одна таблица — шапка, таблицы профиля нет"
    assert "Самый сильный интерес теста." not in text
    # профессия: название жирным, объяснение в той же строке
    job = next(p for p in document.paragraphs if p.text.startswith("Биотехнолог"))
    assert job.text == "Биотехнолог — Создаёт лекарства и материалы из живых клеток."
    assert job.runs[0].bold and job.runs[0].text == "Биотехнолог" and not job.runs[1].bold
    # программа: «Программа — вуз (страна) · уровень», объяснение — абзацем ниже
    lines = [p.text for p in document.paragraphs]
    place = lines.index("Biology — University of Leeds (Великобритания) · Бакалавриат")
    assert lines[place + 1] == "Биология 12 из 12 — ядро программы."


def test_teacher_edits_go_into_the_file_as_on_screen(analysed, teacher, pupils):
    client = login(teacher)
    direction = analysed.directions.first()
    client.patch(
        f"/api/career/analyses/{analysed.pk}/",
        {"summary": "Правка профориентолога.", "directions": [{"id": direction.pk, "title": "Генетика"}]},
        format="json",
    )
    text = "\n".join(p.text for p in _document(_word(client, pupils["aliya"]).content).paragraphs)
    assert "Правка профориентолога." in text and "1. Генетика" in text
    assert "Сильнее всего — биология." not in text


def test_only_ready_analyses_go_into_the_file(analysed, teacher, pupils):
    CareerAnalysis.objects.filter(pk=analysed.pk).update(status=AnalysisStatus.FAILED)
    response = _word(login(teacher), pupils["aliya"])
    assert response.status_code == 400 and "нет готового разбора" in response.json()["detail"]


def test_other_language_asks_to_prepare_the_file(analysed, teacher, pupils):
    response = _word(login(teacher), pupils["aliya"], "kk")
    assert response.status_code == 409 and response.json()["prepare"] is True


@pytest.mark.parametrize("who", ["curator", "asem", "kymbat", "other_teacher"])
def test_only_career_teacher_and_admin_export(request, analysed, pupils, who):
    response = _word(login(request.getfixturevalue(who)), pupils["aliya"])
    assert response.status_code == 403


def test_student_cannot_export_even_own_analysis(analysed, pupils):
    assert _word(login(pupils["aliya"].user), pupils["aliya"]).status_code == 403


def test_admin_exports_any_group(analysed, admin, pupils):
    assert _word(login(admin), pupils["aliya"]).status_code == 200


def test_career_teacher_of_another_group_gets_404(analysed, pupils, make_user, career_subject, riga):
    from academics.cohorts import group_cohort
    from academics.models import Course, TeacherProfile

    user = make_user(Role.TEACHER, "riga.career@example.kz", full_name="Только Рига")
    TeacherProfile.objects.create(user=user).subjects.set([career_subject])
    Course.objects.create(subject=career_subject, teacher=user, cohort=group_cohort(riga))
    assert _word(login(user), pupils["aliya"]).status_code == 404


def test_journal_says_who_exported_whom_and_in_what_language(analysed, teacher, pupils):
    _word(login(teacher), pupils["aliya"])
    entry = AuditLog.objects.get(field_name="career_export")
    assert entry.actor == teacher and entry.student_id == pupils["aliya"].pk
    assert "ru" in entry.new_value
    assert "биология" not in entry.new_value.lower(), "текста разбора в журнале нет"


def test_file_name_has_no_characters_that_break_windows():
    class Pupil:
        last_name, first_name = 'Ахметова: "Алия"', "Мария / Анна"

    assert word.file_name(Pupil()) == "Ахметова_Алия_Мария_Анна_профтест.docx"


# --- Перевод и общая картина ---------------------------------------------------------------

KK = {
    "summary": "Ең күшті қызығушылық — биология.",
    "tests": [{"order": 1, "title": "Қызығушылықтар картасы"}],
    "scales": [{"order": 1, "title": "Биология", "label": "айқын қызығушылық"}],
    "directions": [
        {
            "order": 1,
            "title": "Биотехнология",
            "reasoning": "Биологияға қызығушылық — 12 ішінен 12.",
            "profession_items": [{"order": 1, "title": "Биотехнолог", "text": "Тірі жасушалардан дәрі жасайды."}],
            "program_notes": [{"order": 1, "text": "Биология 12 ішінен 12 — бағдарламаның өзегі."}],
        },
        {"order": 2, "title": "Генетика"},
    ],
}


def test_translation_is_made_once_and_reused(analysed, teacher, pupils, fake):
    from career import exports

    provider = fake(FakeProvider(KK))
    first = exports.build(pupils["aliya"], language="kk", actor=teacher, use_model=True)
    assert len(provider.calls) == 1 and first.language == "kk" and not first.notes
    from core.i18n import answer_rule

    assert provider.calls[0]["system"].endswith(answer_rule("kk")), "перевод — на языке выгрузки"
    second = exports.build(pupils["aliya"], language="kk", actor=teacher, use_model=True)
    assert len(provider.calls) == 1, "второе скачивание на том же языке — без нового перевода"
    document = _document(second.payload)
    text = "\n".join(p.text for p in document.paragraphs)
    assert "Ең күшті қызығушылық — биология." in text and "1. Биотехнология" in text
    assert "Biotechnology 1" in text, "английское название специальности не переводится"
    assert "Мамандықтар" in text and "Каталог бағдарламалары" in text, "подписи разделов — на языке выгрузки"
    assert "Қызығушылықтар бейіні" not in text
    assert "Биотехнолог — Тірі жасушалардан дәрі жасайды." in text, "профессия с объяснением — в переводе"
    assert "Генетик — Изучает наследственность." in text, "чего модель не перевела — остаётся оригиналом"
    assert "Biology — University of Leeds (Великобритания) · Бакалавриат" in text, "название программы не переводится"
    assert "Биология 12 ішінен 12 — бағдарламаның өзегі." in text
    prompt = provider.calls[0]["user"]
    assert "Профессия 1: Биотехнолог | почему подходит: Создаёт" in prompt
    assert "Программа 1: Biology — University of Leeds" in prompt and "смысл:" not in prompt
    # оригинал не тронут
    analysed.refresh_from_db()
    assert analysis_summary(analysed) == "Сильнее всего — биология."
    # перевод сохранён — теперь файл отдаётся сразу, без подготовки
    assert _word(login(teacher), pupils["aliya"], "kk").status_code == 200


def analysis_summary(row) -> str:
    return CareerAnalysis.objects.get(pk=row.pk).summary


def test_edit_after_translation_drops_the_translation(analysed, teacher, pupils, fake):
    from career import exports

    provider = fake(FakeProvider(KK))
    exports.build(pupils["aliya"], language="kk", actor=teacher, use_model=True)
    login(teacher).patch(f"/api/career/analyses/{analysed.pk}/", {"summary": "Новая правка."}, format="json")
    assert _word(login(teacher), pupils["aliya"], "kk").status_code == 409, "перевод устарел"
    exports.build(pupils["aliya"], language="kk", actor=teacher, use_model=True)
    assert len(provider.calls) == 2, "правка после перевода — перевод заново"
    assert "Новая правка." in provider.calls[1]["user"], "переводится уже исправленный текст"
    assert analysed.translations.count() == 1


def test_translation_keeps_numbers_programmes_and_bans_local_exams():
    from career import translation

    system = translation.TRANSLATE_SYSTEM
    for words in ("смысл и цифры не меняй", "не переводи названия вузов и программ", "ЕНТ, ОГЭ, ЕГЭ"):
        assert words in system
    assert "ҚБ, БЖБ, ТЖБ" in system and "Mock Test" in system, "казахский — по глоссарию школы"
    assert "«шанс»" in translation.OVERVIEW_SYSTEM and "ЕНТ, ОГЭ, ЕГЭ" in translation.OVERVIEW_SYSTEM


@pytest.fixture
def two_analyses(analysed, karta, teacher, pupils, example_bytes):
    """Второй готовый разбор Алии — по другому набору тестов."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from career.models import CareerTest

    client = login(teacher)
    response = client.post(
        "/api/career/tests/", {"file": SimpleUploadedFile("second.xlsx", example_bytes)}, format="multipart"
    )
    second = CareerTest.objects.get(pk=response.data["id"])
    CareerTest.objects.filter(pk=second.pk).update(title="Второй тест")
    activate(second, [{"group": pupils["aliya"].group_id}], by=teacher)
    _pass(pupils["aliya"], second)
    from career import analysis

    attempts = [a for t in (karta, second) for a in t.attempts.filter(student=pupils["aliya"])]
    row = analysis.open_analysis(pupils["aliya"], attempts, actor=teacher, language="ru")
    analysis.run(row)
    row.refresh_from_db()
    assert row.status == AnalysisStatus.DONE, row.error
    return [analysed, row]


OVERVIEW = {
    "repeats": "Биология сильнее всего в обоих тестах.",
    "agreements": "Оба теста указывают на естественные науки.",
    "differences": "Не расходятся.",
    "confirmed": "Биотехнологии подтверждаются двумя тестами.",
}


def test_several_analyses_get_the_overall_picture_once(two_analyses, teacher, pupils, fake):
    from career import exports

    assert _word(login(teacher), pupils["aliya"]).status_code == 409, "общей картины ещё нет"
    provider = fake(FakeProvider(OVERVIEW))
    prepared = exports.build(pupils["aliya"], language="ru", actor=teacher, use_model=True)
    assert len(provider.calls) == 1
    prompt = provider.calls[0]["user"]
    assert "Разбор 1" in prompt and "Разбор 2" in prompt and "сильная шкала" in prompt
    document = _document(prepared.payload)
    headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
    assert headings.index("Общая картина по всем тестам") < headings.index("Общий вывод")
    assert "Профиль интересов" not in headings and headings.count("Направления") == 2
    # каждый разбор — с новой страницы
    breaks = [p for p in document.paragraphs if p.style.name == "Heading 1" and p.paragraph_format.page_break_before]
    assert len(breaks) == 2
    assert "Биотехнологии подтверждаются двумя тестами." in "\n".join(p.text for p in document.paragraphs)
    # сохранена: файл теперь сразу
    assert _word(login(teacher), pupils["aliya"]).status_code == 200
    assert len(provider.calls) == 1


def test_overall_picture_is_rewritten_when_an_analysis_changes(two_analyses, teacher, pupils, fake):
    from career import exports

    provider = fake(FakeProvider(OVERVIEW))
    exports.build(pupils["aliya"], language="ru", actor=teacher, use_model=True)
    login(teacher).patch(f"/api/career/analyses/{two_analyses[0].pk}/", {"summary": "Правка."}, format="json")
    assert _word(login(teacher), pupils["aliya"]).status_code == 409
    exports.build(pupils["aliya"], language="ru", actor=teacher, use_model=True)
    assert len(provider.calls) == 2


def test_failed_translation_still_builds_the_file_in_the_analysis_language(analysed, teacher, pupils, fake):
    from career import exports

    fake(FakeProvider(fail=True))
    prepared = exports.build(pupils["aliya"], language="en", actor=teacher, use_model=True)
    assert prepared.language == "ru" and prepared.notes and "перевод не получился" in prepared.notes[0]
    text = "\n".join(p.text for p in _document(prepared.payload).paragraphs)
    assert "Сильнее всего — биология." in text and "Профессии" in text


# --- Подготовка в фоне: архив группы, отмена, сбой перевода, срок хранения ------------------


@pytest.fixture
def both_analysed(analysed, karta, teacher, pupils, fake) -> list[CareerAnalysis]:
    """Готовые разборы Алии и Дамира на русском."""
    _pass(pupils["damir"], karta)
    fake(FakeProvider({"summary": "Биология — главное.", "directions": _directions()}))
    login(teacher).post(
        "/api/career/analyses/",
        {"group": pupils["damir"].group_id, "tests": [karta.pk], "students": [pupils["damir"].pk]},
        format="json",
    )
    return list(CareerAnalysis.objects.filter(status=AnalysisStatus.DONE).order_by("student__last_name"))


def _start(client, **body):
    return client.post("/api/career/exports/", body, format="json")


def _zip(payload: bytes) -> dict[str, bytes]:
    import zipfile

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_one_student_without_model_work_is_ready_at_once(analysed, teacher, pupils):
    response = _start(login(teacher), language="ru", students=[pupils["aliya"].pk])
    assert response.status_code == 200 and response.json()["ready"] is True
    assert response.json()["url"] == f"/career/students/{pupils['aliya'].pk}/word/?language=ru"
    from career.models import CareerExport

    assert not CareerExport.objects.exists(), "без фонового запуска"


def test_group_zip_has_a_file_per_ready_student_and_skips_the_rest(analysed, teacher, pupils, boston):
    from career.models import CareerExport

    client = login(teacher)
    response = _start(client, language="ru", group=boston.pk)
    assert response.status_code == 202, response.content
    export = CareerExport.objects.get()
    state = client.get(f"/api/career/exports/{export.pk}/").json()
    assert state["status"] == "done" and state["total"] == 2 and state["done"] == 2
    assert state["outcome"] == "Готово 1, пропущено 1: нет готового разбора — Сериков Д."
    assert state["file_name"].startswith("Профтест_BOSTON_") and state["file_name"].endswith(".zip")
    file = client.get(f"/api/career/exports/{export.pk}/file/")
    assert file.status_code == 200
    files = _zip(b"".join(file.streaming_content))
    assert list(files) == ["Ахметова_Алия_профтест.docx"]
    assert "Направления" in [p.text for p in _document(files["Ахметова_Алия_профтест.docx"]).paragraphs]
    # колокольчик: «Файлы готовы» со ссылкой на окно с файлом
    from core.models import Notification

    note = Notification.objects.get(recipient=teacher, kind=Notification.Kind.JOB_DONE, text__startswith="Файлы готовы")
    assert note.text == "Файлы готовы: Word профтеста — группа BOSTON" and f"export={export.pk}" in note.link
    # журнал — только по ученику, чей файл в архиве
    assert list(AuditLog.objects.filter(field_name="career_export").values_list("student_id", flat=True)) == [
        pupils["aliya"].pk
    ]


def test_one_selected_student_with_translation_gets_a_docx_not_a_zip(analysed, teacher, pupils, fake):
    from career.models import CareerExport

    fake(FakeProvider(KK))
    client = login(teacher)
    assert _start(client, language="kk", students=[pupils["aliya"].pk]).status_code == 202
    export = CareerExport.objects.get()
    assert export.file_name == "Ахметова_Алия_профтест.docx" and export.language == "kk"
    payload = b"".join(client.get(f"/api/career/exports/{export.pk}/file/").streaming_content)
    assert "Ең күшті қызығушылық — биология." in "\n".join(p.text for p in _document(payload).paragraphs)


class FailsFirst(FakeProvider):
    """Первый вызов модели не получается, остальные — да."""

    def complete(self, **kwargs):
        if not self.calls:
            self.calls.append(kwargs)
            from suggestions.providers import LLMUnavailable

            raise LLMUnavailable("провайдер вернул 503")
        return super().complete(**kwargs)


def test_failed_translation_of_one_student_does_not_break_the_archive(both_analysed, teacher, pupils, boston, fake):
    from career.models import CareerExport

    fake(FailsFirst(KK))
    client = login(teacher)
    assert _start(client, language="kk", group=boston.pk).status_code == 202
    export = CareerExport.objects.get()
    assert export.status == "done"
    files = _zip(b"".join(client.get(f"/api/career/exports/{export.pk}/file/").streaming_content))
    assert sorted(files) == ["Ахметова_Алия_профтест.docx", "Сериков_Дамир_профтест.docx"]
    lines = export.outcome.split("\n")
    assert lines[0] == "Готово 2"
    assert lines[1].startswith("Ахметова А.: перевод не получился") and "файл на языке разбора" in lines[1]
    first = "\n".join(p.text for p in _document(files["Ахметова_Алия_профтест.docx"]).paragraphs)
    second = "\n".join(p.text for p in _document(files["Сериков_Дамир_профтест.docx"]).paragraphs)
    assert "Направления" in first, "у Алии — на русском"
    assert "Бағыттар" in second, "у Дамира — перевод"


class CancelsDuringCall(FakeProvider):
    """Пока модель переводит, подготовку отменяют."""

    def complete(self, **kwargs):
        from core import jobs
        from core.models import BackgroundJob

        job = BackgroundJob.objects.get(kind="career_export")
        jobs.cancel(job, by=job.owner)
        return super().complete(**kwargs)


def test_cancelled_preparation_keeps_no_file(both_analysed, teacher, boston, fake):
    from career.models import CareerExport
    from core.models import BackgroundJob

    fake(CancelsDuringCall(KK))
    _start(login(teacher), language="kk", group=boston.pk)
    export = CareerExport.objects.get()
    assert export.status == "cancelled" and not export.file
    assert BackgroundJob.objects.get(kind="career_export").status == BackgroundJob.Status.CANCELLED
    assert not CareerAnalysis.objects.filter(translations__isnull=False).exists(), "поздний ответ не сохранён"


def test_second_start_of_the_same_preparation_leads_to_the_running_one(analysed, teacher, pupils, boston):
    from career.models import CareerExport
    from core import jobs

    job = jobs.start(user=teacher, kind="career_export", title="Word", task_id="t-1")
    running = CareerExport.objects.create(
        owner=teacher, job=job, group=boston, whole_group=True, language="kk", total=2
    )
    response = _start(login(teacher), language="kk", group=boston.pk)
    assert response.status_code == 200 and response.json()["already"] is True
    assert response.json()["export"]["id"] == running.pk and CareerExport.objects.count() == 1


def test_only_the_owner_and_admin_download_the_prepared_file(analysed, teacher, admin, pupils, boston, make_user):
    from career.models import CareerExport

    _start(login(teacher), language="ru", group=boston.pk)
    export = CareerExport.objects.get()
    assert login(admin).get(f"/api/career/exports/{export.pk}/file/").status_code == 200
    from academics.models import TeacherProfile

    colleague = make_user(Role.TEACHER, "second.career@example.kz", full_name="Второй Профориентатор")
    TeacherProfile.objects.create(user=colleague).subjects.set([teacher.teacher_profile.subjects.first()])
    assert login(colleague).get(f"/api/career/exports/{export.pk}/file/").status_code == 404
    assert login(colleague).get(f"/api/career/exports/{export.pk}/").status_code == 404


def test_prepared_file_is_kept_for_the_school_rule_days_then_deleted(analysed, teacher, boston):
    import datetime as dt

    from django.utils import timezone

    from career import exports
    from career.models import CareerExport

    client = login(teacher)
    _start(client, language="ru", group=boston.pk)
    export = CareerExport.objects.get()
    assert abs((export.expires_at - export.finished_at) - dt.timedelta(days=7)) < dt.timedelta(seconds=1)
    path = export.file.path
    CareerExport.objects.filter(pk=export.pk).update(expires_at=timezone.now() - dt.timedelta(minutes=1))
    assert exports.purge() == 1
    export.refresh_from_db()
    assert export.status == "expired" and not export.file
    import os

    assert not os.path.exists(path)
    response = client.get(f"/api/career/exports/{export.pk}/file/")
    assert response.status_code == 404 and "срок хранения" in response.json()["detail"]
