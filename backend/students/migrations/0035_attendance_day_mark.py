"""Отметка куратора: «в школе / нет / опоздал» вместо «был / не был»."""

from django.db import migrations, models


def forwards(apps, schema_editor):
    AttendanceDay = apps.get_model("students", "AttendanceDay")
    AttendanceDay.objects.filter(present=False).update(mark="absent")


def backwards(apps, schema_editor):
    AttendanceDay = apps.get_model("students", "AttendanceDay")
    AttendanceDay.objects.filter(mark="absent").update(present=False)


class Migration(migrations.Migration):
    dependencies = [("students", "0034_student_phone")]

    operations = [
        migrations.AddField(
            model_name="attendanceday",
            name="mark",
            field=models.CharField(
                choices=[("present", "в школе"), ("absent", "нет"), ("late", "опоздал")],
                default="present",
                max_length=8,
                verbose_name="Отметка",
            ),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(model_name="attendanceday", name="present"),
    ]
