"""Учебная часть: расписание, журналы, посещаемость по урокам, отчёты родителям."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy


class AcademicsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "academics"
    verbose_name = gettext_lazy("Учебная часть")
