"""Кружки: запись без лимита, кабинет ментора, задание, заметки и отметка по QR."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy


class ClubsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "clubs"
    verbose_name = gettext_lazy("Кружки")
