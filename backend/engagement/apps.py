from django.apps import AppConfig
from django.utils.translation import gettext_lazy


class EngagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "engagement"
    verbose_name = gettext_lazy("Онбординг и вовлечение")
