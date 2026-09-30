"""Ученикам — язык их группы; тем, у кого интерфейс сменится, — уведомление.

До этой миграции в выборе был один русский, и интерфейс у всех был русским,
что бы ни лежало в профиле. Теперь три языка открыты: ученик казахской группы
увидит казахский интерфейс и при входе один раз прочитает, что язык сменила
школа и где его вернуть. Ученикам русских групп интерфейс не меняется —
уведомлять не о чем. Сотрудников миграция не трогает.
"""

from django.db import migrations, models


def adopt_group_language(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Student = apps.get_model("students", "Student")
    for language in ("kk", "ru"):
        users = Student._default_manager.filter(user__isnull=False, group__language=language).values("user_id")
        User._default_manager.filter(pk__in=users, role="student").update(
            language=language, language_notice=language != "ru"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_user_phone"),
        ("students", "0031_computed_homework_completion"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="language_notice",
            field=models.BooleanField(default=False, verbose_name="Показать уведомление о языке"),
        ),
        migrations.RunPython(adopt_group_language, migrations.RunPython.noop),
    ]
