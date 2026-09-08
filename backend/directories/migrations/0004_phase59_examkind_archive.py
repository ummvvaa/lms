# Фаза 59: архив у справочника экзаменов — единственный справочник с мягким
# удалением: экзамен тянет за собой цели и баллы (см. docs/DECISIONS.md)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("directories", "0003_phase48_two_exams"),
    ]

    operations = [
        migrations.AddField(
            model_name="examkind",
            name="archive_batch",
            field=models.UUIDField(blank=True, db_index=True, null=True, verbose_name="Номер удаления"),
        ),
        migrations.AddField(
            model_name="examkind",
            name="archived_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="В архиве с"),
        ),
    ]
