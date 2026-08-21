"""Админка предложений — для отладки, рабочий экран появится в Фазе 5."""

from django.contrib import admin

from suggestions.models import Suggestion, SuggestionChange


class SuggestionChangeInline(admin.TabularInline):
    model = SuggestionChange
    extra = 0


@admin.register(Suggestion)
class SuggestionAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "domain_code", "command", "source_type", "status", "author")
    list_filter = ("status", "domain_code", "source_type")
    inlines = [SuggestionChangeInline]
