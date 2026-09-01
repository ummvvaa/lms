"""Фаза 48: профтест отвечается кнопками, а не шестью пустыми окнами.

Ученик открывал анкету, видел шесть текстовых полей и закрывал экран,
не начав: сочинение в шесть окон никто писать не будет. Вопрос получает
набор готовых вариантов, из которых можно выбрать несколько, и поле
«свой вариант» рядом.

Варианты живут справочником у самого вопроса (`CareerQuestion.options`)
и правятся директором школы на его экране — в код они не переезжают.
Здесь только стартовый набор: школа меняет его без выката.
"""

from __future__ import annotations

from django.db import migrations, models

#: код вопроса → варианты. Пустая строка означает «оставить как было».
OPTIONS = {
    "favourite_subjects": [
        "Математика",
        "Физика",
        "Информатика",
        "Химия",
        "Биология",
        "История",
        "География",
        "Языки",
        "Литература",
        "Экономика",
        "Искусство",
        "Физкультура",
    ],
    "outside_school": [
        "Программирование",
        "Робототехника",
        "Олимпиады",
        "Спорт",
        "Музыка",
        "Рисование",
        "Театр",
        "Волонтёрство",
        "Дебаты",
        "Своё дело",
        "Видео и блог",
    ],
    "easy_tasks": [
        "Считать и решать",
        "Разбираться в технике",
        "Писать тексты",
        "Выступать перед людьми",
        "Договариваться",
        "Придумывать новое",
        "Наводить порядок в данных",
        "Учить других",
        "Работать руками",
    ],
    "dislikes": [
        "Однообразие",
        "Много общения",
        "Работа в одиночку",
        "Публичные выступления",
        "Долгие расчёты",
        "Заучивание наизусть",
        "Жёсткий график",
        "Бумажная работа",
    ],
    "in_ten_years": [
        "Наука и исследования",
        "Своё дело",
        "Большая компания",
        "Творческая профессия",
        "Медицина",
        "Государственная служба",
        "Работа за рубежом",
        "Ещё не знаю",
    ],
    "what_matters": [
        "Доход",
        "Интерес к делу",
        "Польза для людей",
        "Свобода",
        "Стабильность",
    ],
}


#: что посеяла фаза 45 — по этому видно, трогала школа вопрос или нет
SEEDED_IN_45 = {"what_matters": ["Доход", "Интерес к делу", "Польза для людей"]}


def fill_options(apps, schema_editor):
    """Заполнить варианты и перевести вопросы на выбор из них.

    Пишем через `update()` по выборке, а не через `save()`: у вопроса
    профтеста есть владелец-домен, и сохранение объекта поднимает сигнал
    аудита — миграция оставила бы в журнале школы дюжину правок без автора.
    """
    CareerQuestion = apps.get_model("engagement", "CareerQuestion")
    for code, options in OPTIONS.items():
        rows = CareerQuestion.objects.filter(code=code)
        question = rows.first()
        if question is None:
            continue
        # свои варианты школы не затираем: если директор уже что-то завёл,
        # оставляем как есть и только меняем вид ответа. Набор, посеянный
        # прошлой фазой, школьным не считается — его дополняем
        current = [line.strip() for line in question.options.splitlines() if line.strip()]
        untouched = not current or current == SEEDED_IN_45.get(code)
        if untouched:
            rows.update(kind="multi", options="\n".join(options))
        else:
            rows.update(kind="multi")


def back_to_text(apps, schema_editor):
    CareerQuestion = apps.get_model("engagement", "CareerQuestion")
    CareerQuestion.objects.filter(kind="multi").update(kind="text")


class Migration(migrations.Migration):

    dependencies = [("engagement", "0004_phase46_quiz_and_badges")]

    operations = [
        migrations.AlterField(
            model_name="careerquestion",
            name="kind",
            field=models.CharField(
                choices=[
                    ("text", "Свободный ответ"),
                    ("choice", "Выбор из вариантов"),
                    ("multi", "Несколько вариантов"),
                ],
                default="text",
                max_length=12,
                verbose_name="Вид ответа",
            ),
        ),
        migrations.RunPython(fill_options, back_to_text),
    ]
