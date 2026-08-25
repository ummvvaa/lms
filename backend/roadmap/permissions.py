"""Права роадмапа и эссе.

Задачи и эссе не принадлежат одному домену: их ведут и директора,
и сам ученик. Правило проще доменного — ученик работает только со своим,
сотрудник видит всех.
"""

from __future__ import annotations

from rest_framework import permissions

from core.domains import ROLE_STUDENT

#: Что ученику можно делать со своей задачей и своим эссе.
#: Отдельные действия, а не PATCH: задачу ставит директор, и переписывать
#: её текст ученик не должен — он двигает её по доске и пишет версии эссе.
STUDENT_ACTIONS = ("set_status", "add_version", "submit")


class OwnStudentOrStaff(permissions.BasePermission):
    """Ученик — только свои задачи и эссе; сотрудник — все.

    Читает ученик своё целиком, а меняет только через названные действия.
    Через обычный PATCH он не правит ничего: задача с чужой формулировкой
    и эссе с подменённым статусом ломают договорённость о том, кто что
    решает, — а выглядит это как обычное сохранение.
    """

    message = "Доступны только свои задачи"

    def has_permission(self, request, view) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role != ROLE_STUDENT:
            return True
        # заводить задачи и эссе ученик не может: их ставит директор
        return request.method in permissions.SAFE_METHODS or getattr(view, "action", "") in STUDENT_ACTIONS

    def has_object_permission(self, request, view, obj) -> bool:
        if request.user.role != ROLE_STUDENT:
            return True
        student = getattr(request.user, "student", None)
        if student is None or obj.student_id != student.pk:
            return False
        return request.method in permissions.SAFE_METHODS or getattr(view, "action", "") in STUDENT_ACTIONS


class StaffOnly(permissions.BasePermission):
    """Шаблоны задач заводит директор, не ученик."""

    message = "Шаблоны задач ведут сотрудники"

    def has_permission(self, request, view) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.role != ROLE_STUDENT


class OwnCommentOrCurator(permissions.BasePermission):
    """Комментарий правит и убирает его автор.

    Читают комментарий все, кому видна сама задача или эссе, а вот менять
    чужую реплику нельзя никому: подпись под ней остаётся прежней, и по
    журналу разговора потом не разобрать, кто что на самом деле сказал.
    Ученик своё замечание куратору тоже не переписывает.
    """

    message = "Комментарий правит тот, кто его написал"

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.author_id == request.user.pk
