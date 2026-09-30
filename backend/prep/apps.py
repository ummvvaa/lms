from django.apps import AppConfig
from django.utils.translation import gettext_lazy


class PrepConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "prep"
    verbose_name = gettext_lazy("Центр подготовки")
