"""Телефоны родителей приводятся к `+7XXXXXXXXXX` — только однозначные."""

from django.db import migrations


def normalize(apps, schema_editor):
    from students.phones import normalize_kz

    ParentContact = apps.get_model("students", "ParentContact")
    for row in ParentContact.objects.exclude(phone="").only("pk", "phone"):
        fixed = normalize_kz(row.phone)
        if fixed != row.phone:
            ParentContact.objects.filter(pk=row.pk).update(phone=fixed[:32])


class Migration(migrations.Migration):
    dependencies = [("students", "0027_competition_in_card_and_school_grade")]

    operations = [migrations.RunPython(normalize, migrations.RunPython.noop)]
