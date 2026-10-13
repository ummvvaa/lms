"""Предмет журнала — в предметы учителя.

Предметы профиля стали единственным источником «ведёт профориентацию»
(`career.rights`, решение владельца, 13.10.2026). Учитель, которому журнал
достался расписанием или передачей без предмета в карточке, не должен
потерять раздел: его предметы дописываются по действующим журналам.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    Course = apps.get_model("academics", "Course")
    TeacherProfile = apps.get_model("academics", "TeacherProfile")
    rows = (
        Course.objects.filter(archived_at__isnull=True, teacher__isnull=False, subject__in_lms=True)
        .values_list("teacher_id", "subject_id")
        .distinct()
    )
    for teacher_id, subject_id in rows:
        profile, _ = TeacherProfile.objects.get_or_create(user_id=teacher_id)
        if not profile.subjects.filter(pk=subject_id).exists():
            profile.subjects.add(subject_id)


class Migration(migrations.Migration):
    dependencies = [("academics", "0011_subject_is_career")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
