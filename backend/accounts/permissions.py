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
#: у куратора нет справочников, настроек, дашбордов, импорта, команд помощника,
#: таблицы и записи за ученика. Внутри разрешённого границу «своя группа —
#: чужая» держит выборка (`core.scope`): чужой ученик — 404, не 403.
#:
#: Чтение — карточка ученика целиком: сам ученик, пять профилей, дочерние
#: строки, документы, задачи и эссе, список своих групп, очередь.
CURATOR_READ_ROUTES = frozenset(
    {
        # помощник в углу: кнопки под куратора и история своих диалогов
        "assistant-quick",
        "assistant-threads",
        "assistant-thread",
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
        "attendance-journal",
        "attendance-journal-export",
        "remarks",
        # куратор вносит за ученика теми же формами, что директор: формам
        # нужны каталог программ, справочники для списков выбора и рассказ
        # «что уйдёт вместе с записью» перед удалением
        "catalog",
        "catalog-facets",
        "university-list",
        "program-list",
        "subject-list",
        "sport-type-list",
        "exam-kind-list",
        "delete-preview",
        # мастера импорта здесь нет намеренно: решением владельца кураторы
        # вносят руками. Разбор «лист чужой группы — ошибка» в коде остался
        # (`students.admission_import`), закрыт только вход — шлюз отвечает 404
        # учебная часть: расписание и журналы своих групп, посещаемость по
        # урокам, успеваемость группы, уважительные причины, отчёты родителям
        "acad-meta",
        "acad-lessons",
        "acad-lesson",
        "acad-journal",
        "acad-attendance",
        "acad-attendance-export",
        "acad-group-grades",
        "acad-group-grades-export",
        "acad-student-grades",
        "acad-excuses",
        "acad-excuse",
        "acad-excuse-file",
        "acad-reports",
        "acad-report",
        "acad-report-pdf",
        "acad-reports-zip",
        # архив отчётов по шаблонам школы собирает очередь: состояние и файл
        "acad-reports-export-state",
        "acad-reports-export-file",
        "acad-curator-home",
    }
)

#: Запись — только решения по очереди и служебное каркаса
CURATOR_WRITE_ROUTES = frozenset(
    {
        # вопрос помощнику и новый диалог; ученики — только своих групп
        "assistant-ask",
        "assistant-threads",
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
        # ссылка на пароль ученику своей группы — на экране, с записью в журнал
        "student-password-link",
        "curator-escalate",
        "note-list",
        "note-detail",
        "suggestion-escalate",
        "suggestion-unescalate",
        # показ и запись пароля ученика своей группы (фаза 65): показ —
        # POST намеренно, его нельзя вызвать ссылкой или предзагрузкой
        "credential-reveal",
        "credential-set",
        # дисциплина по своим группам (фаза 66): куратор вносит её сам, а не
        # подтверждает. Контакты родителей — там же: телефон, по которому
        # он звонит, правит он сам, не дожидаясь директора школы
        "remarks",
        "remark-drop",
        "contact-list",
        "contact-detail",
        # всё, что ученик вносит о себе, куратор вносит за него напрямую,
        # по своим группам. Какие именно поля можно — решает реестр
        # (`core.domains.curator_may_write`), маршрут лишь пускает: профили
        # поступления, экзаменов и спорта, попытки и цели, активности
        # и соревнования, документы, вузы в списке ученика
        "profile-admission-detail",
        "profile-exam-detail",
        "profile-sport-detail",
        "attempt-list",
        "attempt-detail",
        "exam-goal-list",
        "exam-goal-detail",
        "activity-list",
        "activity-detail",
        "competition-list",
        "competition-detail",
        "document-list",
        "document-detail",
        "student-university-detail",
        "catalog-add",
        "catalog-tier",
        "catalog-priority",
        "catalog-remove",
        "notifications-read",
        "job-dismiss",
        "job-retry",
        "auth-preferences",
        # учебная часть: уважительная причина за период, напоминание учителю,
        # проверка и отправка отчётов родителям
        "acad-excuses",
        "acad-excuse",
        "acad-lesson-remind",
        # отметка урока, где куратор сам записан учителем (классный час);
        # чужой урок отсекает `academics.rights.marks_lesson`
        "acad-lesson-attendance",
        "acad-report",
        "acad-report-check",
        "acad-report-refresh",
        "acad-reports-build",
        "acad-reports-check",
        "acad-reports-refresh",
        "acad-reports-sent",
        "acad-report-sent",
        # отчёты по шаблонам школы: архив в очереди, черновик ИИ заново,
        # блок отзыва другого предмета; уровень английского своей группы
        "acad-reports-export",
        "acad-report-draft",
        "acad-report-review",
        "acad-student-english-level",
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

TEACHER_CABINET = "кабинет учителя — экран роли: у администратора расписание и журналы целиком"

DAY_MARKING_CLOSED = "отметка дня закрыта — посещаемость ведётся по урокам, причину за период оформляет куратор"

ADMIN_CLOSED_ROUTES: dict[str, str] = {
    # кабинет учителя: «Сегодня», список своих журналов, профиль, ученик глазами учителя
    "acad-teacher-today": TEACHER_CABINET,
    "acad-teacher-journals": TEACHER_CABINET,
    "acad-teacher-profile": TEACHER_CABINET,
    "acad-teacher-student": TEACHER_CABINET,
    "acad-curator-home": CURATOR_CABINET,
    # прежняя отметка дня: строки остались на чтение, писать их больше некому
    "attendance-save": DAY_MARKING_CLOSED,
    # кабинет ученика: свои оценки и уроки на день
    "acad-my-grades": STUDENT_CABINET,
    "acad-my-lessons": STUDENT_CABINET,
    "acad-my-home": STUDENT_CABINET,
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


#: Маршруты, которых для куратора нет вовсе: шлюз отвечает «не найдено»,
#: а не отказом. Мастер импорта был у куратора открыт и закрыт решением
#: владельца — кураторы вносят руками. Отказ словами тут звучал бы как
#: «попросите доступ», а доступа не будет: экрана у роли нет
CURATOR_HIDDEN_ROUTES = frozenset(
    {
        "admission-imports",
        "admission-template",
        "admission-preview",
        "admission-apply",
        "admission-report",
        "admission-export",
    }
)


#: Что открыто учителю по имени маршрута. Всё остальное для него не существует:
#: шлюз отвечает «не найдено», а не отказом — у роли нет ни карточек учеников,
#: ни очередей, ни справочников, и объяснять, что «раздел закрыт», незачем.
#: Внутри разрешённого границу «свои ученики» держит выборка (`core.scope`)
#: и права учебной части (`academics.rights`).
TEACHER_READ_ROUTES = frozenset(
    {
        # кабинет учителя: сегодня, расписание, журналы, урок, ученик глазами учителя
        "acad-meta",
        "acad-teacher-today",
        "acad-teacher-journals",
        "acad-teacher-profile",
        "acad-teacher-student",
        "acad-lessons",
        "acad-lesson",
        "acad-journal",
        "acad-journal-export",
        "acad-requests",
        # каркас: уведомления, фоновые операции, реестр подписей, поиск своих учеников
        "notifications",
        "jobs",
        "domain-meta",
        "readiness-config",
        "getting-started",
        "materials-state",
        "search",
        "cabinet",
        # помощник в углу: кнопки учителя и история своих диалогов — только чтение
        # данных, ученики — только своих составов (`suggestions.teacher_assistant`)
        "assistant-quick",
        "assistant-threads",
        "assistant-thread",
    }
)

#: Запись — только своё: отметки, оценки, тема и задание, итог, просьба о переносе.
#: Вопрос помощнику и новый диалог — запись истории переписки, а не данных
TEACHER_WRITE_ROUTES = frozenset(
    {
        "assistant-ask",
        "assistant-threads",
        "acad-lesson-attendance",
        "acad-lesson-grade",
        "acad-lesson-meta",
        "acad-journal-final",
        "acad-requests",
        # уровень английского ученика своего состава GE/EEP (`academics.english`)
        "acad-student-english-level",
        "notifications-read",
        "job-dismiss",
        "job-retry",
        "auth-preferences",
    }
)


def teacher_may(url_name: str | None, method: str) -> bool:
    """Открыт ли маршрут учителю. Вход, выход и свой пароль — всегда."""
    if not url_name:
        return False
    if url_name in CURATOR_SESSION_ROUTES:
        return True
    if method in ("GET", "HEAD", "OPTIONS"):
        return url_name in TEACHER_READ_ROUTES
    return url_name in TEACHER_WRITE_ROUTES


class TeacherGateMiddleware:
    """Учителю открыт свой список маршрутов, остальное — «не найдено».

    Та же единая точка, что и у куратора: у роли без домена право «видеть
    чужое» иначе появилось бы само. Ответ 404, а не 403: чужой ученик,
    заметки, документы, поступление и отчёты для учителя не существуют.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            request.path.startswith("/api/")
            and user is not None
            and user.is_authenticated
            and user.role == Role.TEACHER
        ):
            from django.http import JsonResponse
            from django.urls import Resolver404, resolve

            try:
                name = resolve(request.path).url_name
            except Resolver404:
                name = None
            if not teacher_may(name, request.method):
                return JsonResponse({"detail": "Не найдено"}, status=404, json_dumps_params={"ensure_ascii": False})
        return self.get_response(request)


class StudentParallelGateMiddleware:
    """Ученику 8–10 закрыты маршруты поступления — 403 с причиной.

    Что закрыто какой параллели, решает один реестр (`core/parallels.py`):
    раздел знает свои маршруты по имени, шлюз только спрашивает. Меню
    фронта берёт тот же реестр через `/api/auth/me/`, так что прямой
    запрос мимо меню упирается сюда. 403, а не 404: ученик знает, что
    раздел есть, он просто ведётся у 11 параллели.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            request.path.startswith("/api/")
            and user is not None
            and user.is_authenticated
            and user.role == Role.STUDENT
        ):
            student = getattr(user, "student", None)
            if student is not None:
                from django.http import JsonResponse
                from django.urls import Resolver404, resolve

                from core.parallels import closed_section

                try:
                    name = resolve(request.path).url_name
                except Resolver404:
                    name = None
                section = closed_section(name, student)
                if section is not None:
                    return JsonResponse(
                        {
                            "detail": f"Раздел «{section.title}» ведётся только у 11 параллели",
                            "code": "parallel_closed",
                        },
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
            if name in CURATOR_HIDDEN_ROUTES:
                return JsonResponse({"detail": "Не найдено"}, status=404, json_dumps_params={"ensure_ascii": False})
            if not curator_may(name, request.method):
                return JsonResponse(
                    {"detail": CURATOR_GATE_MESSAGE}, status=403, json_dumps_params={"ensure_ascii": False}
                )
        return self.get_response(request)
