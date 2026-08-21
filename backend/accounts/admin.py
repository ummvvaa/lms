"""Админка пользователей и идентичностей."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts.models import Identity, User


class IdentityInline(admin.TabularInline):
    model = Identity
    extra = 0
    fields = ("provider", "email", "external_id", "is_primary", "last_login_at")
    readonly_fields = ("last_login_at",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "full_name")
    inlines = [IdentityInline]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Профиль", {"fields": ("full_name", "role")}),
        ("Права", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "full_name", "role", "password1", "password2")}),
    )


@admin.register(Identity)
class IdentityAdmin(admin.ModelAdmin):
    list_display = ("email", "provider", "user", "is_primary", "last_login_at")
    list_filter = ("provider", "is_primary")
    search_fields = ("email", "external_id", "user__email")
