"""Спортивные секции: запись по часам, отметка по QR, посещаемость и билеты."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy


class SportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sport"
    verbose_name = gettext_lazy("Спортивные секции")
