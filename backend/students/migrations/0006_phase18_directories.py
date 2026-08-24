"""Фаза 18: предмет олимпиады и вид спорта переезжают в справочники.

Порядок важен: сначала заводим ссылочные колонки, потом переносим
в них текст, и только затем сносим текстовую колонку. Иначе перенос
уже нечего было бы переносить.

Похожие написания намеренно не склеиваются: «Футбол» и «футбол» станут
двумя записями, а директору интерфейс покажет их как «возможно, это одно
и то же» с кнопкой объединения. Автоматическая склейка здесь опаснее
дубля: разъединить потом будет нечем.
"""

import django.db.models.deletion
from django.db import migrations, models


def text_to_directory(apps, schema_editor):
    """Собрать виды спорта из текстовой колонки и проставить ссылки."""
    SportProfile = apps.get_model("students", "SportProfile")
    SportType = apps.get_model("directories", "SportType")

    names = sorted(
        {
            (row or "").strip()
            for row in SportProfile.objects.exclude(sport_kind="").values_list("sport_kind", flat=True)
            if (row or "").strip()
        }
    )
    for order, name in enumerate(names, start=1):
        entry, _created = SportType.objects.get_or_create(
            name=name,
            defaults={"category": "other", "sort_order": order * 10},
        )
        SportProfile.objects.filter(sport_kind=name).update(sport_type=entry)

    # Предмет олимпиады отдельной колонкой раньше не жил — переносить
    # нечего, справочник заводит директор талантов сам. Догадываться
    # о предмете по названию активности мы не будем: в справочник попадут
    # придуманные записи, а исправлять их придётся руками.


def directory_to_text(apps, schema_editor):
    """Обратный перенос — на случай отката миграции."""
    SportProfile = apps.get_model("students", "SportProfile")
    for profile in SportProfile.objects.select_related("sport_type").exclude(sport_type__isnull=True):
        profile.sport_kind = profile.sport_type.name
        profile.save(update_fields=["sport_kind"])


class Migration(migrations.Migration):

    dependencies = [
        ("directories", "0001_phase18_directories"),
        ("students", "0005_russian_labels"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="subject",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="activities",
                to="directories.olympiadsubject",
                verbose_name="Предмет",
            ),
        ),
        migrations.AddField(
            model_name="sportprofile",
            name="sport_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="profiles",
                to="directories.sporttype",
                verbose_name="Вид спорта",
            ),
        ),
        migrations.RunPython(text_to_directory, directory_to_text),
        migrations.RemoveField(
            model_name="sportprofile",
            name="sport_kind",
        ),
        migrations.AddIndex(
            model_name="activity",
            index=models.Index(fields=["subject"], name="students_ac_subject_8c46da_idx"),
        ),
    ]
