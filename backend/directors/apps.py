"""Кабинеты директоров: звонки родителям, отчёты, задачи сотрудникам, олимпиады, освобождения, мероприятия."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy


class DirectorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "directors"
    verbose_name = gettext_lazy("Кабинеты директоров")
