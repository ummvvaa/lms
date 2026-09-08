"""Фаза 59: ЕНТ убран насовсем — в архив, не удалён.

Школа готовит за рубеж и в Назарбаев Университет, ЕНТ никто не сдаёт.
Запись справочника, цели и попытки с этим экзаменом уходят в архив одним
номером удаления; задания банка, уроки теории и пробные с кодом «ENT»
гаснут признаком `is_active` — архива у них нет. Данные не удаляются
(инвариант №13), `reverse` возвращает ровно то, что миграция положила
в архив (по номеру), и включает обратно погашенные записи с кодом «ENT».

Записи `ArchiveEntry` не создаются намеренно: иначе кнопка «Восстановить»
на экране архива вернула бы ЕНТ обратно, а решение владельца — насовсем.
Пишем через `update()`: сохранение объекта поднимает сигналы аудита, и
в журнале появились бы правки без автора. Менеджер — `_base_manager`:
у исторических моделей он единственный, а у настоящих (тест гоняет обе
функции на живых моделях) не фильтрует архив, в отличие от `objects`.
"""

import uuid

from django.db import migrations
from django.utils import timezone

#: один номер удаления на всё, что ушло этой миграцией
BATCH = uuid.UUID("59e0a0e0-0000-4000-8000-00000000e001")
NAME = "ЕНТ"
CODE = "ENT"


def archive_ent(apps, schema_editor):
    ExamKind = apps.get_model("directories", "ExamKind")
    ExamGoal = apps.get_model("students", "ExamGoal")
    ExamAttempt = apps.get_model("students", "ExamAttempt")
    now = timezone.now()

    kinds = ExamKind._base_manager.filter(name=NAME, archived_at__isnull=True)
    kind_ids = list(kinds.values_list("pk", flat=True))
    kinds.update(archived_at=now, archive_batch=BATCH)
    ExamGoal._base_manager.filter(exam_id__in=kind_ids, archived_at__isnull=True).update(
        archived_at=now, archive_batch=BATCH
    )
    ExamAttempt._base_manager.filter(exam_type=CODE, archived_at__isnull=True).update(
        archived_at=now, archive_batch=BATCH
    )

    for label in ("Question", "TheoryLesson", "MockExam"):
        apps.get_model("prep", label)._base_manager.filter(exam_type=CODE).update(is_active=False)


def restore_ent(apps, schema_editor):
    for app, label in (("directories", "ExamKind"), ("students", "ExamGoal"), ("students", "ExamAttempt")):
        apps.get_model(app, label)._base_manager.filter(archive_batch=BATCH).update(
            archived_at=None, archive_batch=None
        )
    for label in ("Question", "TheoryLesson", "MockExam"):
        apps.get_model("prep", label)._base_manager.filter(exam_type=CODE).update(is_active=True)


class Migration(migrations.Migration):
    dependencies = [
        ("directories", "0004_phase59_examkind_archive"),
        ("students", "0015_phase59"),
        ("prep", "0005_phase59"),
    ]

    operations = [migrations.RunPython(archive_ent, restore_ent)]
