"""Фаза 62: проверка документов и заметки куратора.

У документа появляются статус («ждёт проверки / подтверждён / отклонён»),
причина отклонения и снимок проверившего. Документы, загруженные до этой
фазы, получают «ждёт проверки» и строку в очереди домена «Документы»:
иначе они висели бы непроверенными без единого места, где их проверить.
Строки очереди заводятся здесь же, `RunPython`; откат их убирает.
Домены сами документы не трогает: аудит правок полей не нужен —
это не правка значения, а появление проверки как таковой.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def queue_existing_documents(apps, schema_editor):
    """Каждому уже загруженному документу — строка очереди проверки."""
    StudentDocument = apps.get_model("students", "StudentDocument")
    Suggestion = apps.get_model("suggestions", "Suggestion")
    SuggestionChange = apps.get_model("suggestions", "SuggestionChange")
    for document in StudentDocument.objects.filter(archived_at__isnull=True).select_related("student"):
        suggestion = Suggestion.objects.create(
            author=document.uploaded_by,
            role="student",
            domain_code="documents",
            source_type="document",
            status="pending",
        )
        SuggestionChange.objects.create(
            suggestion=suggestion,
            student=document.student,
            model_label="students.StudentDocument",
            object_id=str(document.pk),
            field_name="status",
            old_value="pending",
            new_value="confirmed",
            confidence=1,
            is_accepted=True,
        )


def drop_queued_rows(apps, schema_editor):
    Suggestion = apps.get_model("suggestions", "Suggestion")
    Suggestion.objects.filter(source_type="document").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0016_phase61"),
        # строки очереди заводятся здесь — источник «документ» должен уже существовать
        ("suggestions", "0009_phase62"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="studentdocument",
            name="reject_reason",
            field=models.CharField(blank=True, max_length=250, verbose_name="Причина отклонения"),
        ),
        migrations.AddField(
            model_name="studentdocument",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Проверен"),
        ),
        migrations.AddField(
            model_name="studentdocument",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_documents",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Кто проверил",
            ),
        ),
        migrations.AddField(
            model_name="studentdocument",
            name="status",
            field=models.CharField(
                choices=[("pending", "Ждёт проверки"), ("confirmed", "Подтверждён"), ("rejected", "Отклонён")],
                default="pending",
                max_length=16,
                verbose_name="Проверка",
            ),
        ),
        migrations.CreateModel(
            name="CuratorNote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("archived_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="В архиве с")),
                (
                    "archive_batch",
                    models.UUIDField(blank=True, db_index=True, null=True, verbose_name="Номер удаления"),
                ),
                ("author_role", models.CharField(blank=True, max_length=32, verbose_name="Роль автора")),
                ("text", models.TextField(verbose_name="Текст")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создана")),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="curator_notes",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Автор",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="curator_notes",
                        to="students.student",
                        verbose_name="Ученик",
                    ),
                ),
            ],
            options={
                "verbose_name": "Заметка куратора",
                "verbose_name_plural": "Заметки куратора",
                "ordering": ("-created_at", "-id"),
            },
        ),
            migrations.RunPython(queue_existing_documents, drop_queued_rows),
    ]
