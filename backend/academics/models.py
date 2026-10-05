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
from django.utils import translation
from django.utils.translation import gettext, gettext_lazy, pgettext_lazy

from core.archivable import Archivable
from students.models import GroupLanguage


class Scheme(models.TextChoices):
    """Схема оценивания предмета."""

    #: ФО, СОР, СОЧ и итог четверти — обычный предмет
    KZ = "kz", gettext_lazy("ФО, СОР и СОЧ, итог за четверть")
    #: только ФО, в табель не идёт — курсы подготовки (IELTS, SAT)
    FO = "fo", gettext_lazy("Только ФО, в табель не идёт")


class Subject(models.Model):
    """Предмет: название, короткое название, схема и максимумы по умолчанию."""

    code = models.SlugField(gettext_lazy("Код"), max_length=32, unique=True)
    title = models.CharField(gettext_lazy("Название"), max_length=100)
    #: название на казахском — в интерфейсе на казахском и в отчёте родителям на казахском;
    #: пусто — берётся `title`
    title_kk = models.CharField(gettext_lazy("Название на казахском"), max_length=100, blank=True)
    #: название в интерфейсе на английском; пусто — берётся `title`
    title_en = models.CharField(gettext_lazy("Название на английском"), max_length=100, blank=True)
    short_title = models.CharField(gettext_lazy("Короткое название"), max_length=32)
    scheme = models.CharField(gettext_lazy("Схема оценивания"), max_length=2, choices=Scheme.choices, default=Scheme.KZ)
    sor_max = models.PositiveSmallIntegerField(gettext_lazy("Максимум СОР по умолчанию"), default=15)
    soch_max = models.PositiveSmallIntegerField(gettext_lazy("Максимум СОЧ по умолчанию"), default=25)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=100)
    is_active = models.BooleanField(gettext_lazy("Ведётся"), default=True)
    #: посев для разработки — вычищается `purge_fictional`
    is_fictional = models.BooleanField(gettext_lazy("Вымышленный"), default=False)

    class Meta:
        verbose_name = gettext_lazy("Предмет")
        verbose_name_plural = gettext_lazy("Предметы")
        ordering = ("order", "title")

    def __str__(self) -> str:
        return self.title

    @property
    def name(self) -> str:
        """Название на языке ответа: казахское или английское, пусто — русское."""
        lang = (translation.get_language() or "ru").split("-")[0]
        local = {"kk": self.title_kk, "en": self.title_en}.get(lang, "")
        return local.strip() or self.title

    @property
    def short(self) -> str:
        """Короткое название на языке ответа. Короткого казахского и английского
        нет — берётся полное название на этом языке, пусто — русское короткое."""
        name = self.name
        return self.short_title if name == self.title else name


class TeacherProfile(models.Model):
    """Профиль учителя: предметы и свой кабинет. Учётку заводит администратор."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Учётная запись"),
        related_name="teacher_profile",
        on_delete=models.CASCADE,
    )
    subjects = models.ManyToManyField(
        Subject, verbose_name=gettext_lazy("Предметы"), related_name="teachers", blank=True
    )
    room = models.CharField(gettext_lazy("Кабинет"), max_length=40, blank=True)
    is_fictional = models.BooleanField(gettext_lazy("Вымышленный"), default=False)

    class Meta:
        verbose_name = gettext_lazy("Профиль учителя")
        verbose_name_plural = gettext_lazy("Профили учителей")

    def __str__(self) -> str:
        return str(self.user)


# --- Учебный год -------------------------------------------------------------


class AcademicYear(models.Model):
    """Учебный год: четверти, каникулы, праздники, звонки, шкала — всё на него."""

    title = models.CharField(gettext_lazy("Название"), max_length=20)
    starts = models.DateField(gettext_lazy("Начало"))
    ends = models.DateField(gettext_lazy("Конец"))
    is_current = models.BooleanField(gettext_lazy("Текущий"), default=False)
    is_fictional = models.BooleanField(gettext_lazy("Вымышленный"), default=False)

    class Meta:
        verbose_name = gettext_lazy("Учебный год")
        verbose_name_plural = gettext_lazy("Учебные годы")
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
        AcademicYear, verbose_name=gettext_lazy("Учебный год"), related_name="quarters", on_delete=models.CASCADE
    )
    number = models.PositiveSmallIntegerField(gettext_lazy("Номер"))
    title = models.CharField(gettext_lazy("Название"), max_length=40)
    starts = models.DateField(gettext_lazy("Начало"))
    ends = models.DateField(gettext_lazy("Конец"))
    closed_at = models.DateTimeField(gettext_lazy("Итоги закрыты"), null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто закрыл"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = gettext_lazy("Четверть")
        verbose_name_plural = gettext_lazy("Четверти")
        ordering = ("year", "number")
        constraints = [models.UniqueConstraint(fields=("year", "number"), name="unique_quarter_number")]

    def __str__(self) -> str:
        return f"{self.title} {self.year}"

    @property
    def name(self) -> str:
        """Название на языке ответа: название по умолчанию («1 четверть») переводится,
        своё название школы — как введено."""
        from core import stored_text

        return stored_text.localize(self.title)

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None


class Break(models.Model):
    """Каникулы: уроки в эти дни не заводятся."""

    year = models.ForeignKey(
        AcademicYear, verbose_name=gettext_lazy("Учебный год"), related_name="breaks", on_delete=models.CASCADE
    )
    title = models.CharField(gettext_lazy("Название"), max_length=60)
    starts = models.DateField(gettext_lazy("Начало"))
    ends = models.DateField(gettext_lazy("Конец"))

    class Meta:
        verbose_name = gettext_lazy("Каникулы")
        verbose_name_plural = gettext_lazy("Каникулы")
        ordering = ("starts",)

    def __str__(self) -> str:
        return self.title


class Holiday(models.Model):
    """Праздник: один день без уроков."""

    year = models.ForeignKey(
        AcademicYear, verbose_name=gettext_lazy("Учебный год"), related_name="holidays", on_delete=models.CASCADE
    )
    date = models.DateField(gettext_lazy("Дата"))
    title = models.CharField(gettext_lazy("Название"), max_length=80)

    class Meta:
        verbose_name = gettext_lazy("Праздник")
        verbose_name_plural = gettext_lazy("Праздники")
        ordering = ("date",)
        constraints = [models.UniqueConstraint(fields=("year", "date"), name="unique_holiday_date")]

    def __str__(self) -> str:
        return f"{self.date:%d.%m} {self.title}"


class BellSchedule(models.Model):
    """Расписание звонков. У школы их может быть несколько (решение владельца, 27.09.2026).

    Разные классы начинают уроки в разное время, поэтому звонки живут
    не у года, а у расписания звонков; каждое назначается группам. Общего
    расписания «для всех остальных» нет (решение владельца, 05.10.2026):
    время урока берётся из звонков его группы, группа без звонков и поток
    из групп с разными звонками — ошибка в «Расписании» и в накладках.
    """

    year = models.ForeignKey(
        AcademicYear, verbose_name=gettext_lazy("Учебный год"), related_name="bell_schedules", on_delete=models.CASCADE
    )
    title = models.CharField(gettext_lazy("Название"), max_length=60)
    groups = models.ManyToManyField(
        "students.StudyGroup", verbose_name=gettext_lazy("Группы"), related_name="bell_schedules", blank=True
    )

    class Meta:
        verbose_name = gettext_lazy("Расписание звонков")
        verbose_name_plural = gettext_lazy("Расписания звонков")
        ordering = ("year", "title")

    def __str__(self) -> str:
        return self.title


class Bell(models.Model):
    """Звонок: номер урока — начало и конец, внутри расписания звонков.

    Поле `year` осталось от времён одного набора звонков на год; расписание
    звонков (`schedule`) добавлено позже и заполнено миграцией. Год
    у звонка совпадает с годом его расписания.
    """

    year = models.ForeignKey(
        AcademicYear, verbose_name=gettext_lazy("Учебный год"), related_name="bells", on_delete=models.CASCADE
    )
    schedule = models.ForeignKey(
        BellSchedule,
        verbose_name=gettext_lazy("Расписание звонков"),
        related_name="bells",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    number = models.PositiveSmallIntegerField(gettext_lazy("Урок"))
    starts = models.TimeField(gettext_lazy("Начало"))
    ends = models.TimeField(gettext_lazy("Конец"))

    class Meta:
        verbose_name = pgettext_lazy("lesson bell", "Звонок")
        verbose_name_plural = gettext_lazy("Звонки")
        ordering = ("year", "number")
        constraints = [models.UniqueConstraint(fields=("schedule", "number"), name="unique_bell_in_schedule")]

    def __str__(self) -> str:
        return gettext("{number} урок {starts}–{ends}").format(
            number=self.number, starts=f"{self.starts:%H:%M}", ends=f"{self.ends:%H:%M}"
        )


class GradingScale(models.Model):
    """Шкала: веса ФО, СОР, СОЧ, пороги оценок и окно правки учителя."""

    year = models.OneToOneField(
        AcademicYear, verbose_name=gettext_lazy("Учебный год"), related_name="scale", on_delete=models.CASCADE
    )
    weight_fo = models.PositiveSmallIntegerField(gettext_lazy("Вес ФО, %"), default=25)
    weight_sor = models.PositiveSmallIntegerField(gettext_lazy("Вес СОР, %"), default=25)
    weight_soch = models.PositiveSmallIntegerField(gettext_lazy("Вес СОЧ, %"), default=50)
    threshold_5 = models.PositiveSmallIntegerField(gettext_lazy("Пятёрка от, %"), default=85)
    threshold_4 = models.PositiveSmallIntegerField(gettext_lazy("Четвёрка от, %"), default=65)
    threshold_3 = models.PositiveSmallIntegerField(gettext_lazy("Тройка от, %"), default=40)
    fo_max = models.PositiveSmallIntegerField(gettext_lazy("Максимум ФО"), default=10)
    edit_days = models.PositiveSmallIntegerField(gettext_lazy("Учитель правит оценку, дней"), default=7)

    class Meta:
        verbose_name = gettext_lazy("Шкала оценивания")
        verbose_name_plural = gettext_lazy("Шкалы оценивания")

    def __str__(self) -> str:
        return f"{self.weight_fo}/{self.weight_sor}/{self.weight_soch} · {self.year}"


class ReportCadence(models.TextChoices):
    """Когда собираются отчёты родителям."""

    MONTH = "month", gettext_lazy("Последняя пятница месяца и после четверти")
    QUARTER = "quarter", gettext_lazy("Только после закрытия четверти")


class ReportSettings(models.Model):
    """Настройки отчётов родителям: когда собирать и какие разделы входят."""

    year = models.OneToOneField(
        AcademicYear, verbose_name=gettext_lazy("Учебный год"), related_name="report_settings", on_delete=models.CASCADE
    )
    cadence = models.CharField(
        gettext_lazy("Когда собирать"), max_length=8, choices=ReportCadence.choices, default=ReportCadence.MONTH
    )
    section_attendance = models.BooleanField(gettext_lazy("Посещаемость по урокам"), default=True)
    section_grades = models.BooleanField(gettext_lazy("Оценки по предметам"), default=True)
    section_exams = models.BooleanField(gettext_lazy("Экзамены и вузы"), default=True)
    section_documents = models.BooleanField(gettext_lazy("Документы для поступления"), default=True)
    section_curator = models.BooleanField(gettext_lazy("Слово куратора"), default=True)
    section_discipline = models.BooleanField(gettext_lazy("Замечания по дисциплине"), default=False)

    class Meta:
        verbose_name = gettext_lazy("Настройки отчётов")
        verbose_name_plural = gettext_lazy("Настройки отчётов")

    def __str__(self) -> str:
        return gettext("Отчёты · {year}").format(year=self.year)


# --- Составы ----------------------------------------------------------------


class CohortKind(models.TextChoices):
    GROUP = "group", gettext_lazy("Вся группа")
    SUBGROUP = "subgroup", gettext_lazy("Подгруппа")
    STREAM = "stream", gettext_lazy("Поток")


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

    kind = models.CharField(gettext_lazy("Вид"), max_length=8, choices=CohortKind.choices)
    group = models.ForeignKey(
        "students.StudyGroup",
        verbose_name=gettext_lazy("Группа"),
        related_name="cohorts",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    subject = models.ForeignKey(
        Subject,
        verbose_name=gettext_lazy("Предмет подгруппы"),
        related_name="subgroups",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    number = models.PositiveSmallIntegerField(gettext_lazy("Номер подгруппы"), null=True, blank=True)
    name = models.CharField(gettext_lazy("Название"), max_length=120)
    short_name = models.CharField(gettext_lazy("Короткое название"), max_length=60, blank=True)
    rule = models.CharField(gettext_lazy("Как делили"), max_length=60, blank=True)
    stream = models.ForeignKey(
        "self",
        verbose_name=gettext_lazy("Поток подгруппы"),
        related_name="inner_subgroups",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        limit_choices_to={"kind": "stream"},
    )
    room = models.CharField(gettext_lazy("Основной кабинет"), max_length=40, blank=True)
    is_fictional = models.BooleanField(gettext_lazy("Вымышленный"), default=False)
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Состав")
        verbose_name_plural = gettext_lazy("Составы")
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

    cohort = models.ForeignKey(
        Cohort, verbose_name=gettext_lazy("Состав"), related_name="memberships", on_delete=models.CASCADE
    )
    student = models.ForeignKey(
        "students.Student",
        verbose_name=gettext_lazy("Ученик"),
        related_name="cohort_memberships",
        on_delete=models.CASCADE,
    )
    since = models.DateField(gettext_lazy("С"))
    until = models.DateField(gettext_lazy("По"), null=True, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Членство в подгруппе")
        verbose_name_plural = gettext_lazy("Членства в подгруппах")
        ordering = ("cohort", "student")
        indexes = [models.Index(fields=("student", "until"))]

    def __str__(self) -> str:
        return gettext("{student} в {cohort} с {since}").format(
            student=self.student, cohort=self.cohort, since=self.since
        )


class StreamPart(models.Model):
    """Часть потока: группа или подгруппа."""

    stream = models.ForeignKey(
        Cohort, verbose_name=gettext_lazy("Поток"), related_name="parts", on_delete=models.CASCADE
    )
    part = models.ForeignKey(
        Cohort, verbose_name=gettext_lazy("Часть"), related_name="in_streams", on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = gettext_lazy("Часть потока")
        verbose_name_plural = gettext_lazy("Части потоков")
        constraints = [models.UniqueConstraint(fields=("stream", "part"), name="unique_stream_part")]

    def __str__(self) -> str:
        return gettext("{part} в {stream}").format(part=self.part, stream=self.stream)


# --- Журналы и уроки --------------------------------------------------------


class ReportRole(models.TextChoices):
    """Какой отзыв в отчёте родителям пишется по журналу.

    На уровне журнала, а не предмета: SAT — один предмет, а Verbal и Math
    ведут разные учителя (решение владельца, 30.09.2026).
    """

    NONE = "", gettext_lazy("нет")
    EEP = "eep", "GE / EEP"
    SAT_VERBAL = "sat_verbal", "SAT Verbal"
    SAT_MATH = "sat_math", "SAT Math"


class Course(Archivable):
    """Журнал: предмет у одного учителя у одного состава.

    Учитель может быть не назначен (решение владельца, 29.09.2026): у Creative
    Writing его нет ни в расписании школы, ни в списке сотрудников. Такой урок
    стоит в расписании, а отмечает его администратор, пока учителя не назначат.
    """

    subject = models.ForeignKey(
        Subject, verbose_name=gettext_lazy("Предмет"), related_name="courses", on_delete=models.PROTECT
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Учитель"),
        related_name="courses",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    cohort = models.ForeignKey(
        Cohort, verbose_name=gettext_lazy("Состав"), related_name="courses", on_delete=models.CASCADE
    )
    report_role = models.CharField(
        gettext_lazy("Раздел отчёта родителям"),
        max_length=12,
        choices=ReportRole.choices,
        default=ReportRole.NONE,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Журнал")
        verbose_name_plural = gettext_lazy("Журналы")
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

    course = models.ForeignKey(
        Course, verbose_name=gettext_lazy("Журнал"), related_name="series", on_delete=models.CASCADE
    )
    weekday = models.PositiveSmallIntegerField(gettext_lazy("День недели"))
    slot = models.PositiveSmallIntegerField(gettext_lazy("Номер урока"))
    room = models.CharField(gettext_lazy("Кабинет"), max_length=40, blank=True)
    starts = models.DateField(gettext_lazy("С"))
    ends = models.DateField(gettext_lazy("По"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто завёл"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Заведена"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Серия уроков")
        verbose_name_plural = gettext_lazy("Серии уроков")
        ordering = ("weekday", "slot")

    def __str__(self) -> str:
        return gettext("{course} · день {weekday}, {slot} урок").format(
            course=self.course, weekday=self.weekday, slot=self.slot
        )


class LessonStatus(models.TextChoices):
    PLANNED = "planned", gettext_lazy("По плану")
    CANCELLED = "cancelled", gettext_lazy("Отменён")
    MOVED = "moved", gettext_lazy("Перенесён")


class LessonKind(models.TextChoices):
    FO = "fo", gettext_lazy("ФО")
    SOR = "sor", gettext_lazy("СОР")
    SOCH = "soch", gettext_lazy("СОЧ")


class Lesson(Archivable):
    """Конкретный урок: дата, номер, кабинет, учитель, замена, статус, тема.

    Урок с отметками или оценками при удалении уходит в архив администратора
    вместе с ними (каскад `Archivable`) и возвращается оттуда.
    """

    course = models.ForeignKey(
        Course, verbose_name=gettext_lazy("Журнал"), related_name="lessons", on_delete=models.CASCADE
    )
    series = models.ForeignKey(
        LessonSeries,
        verbose_name=gettext_lazy("Серия"),
        related_name="lessons",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    date = models.DateField(gettext_lazy("Дата"))
    slot = models.PositiveSmallIntegerField(gettext_lazy("Номер урока"))
    room = models.CharField(gettext_lazy("Кабинет"), max_length=40, blank=True)
    #: пусто — учитель не назначен (см. `Course`)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Учитель"),
        related_name="lessons",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    substitute = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Замена"),
        related_name="substituted_lessons",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    status = models.CharField(
        gettext_lazy("Статус"), max_length=10, choices=LessonStatus.choices, default=LessonStatus.PLANNED
    )
    reason = models.CharField(gettext_lazy("Причина"), max_length=200, blank=True)
    moved_from_date = models.DateField(gettext_lazy("Перенесён с даты"), null=True, blank=True)
    moved_from_slot = models.PositiveSmallIntegerField(gettext_lazy("Перенесён с урока"), null=True, blank=True)
    topic = models.CharField(gettext_lazy("Тема"), max_length=200, blank=True)
    homework = models.TextField(gettext_lazy("Домашнее задание"), blank=True)
    kind = models.CharField(
        gettext_lazy("Вид оценивания"), max_length=4, choices=LessonKind.choices, default=LessonKind.FO
    )
    number = models.PositiveSmallIntegerField(gettext_lazy("Номер СОР или СОЧ"), null=True, blank=True)
    max_score = models.PositiveSmallIntegerField(gettext_lazy("Максимум баллов"), null=True, blank=True)
    note = models.CharField(gettext_lazy("Примечание"), max_length=120, blank=True)
    marked_at = models.DateTimeField(gettext_lazy("Посещаемость сохранена"), null=True, blank=True)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто отметил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: напоминание о неотмеченном уроке ушло — второго не будет
    reminded_at = models.DateTimeField(gettext_lazy("Напоминание ушло"), null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто завёл"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Заведён"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Изменён"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Урок")
        verbose_name_plural = gettext_lazy("Уроки")
        ordering = ("date", "slot", "id")
        indexes = [
            models.Index(fields=("date", "slot")),
            models.Index(fields=("course", "date")),
            models.Index(fields=("teacher", "date")),
        ]

    def __str__(self) -> str:
        return gettext("{course} · {date}, {slot} урок").format(
            course=self.course, date=f"{self.date:%d.%m.%Y}", slot=self.slot
        )

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

    ABSENT = "absent", gettext_lazy("Не был")
    LATE = "late", gettext_lazy("Опоздал")


class Attendance(Archivable):
    """Отметка ученика на уроке. «У» не хранится: её даёт уважительная причина."""

    lesson = models.ForeignKey(
        Lesson, verbose_name=gettext_lazy("Урок"), related_name="attendance", on_delete=models.CASCADE
    )
    student = models.ForeignKey(
        "students.Student",
        verbose_name=gettext_lazy("Ученик"),
        related_name="lesson_attendance",
        on_delete=models.CASCADE,
    )
    mark = models.CharField(gettext_lazy("Отметка"), max_length=6, choices=Mark.choices)
    #: когда пришёл опоздавший — по Алматы; у опозданий до 30.09.2026 пусто:
    #: такое опоздание считается присутствием целиком, «время не указано»
    arrived_at = models.TimeField(gettext_lazy("Пришёл в"), null=True, blank=True)
    noted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто отметил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Отмечен"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Изменён"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Отметка посещаемости")
        verbose_name_plural = gettext_lazy("Отметки посещаемости")
        constraints = [models.UniqueConstraint(fields=("lesson", "student"), name="unique_lesson_attendance")]
        indexes = [models.Index(fields=("student", "lesson"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.lesson} · {self.get_mark_display()}"


class ExcuseDocument(models.TextChoices):
    CERTIFICATE = "certificate", gettext_lazy("Справка")
    PARENTS = "parents", gettext_lazy("Заявление родителей")
    ORDER = "order", gettext_lazy("Приказ школы")
    OTHER = "other", gettext_lazy("Другое")


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
        "students.Student", verbose_name=gettext_lazy("Ученик"), related_name="excuses", on_delete=models.CASCADE
    )
    starts = models.DateField(gettext_lazy("С"))
    ends = models.DateField(gettext_lazy("По"))
    reason = models.CharField(gettext_lazy("Причина"), max_length=200)
    document = models.CharField(
        gettext_lazy("Вид документа"), max_length=12, choices=ExcuseDocument.choices, default=ExcuseDocument.OTHER
    )
    file = models.FileField(
        gettext_lazy("Файл"), upload_to=excuse_upload_to, storage=_private_storage, max_length=300, blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто оформил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_by_title = models.CharField(gettext_lazy("Автор на момент удаления"), max_length=250, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Оформлена"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Уважительная причина")
        verbose_name_plural = gettext_lazy("Уважительные причины")
        ordering = ("-starts", "-id")
        constraints = [
            models.CheckConstraint(condition=models.Q(ends__gte=models.F("starts")), name="excuse_ends_after_starts")
        ]
        indexes = [models.Index(fields=("student", "starts", "ends"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.starts:%d.%m}–{self.ends:%d.%m} · {self.reason}"


class Grade(Archivable):
    """Оценка ученика за урок: ФО от 1 до 10, СОР и СОЧ — баллы из максимума."""

    lesson = models.ForeignKey(
        Lesson, verbose_name=gettext_lazy("Урок"), related_name="grades", on_delete=models.CASCADE
    )
    student = models.ForeignKey(
        "students.Student", verbose_name=gettext_lazy("Ученик"), related_name="grades", on_delete=models.CASCADE
    )
    value = models.PositiveSmallIntegerField(gettext_lazy("Балл"))
    comment = models.CharField(gettext_lazy("Комментарий"), max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто поставил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Поставлена"), auto_now_add=True)
    updated_at = models.DateTimeField(gettext_lazy("Изменена"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Оценка")
        verbose_name_plural = gettext_lazy("Оценки")
        constraints = [models.UniqueConstraint(fields=("lesson", "student"), name="unique_lesson_grade")]
        indexes = [models.Index(fields=("student", "lesson"))]

    def __str__(self) -> str:
        return f"{self.student} · {self.lesson} · {self.value}"


class QuarterResult(models.Model):
    """Итог четверти по журналу: выставленная оценка и расчётный процент."""

    course = models.ForeignKey(
        Course, verbose_name=gettext_lazy("Журнал"), related_name="results", on_delete=models.CASCADE
    )
    student = models.ForeignKey(
        "students.Student",
        verbose_name=gettext_lazy("Ученик"),
        related_name="quarter_results",
        on_delete=models.CASCADE,
    )
    quarter = models.ForeignKey(
        Quarter, verbose_name=gettext_lazy("Четверть"), related_name="results", on_delete=models.CASCADE
    )
    grade = models.PositiveSmallIntegerField(gettext_lazy("Итог"))
    computed_percent = models.DecimalField(
        gettext_lazy("Расчётный процент"), max_digits=5, decimal_places=1, null=True, blank=True
    )
    reason = models.CharField(gettext_lazy("Причина отличия от расчёта"), max_length=200, blank=True)
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто выставил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    set_at = models.DateTimeField(gettext_lazy("Выставлен"), auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("Итог четверти")
        verbose_name_plural = gettext_lazy("Итоги четверти")
        constraints = [models.UniqueConstraint(fields=("course", "student", "quarter"), name="unique_quarter_result")]

    def __str__(self) -> str:
        return f"{self.student} · {self.course} · {self.quarter.title}: {self.grade}"


class RequestStatus(models.TextChoices):
    PENDING = "pending", gettext_lazy("Ждёт")
    APPROVED = "approved", gettext_lazy("Одобрено")
    REJECTED = "rejected", gettext_lazy("Отклонено")


class LessonRequest(models.Model):
    """Просьба учителя о переносе урока. Решает Кымбат или администратор."""

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Учитель"),
        related_name="lesson_requests",
        on_delete=models.CASCADE,
    )
    lesson = models.ForeignKey(
        Lesson, verbose_name=gettext_lazy("Урок"), related_name="requests", on_delete=models.CASCADE
    )
    wanted = models.CharField(gettext_lazy("Куда удобно"), max_length=200, blank=True)
    reason = models.CharField(gettext_lazy("Причина"), max_length=300)
    status = models.CharField(
        gettext_lazy("Состояние"), max_length=8, choices=RequestStatus.choices, default=RequestStatus.PENDING
    )
    answer = models.CharField(gettext_lazy("Ответ"), max_length=300, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто решил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    decided_at = models.DateTimeField(gettext_lazy("Решено"), null=True, blank=True)
    created_at = models.DateTimeField(gettext_lazy("Подана"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Просьба о переносе")
        verbose_name_plural = gettext_lazy("Просьбы о переносе")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.teacher}: {self.lesson} · {self.get_status_display()}"


# --- Отчёты родителям -------------------------------------------------------


class ReportPeriod(models.TextChoices):
    MONTH = "month", gettext_lazy("Месяц")
    QUARTER = "quarter", gettext_lazy("Четверть")
    #: «с — по» — отчёты по шаблонам школы (решение владельца, 30.09.2026)
    CUSTOM = "custom", gettext_lazy("Свой период")


class ReportTemplate(models.TextChoices):
    """Вид отчёта: прежний отчёт LMS и два шаблона школы."""

    STANDARD = "standard", gettext_lazy("Стандартный")
    REVIEW = "review", gettext_lazy("Вариант 1 · отзыв об успеваемости")
    PROGRESS = "progress", gettext_lazy("Вариант 2 · отчёт о прогрессе")


class DraftState(models.TextChoices):
    """Черновик текстов отчёта от ИИ."""

    NONE = "", gettext_lazy("не заказан")
    PENDING = "pending", gettext_lazy("пишется")
    DONE = "done", gettext_lazy("написан")
    SKIPPED = "skipped", gettext_lazy("данных нет")
    FAILED = "failed", gettext_lazy("ИИ недоступен")


class ReportStatus(models.TextChoices):
    DRAFT = "draft", gettext_lazy("Черновик")
    CHECKED = "checked", gettext_lazy("Проверен")
    EXPORTED = "exported", gettext_lazy("Выгружен")
    SENT = "sent", gettext_lazy("Отправлен родителям")


class ParentReport(Archivable):
    """Отчёт родителям: снимок строками, статус и слово куратора.

    Снимок собирается сборкой и не пересчитывается при чтении: родитель
    видит ровно то, что проверил куратор. PDF строится по запросу
    и не хранится.
    """

    student = models.ForeignKey(
        "students.Student", verbose_name=gettext_lazy("Ученик"), related_name="parent_reports", on_delete=models.CASCADE
    )
    period_kind = models.CharField(gettext_lazy("Период"), max_length=8, choices=ReportPeriod.choices)
    period_start = models.DateField(gettext_lazy("Начало периода"))
    period_end = models.DateField(gettext_lazy("Конец периода"))
    title = models.CharField(gettext_lazy("Название периода"), max_length=60)
    status = models.CharField(
        gettext_lazy("Статус"), max_length=8, choices=ReportStatus.choices, default=ReportStatus.DRAFT
    )
    template = models.CharField(
        gettext_lazy("Вид отчёта"), max_length=10, choices=ReportTemplate.choices, default=ReportTemplate.STANDARD
    )
    #: язык отчёта: по умолчанию — язык группы
    language = models.CharField(
        gettext_lazy("Язык"), max_length=2, choices=GroupLanguage.choices, default=GroupLanguage.RU
    )
    built_at = models.DateTimeField(gettext_lazy("Собран"))
    fingerprint = models.CharField(gettext_lazy("Отпечаток данных"), max_length=64, blank=True)
    curator_word = models.TextField(gettext_lazy("Слово куратора"), blank=True)
    #: кто и когда написал слово — видно в отчёте (решение владельца, 27.09.2026)
    word_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто написал слово"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    word_at = models.DateTimeField(gettext_lazy("Слово написано"), null=True, blank=True)
    # тексты отчётов по шаблонам школы: черновик пишет ИИ, правит куратор
    mock_comment = models.TextField(gettext_lazy("Комментарий по Mock Test"), blank=True)
    character = models.TextField(gettext_lazy("Характеристика"), blank=True)
    summary = models.TextField(gettext_lazy("Итоги и рекомендации"), blank=True)
    draft_state = models.CharField(
        gettext_lazy("Черновик ИИ"), max_length=8, choices=DraftState.choices, default=DraftState.NONE, blank=True
    )
    draft_note = models.CharField(gettext_lazy("Почему черновика нет"), max_length=250, blank=True)
    drafted_at = models.DateTimeField(gettext_lazy("Черновик написан"), null=True, blank=True)
    #: тексты правил человек после черновика ИИ — «Обновить данные» не
    #: переписывает их без вопроса «Перезаписать мои правки?» (30.09.2026)
    texts_edited_at = models.DateTimeField(gettext_lazy("Тексты правил человек"), null=True, blank=True)
    checked_at = models.DateTimeField(gettext_lazy("Проверен"), null=True, blank=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто проверил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    exported_at = models.DateTimeField(gettext_lazy("Выгружен"), null=True, blank=True)
    sent_at = models.DateTimeField(gettext_lazy("Отправлен родителям"), null=True, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто отправил"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Создан"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Отчёт родителям")
        verbose_name_plural = gettext_lazy("Отчёты родителям")
        ordering = ("-period_start", "student__last_name", "student__first_name")
        constraints = [
            models.UniqueConstraint(
                fields=("student", "template", "language", "period_kind", "period_start", "period_end"),
                condition=models.Q(archived_at__isnull=True),
                name="one_report_per_period",
            )
        ]

    def __str__(self) -> str:
        return gettext("{student} · отчёт за {period}").format(student=self.student, period=self.title)


class ReportSection(models.TextChoices):
    ATTENDANCE = "attendance", gettext_lazy("Посещаемость")
    GRADES = "grades", gettext_lazy("Оценки")
    EXAMS = "exams", gettext_lazy("Экзамены и вузы")
    DOCUMENTS = "documents", gettext_lazy("Документы")
    DISCIPLINE = "discipline", gettext_lazy("Дисциплина")
    # отчёты по шаблонам школы
    IELTS = "ielts", gettext_lazy("IELTS Mock Test")
    SAT = "sat", gettext_lazy("SAT Mock Test")
    PROFILE = "profile", gettext_lazy("Уровень английского и спорт")


class ReportLine(models.Model):
    """Строка снимка отчёта: раздел, подпись, значение, примечание."""

    report = models.ForeignKey(
        ParentReport, verbose_name=gettext_lazy("Отчёт"), related_name="lines", on_delete=models.CASCADE
    )
    section = models.CharField(gettext_lazy("Раздел"), max_length=12, choices=ReportSection.choices)
    #: что это за строка в шаблоне школы («days_total», «grade»); у стандартного пусто
    code = models.CharField(gettext_lazy("Код строки"), max_length=24, blank=True)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=0)
    title = models.CharField(gettext_lazy("Подпись"), max_length=120)
    value = models.CharField(gettext_lazy("Значение"), max_length=120, blank=True)
    note = models.CharField(gettext_lazy("Примечание"), max_length=300, blank=True)

    class Meta:
        verbose_name = gettext_lazy("Строка отчёта")
        verbose_name_plural = gettext_lazy("Строки отчёта")
        ordering = ("report", "section", "order", "id")

    def __str__(self) -> str:
        return f"{self.title}: {self.value}"


class ReviewKind(models.TextChoices):
    EEP = "eep", "GE / EEP"
    SAT_VERBAL = "sat_verbal", "SAT Verbal"
    SAT_MATH = "sat_math", "SAT Math"
    #: отзыв учителя другого предмета — «ФИО учителя — предмет»
    SUBJECT = "subject", gettext_lazy("Предмет")


class ReportReview(models.Model):
    """Отзыв учителя в отчёте по шаблону школы: блок с заголовком и текстом.

    Три блока (GE/EEP, SAT Verbal, SAT Math) есть всегда; блоки других
    предметов добавляет ИИ, если учителя оставили комментарии за период,
    и любой из них куратор может убрать.
    """

    report = models.ForeignKey(
        ParentReport, verbose_name=gettext_lazy("Отчёт"), related_name="reviews", on_delete=models.CASCADE
    )
    kind = models.CharField(gettext_lazy("Вид"), max_length=12, choices=ReviewKind.choices)
    order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=0)
    course = models.ForeignKey(
        Course, verbose_name=gettext_lazy("Журнал"), related_name="+", on_delete=models.SET_NULL, null=True, blank=True
    )
    teacher_name = models.CharField(gettext_lazy("Учитель"), max_length=200, blank=True)
    subject_title = models.CharField(gettext_lazy("Предмет"), max_length=120, blank=True)
    text = models.TextField(gettext_lazy("Текст"), blank=True)
    #: текст написал ИИ и человек его ещё не менял
    by_ai = models.BooleanField(gettext_lazy("Черновик ИИ"), default=False)

    class Meta:
        verbose_name = gettext_lazy("Отзыв в отчёте")
        verbose_name_plural = gettext_lazy("Отзывы в отчёте")
        ordering = ("report", "order", "id")

    def __str__(self) -> str:
        return f"{self.report} · {self.get_kind_display()}"


# --- Уровень английского ------------------------------------------------------


class CefrLevel(models.TextChoices):
    A1 = "A1", "A1"
    A2 = "A2", "A2"
    B1 = "B1", "B1"
    B2 = "B2", "B2"
    C1 = "C1", "C1"
    C2 = "C2", "C2"


class EnglishLevel(models.Model):
    """Уровень английского ученика с даты — строками, у уровня есть история.

    Вносят учитель GE/EEP своего состава, Кымбат, куратор группы
    и администратор (решение владельца, 30.09.2026). Из балла IELTS
    не выводится. Отчёт берёт последний уровень на конец периода.
    """

    student = models.ForeignKey(
        "students.Student", verbose_name=gettext_lazy("Ученик"), related_name="english_levels", on_delete=models.CASCADE
    )
    level = models.CharField(gettext_lazy("Уровень"), max_length=2, choices=CefrLevel.choices)
    since = models.DateField(gettext_lazy("С"))
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=gettext_lazy("Кто внёс"),
        related_name="+",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(gettext_lazy("Внесён"), auto_now_add=True)

    class Meta:
        verbose_name = gettext_lazy("Уровень английского")
        verbose_name_plural = gettext_lazy("Уровни английского")
        ordering = ("student", "-since", "-id")
        constraints = [models.UniqueConstraint(fields=("student", "since"), name="one_english_level_per_day")]

    def __str__(self) -> str:
        return gettext("{student} · {level} с {since}").format(
            student=self.student, level=self.level, since=f"{self.since:%d.%m.%Y}"
        )
