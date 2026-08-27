"""Фаза 36: снятие блокировки входа администратором.

Попытка остаётся в журнале, но помечается снятой и в серию неудач
больше не входит.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_phase29_temp_password"),
    ]

    operations = [
        migrations.AddField(
            model_name="loginattempt",
            name="cleared_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Снята"),
        ),
        migrations.AddField(
            model_name="loginattempt",
            name="cleared_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cleared_login_attempts",
                to="accounts.user",
                verbose_name="Кто снял",
            ),
        ),
    ]
