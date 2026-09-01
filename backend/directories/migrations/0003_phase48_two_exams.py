"""Фаза 48: школа ведёт два экзамена — SAT и IELTS.

Остальные пять убраны из виду признаком показа, а не удалены: внесённые
по ним баллы, цели и попытки целы, и понадобится ЕНТ — включается
галочкой на экране «Экзамены», без выката.
"""

from __future__ import annotations

from django.db import migrations

#: что школа показывает сейчас; остальное прячется
VISIBLE = ("SAT", "IELTS")


def hide_extra_exams(apps, schema_editor):
    ExamKind = apps.get_model("directories", "ExamKind")
    ExamKind.objects.exclude(name__in=VISIBLE).update(is_active=False)
    ExamKind.objects.filter(name__in=VISIBLE).update(is_active=True)


def show_all_exams(apps, schema_editor):
    ExamKind = apps.get_model("directories", "ExamKind")
    ExamKind.objects.update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [("directories", "0002_phase39_exam_kinds")]

    operations = [migrations.RunPython(hide_extra_exams, show_all_exams)]
