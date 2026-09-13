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
        # документы, заметки, журнал (фаза 62)
        "curator-documents",
        "curator-documents-export",
        "curator-journal",
        "curator-journal-export",
        # пробники файлом (фаза 63): список, результаты, исходник, выгрузка, шаблон
        "mock-imports",
        "mock-results",
        "mock-file",
        "mock-export",
        "mock-template",
        "note-list",
        "note-detail",
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
        # пароли ученика своей группы (фаза 65): «есть / нет» — чтением,
        # сам показ пишет журнал и стоит в списке записи
        "credentials-state",
        # дисциплина и письма (фаза 66): лист посещаемости, замечания,
        # контакты родителей и шаблоны писем. У замечаний и контактов чтение
        # и запись живут по одному адресу, поэтому имя стоит в обоих списках.
        # Границу «своя группа» держит выборка, а не этот список
        "attendance-day",
        "remarks",
        "letter-templates",
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
        # документы, заметки, звонок, передача владельцу (фаза 62)
        "curator-documents-remind",
        "curator-document-revoke",
        "curator-call",
        "curator-escalate",
        "note-list",
        "note-detail",
        "suggestion-escalate",
        "suggestion-unescalate",
        # мастер загрузки пробника и судьба загрузки (фаза 63); возврат
        # из архива куратору не открыт — его делает Кымбат
        "mock-preview",
        "mock-apply",
        "mock-archive",
        "mock-remind",
        # показ и запись пароля ученика своей группы (фаза 65): показ —
        # POST намеренно, его нельзя вызвать ссылкой или предзагрузкой
        "credential-reveal",
        "credential-set",
        # дисциплина по своим группам (фаза 66): куратор вносит её сам, а не
        # подтверждает. Контакты родителей — там же: телефон, по которому
        # он звонит, правит он сам, не дожидаясь директора школы
        "attendance-save",
        "remarks",
        "remark-drop",
        "contact-list",
        "contact-detail",
        # блок «Поступление» у ученика своей группы (фаза 70): телефон,
        # почта Common App и папка. Какие именно поля можно — решает
        # реестр доменов полем `curator_writes`, маршрут лишь пускает
        "profile-admission-detail",
        "letter-compose",
        "letter-open",
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


#: Что закрыто администратору — и почему (фаза 68). Администратор видит
#: и правит все домены, поэтому список короткий и обратный кураторскому:
#: не «что открыто», а «что закрыто с причиной». Две причины:
#:
#: * первичные данные вносит ученик — предложение о себе, документ,
#:   анкету первого входа и упражнения администратор за него не делает.
#:   Он подтверждает и правит, но не сочиняет: инвариант «ученик вносит,
#:   школа подтверждает» этой фазой не двигается;
#: * кабинет куратора и кабинет ученика — экраны роли, у администратора
#:   свои: карточка ученика целиком, таблица, очередь.
#:
#: Страж `test_every_api_route_is_either_open_or_closed_to_the_admin`
#: требует: маршрут, отвечающий администратору 403, обязан быть здесь.
CURATOR_CABINET = "кабинет куратора — у администратора карточка ученика целиком, таблица и очередь"
STUDENT_CABINET = "кабинет ученика — экран роли, а не данные"
STUDENT_ENTERS = "первичные данные вносит ученик — администратор подтверждает и правит, но не вносит за него"

ADMIN_CLOSED_ROUTES: dict[str, str] = {
    # кабинет куратора (фазы 60–63): свои группы, свой журнал
    "curator-overview": CURATOR_CABINET,
    "curator-students": CURATOR_CABINET,
    "curator-students-export": CURATOR_CABINET,
    "curator-student": CURATOR_CABINET,
    "curator-tasks": CURATOR_CABINET,
    "curator-profile": CURATOR_CABINET,
    "curator-documents": CURATOR_CABINET,
    "curator-documents-export": CURATOR_CABINET,
    "curator-journal": CURATOR_CABINET,
    "curator-journal-export": CURATOR_CABINET,
    # кабинет ученика: то, что он видит о себе
    "portfolio": STUDENT_CABINET,
    "portfolio-cv": STUDENT_CABINET,
    "selection-runs": STUDENT_CABINET,
    "selection-run": STUDENT_CABINET,
    "selection-explain": STUDENT_CABINET,
    "favorites": STUDENT_CABINET,
    "scholarships-saved": STUDENT_CABINET,
    "essay-requirements": STUDENT_CABINET,
    "suggestion-mine": STUDENT_CABINET,
    "game-state": STUDENT_CABINET,
    "journey-state": STUDENT_CABINET,
    "home-cues": STUDENT_CABINET,
    "achievements": STUDENT_CABINET,
    "prep-center-exams": STUDENT_CABINET,
    "prep-center-sections": STUDENT_CABINET,
    "prep-center-topics": STUDENT_CABINET,
    "prep-center-statistics": STUDENT_CABINET,
    "prep-my-runs": STUDENT_CABINET,
    # то, что ученик вносит о себе сам: предложения, анкета, профтест,
    # упражнения. Администратор их не заполняет — он их подтверждает
    "suggestion-propose": STUDENT_ENTERS,
    "onboarding-state": STUDENT_ENTERS,
    "onboarding-answer": STUDENT_ENTERS,
    "onboarding-skip": STUDENT_ENTERS,
    "career-state": STUDENT_ENTERS,
    "career-run": STUDENT_ENTERS,
    "career-agree": STUDENT_ENTERS,
    "prep-quiz": STUDENT_ENTERS,
    "prep-quiz-start": STUDENT_ENTERS,
    "prep-quiz-join": STUDENT_ENTERS,
    "prep-quiz-finish": STUDENT_ENTERS,
    "prep-quiz-match": STUDENT_ENTERS,
    "prep-practice-answer": STUDENT_ENTERS,
    "essay-assist-log": STUDENT_ENTERS,
    "essay-reading-day": STUDENT_ENTERS,
}

#: Маршруты, где чтение администратору открыто, а запись — нет: список
#: документов и эссе он видит, а загрузить документ или начать эссе
#: за ученика не может
ADMIN_CLOSED_WRITES: dict[str, str] = {
    "document-list": STUDENT_ENTERS,
    "essay-list": STUDENT_ENTERS,
}

ADMIN_GATE_MESSAGE = "Этот маршрут администратору закрыт"


def admin_refusal(url_name: str | None, method: str) -> str:
    """Почему маршрут закрыт администратору. Пусто — открыт."""
    if not url_name:
        return ""
    reason = ADMIN_CLOSED_ROUTES.get(url_name)
    if reason is not None:
        return reason
    if method not in ("GET", "HEAD", "OPTIONS"):
        return ADMIN_CLOSED_WRITES.get(url_name, "")
    return ""


class AdminGateMiddleware:
    """Администратору закрыт короткий список маршрутов — с причиной (фаза 68).

    Зеркало кураторского шлюза: у того список открытого, у этого —
    закрытого. Проверяется здесь, а не во вьюхах, чтобы граница «первичные
    данные вносит ученик» была в одном месте и её стерёг один тест.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if request.path.startswith("/api/") and user is not None and user.is_authenticated and user.role == Role.ADMIN:
            from django.http import JsonResponse
            from django.urls import Resolver404, resolve

            try:
                name = resolve(request.path).url_name
            except Resolver404:
                name = None
            reason = admin_refusal(name, request.method)
            if reason:
                return JsonResponse(
                    {"detail": f"{ADMIN_GATE_MESSAGE}: {reason}"},
                    status=403,
                    json_dumps_params={"ensure_ascii": False},
                )
        return self.get_response(request)


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
