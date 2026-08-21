"""Права роадмапа и эссе.

Задачи и эссе не принадлежат одному домену: их ведут и директора,
и сам ученик. Правило проще доменного — ученик работает только со своим,
сотрудник видит всех.
"""

from __future__ import annotations

from rest_framework import permissions

from core.domains import ROLE_STUDENT


class OwnStudentOrStaff(permissions.BasePermission):
    """Ученик — только свои задачи и эссе; сотрудник — все."""

    message = "Доступны только свои задачи"

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        if request.user.role != ROLE_STUDENT:
            return True
        student = getattr(request.user, "student", None)
        return student is not None and obj.student_id == student.pk


class StaffOnly(permissions.BasePermission):
    """Шаблоны задач заводит директор, не ученик."""

    message = "Шаблоны задач ведут сотрудники"

    def has_permission(self, request, view) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.role != ROLE_STUDENT
