"""Английское название предмета: поле и названия для предметов, которые уже есть.

В интерфейсе на английском предмет показывается по `title_en`, пусто — по-русски.
Названия ниже — привычные английские названия предметов школ Казахстана (как их
пишут NIS и международные школы); сопоставление по русскому названию без учёта
регистра. Предмет, которого нет в таблице, остаётся без английского названия —
его вносит администратор в «Учебном году», рядом с казахским.
"""

from django.db import migrations, models

EN = {
    "алгебра": "Algebra",
    "алгебра и начала анализа": "Algebra and Calculus",
    "геометрия": "Geometry",
    "математика": "Mathematics",
    "физика": "Physics",
    "химия": "Chemistry",
    "биология": "Biology",
    "естествознание": "Natural Science",
    "география": "Geography",
    "информатика": "Computer Science",
    "английский язык": "English",
    "английский": "English",
    "казахский язык": "Kazakh Language",
    "казахская литература": "Kazakh Literature",
    "казахский язык и литература": "Kazakh Language and Literature",
    "русский язык": "Russian Language",
    "русская литература": "Russian Literature",
    "русский язык и литература": "Russian Language and Literature",
    "история казахстана": "History of Kazakhstan",
    "всемирная история": "World History",
    "история": "History",
    "основы права": "Fundamentals of Law",
    "право": "Law",
    "экономика": "Economics",
    "глобальные перспективы": "Global Perspectives",
    "глобальные перспективы и проектные работы": "Global Perspectives and Project Work",
    "физкультура": "Physical Education",
    "физическая культура": "Physical Education",
    "нвтп": "Basic Military and Technological Training",
    "начальная военная и технологическая подготовка": "Basic Military and Technological Training",
    "графика и проектирование": "Graphics and Design",
    "художественный труд": "Art and Technology",
    "самопознание": "Self-Knowledge",
    "музыка": "Music",
    "изобразительное искусство": "Art",
    "технология": "Technology",
    "черчение": "Technical Drawing",
    "психология": "Psychology",
    "философия": "Philosophy",
    "китайский язык": "Chinese",
    "немецкий язык": "German",
    "французский язык": "French",
    "турецкий язык": "Turkish",
}


def fill_english(apps, schema_editor):
    Subject = apps.get_model("academics", "Subject")
    for row in Subject.objects.filter(title_en="").only("pk", "title"):
        english = EN.get(" ".join(row.title.lower().split()))
        if english is None and row.title.isascii():
            # IELTS, SAT Math, Creative Writing — название уже английское
            english = row.title
        if english:
            Subject.objects.filter(pk=row.pk).update(title_en=english)


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0007_mock_test_labels"),
    ]

    operations = [
        migrations.AddField(
            model_name="subject",
            name="title_en",
            field=models.CharField(blank=True, max_length=100, verbose_name="Название на английском"),
        ),
        migrations.RunPython(fill_english, migrations.RunPython.noop),
    ]
