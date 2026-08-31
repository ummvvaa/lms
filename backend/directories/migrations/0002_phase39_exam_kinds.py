"""Справочник экзаменов с семью стартовыми записями (фаза 39).

Семь экзаменов заводятся данными миграции: это справочник, а не выдуманные
ученики (инвариант №8 не задевается), и ЕНТ обязан быть в списке наравне
с международными — для казахстанской школы это не второстепенный экзамен.
Директор пополняет и правит список со своего экрана.
"""

from django.db import migrations, models

SEED = (
    ("IELTS", 0, 9, 10),
    ("TOEFL", 0, 120, 20),
    ("SAT", 400, 1600, 30),
    ("ACT", 1, 36, 40),
    ("ЕНТ", 0, 140, 50),
    ("Duolingo", 10, 160, 60),
    ("HSK", 1, 6, 70),
)


def seed_exams(apps, schema_editor):
    ExamKind = apps.get_model("directories", "ExamKind")
    for name, low, high, order in SEED:
        ExamKind.objects.get_or_create(
            name=name, defaults={"min_score": low, "max_score": high, "sort_order": order}
        )


def unseed_exams(apps, schema_editor):
    ExamKind = apps.get_model("directories", "ExamKind")
    ExamKind.objects.filter(name__in=[row[0] for row in SEED], goals__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("directories", "0001_phase18_directories"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExamKind",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True, verbose_name="Название")),
                ("description", models.TextField(blank=True, verbose_name="Описание")),
                ("is_active", models.BooleanField(default=True, verbose_name="Показывать в списке выбора")),
                ("sort_order", models.PositiveSmallIntegerField(default=100, verbose_name="Порядок")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                (
                    "min_score",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=6, null=True, verbose_name="Минимум шкалы"
                    ),
                ),
                (
                    "max_score",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=6, null=True, verbose_name="Максимум шкалы"
                    ),
                ),
            ],
            options={
                "verbose_name": "Экзамен",
                "verbose_name_plural": "Экзамены",
                "ordering": ("sort_order", "name"),
                "abstract": False,
            },
        ),
        migrations.RunPython(seed_exams, unseed_exams),
    ]
