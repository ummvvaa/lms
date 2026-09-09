"""Фаза 63: пробники файлом и секции IELTS.

Одна загрузка — одна строка `MockImport` с файлом учителя; попытки
ссылаются на неё и уходят вместе с ней в архив (каскад). Ограничение
«один пробник экзамена на группу и дату» условное: архивная загрузка
дорогу новой не закрывает — иначе перезалить исправленный файл было бы
нечем. Данные миграция не трогает: у прежних мок-попыток ссылки нет,
и это правда — их вносили руками, а не файлом.
"""

import django.db.models.deletion
import students.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0017_phase62"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MockImport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("archived_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="В архиве с")),
                (
                    "archive_batch",
                    models.UUIDField(blank=True, db_index=True, null=True, verbose_name="Номер удаления"),
                ),
                (
                    "exam_type",
                    models.CharField(
                        choices=[
                            ("IELTS", "IELTS"),
                            ("TOEFL", "TOEFL"),
                            ("SAT", "SAT"),
                            ("ACT", "ACT"),
                            ("Duolingo", "Duolingo"),
                            ("HSK", "HSK"),
                        ],
                        max_length=8,
                        verbose_name="Экзамен",
                    ),
                ),
                ("date", models.DateField(verbose_name="Дата пробника")),
                ("teacher", models.CharField(blank=True, max_length=200, verbose_name="Кто проверял")),
                (
                    "file",
                    models.FileField(
                        max_length=300,
                        storage=students.models._mock_storage,
                        upload_to=students.models.mock_upload_to,
                        verbose_name="Файл",
                    ),
                ),
                ("file_name", models.CharField(blank=True, max_length=250, verbose_name="Имя файла")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Когда загружен")),
                ("rows_total", models.PositiveIntegerField(default=0, verbose_name="Строк в файле")),
                ("rows_applied", models.PositiveIntegerField(default=0, verbose_name="Записано результатов")),
                ("rows_skipped", models.PositiveIntegerField(default=0, verbose_name="Пропущено строк")),
                ("skipped_report", models.TextField(blank=True, verbose_name="Пропущенные строки")),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mock_imports",
                        to="students.studygroup",
                        verbose_name="Группа",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="mock_imports",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Кто загрузил",
                    ),
                ),
            ],
            options={
                "verbose_name": "Загрузка пробника",
                "verbose_name_plural": "Загрузки пробников",
                "ordering": ("-date", "-created_at"),
            },
        ),
        migrations.AddField(
            model_name="examattempt",
            name="mock_import",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="attempts",
                to="students.mockimport",
                verbose_name="Загрузка пробника",
            ),
        ),
        migrations.AddConstraint(
            model_name="mockimport",
            constraint=models.UniqueConstraint(
                condition=models.Q(("archived_at__isnull", True)),
                fields=("exam_type", "group", "date"),
                name="unique_active_mock_import",
            ),
        ),
    ]
