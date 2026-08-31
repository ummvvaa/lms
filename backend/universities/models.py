"""Справочник вузов и заявки учеников.

Инвариант №4: дедлайн принадлежит вузу, а не ученику — он живёт
в `AdmissionRound` и меняется один раз для всех, кто туда подаётся.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.archivable import Archivable
from students.models import Student

#: Текст плашки над непроверенной записью справочника (инвариант №14).
UNVERIFIED_NOTE = "Данные не подтверждены, проверьте на сайте вуза"


class CatalogSource(models.TextChoices):
    """Откуда взялась запись справочника.

    Отличать нужно ради инварианта №14: всё, что пришло не от сотрудника
    школы и не с официального сайта, показывается только с плашкой.
    """

    SCHOOL = "school", "Заведено школой"
    SEED = "seed", "Стартовый справочник"
    IMPORT = "import", "Импорт файла"
    SYNC = "sync", "Фоновая сверка"
    #: разобрано моделью по названию или ссылке — такие записи всегда
    #: заводятся неподтверждёнными и сверяются человеком (инвариант №14)
    AI = "ai", "Разобрано помощником"


class VerifiableRecord(models.Model):
    """Запись справочника с признаком «данные подтверждены» (инвариант №14).

    Снять признак вправе только директор по поступлению — руками или через
    сверку с официальным сайтом. До этого запись живёт с оранжевой плашкой,
    и ученику она показывается только вместе с ней.
    """

    data_source = models.CharField(
        "Источник записи", max_length=16, choices=CatalogSource.choices, default=CatalogSource.SCHOOL
    )
    is_verified = models.BooleanField("Данные подтверждены", default=True)
    verified_at = models.DateTimeField("Когда подтверждено", null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто подтвердил",
        related_name="verified_%(class)s_set",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True

    @property
    def verification_note(self) -> str:
        """Текст плашки. Пустая строка — плашки нет."""
        return "" if self.is_verified else UNVERIFIED_NOTE


class University(VerifiableRecord):
    """Вуз."""

    name = models.CharField("Название", max_length=250, unique=True)
    country = models.CharField("Страна", max_length=100)
    website = models.URLField("Сайт", blank=True)
    domain = models.CharField(
        "Домен для сверки", max_length=100, blank=True, help_text="Например utoronto.ca — по нему сверяются источники"
    )
    #: место в мировом рейтинге — для порядка «других университетов»
    #: в результате подбора (фаза 40). Ведёт директор по поступлению;
    #: рейтинги мы не выдумываем: пусто — значит не заполнено
    world_rank = models.PositiveSmallIntegerField("Место в мировом рейтинге", null=True, blank=True)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Вуз"
        verbose_name_plural = "Вузы"
        ordering = ("name",)
        indexes = [models.Index(fields=("country",))]

    def __str__(self) -> str:
        return self.name


class ProgramLevel(models.TextChoices):
    BACHELOR = "bachelor", "Бакалавриат"
    MASTER = "master", "Магистратура"
    FOUNDATION = "foundation", "Foundation"


class Program(VerifiableRecord):
    """Программа обучения в вузе."""

    university = models.ForeignKey(University, verbose_name="Вуз", related_name="programs", on_delete=models.CASCADE)
    name = models.CharField("Специальность", max_length=250)
    level = models.CharField("Уровень", max_length=16, choices=ProgramLevel.choices, default=ProgramLevel.BACHELOR)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Программа"
        verbose_name_plural = "Программы"
        ordering = ("university__name", "name")
        constraints = [
            models.UniqueConstraint(fields=("university", "name", "level"), name="uniq_program_per_university")
        ]

    def __str__(self) -> str:
        return f"{self.university.name} — {self.name}"


class RoundType(models.TextChoices):
    ED = "ED", "Early Decision"
    EA = "EA", "Early Action"
    RD = "RD", "Regular Decision"
    ROLLING = "Rolling", "Rolling"


class AdmissionRound(VerifiableRecord):
    """Раунд подачи с дедлайном. Дедлайн — здесь и только здесь."""

    program = models.ForeignKey(Program, verbose_name="Программа", related_name="rounds", on_delete=models.CASCADE)
    round_type = models.CharField("Тип раунда", max_length=8, choices=RoundType.choices)
    deadline = models.DateField("Дедлайн")
    source_url = models.URLField("Источник", blank=True)
    checked_at = models.DateTimeField("Последняя сверка", null=True, blank=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Раунд подачи"
        verbose_name_plural = "Раунды подачи"
        ordering = ("deadline",)
        constraints = [
            models.UniqueConstraint(fields=("program", "round_type"), name="uniq_round_per_program"),
        ]
        indexes = [models.Index(fields=("deadline",))]

    def __str__(self) -> str:
        return f"{self.program} · {self.round_type} до {self.deadline}"


class Tier(models.TextChoices):
    REACH = "reach", "Reach"
    TARGET = "target", "Target"
    SAFETY = "safety", "Safety"


class ApplicationStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Не начата"
    IN_PROGRESS = "in_progress", "В работе"
    READY = "ready", "Готова"
    SUBMITTED = "submitted", "Подана"
    ACCEPTED = "accepted", "Принят"
    REJECTED = "rejected", "Отказ"
    WAITLIST = "waitlist", "Лист ожидания"


class AddedBy(models.TextChoices):
    """Кто положил программу в список ученика."""

    DIRECTOR = "director", "Директор по поступлению"
    STUDENT = "student", "Ученик"
    IMPORT = "import", "Импорт"


class StudentUniversity(Archivable):
    """Программа в списке ученика. Владелец — домен `admission`.

    Ученик может добавить программу себе сам — такая запись помечается
    `added_by=student` и ждёт подтверждения директора. Удалить он может
    только то, что добавил сам: чужое решение снимает тот, кто его принял.
    """

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="universities", on_delete=models.CASCADE)
    program = models.ForeignKey(Program, verbose_name="Программа", related_name="applicants", on_delete=models.PROTECT)
    admission_round = models.ForeignKey(
        AdmissionRound,
        verbose_name="Раунд",
        related_name="applicants",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    tier = models.CharField("Категория", max_length=8, choices=Tier.choices, default=Tier.TARGET)
    application_status = models.CharField(
        "Статус заявки", max_length=16, choices=ApplicationStatus.choices, default=ApplicationStatus.NOT_STARTED
    )
    note = models.CharField("Примечание", max_length=250, blank=True)
    added_by = models.CharField("Кто добавил", max_length=16, choices=AddedBy.choices, default=AddedBy.DIRECTOR)
    #: подтверждение директора нужно только тому, что добавил ученик
    is_confirmed = models.BooleanField("Подтверждено директором", default=True)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        verbose_name = "Вуз ученика"
        verbose_name_plural = "Вузы учеников"
        ordering = ("student", "tier")
        constraints = [
            # архивную запись ученик не видит, и она не должна мешать
            # добавить ту же программу заново
            models.UniqueConstraint(
                fields=("student", "program"),
                condition=models.Q(archived_at__isnull=True),
                name="uniq_student_program",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student} → {self.program}"

    @property
    def deadline(self):
        """Дедлайн берётся из раунда вуза, у ученика своего дедлайна нет."""
        return self.admission_round.deadline if self.admission_round_id else None


class AdmissionRequirement(VerifiableRecord):
    """Требования программы к абитуриенту.

    Ровно те таблицы, которые директор по поступлению ведёт в своих файлах.
    Владелец — домен `admission`. Пороги хранятся типизированными колонками
    (инвариант №6): по ним считается соответствие и строятся подборки.

    Пустой порог означает «требования нет», а не «ноль».
    """

    program = models.OneToOneField(
        Program, verbose_name="Программа", related_name="requirement", on_delete=models.CASCADE
    )
    min_gpa = models.DecimalField("Минимальный GPA", max_digits=4, decimal_places=2, null=True, blank=True)
    min_ielts = models.DecimalField("Минимальный IELTS", max_digits=3, decimal_places=1, null=True, blank=True)
    min_toefl = models.PositiveSmallIntegerField("Минимальный TOEFL", null=True, blank=True)
    min_sat = models.PositiveSmallIntegerField("Минимальный SAT", null=True, blank=True)
    min_act = models.PositiveSmallIntegerField("Минимальный ACT", null=True, blank=True)
    required_subjects = models.CharField("Требуемые предметы", max_length=300, blank=True, help_text="Через запятую")
    portfolio_required = models.BooleanField("Нужно портфолио", default=False)
    portfolio_note = models.CharField("Требования к портфолио", max_length=300, blank=True)
    notes = models.TextField("Примечания", blank=True)
    source_url = models.URLField("Источник", blank=True)
    checked_at = models.DateTimeField("Дата актуализации", null=True, blank=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Требования программы"
        verbose_name_plural = "Требования программ"
        ordering = ("program__university__name", "program__name")

    def __str__(self) -> str:
        return f"Требования: {self.program}"

    @property
    def subjects_list(self) -> list[str]:
        return [x.strip() for x in self.required_subjects.split(",") if x.strip()]


# --- Подбор вузов: прогон с историей (фаза 40) ----------------------------


class MatchRunStatus(models.TextChoices):
    RUNNING = "running", "Считается"
    DONE = "done", "Готов"
    FAILED = "failed", "Не получился"


class RunTier(models.TextChoices):
    """Категории результата подбора — четыре, как в согласованном образце.

    Это категории соответствия требованиям, а не шансы поступления
    (инвариант №11). Границы — в настройках (`MATCH_TIER_*`), не в коде.
    """

    DREAM = "dream", "Dream — очень конкурентно, но стоит попробовать"
    REACH = "reach", "Reach — амбициозно, нужны усилия"
    MATCH = "match", "Match — реалистично при текущей траектории"
    SAFETY = "safety", "Safety — уже соответствуете или превышаете"


class ResultSection(models.TextChoices):
    TOP = "top", "Финальный список"
    STRONG = "strong", "Ещё сильные варианты"
    OTHER = "other", "Другие университеты"


class MatchRun(models.Model):
    """Один прогон подбора — датированный снимок.

    Соответствие остаётся вычисляемым для живых экранов; здесь хранится
    именно снимок «подбор от такого-то числа» — как недельные срезы
    Readiness. Шапка результата показывает и дату, и профиль, из которого
    считалось: ученик видит исходные данные, а не только вывод.
    """

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="match_runs", on_delete=models.CASCADE)
    major = models.CharField("Специальность", max_length=150, blank=True)
    level = models.CharField("Уровень", max_length=16, choices=ProgramLevel.choices, blank=True)
    #: охват стран через запятую; пусто — весь справочник
    countries = models.CharField("Страны", max_length=500, blank=True)

    status = models.CharField("Статус", max_length=12, choices=MatchRunStatus.choices, default=MatchRunStatus.RUNNING)
    stage = models.CharField("Этап", max_length=24, blank=True)
    progress = models.PositiveSmallIntegerField("Прогресс, %", default=0)
    error = models.CharField("Что пошло не так", max_length=250, blank=True)

    # снимок профиля на момент запуска
    snapshot_gpa = models.DecimalField("GPA на момент", max_digits=4, decimal_places=2, null=True, blank=True)
    snapshot_ielts = models.DecimalField("IELTS на момент", max_digits=3, decimal_places=1, null=True, blank=True)
    snapshot_sat = models.PositiveSmallIntegerField("SAT на момент", null=True, blank=True)
    snapshot_grade = models.PositiveSmallIntegerField("Класс", null=True, blank=True)
    snapshot_graduation_year = models.PositiveSmallIntegerField("Год выпуска", null=True, blank=True)

    # воронка: сколько было и сколько осталось на каждом шаге
    funnel_catalog = models.PositiveIntegerField("В каталоге", default=0)
    funnel_filtered = models.PositiveIntegerField("Прошло фильтр", default=0)
    funnel_analyzed = models.PositiveIntegerField("Разобрано подробно", default=0)
    funnel_final = models.PositiveIntegerField("В финальном списке", default=0)

    # стратегия — три карточки текстом
    strategy_position = models.TextField("Текущая позиция", blank=True)
    strategy_improve = models.TextField("Что важно усилить", blank=True)
    strategy_next = models.TextField("Следующий шаг", blank=True)
    strategy_offline = models.BooleanField("Собрана правилами", default=True)

    created_at = models.DateTimeField("Запущен", auto_now_add=True)
    finished_at = models.DateTimeField("Закончен", null=True, blank=True)

    class Meta:
        verbose_name = "Прогон подбора"
        verbose_name_plural = "Прогоны подбора"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("student", "-created_at"))]

    def __str__(self) -> str:
        return f"Подбор #{self.pk} · {self.student}"


class MatchRunResult(models.Model):
    """Одна программа в результате прогона — со снимком процентов."""

    run = models.ForeignKey(MatchRun, verbose_name="Прогон", related_name="results", on_delete=models.CASCADE)
    program = models.ForeignKey(Program, verbose_name="Программа", related_name="run_results", on_delete=models.CASCADE)
    #: соответствие сейчас и «если закрыть разрывы» — при целевых баллах
    #: из целей по экзаменам (фаза 39). Ни то ни другое — не шанс поступления
    percent_now = models.PositiveSmallIntegerField("Соответствие сейчас", default=0)
    percent_goal = models.PositiveSmallIntegerField("Если закрыть разрывы", default=0)
    tier = models.CharField("Категория", max_length=8, choices=RunTier.choices, blank=True)
    section = models.CharField("Раздел", max_length=8, choices=ResultSection.choices, default=ResultSection.OTHER)
    position = models.PositiveSmallIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Строка результата подбора"
        verbose_name_plural = "Строки результатов подбора"
        ordering = ("position", "id")
        constraints = [models.UniqueConstraint(fields=("run", "program"), name="uniq_program_per_run")]

    def __str__(self) -> str:
        return f"{self.run_id} · {self.program} · {self.percent_now}%"


class FavoriteProgram(models.Model):
    """Избранное ученика: «присмотрел», в отличие от списка «подаюсь».

    Истории у отметки нет, удаление физическое — как у справочников.
    """

    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="favorites", on_delete=models.CASCADE)
    program = models.ForeignKey(
        Program, verbose_name="Программа", related_name="favorited_by", on_delete=models.CASCADE
    )
    created_at = models.DateTimeField("Отмечено", auto_now_add=True)

    class Meta:
        verbose_name = "Избранная программа"
        verbose_name_plural = "Избранные программы"
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("student", "program"), name="uniq_favorite_per_student")]

    def __str__(self) -> str:
        return f"{self.student} · избранное · {self.program}"


# --- Стипендии и гранты (фаза 44) -----------------------------------------


class FundingType(models.TextChoices):
    """Что покрывает стипендия. Типизированной колонкой, а не текстом."""

    FULL = "full", "Полное финансирование"
    PARTIAL = "partial", "Частичное финансирование"
    TUITION = "tuition", "Только обучение"


class Scholarship(VerifiableRecord):
    """Стипендия или грант. Справочник ведёт директор по поступлению.

    Инвариант №14 действует здесь так же, как у требований вузов: запись,
    попавшая сюда не с официального сайта, живёт с плашкой «не подтверждено»,
    и ученику она показывается только вместе с ней.

    Основание (для иностранцев, за заслуги, по нужде) — три отдельные
    колонки, а не список в одном поле: оснований у стипендии бывает
    несколько, и по каждому нужен фильтр (инвариант №6).
    """

    name = models.CharField("Название", max_length=250)
    organizer = models.CharField("Организатор", max_length=250, blank=True)
    country = models.CharField("Страна", max_length=100, blank=True)
    #: пусто — стипендия не привязана к уровню обучения
    level = models.CharField("Уровень обучения", max_length=16, choices=ProgramLevel.choices, blank=True)
    funding_type = models.CharField(
        "Тип финансирования", max_length=12, choices=FundingType.choices, default=FundingType.PARTIAL
    )
    #: сумма или диапазон: одна граница — фиксированная сумма
    amount_min = models.DecimalField("Сумма от", max_digits=12, decimal_places=2, null=True, blank=True)
    amount_max = models.DecimalField("Сумма до", max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField("Валюта", max_length=8, blank=True, default="USD")

    for_international = models.BooleanField("Для иностранцев", default=False)
    for_merit = models.BooleanField("За заслуги", default=False)
    for_need = models.BooleanField("По нужде", default=False)

    #: дедлайн подачи живёт у самой стипендии — как дедлайн вуза живёт
    #: у раунда: сдвинулся один раз, сдвинулся у всех (инвариант №4)
    deadline = models.DateField("Дедлайн подачи", null=True, blank=True)
    url = models.URLField("Страница стипендии", blank=True)
    requirements = models.TextField("Требования", blank=True)
    description = models.TextField("Описание", blank=True)
    #: PROTECT: стипендию вуза не сносит удаление вуза молча — отказ
    #: назовёт число ссылок, как и у программ в списках учеников
    university = models.ForeignKey(
        University,
        verbose_name="Вуз",
        related_name="scholarships",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Пусто — стипендия не привязана к вузу",
    )
    is_active = models.BooleanField("Показывать", default=True)
    created_at = models.DateTimeField("Заведена", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        verbose_name = "Стипендия"
        verbose_name_plural = "Стипендии"
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=("name", "organizer"), name="uniq_scholarship_name")]
        indexes = [models.Index(fields=("deadline",)), models.Index(fields=("country",))]

    def __str__(self) -> str:
        return self.name

    @property
    def basis_titles(self) -> list[str]:
        """Метки основания для карточки — по одной на каждую колонку."""
        out = []
        if self.for_international:
            out.append("Для иностранцев")
        if self.for_merit:
            out.append("За заслуги")
        if self.for_need:
            out.append("По нужде")
        return out


class SavedScholarship(models.Model):
    """Сохранённая стипендия — тот же механизм, что избранное программ.

    Истории у отметки нет, удаление физическое. От неё растут дедлайн
    в календаре, напоминание и задача в роадмапе.
    """

    student = models.ForeignKey(
        Student, verbose_name="Ученик", related_name="saved_scholarships", on_delete=models.CASCADE
    )
    scholarship = models.ForeignKey(
        Scholarship, verbose_name="Стипендия", related_name="saved_by", on_delete=models.CASCADE
    )
    created_at = models.DateTimeField("Сохранена", auto_now_add=True)

    class Meta:
        verbose_name = "Сохранённая стипендия"
        verbose_name_plural = "Сохранённые стипендии"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("student", "scholarship"), name="uniq_saved_scholarship_per_student")
        ]

    def __str__(self) -> str:
        return f"{self.student} · сохранил · {self.scholarship}"
