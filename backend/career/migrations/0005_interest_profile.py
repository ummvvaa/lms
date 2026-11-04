"""Подробный разбор: профиль интересов по всем шкалам теста.

Только добавляет: новая таблица шкал разбора и новый номер правил по умолчанию
для новых разборов. Готовые разборы не трогаются — у них профиля нет,
и они открываются как есть, с плашкой «по старым правилам».
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("career", "0004_abroad_rules"),
    ]

    operations = [
        migrations.AlterField(
            model_name="careeranalysis",
            name="rules",
            field=models.PositiveSmallIntegerField(default=3, verbose_name="Правила разбора"),
        ),
        migrations.CreateModel(
            name="CareerAnalysisScale",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveSmallIntegerField(default=1, verbose_name="Порядок")),
                ("test_title", models.CharField(max_length=200, verbose_name="Тест")),
                ("title", models.CharField(max_length=120, verbose_name="Шкала")),
                ("score", models.SmallIntegerField(verbose_name="Балл")),
                ("top", models.SmallIntegerField(default=0, verbose_name="Наибольший балл")),
                ("label", models.CharField(blank=True, max_length=120, verbose_name="Подпись диапазона")),
                ("meaning", models.TextField(blank=True, verbose_name="Что это значит")),
                ("meaning_student", models.TextField(blank=True, verbose_name="Что это значит — для ученика")),
                (
                    "analysis",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="scales", to="career.careeranalysis"
                    ),
                ),
            ],
            options={
                "verbose_name": "Шкала профиля интересов",
                "verbose_name_plural": "Профиль интересов",
                "ordering": ("order", "id"),
            },
        ),
    ]
