"""Общего расписания звонков больше нет (решение владельца, 05.10.2026).

У каждой группы свои звонки; группа без них — ошибка в «Расписании», а не
молчаливая общая сетка. Запись «Общее» разбирается по данным: группы, которые
жили по ней (активные, без своего расписания в этом году), получают её своим
расписанием — время их уроков не меняется, дальше школа переименует или
разделит её сама. Если по ней не жила ни одна группа, она удаляется вместе
со своими звонками. Звонки без расписания (остаток времён одной сетки на
год) уходят в «Общее» своего года, а где его нет — удаляются: календарь их
и раньше не читал.
"""

from django.db import migrations


def settle_common(apps, schema_editor):
    BellSchedule = apps.get_model("academics", "BellSchedule")
    Bell = apps.get_model("academics", "Bell")
    StudyGroup = apps.get_model("students", "StudyGroup")
    Through = BellSchedule.groups.through
    for common in BellSchedule.objects.filter(is_default=True):
        Bell.objects.filter(year_id=common.year_id, schedule__isnull=True).update(schedule=common)
        own = Through.objects.filter(bellschedule__year_id=common.year_id, bellschedule__is_default=False)
        bare = StudyGroup.objects.filter(is_active=True, archived_at__isnull=True).exclude(
            pk__in=own.values("studygroup_id")
        )
        Through.objects.filter(bellschedule_id=common.pk).delete()
        rows = [Through(bellschedule_id=common.pk, studygroup_id=pk) for pk in bare.values_list("pk", flat=True)]
        if rows:
            Through.objects.bulk_create(rows)
        else:
            BellSchedule.objects.filter(pk=common.pk).delete()
    Bell.objects.filter(schedule__isnull=True).delete()
    # отложенные проверки связей удалённых и добавленных строк — сейчас: иначе
    # PostgreSQL не даст изменить таблицу в той же транзакции («pending trigger events»)
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0008_subject_title_en"),
        ("students", "0033_author_trails_of_uploads"),
    ]

    operations = [
        migrations.RunPython(settle_common, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="bellschedule", name="one_default_bell_schedule"),
        migrations.AlterModelOptions(
            name="bellschedule",
            options={
                "ordering": ("year", "title"),
                "verbose_name": "Расписание звонков",
                "verbose_name_plural": "Расписания звонков",
            },
        ),
        migrations.RemoveField(model_name="bellschedule", name="is_default"),
    ]
