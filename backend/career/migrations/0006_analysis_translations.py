"""Выгрузка разборов в Word: перевод разбора по языку и общая картина по тестам.

Только добавляет таблицы: перевод хранится рядом с разбором, оригинал не трогается.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("career", "0005_interest_profile"),
        ("students", "0035_attendance_day_mark"),
    ]

    operations = [
        migrations.CreateModel(
            name="CareerAnalysisTranslation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("language", models.CharField(max_length=2, verbose_name="Язык")),
                ("summary", models.TextField(blank=True, verbose_name="Общий вывод")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Переведён")),
                (
                    "analysis",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="translations",
                        to="career.careeranalysis",
                    ),
                ),
            ],
            options={
                "verbose_name": "Перевод разбора",
                "verbose_name_plural": "Переводы разборов",
            },
        ),
        migrations.CreateModel(
            name="CareerDirectionTranslation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveSmallIntegerField(verbose_name="Порядок")),
                ("title", models.CharField(blank=True, max_length=150, verbose_name="Направление")),
                ("reasoning", models.TextField(blank=True, verbose_name="Почему подходит")),
                ("professions", models.TextField(blank=True, verbose_name="Профессии")),
                ("exams", models.TextField(blank=True, verbose_name="Что сдавать для поступления")),
                ("subjects", models.TextField(blank=True, verbose_name="Что подтянуть в школе")),
                ("next_steps", models.TextField(blank=True, verbose_name="Что сделать уже сейчас")),
                (
                    "translation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="directions",
                        to="career.careeranalysistranslation",
                    ),
                ),
            ],
            options={
                "verbose_name": "Направление в переводе",
                "verbose_name_plural": "Направления в переводе",
                "ordering": ("order", "id"),
            },
        ),
        migrations.CreateModel(
            name="CareerOverview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("language", models.CharField(max_length=2, verbose_name="Язык")),
                ("basis", models.CharField(max_length=400, verbose_name="По каким разборам")),
                ("repeats", models.TextField(blank=True, verbose_name="Что повторяется в разных тестах")),
                ("agreements", models.TextField(blank=True, verbose_name="Где тесты согласуются")),
                ("differences", models.TextField(blank=True, verbose_name="Где тесты расходятся")),
                (
                    "confirmed",
                    models.TextField(blank=True, verbose_name="Какие направления подтверждаются несколькими тестами"),
                ),
                ("created_at", models.DateTimeField(verbose_name="Написана")),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="career_overviews",
                        to="students.student",
                    ),
                ),
            ],
            options={
                "verbose_name": "Общая картина по тестам",
                "verbose_name_plural": "Общие картины по тестам",
            },
        ),
        migrations.CreateModel(
            name="CareerScaleTranslation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveSmallIntegerField(verbose_name="Порядок")),
                ("test_title", models.CharField(blank=True, max_length=200, verbose_name="Тест")),
                ("title", models.CharField(blank=True, max_length=120, verbose_name="Шкала")),
                ("label", models.CharField(blank=True, max_length=120, verbose_name="Подпись диапазона")),
                ("meaning", models.TextField(blank=True, verbose_name="Что это значит")),
                (
                    "translation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scales",
                        to="career.careeranalysistranslation",
                    ),
                ),
            ],
            options={
                "verbose_name": "Шкала в переводе",
                "verbose_name_plural": "Шкалы в переводе",
                "ordering": ("order", "id"),
            },
        ),
        migrations.AddConstraint(
            model_name="careeranalysistranslation",
            constraint=models.UniqueConstraint(
                fields=("analysis", "language"), name="uniq_career_translation_language"
            ),
        ),
        migrations.AddConstraint(
            model_name="careeroverview",
            constraint=models.UniqueConstraint(fields=("student", "language"), name="uniq_career_overview_language"),
        ),
    ]
