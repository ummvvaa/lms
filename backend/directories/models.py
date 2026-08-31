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


class DirectoryEntry(models.Model):
    """Общая часть обоих справочников: название, описание, видимость."""

    #: строковое значение из файла или из старой текстовой колонки
    #: приводится к записи справочника по названию — см. `core.references`
    resolve_by_name = True

    name = models.CharField("Название", max_length=120, unique=True)
    description = models.TextField("Описание", blank=True)
    #: снятый признак убирает запись из списков выбора, но не рвёт ссылки
    is_active = models.BooleanField("Показывать в списке выбора", default=True)
    sort_order = models.PositiveSmallIntegerField("Порядок", default=100)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ("sort_order", "name")

    def __str__(self) -> str:
        return self.name


class SubjectArea(models.TextChoices):
    """Направление предмета — по нему группируется список."""

    NATURAL = "natural", "Естественные науки"
    EXACT = "exact", "Точные науки"
    HUMANITIES = "humanities", "Гуманитарные науки"
    LANGUAGES = "languages", "Языки"
    OTHER = "other", "Прочее"


class OlympiadSubject(DirectoryEntry):
    """Предмет олимпиады. Владелец — домен `talent` (Арман)."""

    area = models.CharField("Направление", max_length=16, choices=SubjectArea.choices, default=SubjectArea.OTHER)

    class Meta(DirectoryEntry.Meta):
        abstract = False
        verbose_name = "Предмет олимпиады"
        verbose_name_plural = "Предметы олимпиад"


class SportCategory(models.TextChoices):
    """Категория вида спорта."""

    TEAM = "team", "Командный"
    INDIVIDUAL = "individual", "Индивидуальный"
    MARTIAL = "martial", "Единоборства"
    OTHER = "other", "Прочее"


class SportType(DirectoryEntry):
    """Вид спорта. Владелец — домен `sport` (Нурлыбек)."""

    category = models.CharField("Категория", max_length=16, choices=SportCategory.choices, default=SportCategory.OTHER)

    class Meta(DirectoryEntry.Meta):
        abstract = False
        verbose_name = "Вид спорта"
        verbose_name_plural = "Виды спорта"


class ExamKind(DirectoryEntry):
    """Экзамен: IELTS, TOEFL, SAT, ACT, ЕНТ, Duolingo, HSK. Владелец — `exam`.

    Для казахстанской школы ЕНТ — не второстепенный экзамен: часть учеников
    сдаёт и его, и международные, поэтому он в списке наравне со всеми
    (фаза 39). Справочник пополняется академическим директором.
    """

    min_score = models.DecimalField("Минимум шкалы", max_digits=6, decimal_places=1, null=True, blank=True)
    max_score = models.DecimalField("Максимум шкалы", max_digits=6, decimal_places=1, null=True, blank=True)

    class Meta(DirectoryEntry.Meta):
        abstract = False
        verbose_name = "Экзамен"
        verbose_name_plural = "Экзамены"
