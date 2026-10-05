"""Старые файлы-списки дают через мастер те же записи и тот же журнал, что давала вкладка «Поля по CSV».

Вкладка с ручным сопоставлением колонок убрана: её файлы — ключ ученика
по почте или логину, произвольные заголовки, один домен на файл — теперь
принимает мастер. Здесь прежний движок (`import_service`) и мастер
(`admission_import`) получают один и тот же файл на одной и той же базе;
сравниваются значения профилей, строки журнала (поле, было, стало, источник,
домен, «за кого», пачка загрузки) и результат отмены загрузки. Эти тесты
написаны до удаления прежнего движка и прошли на нём; после удаления
`run_old` читает его записанный результат — см. `EXPECTED`.
"""

# ruff: noqa: F811 — фикстуры таблицы поступления приходят импортом и стоят параметрами тестов

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from core.audit import to_text
from core.models import AuditLog, ImportBatch
from students import admission_import
from students.models import AdmissionProfile, BehaviorProfile, ExamProfile, SportProfile, Student, TalentProfile
from students.tests.test_admission_import_and_credentials import (  # noqa: F401 — фикстуры той же таблицы
    admin,
    boston,
    chicago,
    klass,
    make_student,
    stranger,
)

pytestmark = pytest.mark.django_db

PROFILES = (BehaviorProfile, AdmissionProfile, ExamProfile, TalentProfile, SportProfile)
SKIP_FIELDS = {"id", "student", "updated_at", "created_at"}


def state() -> dict:
    """Значения всех полей профилей всех учеников — текстом, как в журнале."""
    out = {}
    for model in PROFILES:
        for row in model.objects.select_related("student"):
            for field in model._meta.concrete_fields:
                if field.name in SKIP_FIELDS:
                    continue
                out[f"{row.student.email}|{model._meta.label}.{field.name}"] = to_text(getattr(row, field.name))
    return out


def journal() -> list[tuple]:
    emails = dict(Student.objects.values_list("pk", "email"))
    return sorted(
        (
            emails.get(entry.student_id, ""),
            entry.model_label,
            entry.field_name,
            entry.old_value,
            entry.new_value,
            entry.source,
            entry.domain_code,
            bool(entry.acting_for),
            entry.actor_id,
            entry.import_batch.domain_code if entry.import_batch_id else "",
        )
        for entry in AuditLog.objects.select_related("import_batch")
    )


def batches() -> list[tuple]:
    return sorted((b.domain_code, b.kind, b.file_name, b.rows_updated, b.status) for b in ImportBatch.objects.all())


def sandbox(run) -> dict:
    """Выполнить загрузку и вернуть её след; база после этого — как до неё."""
    point = transaction.savepoint()
    try:
        run()
        loaded = {"state": state(), "journal": journal(), "batches": batches()}
        from core.imports import revert_batch

        for batch in ImportBatch.objects.order_by("pk"):
            revert_batch(batch)
        loaded["after_revert"] = state()
        return loaded
    finally:
        transaction.savepoint_rollback(point)


def as_csv(header: list[str], rows: list[list[str]], name: str = "list.csv") -> SimpleUploadedFile:
    text = "\n".join(",".join(line) for line in [header, *rows]) + "\n"
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


def run_old(header, rows, mapping, domain, actor, name="list.csv"):
    """Как грузила вкладка: предпросмотр по ручному сопоставлению, затем строки без ошибок."""
    from students.import_service import apply_preview, build_preview

    preview = build_preview(header=header, rows=rows, mapping=mapping, domain_code=domain)
    apply_preview(preview_rows=preview.ready_rows, domain_code=domain, actor=actor, file_name=name)


def run_wizard(header, rows, assigned, domain, actor, name="list.csv"):
    """Как грузит мастер: разбор, строки с ошибкой пропущены человеком, один домен выбран."""
    sheets = admission_import.parse(as_csv(header, rows, name), actor=actor, assigned=assigned)
    fixes = {
        f"{sheet.name}:{row.index}": admission_import.Fix(skip=True)
        for sheet in sheets
        for row in sheet.rows
        if row.error
    }
    admission_import.apply(as_csv(header, rows, name), actor=actor, fixes=fixes, domains=[domain], assigned=assigned)


@pytest.fixture
def school(klass, stranger, make_user):
    """Два ученика 11 класса CHICAGO, один BOSTON (с логином) и девятиклассник — с прежними значениями."""
    from students.models import StudyGroup

    junior = make_student(
        StudyGroup.objects.create(code="KIOTO", parallel=9), "Младшев", "Тимур", "j65@example.kz", make_user
    )
    stranger.user.login = "chuzhakov.a"
    stranger.user.save(update_fields=["login"])
    klass[0].exam.ielts_current = "6.0"
    klass[0].exam.save(update_fields=["ielts_current"])
    klass[1].admission.target_country = "США"
    klass[1].admission.save(update_fields=["target_country"])
    return {"first": klass[0], "second": klass[1], "login": stranger, "junior": junior}


def cases(school) -> dict[str, dict]:
    first, second, by_login, junior = school["first"], school["second"], school["login"], school["junior"]
    exam, admission, behavior = "students.ExamProfile.", "students.AdmissionProfile.", "students.BehaviorProfile."
    return {
        # ключ — почта, заголовки узнаются сами; кривое значение, незнакомая почта и пустая клетка
        "ключ по почте": {
            "domain": "exam",
            "header": ["email", "ielts", "sat", "Часов в неделю"],
            "rows": [
                [first.email, "7.0", "1350", "6"],
                [second.email, "12.5", "1200", "4"],
                ["nobody@example.kz", "6.5", "1100", "2"],
                [by_login.email, "6.5", "", "3"],
            ],
            "mapping": {
                "email": "student",
                "ielts": exam + "ielts_current",
                "sat": exam + "sat_current",
                "Часов в неделю": exam + "hours_per_week",
            },
            "assigned": {},
        },
        # ключ — логин в любом регистре; вариант из списка подписью, да/нет словом
        "ключ по логину": {
            "domain": "admission",
            "header": ["логин", "Целевая страна", "Уровень обучения цели", "Кабинет подачи заведён"],
            "rows": [["CHUZHAKOV.A", "Канада", "Бакалавриат", "да"], [second.email, "Германия", "master", "нет"]],
            "mapping": {
                "логин": "student",
                "Целевая страна": admission + "target_country",
                "Уровень обучения цели": admission + "target_level",
                "Кабинет подачи заведён": admission + "has_application_account",
            },
            "assigned": {},
        },
        # заголовки ни на что не похожи: и ключ, и поля назначает человек
        "произвольный заголовок с ручным назначением": {
            "domain": "exam",
            "header": ["кто", "балл", "хотим", "мусор"],
            "rows": [[first.email, "7.5", "8.0", "x"], [by_login.email, "5.5", "6.5", "y"]],
            "mapping": {"кто": "student", "балл": exam + "ielts_current", "хотим": exam + "ielts_target", "мусор": ""},
            "assigned": {"кто": "student_key", "балл": "ielts_current", "хотим": "ielts_target", "мусор": ""},
        },
        # дисциплина у 8–10 ведётся: девятиклассник загружается наравне с выпускником
        "дисциплина у девятиклассника": {
            "domain": "behavior",
            "header": ["email", "Статус по дисциплине", "Замечания за поведение"],
            "rows": [[junior.email, "critical", "3"], [first.email, "Работает самостоятельно", "0"]],
            "mapping": {
                "email": "student",
                "Статус по дисциплине": behavior + "status",
                "Замечания за поведение": behavior + "remarks_count",
            },
            "assigned": {},
        },
        # экзамены у 8–10 не ведутся: строка девятиклассника не применяется ни там, ни там
        "экзамены у девятиклассника": {
            "domain": "exam",
            "header": ["email", "ielts"],
            "rows": [[junior.email, "6.5"], [first.email, "6.5"]],
            "mapping": {"email": "student", "ielts": exam + "ielts_current"},
            "assigned": {},
        },
        # поля, которые есть и в таблице поступления: в списке читаются «как в карточке», как раньше
        "телефон и почта Common App списком": {
            "domain": "admission",
            "header": ["email", "Номер телефона", "Электронный адрес Common App"],
            "rows": [[first.email, "8 707 000 00 00", "ca@example.org"]],
            "mapping": {
                "email": "student",
                "Номер телефона": admission + "student_phone",
                "Электронный адрес Common App": admission + "common_app_email",
            },
            "assigned": {},
        },
    }


CASES = [
    "ключ по почте",
    "ключ по логину",
    "произвольный заголовок с ручным назначением",
    "дисциплина у девятиклассника",
    "экзамены у девятиклассника",
    "телефон и почта Common App списком",
]


@pytest.mark.parametrize("name", CASES)
def test_wizard_gives_the_same_records_and_journal_as_the_old_tab(name, school, admin):
    case = cases(school)[name]
    old = sandbox(lambda: run_old(case["header"], case["rows"], case["mapping"], case["domain"], admin))
    new = sandbox(lambda: run_wizard(case["header"], case["rows"], case["assigned"], case["domain"], admin))
    assert old["journal"], "прежний движок ничего не записал — случай ничего не проверяет"
    assert new["state"] == old["state"], "значения профилей разошлись"
    assert new["journal"] == old["journal"], "журнал изменений разошёлся"
    assert new["batches"] == old["batches"], "пачки загрузки разошлись"
    assert new["after_revert"] == old["after_revert"], "отмена загрузки вернула разное"
