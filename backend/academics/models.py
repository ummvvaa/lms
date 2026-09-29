"""Учебная часть: предметы, учителя, составы, уроки, отметки, оценки, отчёты.

Всё, что имеет историю, хранится строками с датами (инвариант №5):
уроки материализованы на год вперёд, отметка и оценка — строка на ученика
и урок, уважительная причина — период, отчёт родителям — снимок строками.
Типизированные колонки без JSONB (инвариант №6): по ним считаются журнал,
успеваемость и посещаемость.

Владелец блока в реестре — академический директор (`core.domains.ACADEMICS`),
но пишут сюда и учитель (свои уроки), и куратор (уважительная причина,
слово в отчёте). Границы держит `academics.rights`, а не список во вьюхе.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.archivable import Archivable


class Scheme(models.TextChoices):
    """Схема оценивания предмета."""

    #: ФО, СОР, СОЧ и итог четверти — обычный предмет
    KZ = "kz", "ФО, СОР и СОЧ, итог за четверть"
    #: только ФО, в табель не идёт — курсы подготовки (IELTS, SAT)
    FO = "fo", "Только ФО, в табель не идёт"


class Subject(models.Model):
    """Предмет: название, короткое название, схема и максимумы по умолчанию."""

    code = models.SlugField("Код", max_length=32, unique=True)
    title = models.CharField("Название", max_length=100)
    short_title = models.CharField("Короткое название", max_length=32)
    scheme = models.CharField("Схема оценивания", max_length=2, choices=Scheme.choices, default=Scheme.KZ)
    sor_max = models.PositiveSmallIntegerField("Максимум СОР по умолчанию", default=15)
    soch_max = models.PositiveSmallIntegerField("Максимум СОЧ по умолчанию", default=25)
    order = models.PositiveSmallIntegerField("Порядок", default=100)
    is_active = models.BooleanField("Ведётся", default=True)
    #: посев для разработки — вычищается `purge_fictional`
    is_fictional = models.BooleanField("Вымышленный", default=False)

    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"
        ordering = ("order", "title")

    def __str__(self) -> str:
        return self.title


class TeacherProfile(models.Model):
    """Профиль учителя: предметы и свой кабинет. Учётку заводит администратор."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="Учётная запись",
        related_name="teacher_profile",
        on_delete=models.CASCADE,
    )
    subjects = models.ManyToManyField(Subject, verbose_name="Предметы", related_name="teachers", blank=True)
    room = models.CharField("Кабинет", max_length=40, blank=True)
    is_fictional = models.BooleanField("Вымышленный", default=False)

    class Meta:
        verbose_name = "Профиль учителя"
        verbose_name_plural = "Профили учителей"

    def __str__(self) -> str:
        return str(self.user)


# --- Учебный год -------------------------------------------------------------


class AcademicYear(models.Model):
    """Учебный год: четверти, каникулы, праздники, звонки, шкала — всё на него."""

    title = models.CharField("Название", max_length=20)
    starts = models.DateField("Начало")
    ends = models.DateField("Конец")
    is_current = models.BooleanField("Текущий", default=False)
    is_fictional = models.BooleanField("Вымышленный", default=False)

    class Meta:
        verbose_name = "Учебный год"
        verbose_name_plural = "Учебные годы"
        ordering = ("-starts",)
        constraints = [
            models.UniqueConstraint(
                fields=("is_current",), condition=models.Q(is_current=True), name="one_current_year"
            )
        ]

    def __str__(self) -> str:
        return self.title


class Quarter(models.Model):
    """Четверть. Закрытая четверть: итоги правят только Кымбат и администратор."""

    year = models.ForeignKey(
        AcademicYear, verbose_name="Учебный год", related_name="quarters", on_delete=models.CASCADE
    )
    number = models.PositiveSmallIntegerField("Номер")
    title = models.CharField("Название", max_length=40)
    starts = models.DateField("Начало")
    ends = models.DateField("Конец")
    closed_at = models.DateTimeField("Итоги закрыты", null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто закрыл",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Четверть"
        verbose_name_plural = "Четверти"
        ordering = ("year", "number")
        constraints = [models.UniqueConstraint(fields=("year", "number"), name="unique_quarter_number")]

    def __str__(self) -> str:
        return f"{self.title} {self.year}"

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None


class Break(models.Model):
    """Каникулы: уроки в эти дни не заводятся."""

    year = models.ForeignKey(AcademicYear, verbose_name="Учебный год", related_name="breaks", on_delete=models.CASCADE)
    title = models.CharField("Название", max_length=60)
    starts = models.DateField("Начало")
    ends = models.DateField("Конец")

    class Meta:
        verbose_name = "Каникулы"
        verbose_name_plural = "Каникулы"
        ordering = ("starts",)

    def __str__(self) -> str:
        return self.title


class Holiday(models.Model):
    """Праздник: один день без уроков."""

    year = models.ForeignKey(
        AcademicYear, verbose_name="Учебный год", related_name="holidays", on_delete=models.CASCADE
    )
    date = models.DateField("Дата")
    title = models.CharField("Название", max_length=80)

    class Meta:
        verbose_name = "Праздник"
        verbose_name_plural = "Праздники"
        ordering = ("date",)
        constraints = [models.UniqueConstraint(fields=("year", "date"), name="unique_holiday_date")]

    def __str__(self) -> str:
        return f"{self.date:%d.%m} {self.title}"


class BellSchedule(models.Model):
    """Расписание звонков. У школы их может быть несколько (решение владельца, 27.09.2026).

    Разные классы начинают уроки в разное время, поэтому звонки живут
    не у года, а у расписания звонков; каждое назначается группам, одно —
    общее по умолчанию для всех групп без своего. Время урока берётся
    из звонков его группы; поток из групп с разными звонками при сохранении
    урока — предупреждение, как накладка.
    """

    year = models.ForeignKey(
        AcademicYear, verbose_name="Учебный год", related_name="bell_schedules", on_delete=models.CASCADE
    )
    title = models.CharField("Название", max_length=60)
    is_default = models.BooleanField("Общее по умолчанию", default=False)
    groups = models.ManyToManyField(
        "students.StudyGroup", verbose_name="Группы", related_name="bell_schedules", blank=True
    )

    class Meta:
        verbose_name = "Расписание звонков"
        verbose_name_plural = "Расписания звонков"
        ordering = ("year", "-is_default", "title")
        constraints = [
            models.UniqueConstraint(
                fields=("year",), condition=models.Q(is_default=True), name="one_default_bell_schedule"
            )
        ]

    def __str__(self) -> str:
        return self.title


class Bell(models.Model):
    """Звонок: номер урока — начало и конец, внутри расписания звонков.

    Поле `year` осталось от времён одного набора звонков на год; расписание
    звонков (`schedule`) добавлено позже и заполнено миграцией. Год
    у звонка совпадает с годом его расписания.
    """

    year = models.ForeignKey(AcademicYear, verbose_name="Учебный год", related_name="bells", on_delete=models.CASCADE)
    schedule = models.ForeignKey(
        BellSchedule,
        verbose_name="Расписание звонков",
        related_name="bells",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    number = models.PositiveSmallIntegerField("Урок")
    starts = models.TimeField("Начало")
    ends = models.TimeField("Конец")

    class Meta:
        verbose_name = "Звонок"
        verbose_name_plural = "Звонки"
        ordering = ("year", "number")
        constraints = [models.UniqueConstraint(fields=("schedule", "number"), name="unique_bell_in_schedule")]

    def __str__(self) -> str:
        return f"{self.number} урок {self.starts:%H:%M}–{self.ends:%H:%M}"


class GradingScale(models.Model):
    """Шкала: веса ФО, СОР, СОЧ, пороги оценок и окно правки учителя."""

    year = models.OneToOneField(
        AcademicYear, verbose_name="Учебный год", related_name="scale", on_delete=models.CASCADE
    )
    weight_fo = models.PositiveSmallIntegerField("Вес ФО, %", default=25)
    weight_sor = models.PositiveSmallIntegerField("Вес СОР, %", default=25)
    weight_soch = models.PositiveSmallIntegerField("Вес СОЧ, %", default=50)
    threshold_5 = models.PositiveSmallIntegerField("Пятёрка от, %", default=85)
    threshold_4 = models.PositiveSmallIntegerField("Четвёрка от, %", default=65)
    threshold_3 = models.PositiveSmallIntegerField("Тройка от, %", default=40)
    fo_max = models.PositiveSmallIntegerField("Максимум ФО", default=10)
    edit_days = models.PositiveSmallIntegerField("Учитель правит оценку, дней", default=7)

    class Meta:
        verbose_name = "Шкала оценивания"
        verbose_name_plural = "Шкалы оценивания"

    def __str__(self) -> str:
        return f"{self.weight_fo}/{self.weight_sor}/{self.weight_soch} · {self.year}"


class ReportCadence(models.TextChoices):
    """Когда собираются отчёты родителям."""

    MONTH = "month", "Последняя пятница месяца и после четверти"
    QUARTER = "quarter", "Только после закрытия четверти"


class ReportSettings(models.Model):
    """Настройки отчётов родителям: когда собирать и какие разделы входят."""

    year = models.OneToOneField(
        AcademicYear, verbose_name="Учебный год", related_name="report_settings", on_delete=models.CASCADE
    )
    cadence = models.CharField(
        "Когда собирать", max_length=8, choices=ReportCadence.choices, default=ReportCadence.MONTH
    )
    section_attendance = models.BooleanField("Посещаемость по урокам", default=True)
    section_grades = models.BooleanField("Оценки по предметам", default=True)
    section_exams = models.BooleanField("Экзамены и вузы", default=True)
    section_documents = models.BooleanField("Документы для поступления", default=True)
    section_curator = models.BooleanField("Слово куратора", default=True)
    section_discipline = models.BooleanField("Замечания по дисциплине", default=False)

    class Meta:
        verbose_name = "Настройки отчётов"
        verbose_name_plural = "Настройки отчётов"

    def __str__(self) -> str:
        return f"Отчёты · {self.year}"


# --- Составы ----------------------------------------------------------------


class CohortKind(models.TextChoices):
    GROUP = "group", "Вся группа"
    SUBGROUP = "subgroup", "Подгруппа"
    STREAM = "stream", "Поток"


class Cohort(Archivable):
    """Состав урока: вся группа, подгруппа группы по предмету или поток.

    Подгруппа хранит членство строками с датами (`CohortMembership`), чтобы
    перевод ученика не ломал прошлые оценки. Поток — части (`StreamPart`):
    группы и подгруппы; ученик, попавший дважды, не задваивается.

    Подгруппа бывает и внутри потока (решение владельца, 29.09.2026):
    английский EEP-8-1 набирается из четырёх групп потока EEP-8. У такой
    подгруппы нет своей группы (`group`), есть поток (`stream`), и её
    группы — для звонков и видимости куратору — это группы потока.
    """

    kind = models.CharField("Вид", max_length=8, choices=CohortKind.choices)
    group = models.ForeignKey(
        "students.StudyGroup",
        verbose_name="Группа",
        related_name="cohorts",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    subject = models.ForeignKey(
        Subject,
        verbose_name="Предмет подгруппы",
        related_name="subgroups",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    number = models.PositiveSmallIntegerField("Номер подгруппы", null=True, blank=True)
    name = models.CharField("Название", max_length=120)
    short_name = models.CharField("Короткое название", max_length=60, blank=True)
    rule = models.CharField("Как делили", max_length=60, blank=True)
    stream = models.ForeignKey(
        "self",
        verbose_name="Поток подгруппы",
        related_name="inner_subgroups",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        limit_choices_to={"kind": "stream"},
    )
    room = models.CharField("Основной кабинет", max_length=40, blank=True)
    is_fictional = models.BooleanField("Вымышленный", default=False)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Состав"
        verbose_name_plural = "Составы"
        ordering = ("kind", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("group",),
                condition=models.Q(kind="group", archived_at__isnull=True),
                name="one_group_cohort_per_group",
            )
        ]

    def __str__(self) -> str:
        return self.name


class CohortMembership(models.Model):
    """Ученик в подгруппе с даты по дату. Пустое `until` — состоит."""

    cohort = models.ForeignKey(Cohort, verbose_name="Состав", related_name="memberships", on_delete=models.CASCADE)
    student = models.ForeignKey(
        "students.Student", verbose_name="Ученик", related_name="cohort_memberships", on_delete=models.CASCADE
    )
    since = models.DateField("С")
    until = models.DateField("По", null=True, blank=True)

    class Meta:
        verbose_name = "Членство в подгруппе"
        verbose_name_plural = "Членства в подгруппах"
        ordering = ("cohort", "student")
        indexes = [models.Index(fields=("student", "until"))]

    def __str__(self) -> str:
        return f"{self.student} в {self.cohort} с {self.since}"


class StreamPart(models.Model):
    """Часть потока: группа или подгруппа."""

    stream = models.ForeignKey(Cohort, verbose_name="Поток", related_name="parts", on_delete=models.CASCADE)
    part = models.ForeignKey(Cohort, verbose_name="Часть", related_name="in_streams", on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Часть потока"
        verbose_name_plural = "Части потоков"
        constraints = [models.UniqueConstraint(fields=("stream", "part"), name="unique_stream_part")]

    def __str__(self) -> str:
        return f"{self.part} в {self.stream}"


# --- Журналы и уроки --------------------------------------------------------


class Course(Archivable):
    """Журнал: предмет у одного учителя у одного состава.

    Учитель может быть не назначен (решение владельца, 29.09.2026): у Creative
    Writing его нет ни в расписании школы, ни в списке сотрудников. Такой урок
    стоит в расписании, а отмечает его администратор, пока учителя не назначат.
    """

    subject = models.ForeignKey(Subject, verbose_name="Предмет", related_name="courses", on_delete=models.PROTECT)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Учитель",
        related_name="courses",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    cohort = models.ForeignKey(Cohort, verbose_name="Состав", related_name="courses", on_delete=models.CASCADE)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Журнал"
        verbose_name_plural = "Журналы"
        ordering = ("subject__order", "cohort__name")
        constraints = [
            models.UniqueConstraint(
                fields=("subject", "teacher", "cohort"),
                condition=models.Q(archived_at__isnull=True),
                name="unique_course",
                # журнал без учителя тоже один на предмет и состав
                nulls_distinct=False,
            )
        ]

    def __str__(self) -> str:
        return f"{self.subject} · {self.cohort}"


class LessonSeries(models.Model):
    """Еженедельный урок: день недели, номер, кабинет, с даты по дату."""

    course = models.ForeignKey(Course, verbose_name="Журнал", related_name="series", on_delete=models.CASCADE)
    weekday = models.PositiveSmallIntegerField("День недели")
    slot = models.PositiveSmallIntegerField("Номер урока")
    room = models.CharField("Кабинет", max_length=40, blank=True)
    starts = models.DateField("С")
    ends = models.DateField("По")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто завёл",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Заведена", auto_now_add=True)

    class Meta:
        verbose_name = "Серия уроков"
        verbose_name_plural = "Серии уроков"
        ordering = ("weekday", "slot")

    def __str__(self) -> str:
        return f"{self.course} · день {self.weekday}, {self.slot} урок"


class LessonStatus(models.TextChoices):
    PLANNED = "planned", "По плану"
    CANCELLED = "cancelled", "Отменён"
    MOVED = "moved", "Перенесён"


class LessonKind(models.TextChoices):
    FO = "fo", "ФО"
    SOR = "sor", "СОР"
    SOCH = "soch", "СОЧ"


class Lesson(Archivable):
    """Конкретный урок: дата, номер, кабинет, учитель, замена, статус, тема.

    Урок с отметками или оценками при удалении уходит в архив администратора
    вместе с ними (каскад `Archivable`) и возвращается оттуда.
    """

    course = models.ForeignKey(Course, verbose_name="Журнал", related_name="lessons", on_delete=models.CASCADE)
    series = models.ForeignKey(
        LessonSeries, verbose_name="Серия", related_name="lessons", on_delete=models.SET_NULL, null=True, blank=True
    )
    date = models.DateField("Дата")
    slot = models.PositiveSmallIntegerField("Номер урока")
    room = models.CharField("Кабинет", max_length=40, blank=True)
    #: пусто — учитель не назначен (см. `Course`)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Учитель",
        related_name="lessons",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    substitute = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Замена",
        related_name="substituted_lessons",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    status = models.CharField("Статус", max_length=10, choices=LessonStatus.choices, default=LessonStatus.PLANNED)
    reason = models.CharField("Причина", max_length=200, blank=True)
    moved_from_date = models.DateField("Перенесён с даты", null=True, blank=True)
    moved_from_slot = models.PositiveSmallIntegerField("Перенесён с урока", null=True, blank=True)
    topic = models.CharField("Тема", max_length=200, blank=True)
    homework = models.TextField("Домашнее задание", blank=True)
    kind = models.CharField("Вид оценивания", max_length=4, choices=LessonKind.choices, default=LessonKind.FO)
    number = models.PositiveSmallIntegerField("Номер СОР или СОЧ", null=True, blank=True)
    max_score = models.PositiveSmallIntegerField("Максимум баллов", null=True, blank=True)
    note = models.CharField("Примечание", max_length=120, blank=True)
    marked_at = models.DateTimeField("Посещаемость сохранена", null=True, blank=True)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто отметил",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: напоминание о неотмеченном уроке ушло — второго не будет
    reminded_at = models.DateTimeField("Напоминание ушло", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто завёл",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Заведён", auto_now_add=True)
    updated_at = models.DateTimeField("Изменён", auto_now=True)

    class Meta:
        verbose_name = "Урок"
        verbose_name_plural = "Уроки"
        ordering = ("date", "slot", "id")
        indexes = [
            models.Index(fields=("date", "slot")),
            models.Index(fields=("course", "date")),
            models.Index(fields=("teacher", "date")),
        ]

    def __str__(self) -> str:
        return f"{self.course} · {self.date:%d.%m.%Y}, {self.slot} урок"

    @property
    def actual_teacher_id(self) -> int | None:
        """Кто ведёт урок на деле: заменяющий, если он назначен."""
        return self.substitute_id or self.teacher_id

    @property
    def is_live(self) -> bool:
        return self.status != LessonStatus.CANCELLED

    @property
    def is_marked(self) -> bool:
        return self.marked_at is not None


class Mark(models.TextChoices):
    """Отметка посещаемости. Присутствие — отсутствие строки."""

    ABSENT = "absent", "Не был"
    LATE = "late", "Опоздал"


class Attendance(Archivable):
    """Отметка ученика на уроке. «У» не хранится: её даёт уважительная причина."""

    lesson = models.ForeignKey(Lesson, verbose_name="Урок", related_name="attendance", on_delete=models.CASCADE)
    student = models.ForeignKey(
        "students.Student", verbose_name="Ученик", related_name="lesson_attendance", on_delete=models.CASCADE
    )
    mark = models.CharField("Отметка", max_length=6, choices=Mark.choices)
    noted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто отметил",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Отмечен", auto_now_add=True)
    updated_at = models.DateTimeField("Изменён", auto_now=True)

    class Meta:
        verbose_name = "Отметка посещаемости"
        verbose_name_plural = "Отметки посещаемости"
        constraints = [models.UniqueConstraint(fields=("lesson", "student"), name="unique_lesson_attendance")]
        indexes = [models.Index(fields=("student", "lesson"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.lesson} · {self.get_mark_display()}"


class ExcuseDocument(models.TextChoices):
    CERTIFICATE = "certificate", "Справка"
    PARENTS = "parents", "Заявление родителей"
    ORDER = "order", "Приказ школы"
    OTHER = "other", "Другое"


def excuse_upload_to(instance: Excuse, filename: str) -> str:
    return f"excuses/{instance.student_id}/{filename}"


def _private_storage():
    from materials.storage import private_storage

    return private_storage()


class Excuse(Archivable):
    """Уважительная причина за период: пропуски «н» внутри читаются как «у».

    Строк посещаемости не меняет: сняли причину — снова «н».
    """

    student = models.ForeignKey(
        "students.Student", verbose_name="Ученик", related_name="excuses", on_delete=models.CASCADE
    )
    starts = models.DateField("С")
    ends = models.DateField("По")
    reason = models.CharField("Причина", max_length=200)
    document = models.CharField(
        "Вид документа", max_length=12, choices=ExcuseDocument.choices, default=ExcuseDocument.OTHER
    )
    file = models.FileField("Файл", upload_to=excuse_upload_to, storage=_private_storage, max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто оформил",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_by_title = models.CharField("Автор на момент удаления", max_length=250, blank=True)
    created_at = models.DateTimeField("Оформлена", auto_now_add=True)

    class Meta:
        verbose_name = "Уважительная причина"
        verbose_name_plural = "Уважительные причины"
        ordering = ("-starts", "-id")
        constraints = [
            models.CheckConstraint(condition=models.Q(ends__gte=models.F("starts")), name="excuse_ends_after_starts")
        ]
        indexes = [models.Index(fields=("student", "starts", "ends"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.starts:%d.%m}–{self.ends:%d.%m} · {self.reason}"


class Grade(Archivable):
    """Оценка ученика за урок: ФО от 1 до 10, СОР и СОЧ — баллы из максимума."""

    lesson = models.ForeignKey(Lesson, verbose_name="Урок", related_name="grades", on_delete=models.CASCADE)
    student = models.ForeignKey(
        "students.Student", verbose_name="Ученик", related_name="grades", on_delete=models.CASCADE
    )
    value = models.PositiveSmallIntegerField("Балл")
    comment = models.CharField("Комментарий", max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто поставил",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Поставлена", auto_now_add=True)
    updated_at = models.DateTimeField("Изменена", auto_now=True)

    class Meta:
        verbose_name = "Оценка"
        verbose_name_plural = "Оценки"
        constraints = [models.UniqueConstraint(fields=("lesson", "student"), name="unique_lesson_grade")]
        indexes = [models.Index(fields=("student", "lesson"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.lesson} · {self.value}"


class QuarterResult(models.Model):
    """Итог четверти по журналу: выставленная оценка и расчётный процент."""

    course = models.ForeignKey(Course, verbose_name="Журнал", related_name="results", on_delete=models.CASCADE)
    student = models.ForeignKey(
        "students.Student", verbose_name="Ученик", related_name="quarter_results", on_delete=models.CASCADE
    )
    quarter = models.ForeignKey(Quarter, verbose_name="Четверть", related_name="results", on_delete=models.CASCADE)
    grade = models.PositiveSmallIntegerField("Итог")
    computed_percent = models.DecimalField("Расчётный процент", max_digits=5, decimal_places=1, null=True, blank=True)
    reason = models.CharField("Причина отличия от расчёта", max_length=200, blank=True)
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто выставил",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    set_at = models.DateTimeField("Выставлен", auto_now=True)

    class Meta:
        verbose_name = "Итог четверти"
        verbose_name_plural = "Итоги четверти"
        constraints = [models.UniqueConstraint(fields=("course", "student", "quarter"), name="unique_quarter_result")]

    def __str__(self) -> str:
        return f"{self.student} · {self.course} · {self.quarter.title}: {self.grade}"


class RequestStatus(models.TextChoices):
    PENDING = "pending", "Ждёт"
    APPROVED = "approved", "Одобрено"
    REJECTED = "rejected", "Отклонено"


class LessonRequest(models.Model):
    """Просьба учителя о переносе урока. Решает Кымбат или администратор."""

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="Учитель", related_name="lesson_requests", on_delete=models.CASCADE
    )
    lesson = models.ForeignKey(Lesson, verbose_name="Урок", related_name="requests", on_delete=models.CASCADE)
    wanted = models.CharField("Куда удобно", max_length=200, blank=True)
    reason = models.CharField("Причина", max_length=300)
    status = models.CharField("Состояние", max_length=8, choices=RequestStatus.choices, default=RequestStatus.PENDING)
    answer = models.CharField("Ответ", max_length=300, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто решил",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    decided_at = models.DateTimeField("Решено", null=True, blank=True)
    created_at = models.DateTimeField("Подана", auto_now_add=True)

    class Meta:
        verbose_name = "Просьба о переносе"
        verbose_name_plural = "Просьбы о переносе"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.teacher}: {self.lesson} · {self.get_status_display()}"


# --- Отчёты родителям -------------------------------------------------------


class ReportPeriod(models.TextChoices):
    MONTH = "month", "Месяц"
    QUARTER = "quarter", "Четверть"


class ReportStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    CHECKED = "checked", "Проверен"
    EXPORTED = "exported", "Выгружен"
    SENT = "sent", "Отправлен родителям"


class ParentReport(Archivable):
    """Отчёт родителям: снимок строками, статус и слово куратора.

    Снимок собирается сборкой и не пересчитывается при чтении: родитель
    видит ровно то, что проверил куратор. PDF строится по запросу
    и не хранится.
    """

    student = models.ForeignKey(
        "students.Student", verbose_name="Ученик", related_name="parent_reports", on_delete=models.CASCADE
    )
    period_kind = models.CharField("Период", max_length=8, choices=ReportPeriod.choices)
    period_start = models.DateField("Начало периода")
    period_end = models.DateField("Конец периода")
    title = models.CharField("Название периода", max_length=60)
    status = models.CharField("Статус", max_length=8, choices=ReportStatus.choices, default=ReportStatus.DRAFT)
    built_at = models.DateTimeField("Собран")
    fingerprint = models.CharField("Отпечаток данных", max_length=64, blank=True)
    curator_word = models.TextField("Слово куратора", blank=True)
    #: кто и когда написал слово — видно в отчёте (решение владельца, 27.09.2026)
    word_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто написал слово",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    word_at = models.DateTimeField("Слово написано", null=True, blank=True)
    checked_at = models.DateTimeField("Проверен", null=True, blank=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто проверил",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    exported_at = models.DateTimeField("Выгружен", null=True, blank=True)
    sent_at = models.DateTimeField("Отправлен родителям", null=True, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто отправил",
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Отчёт родителям"
        verbose_name_plural = "Отчёты родителям"
        ordering = ("-period_start", "student__last_name", "student__first_name")
        constraints = [
            models.UniqueConstraint(
                fields=("student", "period_kind", "period_start"),
                condition=models.Q(archived_at__isnull=True),
                name="one_report_per_period",
            )
        ]

    def __str__(self) -> str:
        return f"{self.student} · отчёт за {self.title}"


class ReportSection(models.TextChoices):
    ATTENDANCE = "attendance", "Посещаемость"
    GRADES = "grades", "Оценки"
    EXAMS = "exams", "Экзамены и вузы"
    DOCUMENTS = "documents", "Документы"
    DISCIPLINE = "discipline", "Дисциплина"


class ReportLine(models.Model):
    """Строка снимка отчёта: раздел, подпись, значение, примечание."""

    report = models.ForeignKey(ParentReport, verbose_name="Отчёт", related_name="lines", on_delete=models.CASCADE)
    section = models.CharField("Раздел", max_length=12, choices=ReportSection.choices)
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    title = models.CharField("Подпись", max_length=120)
    value = models.CharField("Значение", max_length=120, blank=True)
    note = models.CharField("Примечание", max_length=300, blank=True)

    class Meta:
        verbose_name = "Строка отчёта"
        verbose_name_plural = "Строки отчёта"
        ordering = ("report", "section", "order", "id")

    def __str__(self) -> str:
        return f"{self.title}: {self.value}"
