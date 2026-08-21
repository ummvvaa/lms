"""Админка журнала изменений — только чтение."""

from django.contrib import admin

from core.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "model_label", "object_id", "field_name", "old_value", "new_value", "source", "actor")
    list_filter = ("source", "domain_code", "model_label")
    search_fields = ("object_id", "field_name", "old_value", "new_value")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
