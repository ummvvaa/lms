from django.apps import AppConfig
from django.utils.translation import gettext_lazy


class DirectoriesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "directories"
    verbose_name = gettext_lazy("Справочники")
