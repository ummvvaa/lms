"""Админка справочника вузов. Внутренний инструмент: важна работоспособность."""

from django.contrib import admin

from universities.models import AdmissionRound, Program, StudentUniversity, University


class ProgramInline(admin.TabularInline):
    model = Program
    extra = 1
    fields = ("name", "level", "is_active")


class AdmissionRoundInline(admin.TabularInline):
    model = AdmissionRound
    extra = 1
    fields = ("round_type", "deadline", "source_url", "checked_at")


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "domain", "is_active")
    list_filter = ("country", "is_active")
    search_fields = ("name", "domain")
    inlines = [ProgramInline]


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("name", "university", "level", "is_active")
    list_filter = ("level", "is_active", "university__country")
    search_fields = ("name", "university__name")
    autocomplete_fields = ("university",)
    inlines = [AdmissionRoundInline]


@admin.register(AdmissionRound)
class AdmissionRoundAdmin(admin.ModelAdmin):
    list_display = ("program", "round_type", "deadline", "checked_at")
    list_filter = ("round_type", "program__university__country")
    search_fields = ("program__name", "program__university__name")
    autocomplete_fields = ("program",)
    date_hierarchy = "deadline"


@admin.register(StudentUniversity)
class StudentUniversityAdmin(admin.ModelAdmin):
    list_display = ("student", "program", "tier", "application_status", "admission_round")
    list_filter = ("tier", "application_status")
    search_fields = ("student__last_name", "student__first_name", "program__name")
    autocomplete_fields = ("student", "program", "admission_round")
