"""Права доступа поверх реестра доменов (инварианты №1 и №2).

Правила, одинаковые для всего API:

* ученик читает только свой профиль и ничего не пишет;
* директор читает всех, пишет только поля своего домена;
* `admin` (директор школы) читает всё и пишет свой домен — как и остальные.

Проверка идёт по имени поля, а не по модели целиком: в одной модели
не бывает полей двух доменов, но правило формулируется именно так,
чтобы реестр остался единственным источником правды.
"""

from __future__ import annotations

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied

from core.audit import model_label
from core.domains import ROLE_STUDENT, can_write, domain_of_role

SAFE = permissions.SAFE_METHODS


class IsAuthenticatedStaffOrOwnStudent(permissions.BasePermission):
    """Доступ к API: сотрудник или ученик со своим профилем."""

    message = "Недостаточно прав"

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)


class DomainFieldPermission(permissions.BasePermission):
    """Запись разрешена только в поля своего домена.

    Вьюха обязана объявить `domain_model_label` — метку модели, поля
    которой она правит. Читать может любой аутентифицированный сотрудник.
    """

    message = "Это поле ведёт другой директор — вы можете его видеть, но не менять"

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE:
            return True
        if user.role == ROLE_STUDENT:
            return False
        return domain_of_role(user.role) is not None

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in SAFE:
            return True
        label = getattr(view, "domain_model_label", None) or model_label(obj)
        fields = set(getattr(request, "data", {}) or {})
        return all(can_write(request.user.role, label, name) for name in fields)


class IsOwnStudentOrStaff(permissions.BasePermission):
    """Ученик видит только себя, сотрудник — всех."""

    message = "Чужой профиль недоступен"

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if user.role != ROLE_STUDENT:
            return True
        student = obj if obj.__class__.__name__ == "Student" else getattr(obj, "student", None)
        return student is not None and getattr(user, "student", None) == student


def assert_writable(role: str, label: str, field_names) -> None:
    """Бросить 403 со списком чужих полей. Используется в батч-эндпойнтах."""
    foreign = sorted(name for name in field_names if not can_write(role, label, name))
    if foreign:
        raise PermissionDenied(
            {
                "detail": "Поля чужого домена изменить нельзя",
                "model": label,
                "fields": foreign,
            }
        )
