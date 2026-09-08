"""Фаза 61: задача знает, кто её поставил и кто закрыл.

`author_role` — роль автора снимком: ученику показывается «от куратора»,
а не имя (имени куратора он не видит нигде, фаза 60), и запись переживает
смену роли у человека. `closed_by` — кто закрыл: ученик сам или куратор.
Статус «отменена» — задача перестала быть нужной: не «готово» (XP за неё
не начисляется, инвариант №12) и не удаление (ученик её уже видел).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("roadmap", "0008_phase49"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="author_role",
            field=models.CharField(blank=True, max_length=32, verbose_name="Роль автора"),
        ),
        migrations.AddField(
            model_name="task",
            name="closed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="closed_tasks",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Кто закрыл",
            ),
        ),
        migrations.AlterField(
            model_name="task",
            name="status",
            field=models.CharField(
                choices=[
                    ("todo", "Сделать"),
                    ("in_progress", "В работе"),
                    ("review", "На проверке"),
                    ("done", "Готово"),
                    ("cancelled", "Отменена"),
                ],
                default="todo",
                max_length=16,
                verbose_name="Статус",
            ),
        ),
    ]
