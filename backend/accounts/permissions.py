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


#: Что открыто куратору по имени маршрута (фаза 60). Всё, чего здесь нет,
#: отвечает ему 403 — до вьюхи запрос не доходит. Список короткий намеренно:
#: у куратора нет справочников, настроек, дашбордов, импорта, помощника,
#: таблицы и записи за ученика. Внутри разрешённого границу «своя группа —
#: чужая» держит выборка (`core.scope`): чужой ученик — 404, не 403.
#:
#: Чтение — карточка ученика целиком: сам ученик, пять профилей, дочерние
#: строки, документы, задачи и эссе, список своих групп, очередь.
CURATOR_READ_ROUTES = frozenset(
    {
        "student-list",
        "student-detail",
        "student-history",
        "student-readiness",
        "profile-behavior-detail",
        "profile-admission-detail",
        "profile-exam-detail",
        "profile-talent-detail",
        "profile-sport-detail",
        "attempt-list",
        "attempt-detail",
        "activity-list",
        "activity-detail",
        "competition-list",
        "competition-detail",
        "contact-list",
        "contact-detail",
        "document-list",
        "document-detail",
        "document-file",
        "exam-goal-list",
        "exam-goal-detail",
        "task-list",
        "task-detail",
        "task-comment-list",
        "essay-list",
        "essay-detail",
        "essay-comment-list",
        "student-university-list",
        "student-university-detail",
        "group-list",
        "group-detail",
        "suggestion-list",
        "suggestion-detail",
        "suggestion-students-queue",
        # кабинет куратора (фаза 61): главная, ученики, карточка, задачи, профиль
        "curator-overview",
        "curator-students",
        "curator-students-export",
        "curator-student",
        "curator-tasks",
        "curator-profile",
        # поиск по своим группам — тем же эндпоинтом, что у директоров,
        # но выборка сужена (`core.scope`): чужих учеников он не находит
        "search",
        # каркас: кабинет, реестр подписей, уведомления, фоновые операции
        "cabinet",
        "domain-meta",
        "readiness-config",
        "getting-started",
        "notifications",
        "jobs",
        "materials-state",
    }
)

#: Запись — только решения по очереди и служебное каркаса
CURATOR_WRITE_ROUTES = frozenset(
    {
        "suggestion-review",
        "suggestion-reject",
        "suggestion-students-confirm",
        # задачи ученикам своих групп: постановка и смена статуса (фаза 61)
        "curator-tasks",
        "curator-task-status",
        "notifications-read",
        "job-dismiss",
        "job-retry",
        "auth-preferences",
    }
)

#: Своя сессия: вход, выход, кто я, пароль, привязка почты. Любым методом.
#: Перечислены поимённо, а не по началу имени `auth-`: под тем же началом
#: живут блокировки входа — экран администратора, куратору там нечего делать
CURATOR_SESSION_ROUTES = frozenset(
    {
        "auth-login",
        "auth-logout",
        "auth-me",
        "auth-password-change",
        "auth-password-reset",
        "auth-password-set",
        "auth-magic-request",
        "auth-magic-redeem",
        "auth-link-identity",
    }
)

CURATOR_GATE_MESSAGE = "Этот раздел куратору не открыт: у него карточки учеников своих групп и очередь подтверждений"


def curator_may(url_name: str | None, method: str) -> bool:
    """Открыт ли маршрут куратору. Вход, выход и свой пароль — всегда."""
    if not url_name:
        return False
    if url_name in CURATOR_SESSION_ROUTES:
        return True
    if method in ("GET", "HEAD", "OPTIONS"):
        return url_name in CURATOR_READ_ROUTES
    return url_name in CURATOR_WRITE_ROUTES


class CuratorGateMiddleware:
    """Куратору открыт короткий список маршрутов, остальное — 403 (фаза 60).

    Единая точка, а не проверка в каждой вьюхе: у роли без домена право
    «видеть чужой справочник» иначе появилось бы само — `DomainFieldPermission`
    на безопасных методах пропускает любого вошедшего. Так уже терялись
    правила обзвона (D27). Проверяется здесь, после опознания пользователя
    и до маршрутизации во вьюху.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            request.path.startswith("/api/")
            and user is not None
            and user.is_authenticated
            and user.role == Role.CURATOR
        ):
            from django.http import JsonResponse
            from django.urls import Resolver404, resolve

            try:
                name = resolve(request.path).url_name
            except Resolver404:
                name = None
            if not curator_may(name, request.method):
                return JsonResponse(
                    {"detail": CURATOR_GATE_MESSAGE}, status=403, json_dumps_params={"ensure_ascii": False}
                )
        return self.get_response(request)
