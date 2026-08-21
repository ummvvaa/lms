"""Админка роадмапа и эссе."""

from django.contrib import admin

from roadmap.models import Essay, EssayVersion, Task, TaskTemplate


@admin.register(TaskTemplate)
class TaskTemplateAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "priority", "due_month", "due_day", "graduation_year", "grade", "is_active")
    list_filter = ("category", "priority", "is_active")
    search_fields = ("title",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "student", "category", "priority", "status", "effective_due_date")
    list_filter = ("status", "category", "priority")
    search_fields = ("title", "student__last_name")
    autocomplete_fields = ("student", "admission_round", "template")


class EssayVersionInline(admin.TabularInline):
    model = EssayVersion
    extra = 0
    readonly_fields = ("number", "word_count", "created_at")


@admin.register(Essay)
class EssayAdmin(admin.ModelAdmin):
    list_display = ("title", "student", "essay_type", "status", "updated_at")
    list_filter = ("status", "essay_type")
    search_fields = ("title", "student__last_name")
    autocomplete_fields = ("student", "program", "curator")
    inlines = [EssayVersionInline]
