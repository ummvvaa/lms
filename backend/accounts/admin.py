"""Админка пользователей и идентичностей."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts.models import Identity, LoginAttempt, MagicLinkToken, User


class IdentityInline(admin.TabularInline):
    model = Identity
    extra = 0
    fields = ("provider", "email", "external_id", "is_primary", "last_login_at")
    readonly_fields = ("last_login_at",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "role", "is_active", "sees_whole_school", "must_change_password")
    list_filter = ("role", "is_active", "sees_whole_school")
    search_fields = ("email", "full_name")
    inlines = [IdentityInline]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Профиль", {"fields": ("full_name", "role")}),
        (
            "Доступ",
            {
                "fields": ("is_active", "must_change_password", "sees_whole_school"),
                "description": (
                    "«Видит всю школу» — право читать все домены и сводный вид. "
                    "Писать человек по-прежнему может только в свой домен."
                ),
            },
        ),
        ("Права Django", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "full_name", "role", "password1", "password2")}),
    )


@admin.register(Identity)
class IdentityAdmin(admin.ModelAdmin):
    list_display = ("email", "provider", "user", "is_primary", "last_login_at")
    list_filter = ("provider", "is_primary")
    search_fields = ("email", "external_id", "user__email")


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """Журнал входов. Только чтение: это след, а не рабочая таблица."""

    list_display = ("created_at", "email", "ip", "successful", "reason")
    list_filter = ("successful", "reason")
    search_fields = ("email", "ip")
    readonly_fields = ("email", "ip", "successful", "reason", "user_agent", "created_at")

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(MagicLinkToken)
class MagicLinkTokenAdmin(admin.ModelAdmin):
    """Одноразовые ссылки. Самого токена здесь нет — только его хеш."""

    list_display = ("email", "purpose", "created_at", "expires_at", "used_at")
    list_filter = ("purpose",)
    search_fields = ("email",)
    readonly_fields = ("email", "token_hash", "purpose", "created_at", "expires_at", "used_at")

    def has_add_permission(self, request) -> bool:
        return False
