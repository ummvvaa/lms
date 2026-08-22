"""Права на управление учётными записями."""

from __future__ import annotations

from rest_framework import permissions

from accounts.models import Role


class IsAdmin(permissions.BasePermission):
    """Роль `admin` — техническая: люди и справочники, но не доменные поля."""

    message = "Управление пользователями доступно администратору"

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.role == Role.ADMIN)


#: Что доступно человеку, которому ещё предстоит сменить пароль.
#: Всё остальное закрыто: иначе «обязательная смена» необязательна.
PASSWORD_GATE_ALLOWED = (
    "/api/auth/me/",
    "/api/auth/login/",
    "/api/auth/logout/",
    "/api/auth/password/change/",
    "/api/auth/password/reset/",
    "/api/auth/password/set/",
    "/api/auth/magic-link/",
)


class MustChangePasswordMiddleware:
    """Пока пароль не сменён, дальше экрана смены пароля не пускаем.

    Проверка на сервере, а не только в интерфейсе: обойти форму запросом
    к API не должно получаться.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith("/api/") and not path.startswith(PASSWORD_GATE_ALLOWED):
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated and user.must_change_password:
                from django.http import JsonResponse

                return JsonResponse(
                    {"detail": "Сначала смените пароль", "code": "password_change_required"},
                    status=403,
                )
        return self.get_response(request)
