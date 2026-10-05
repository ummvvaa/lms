"""Файл-список для тестов: поля профилей загружает мастер импорта.

Раньше такие загрузки делал `import_service.apply_preview` — движок вкладки
«Поля по CSV». Вкладка убрана, и тесты истории загрузок, отмены и границ
домена получают загрузку тем же путём, каким её делает человек: файл с ключом
«почта или логин», колонки назначены полям реестра, домен выбран.
"""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import AuditLog, ImportBatch
from students import admission_import, import_registry
from students.models import Student


def load_list(*, preview_rows: list[dict], domain_code: str, actor=None, file_name: str = "list.csv") -> dict:
    """Загрузить строки «ученик — поле — значение» мастером за один домен.

    `preview_rows` — как их отдавал прежний предпросмотр: `student` и
    `changes` с `model`, `field` и `raw`. Возвращает номер пачки домена
    и сколько значений записано.
    """
    targets: list[str] = []
    for row in preview_rows:
        for change in row.get("changes", []):
            target = f"{change['model']}.{change['field']}"
            if target not in targets:
                targets.append(target)
    lines = [",".join(["email", *targets])]
    for row in preview_rows:
        student = Student.all_objects.filter(pk=row.get("student")).select_related("user").first()
        key = (student.email or getattr(student.user, "login", "")) if student else f"nobody-{row.get('student')}"
        cells = {f"{c['model']}.{c['field']}": str(c.get("raw", c.get("new", ""))) for c in row.get("changes", [])}
        lines.append(",".join([key, *[cells.get(target, "") for target in targets]]))
    content = ("\n".join(lines) + "\n").encode("utf-8")
    assigned = {
        target: import_registry.FIELD_TARGETS[target].key if target in import_registry.FIELD_TARGETS else ""
        for target in targets
    }

    def upload():
        return SimpleUploadedFile(file_name, content, content_type="text/csv")

    before = set(ImportBatch.objects.values_list("pk", flat=True))
    sheets = admission_import.parse(upload(), actor=actor, assigned=assigned)
    fixes = {
        f"{sheet.name}:{row.index}": admission_import.Fix(skip=True)
        for sheet in sheets
        for row in sheet.rows
        if row.error
    }
    rejected = [{"student": row.student, "reason": row.error} for sheet in sheets for row in sheet.rows if row.error]
    admission_import.apply(upload(), actor=actor, fixes=fixes, domains=[domain_code], assigned=assigned)
    batch = ImportBatch.objects.exclude(pk__in=before).filter(domain_code=domain_code).first()
    entries = AuditLog.objects.filter(import_batch=batch).count() if batch else 0
    return {"batch": batch.pk if batch else None, "applied": entries, "audit_entries": entries, "rejected": rejected}
