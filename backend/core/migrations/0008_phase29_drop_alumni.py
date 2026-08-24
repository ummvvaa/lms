"""Фаза 29: каталог выпускников и менторство убраны из системы.

Приложение `alumni` удалено целиком — вместе с моделями, эндпойнтами
и экраном. Здесь остаётся только уборка за ним: таблицы в базе живут
своей жизнью и после удаления кода никуда не денутся сами.

`IF EXISTS` и `CASCADE` намеренно: контур, поднятый после удаления кода,
этих таблиц не увидит вовсе, а на боевом их держат внешние ключи между
собой. Записи в `django_migrations` тоже убираем — иначе Django будет
считать, что приложение просто отключили, и при возврате имени `alumni`
попытается накатить миграции поверх удалённых таблиц.

Обратного хода нет и быть не может: восстановить удалённые таблицы
из миграции нельзя, данные в них не хранятся нигде ещё.
"""

from django.db import migrations

TABLES = (
    "alumni_archivedessay",
    "alumni_mentorshipmeeting",
    "alumni_mentorshiprequest",
    "alumni_alumnusapplication",
    "alumni_alumnus",
)

DROP = "\n".join(f'DROP TABLE IF EXISTS "{name}" CASCADE;' for name in TABLES)
FORGET = "DELETE FROM django_migrations WHERE app = 'alumni';"


class Migration(migrations.Migration):
    dependencies = [("core", "0007_phase28_purge")]

    operations = [
        migrations.RunSQL(sql=DROP + "\n" + FORGET, reverse_sql=migrations.RunSQL.noop),
    ]
