from django.contrib import admin

from directories.models import OlympiadSubject, SportType


@admin.register(OlympiadSubject)
class OlympiadSubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "area", "is_active", "sort_order")
    list_filter = ("area", "is_active")
    search_fields = ("name", "description")


@admin.register(SportType)
class SportTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active", "sort_order")
    list_filter = ("category", "is_active")
    search_fields = ("name", "description")
