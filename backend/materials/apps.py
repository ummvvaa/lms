from django.apps import AppConfig
from django.utils.translation import gettext_lazy


class MaterialsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "materials"
    verbose_name = gettext_lazy("Материалы олимпиадников")
