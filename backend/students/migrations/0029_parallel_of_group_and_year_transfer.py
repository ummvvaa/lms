from django.conf import settings
from django.db import migrations, models


def every_group_is_eleven(apps, schema_editor):
    """Все существующие группы — 11: школа до этого вела только выпускников.

    Старое поле класса могло хранить что угодно (API принимал его молча),
    а поступление у группы должно остаться ровно таким, каким было.
    """
    apps.get_model("students", "StudyGroup").objects.update(parallel=11)


class Migration(migrations.Migration):
    """Параллель у группы вместо класса, почта ученика необязательна,
    код группы уникален среди действующих, перевод на следующий год.

    `grade` группы переименовывается, и всем существующим группам ставится
    11 — школа до сих пор вела только выпускников.
    """

    dependencies = [
        ("students", "0028_parent_phones_normalized"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveIndex(model_name="student", name="students_st_grade_39b9da_idx"),
        migrations.RemoveField(model_name="student", name="grade"),
        migrations.RenameField(model_name="studygroup", old_name="grade", new_name="parallel"),
        migrations.AlterField(
            model_name="studygroup",
            name="parallel",
            field=models.PositiveSmallIntegerField(
                choices=[(8, "8"), (9, "9"), (10, "10"), (11, "11")], default=11, verbose_name="Параллель"
            ),
        ),
        migrations.RunPython(every_group_is_eleven, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="student",
            name="email",
            field=models.EmailField(blank=True, max_length=254, null=True, unique=True, verbose_name="Email"),
        ),
        migrations.AlterField(
            model_name="studygroup",
            name="code",
            field=models.CharField(max_length=16, verbose_name="Код"),
        ),
        migrations.AddConstraint(
            model_name="studygroup",
            constraint=models.UniqueConstraint(
                condition=models.Q(("archived_at__isnull", True)),
                fields=("code",),
                name="group_code_unique_among_active",
            ),
        ),
        migrations.CreateModel(
            name="YearTransfer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("school_year", models.CharField(max_length=9, unique=True, verbose_name="Учебный год")),
                ("done_at", models.DateTimeField(auto_now_add=True, verbose_name="Когда")),
                ("actor_title", models.CharField(blank=True, max_length=200, verbose_name="Кто перевёл, текстом")),
                ("groups_moved", models.PositiveSmallIntegerField(default=0, verbose_name="Групп переведено")),
                ("students_moved", models.PositiveIntegerField(default=0, verbose_name="Учеников переведено")),
                ("groups_graduated", models.PositiveSmallIntegerField(default=0, verbose_name="Групп выпущено")),
                ("students_graduated", models.PositiveIntegerField(default=0, verbose_name="Учеников выпущено")),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="year_transfers",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Кто перевёл",
                    ),
                ),
            ],
            options={
                "verbose_name": "Перевод на следующий год",
                "verbose_name_plural": "Переводы на следующий год",
                "ordering": ("-done_at",),
            },
        ),
    ]
