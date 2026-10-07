from django.db import migrations, models


def classify_uploads(apps, schema_editor):
    batch_model = apps.get_model("core", "ImportBatch")
    audit_model = apps.get_model("core", "AuditLog")
    alias = schema_editor.connection.alias
    for batch in batch_model.objects.using(alias).filter(kind="students").iterator():
        labels = set(
            audit_model.objects.using(alias)
            .filter(import_batch_id=batch.pk)
            .order_by()
            .values_list("model_label", flat=True)
            .distinct()
        )
        # Без журнала или при нескольких моделях происхождение не доказано.
        kind = None
        if batch.domain_code == "behavior" and labels == {"students.ParentContact"}:
            kind = "contacts"
        elif batch.domain_code == "sport" and labels == {"students.Competition"}:
            kind = "competitions"
        if kind:
            batch_model.objects.using(alias).filter(pk=batch.pk).update(kind=kind)


def restore_general_kind(apps, schema_editor):
    apps.get_model("core", "ImportBatch").objects.using(schema_editor.connection.alias).filter(
        kind__in=("contacts", "competitions")
    ).update(kind="students")


class Migration(migrations.Migration):
    dependencies = [("core", "0021_author_trails_of_uploads")]

    operations = [
        migrations.AlterField(
            model_name="importbatch",
            name="kind",
            field=models.CharField(
                choices=[
                    ("students", "Данные учеников"),
                    ("contacts", "Контакты родителей"),
                    ("competitions", "Соревнования"),
                    ("requirements", "Требования вузов"),
                    ("questions", "Банк заданий"),
                    ("scholarships", "Стипендии"),
                ],
                default="students",
                max_length=16,
                verbose_name="Что загружали",
            ),
        ),
        migrations.RunPython(classify_uploads, restore_general_kind),
    ]
