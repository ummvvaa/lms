"""Секции, занятия по часам, записи, отметки, раздачи билетов и расписание школы.

Начальные данные — расписание секций школы на 2026–2027 учебный год
(решение владельца, 27.10.2026), не вымышленные: пять секций, четырнадцать
занятий и недостающие виды спорта в справочнике.
"""

import datetime

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


#: секция, вид спорта, категория вида, адрес и занятия: день (0 — понедельник), начало, конец, классы, кабинет, лимит
SCHEDULE = (
    (
        "Теннис",
        "individual",
        "Нуркент, 14 — теннисный корт «Алатау»",
        (
            (3, "17:00", "18:00", 8, 9, "", 28),
            (5, "12:00", "13:00", 10, 11, "", 28),
            (5, "13:00", "14:00", 10, 11, "", 27),
            (5, "14:00", "15:00", 10, 11, "", 27),
        ),
    ),
    (
        "Волейбол",
        "team",
        "ул. Толеби, 106А",
        (
            (5, "11:00", "12:00", 8, 9, "", 20),
            (5, "14:00", "15:00", 8, 9, "", 20),
            (5, "12:00", "13:00", 10, 11, "", 35),
            (5, "13:00", "14:00", 10, 11, "", 35),
        ),
    ),
    (
        "ММА",
        "martial",
        "ул. Тажыбаевой, 155",
        ((2, "16:00", "17:00", 8, 9, "", 40), (5, "12:00", "13:00", 10, 11, "", 70)),
    ),
    (
        "Футбол",
        "team",
        "ул. Шевченко, 110/1 — футбольный клуб KIFS",
        ((3, "16:00", "17:00", 8, 9, "", 30), (5, "12:00", "13:00", 10, 11, "", 80)),
    ),
    (
        "Шахматы",
        "other",
        "Школа, кабинеты 405 и 506",
        ((2, "15:00", "17:00", 8, 9, "каб. 405", 20), (4, "17:00", "18:00", 10, 11, "каб. 506", 90)),
    ),
)


def _time(value):
    hours, minutes = value.split(":")
    return datetime.time(int(hours), int(minutes))


def seed(apps, schema_editor):
    SportType = apps.get_model("directories", "SportType")
    Section = apps.get_model("sport", "Section")
    SectionSlot = apps.get_model("sport", "SectionSlot")
    for order, (title, category, address, slots) in enumerate(SCHEDULE, start=1):
        sport = SportType.objects.filter(name__iexact=title).first()
        if sport is None:
            sport = SportType.objects.create(name=title, category=category)
        section = Section.objects.create(title=title, sport_type=sport, address=address, order=order)
        SectionSlot.objects.bulk_create(
            SectionSlot(
                section=section,
                weekday=weekday,
                starts=_time(starts),
                ends=_time(ends),
                grade_from=grade_from,
                grade_to=grade_to,
                room=room,
                capacity=capacity,
            )
            for weekday, starts, ends, grade_from, grade_to, room, capacity in slots
        )


def unseed(apps, schema_editor):
    """Назад — только таблицы уходят целиком; виды спорта остаются в справочнике."""


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("directories", "0006_subject_area_as_text"),
        ("students", "0035_attendance_day_mark"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Section",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("archived_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="В архиве с")),
                (
                    "archive_batch",
                    models.UUIDField(blank=True, db_index=True, null=True, verbose_name="Номер удаления"),
                ),
                ("title", models.CharField(max_length=120, verbose_name="Название")),
                ("address", models.CharField(max_length=250, verbose_name="Адрес площадки")),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="Порядок в списке")),
                ("is_fictional", models.BooleanField(default=False, verbose_name="Вымышленная")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Добавлена")),
                (
                    "sport_type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sections",
                        to="directories.sporttype",
                        verbose_name="Вид спорта",
                    ),
                ),
            ],
            options={
                "verbose_name": "Секция",
                "verbose_name_plural": "Секции",
                "ordering": ("order", "title", "id"),
            },
        ),
        migrations.CreateModel(
            name="SectionSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "enroll_until",
                    models.DateTimeField(blank=True, null=True, verbose_name="Запись на секции открыта до"),
                ),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Когда поменяли")),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Кто поменял",
                    ),
                ),
            ],
            options={
                "verbose_name": "Настройка записи на секции",
                "verbose_name_plural": "Настройки записи на секции",
            },
        ),
        migrations.CreateModel(
            name="SectionSlot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("archived_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="В архиве с")),
                (
                    "archive_batch",
                    models.UUIDField(blank=True, db_index=True, null=True, verbose_name="Номер удаления"),
                ),
                (
                    "weekday",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (0, "Понедельник"),
                            (1, "Вторник"),
                            (2, "Среда"),
                            (3, "Четверг"),
                            (4, "Пятница"),
                            (5, "Суббота"),
                            (6, "Воскресенье"),
                        ],
                        verbose_name="День недели",
                    ),
                ),
                ("starts", models.TimeField(verbose_name="Начало")),
                ("ends", models.TimeField(verbose_name="Конец")),
                ("grade_from", models.PositiveSmallIntegerField(verbose_name="С класса")),
                ("grade_to", models.PositiveSmallIntegerField(verbose_name="По класс")),
                ("room", models.CharField(blank=True, max_length=80, verbose_name="Кабинет или уточнение")),
                ("capacity", models.PositiveSmallIntegerField(verbose_name="Мест")),
                (
                    "section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="slots",
                        to="sport.section",
                        verbose_name="Секция",
                    ),
                ),
            ],
            options={
                "verbose_name": "Занятие секции",
                "verbose_name_plural": "Занятия секций",
                "ordering": ("section", "weekday", "starts", "grade_from", "id"),
            },
        ),
        migrations.CreateModel(
            name="SectionMark",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(verbose_name="Дата занятия")),
                ("marked_at", models.DateTimeField(default=django.utils.timezone.now, verbose_name="Когда отмечен")),
                (
                    "method",
                    models.CharField(
                        choices=[("qr", "По QR"), ("manual", "Вручную")], max_length=8, verbose_name="Как отмечен"
                    ),
                ),
                (
                    "marked_by_title",
                    models.CharField(blank=True, max_length=250, verbose_name="Кто отметил на момент отметки"),
                ),
                (
                    "marked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Кто отметил вручную",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="section_marks",
                        to="students.student",
                        verbose_name="Ученик",
                    ),
                ),
                (
                    "slot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="marks",
                        to="sport.sectionslot",
                        verbose_name="Занятие",
                    ),
                ),
            ],
            options={
                "verbose_name": "Отметка на занятии",
                "verbose_name_plural": "Отметки на занятиях",
                "ordering": ("-date", "-marked_at"),
            },
        ),
        migrations.CreateModel(
            name="SectionEnrollment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enrolled_at", models.DateTimeField(default=django.utils.timezone.now, verbose_name="Записался")),
                (
                    "source",
                    models.CharField(
                        choices=[("lms", "LMS"), ("bot", "Перенос из бота"), ("director", "Записал директор спорта")],
                        max_length=10,
                        verbose_name="Откуда запись",
                    ),
                ),
                ("slot_set_at", models.DateTimeField(blank=True, null=True, verbose_name="Когда назначен час")),
                ("ended_at", models.DateTimeField(blank=True, null=True, verbose_name="Вышел из секции")),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Кто записал",
                    ),
                ),
                (
                    "ended_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Кто закрыл запись",
                    ),
                ),
                (
                    "section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="enrollments",
                        to="sport.section",
                        verbose_name="Секция",
                    ),
                ),
                (
                    "slot_set_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Кто назначил час",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="section_enrollments",
                        to="students.student",
                        verbose_name="Ученик",
                    ),
                ),
                (
                    "slot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="enrollments",
                        to="sport.sectionslot",
                        verbose_name="Час занятия",
                    ),
                ),
            ],
            options={
                "verbose_name": "Запись в секцию",
                "verbose_name_plural": "Записи в секции",
                "ordering": ("-enrolled_at", "-id"),
            },
        ),
        migrations.CreateModel(
            name="SessionEnd",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(verbose_name="Дата занятия")),
                ("ended_at", models.DateTimeField(default=django.utils.timezone.now, verbose_name="Когда закончено")),
                (
                    "ended_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Кто закончил",
                    ),
                ),
                (
                    "slot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ends_early",
                        to="sport.sectionslot",
                        verbose_name="Занятие",
                    ),
                ),
            ],
            options={
                "verbose_name": "Законченное занятие",
                "verbose_name_plural": "Законченные занятия",
            },
        ),
        migrations.CreateModel(
            name="TicketDrop",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("archived_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="В архиве с")),
                (
                    "archive_batch",
                    models.UUIDField(blank=True, db_index=True, null=True, verbose_name="Номер удаления"),
                ),
                ("title", models.CharField(max_length=250, verbose_name="Событие")),
                ("event_at", models.DateTimeField(verbose_name="Когда событие")),
                ("place", models.CharField(max_length=200, verbose_name="Где")),
                ("count", models.PositiveSmallIntegerField(verbose_name="Сколько билетов")),
                ("opens_at", models.DateTimeField(verbose_name="Старт раздачи")),
                ("pickup", models.CharField(max_length=250, verbose_name="Где и до когда забрать")),
                ("grade_from", models.PositiveSmallIntegerField(default=8, verbose_name="С класса")),
                ("grade_to", models.PositiveSmallIntegerField(default=11, verbose_name="По класс")),
                (
                    "offer_minutes",
                    models.PositiveSmallIntegerField(default=30, verbose_name="Минут на ответ из очереди"),
                ),
                ("announced_at", models.DateTimeField(blank=True, null=True, verbose_name="Анонс разослан")),
                ("reminded_at", models.DateTimeField(blank=True, null=True, verbose_name="Напоминание разослано")),
                ("is_fictional", models.BooleanField(default=False, verbose_name="Вымышленная")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Опубликована")),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Кто опубликовал",
                    ),
                ),
            ],
            options={
                "verbose_name": "Раздача билетов",
                "verbose_name_plural": "Раздачи билетов",
                "ordering": ("-opens_at", "-id"),
            },
        ),
        migrations.CreateModel(
            name="TicketClaim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pressed_at", models.DateTimeField(default=django.utils.timezone.now, verbose_name="Нажал")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("received", "Получил"),
                            ("queued", "В очереди"),
                            ("offered", "Предложен"),
                            ("declined", "Отказался"),
                            ("expired", "Истёк"),
                            ("left", "Вышел из очереди"),
                            ("missed", "Не забрал"),
                        ],
                        max_length=10,
                        verbose_name="Статус",
                    ),
                ),
                ("from_queue", models.BooleanField(default=False, verbose_name="Из очереди")),
                ("offered_at", models.DateTimeField(blank=True, null=True, verbose_name="Предложен")),
                ("offer_until", models.DateTimeField(blank=True, null=True, verbose_name="Ответить до")),
                ("decided_at", models.DateTimeField(blank=True, null=True, verbose_name="Когда изменился статус")),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ticket_claims",
                        to="students.student",
                        verbose_name="Ученик",
                    ),
                ),
                (
                    "drop",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="claims",
                        to="sport.ticketdrop",
                        verbose_name="Раздача",
                    ),
                ),
            ],
            options={
                "verbose_name": "Заявка на билет",
                "verbose_name_plural": "Заявки на билеты",
                "ordering": ("pressed_at", "id"),
            },
        ),
        migrations.AddConstraint(
            model_name="sectionslot",
            constraint=models.CheckConstraint(
                condition=models.Q(("ends__gt", models.F("starts"))), name="slot_ends_after_starts"
            ),
        ),
        migrations.AddConstraint(
            model_name="sectionslot",
            constraint=models.CheckConstraint(
                condition=models.Q(("grade_to__gte", models.F("grade_from"))), name="slot_grades_ordered"
            ),
        ),
        migrations.AddIndex(
            model_name="sectionmark",
            index=models.Index(fields=["slot", "date"], name="sport_secti_slot_id_b3873e_idx"),
        ),
        migrations.AddIndex(
            model_name="sectionmark",
            index=models.Index(fields=["student", "-date"], name="sport_secti_student_edb516_idx"),
        ),
        migrations.AddConstraint(
            model_name="sectionmark",
            constraint=models.UniqueConstraint(fields=("student", "slot", "date"), name="unique_section_mark"),
        ),
        migrations.AddIndex(
            model_name="sectionenrollment",
            index=models.Index(fields=["slot", "ended_at"], name="sport_secti_slot_id_e01670_idx"),
        ),
        migrations.AddIndex(
            model_name="sectionenrollment",
            index=models.Index(fields=["section", "ended_at"], name="sport_secti_section_711f39_idx"),
        ),
        migrations.AddConstraint(
            model_name="sectionenrollment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("ended_at__isnull", True)), fields=("student",), name="one_active_section"
            ),
        ),
        migrations.AddConstraint(
            model_name="sessionend",
            constraint=models.UniqueConstraint(fields=("slot", "date"), name="unique_session_end"),
        ),
        migrations.AddConstraint(
            model_name="ticketdrop",
            constraint=models.CheckConstraint(
                condition=models.Q(("grade_to__gte", models.F("grade_from"))), name="ticket_grades_ordered"
            ),
        ),
        migrations.AddConstraint(
            model_name="ticketdrop",
            constraint=models.CheckConstraint(condition=models.Q(("count__gte", 1)), name="ticket_count_positive"),
        ),
        migrations.AddIndex(
            model_name="ticketclaim",
            index=models.Index(fields=["drop", "status", "pressed_at"], name="sport_ticke_drop_id_d2e672_idx"),
        ),
        migrations.AddIndex(
            model_name="ticketclaim",
            index=models.Index(fields=["status", "offer_until"], name="sport_ticke_status_a14e90_idx"),
        ),
        migrations.AddConstraint(
            model_name="ticketclaim",
            constraint=models.UniqueConstraint(fields=("drop", "student"), name="one_ticket_claim"),
        ),
        migrations.RunPython(seed, unseed),
    ]
