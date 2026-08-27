"""Фаза 35: за какой домен действовал автор правки.

Файлы теперь грузит только администратор, по всем пяти доменам. Каждая
его правка помечается доменом, за который он действовал, — чтобы владелец
домена видел в истории, откуда взялось значение, которое он не вносил.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_phase34_auditlog_actor_title"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="acting_for",
            field=models.CharField(blank=True, max_length=32, verbose_name="За домен"),
        ),
    ]
