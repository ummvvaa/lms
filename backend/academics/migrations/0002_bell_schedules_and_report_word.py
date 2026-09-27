"""Расписания звонков по группам и автор слова куратора (решение владельца, 27.09.2026).

Только добавление: новая таблица расписаний звонков, ссылка звонка на
расписание, автор и время слова в отчёте. Прежние звонки года переходят
в общее расписание «Общее» того же года; уникальность звонка теперь
считается внутри расписания, а не года — иначе двум расписаниям не
завести первый урок.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def default_schedules(apps, schema_editor):
    AcademicYear = apps.get_model("academics", "AcademicYear")
    BellSchedule = apps.get_model("academics", "BellSchedule")
    Bell = apps.get_model("academics", "Bell")
    for year in AcademicYear.objects.all():
        schedule = BellSchedule.objects.filter(year=year, is_default=True).first()
        if schedule is None:
            schedule = BellSchedule.objects.create(year=year, title="Общее", is_default=True)
        Bell.objects.filter(year=year, schedule__isnull=True).update(schedule=schedule)


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0001_initial"),
        ("students", "0028_parent_phones_normalized"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BellSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=60, verbose_name="Название")),
                ("is_default", models.BooleanField(default=False, verbose_name="Общее по умолчанию")),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True, related_name="bell_schedules", to="students.studygroup", verbose_name="Группы"
                    ),
                ),
                (
                    "year",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bell_schedules",
                        to="academics.academicyear",
                        verbose_name="Учебный год",
                    ),
                ),
            ],
            options={
                "verbose_name": "Расписание звонков",
                "verbose_name_plural": "Расписания звонков",
                "ordering": ("year", "-is_default", "title"),
            },
        ),
        migrations.AddConstraint(
            model_name="bellschedule",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_default", True)), fields=("year",), name="one_default_bell_schedule"
            ),
        ),
        migrations.AddField(
            model_name="bell",
            name="schedule",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="bells",
                to="academics.bellschedule",
                verbose_name="Расписание звонков",
            ),
        ),
        migrations.RunPython(default_schedules, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="bell", name="unique_bell_number"),
        migrations.AddConstraint(
            model_name="bell",
            constraint=models.UniqueConstraint(fields=("schedule", "number"), name="unique_bell_in_schedule"),
        ),
        migrations.AddField(
            model_name="parentreport",
            name="word_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Слово написано"),
        ),
        migrations.AddField(
            model_name="parentreport",
            name="word_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Кто написал слово",
            ),
        ),
    ]
