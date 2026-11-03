"""Разбор под поступление за рубеж: правила разбора, название за рубежом, шаги.

Уже готовые разборы получают `rules=1` — они считались по прежним правилам
и показываются как есть, с плашкой; новые получают 2. Профессии, предметы
и экзамены — текстом без предела длины, чтобы ответ модели не резался.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("career", "0003_analysis_job_and_cancelled"),
    ]

    operations = [
        # существующие строки — прежние правила; дальше по умолчанию новые
        migrations.AddField(
            model_name="careeranalysis",
            name="rules",
            field=models.PositiveSmallIntegerField(default=1, verbose_name="Правила разбора"),
        ),
        migrations.AlterField(
            model_name="careeranalysis",
            name="rules",
            field=models.PositiveSmallIntegerField(default=2, verbose_name="Правила разбора"),
        ),
        migrations.AddField(
            model_name="careeranalysisdirection",
            name="next_steps",
            field=models.TextField(blank=True, verbose_name="Что сделать уже сейчас"),
        ),
        migrations.AddField(
            model_name="careeranalysisdirection",
            name="title_abroad",
            field=models.CharField(blank=True, max_length=150, verbose_name="Название за рубежом"),
        ),
        migrations.AlterField(
            model_name="careeranalysisdirection",
            name="exams",
            field=models.TextField(blank=True, verbose_name="Что сдавать для поступления"),
        ),
        migrations.AlterField(
            model_name="careeranalysisdirection",
            name="professions",
            field=models.TextField(blank=True, verbose_name="Профессии"),
        ),
        migrations.AlterField(
            model_name="careeranalysisdirection",
            name="subjects",
            field=models.TextField(blank=True, verbose_name="Что подтянуть в школе"),
        ),
    ]
