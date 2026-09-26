"""Учебная часть: расписание, журналы, посещаемость по урокам, отчёты родителям."""

from django.apps import AppConfig


class AcademicsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "academics"
    verbose_name = "Учебная часть"
