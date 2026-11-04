"""Выгрузка разборов в Word: подготовленный файл хранится строкой с итогом и сроком хранения."""

import career.models
import django.db.models.deletion
import materials.storage
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("career", "0006_analysis_translations"),
        ("core", "0026_background_job_queue_and_cancel"),
        ("students", "0035_attendance_day_mark"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CareerExport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("whole_group", models.BooleanField(default=False, verbose_name="Вся группа")),
                ("language", models.CharField(max_length=2, verbose_name="Язык")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("running", "Готовится"),
                            ("done", "Готов"),
                            ("failed", "Не получился"),
                            ("cancelled", "Отменён"),
                            ("expired", "Удалён по сроку"),
                        ],
                        default="running",
                        max_length=10,
                        verbose_name="Состояние",
                    ),
                ),
                ("total", models.PositiveSmallIntegerField(default=0, verbose_name="Учеников")),
                ("done", models.PositiveSmallIntegerField(default=0, verbose_name="Готово")),
                (
                    "file",
                    models.FileField(
                        blank=True,
                        max_length=300,
                        storage=materials.storage.private_storage,
                        upload_to=career.models.export_upload_to,
                        verbose_name="Файл",
                    ),
                ),
                ("file_name", models.CharField(blank=True, max_length=200, verbose_name="Имя файла")),
                ("outcome", models.TextField(blank=True, verbose_name="Итог")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Запущен")),
                ("finished_at", models.DateTimeField(blank=True, null=True, verbose_name="Готов")),
                ("expires_at", models.DateTimeField(blank=True, null=True, verbose_name="Хранится до")),
                (
                    "group",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="career_exports",
                        to="students.studygroup",
                    ),
                ),
                (
                    "job",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="career_exports",
                        to="core.backgroundjob",
                        verbose_name="Запуск",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="career_exports",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Кто запустил",
                    ),
                ),
            ],
            options={
                "verbose_name": "Выгрузка разборов в Word",
                "verbose_name_plural": "Выгрузки разборов в Word",
                "ordering": ("-created_at", "-id"),
            },
        ),
    ]
