from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0022_import_upload_kinds"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UsageEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_id", models.UUIDField(unique=True, verbose_name="Идентификатор события")),
                ("role", models.CharField(max_length=32, verbose_name="Роль на момент действия")),
                ("action", models.CharField(max_length=64, verbose_name="Действие")),
                ("screen", models.CharField(max_length=64, verbose_name="Экран")),
                ("occurred_at", models.DateTimeField(verbose_name="Когда")),
                ("source", models.CharField(choices=[("server", "Сервер"), ("client", "Интерфейс")], max_length=6, verbose_name="Источник")),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="usage_events", to=settings.AUTH_USER_MODEL, verbose_name="Пользователь")),
            ],
            options={
                "verbose_name": "Действие пользователя",
                "verbose_name_plural": "Действия пользователей",
                "ordering": ("-occurred_at", "-pk"),
                "indexes": [models.Index(fields=["occurred_at", "action"], name="usage_time_action_idx")],
            },
        ),
    ]
