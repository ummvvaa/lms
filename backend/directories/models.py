"""Справочники предметов олимпиад и видов спорта.

Свободный текст в этих полях расползается: «Математика», «математика»
и «Матем.» становятся тремя разными значениями, и фильтр по предмету
перестаёт что-либо показывать. Поэтому — таблица со своим владельцем.

Истории у справочника нет, поэтому удаление физическое (инвариант №13).
Но запись, на которую ссылаются, удалить нельзя: её либо прячут из списка
выбора, либо заменяют на другую вместе со всеми ссылками.
"""

from __future__ import annotations

from django.db import models
from django.utils import translation
from django.utils.translation import gettext_lazy

from core.archivable import Archivable


class DirectoryEntry(models.Model):
    """Общая часть обоих справочников: название, описание, видимость."""

    #: строковое значение из файла или из старой текстовой колонки
    #: приводится к записи справочника по названию — см. `core.references`
    resolve_by_name = True

    name = models.CharField(gettext_lazy("Название"), max_length=120, unique=True)
    description = models.TextField(gettext_lazy("Описание"), blank=True)
    #: снятый признак убирает запись из списков выбора, но не рвёт ссылки
    is_active = models.BooleanField(gettext_lazy("Показывать в списке выбора"), default=True)
    sort_order = models.PositiveSmallIntegerField(gettext_lazy("Порядок"), default=100)
    created_at = models.DateTimeField(gettext_lazy("Создано"), auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ("sort_order", "name")

    def __str__(self) -> str:
        return self.name


class SubjectArea(models.TextChoices):
    """Направления, с которых список начинается. Арман выбирает из них или
    вводит своё: введённое хранится текстом и предлагается следующим."""

    NATURAL = "natural", gettext_lazy("Естественные науки")
    EXACT = "exact", gettext_lazy("Точные науки")
    HUMANITIES = "humanities", gettext_lazy("Гуманитарные науки")
    LANGUAGES = "languages", gettext_lazy("Языки")
    OTHER = "other", gettext_lazy("Прочее")


class OlympiadSubject(DirectoryEntry):
    """Предмет олимпиады. Владелец — домен `talent` (Арман)."""

    #: направление — текстом, как его видит человек: из списка или своё.
    #: До разбора кабинетов здесь был код из пяти вариантов, и «Робототехнике»
    #: доставалось «Прочее». Разнобой регистра и пробелов снимает сериализатор
    area = models.CharField(gettext_lazy("Направление"), max_length=80, default=SubjectArea.OTHER.label)

    class Meta(DirectoryEntry.Meta):
        abstract = False
        verbose_name = gettext_lazy("Предмет олимпиады")
        verbose_name_plural = gettext_lazy("Предметы олимпиад")
        # числового «порядка» у предметов больше нет — по алфавиту
        ordering = ("name",)

    @classmethod
    def known_areas(cls) -> list[str]:
        """Что предложить в поле «Направление»: исходные пять и всё введённое раньше."""
        entered = cls.objects.exclude(area="").values_list("area", flat=True).distinct()
        # направление — значение данных, оно пишется в базу: отдаём русский исходник,
        # иначе казахский и английский варианты легли бы рядом с русским дублями
        with translation.override("ru"):
            base = {str(label) for label in SubjectArea.labels}
        return sorted({*base, *entered}, key=str.lower)


class SportCategory(models.TextChoices):
    """Категория вида спорта."""

    TEAM = "team", gettext_lazy("Командный")
    INDIVIDUAL = "individual", gettext_lazy("Индивидуальный")
    MARTIAL = "martial", gettext_lazy("Единоборства")
    OTHER = "other", gettext_lazy("Прочее")


class SportType(DirectoryEntry):
    """Вид спорта. Владелец — домен `sport` (Нурлыбек)."""

    category = models.CharField(
        gettext_lazy("Категория"), max_length=16, choices=SportCategory.choices, default=SportCategory.OTHER
    )

    class Meta(DirectoryEntry.Meta):
        abstract = False
        verbose_name = gettext_lazy("Вид спорта")
        verbose_name_plural = gettext_lazy("Виды спорта")


class ExamKind(Archivable, DirectoryEntry):
    """Экзамен: IELTS, TOEFL, SAT, ACT, Duolingo, HSK. Владелец — `exam`.

    Справочник пополняется академическим директором. Единственный
    справочник с архивом (фаза 59): экзамен тянет за собой цели и баллы,
    поэтому убранный насовсем экзамен уходит в архив вместе с ними, а не
    удаляется физически — остальные справочники по-прежнему удаляются
    (инвариант №13). Архивная запись не попадает ни в один список:
    `objects` её не видит, `all_objects` — только для миграций и тестов.
    """

    min_score = models.DecimalField(
        gettext_lazy("Минимум шкалы"), max_digits=6, decimal_places=1, null=True, blank=True
    )
    max_score = models.DecimalField(
        gettext_lazy("Максимум шкалы"), max_digits=6, decimal_places=1, null=True, blank=True
    )

    class Meta(DirectoryEntry.Meta):
        abstract = False
        verbose_name = gettext_lazy("Экзамен")
        verbose_name_plural = gettext_lazy("Экзамены")
