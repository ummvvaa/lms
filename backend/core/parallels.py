"""Реестр параллелей: какая параллель что видит. Единственное место.

Школа ведёт 8, 9, 10 и 11 параллели. Учёба — у всех, поступление —
только у 11. Параллель есть только у группы (`StudyGroup.parallel`);
ученику она не выбирается и не вводится, его параллель — параллель
его группы. Проверок «если 11» по разным файлам быть не должно:
меню, маршруты фронта, шлюз сервера (`accounts.permissions.StudentParallelGateMiddleware`),
счётчики директоров и контекст помощника спрашивают только здесь.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q, QuerySet

#: все параллели школы по порядку
PARALLELS: tuple[int, ...] = (8, 9, 10, 11)
#: параллель выпускников — у неё поступление
ADMISSION_PARALLEL = 11
#: все параллели
ALL = frozenset(PARALLELS)
#: только выпускники
ADMISSION_ONLY = frozenset({ADMISSION_PARALLEL})


def parallel_of(student) -> int:
    """Параллель ученика — параллель его группы.

    Ученик без группы считается выпускником: так было до 8–10, и 185
    заведённых учеников не должны потерять свои разделы. Новых учеников
    без группы не заводят — колонка «группа» при заведении обязательна.
    """
    group = getattr(student, "group", None) if getattr(student, "group_id", None) else None
    return int(group.parallel) if group is not None else ADMISSION_PARALLEL


def graduation_year_for(parallel: int, today=None) -> int:
    """Год выпуска ученика этой параллели.

    11 выпускается в этом учебном году: до июля — в этом календарном,
    с июля — в следующем. Остальные — на столько лет позже, сколько
    параллелей им осталось. Перевод на следующий год его не меняет:
    параллель растёт, год выпуска остаётся.
    """
    from django.utils import timezone

    today = today or timezone.localdate()
    graduating = today.year if today.month <= 6 else today.year + 1
    return graduating + (ADMISSION_PARALLEL - int(parallel))


def has_admission(student) -> bool:
    """Ведётся ли у ученика поступление."""
    return parallel_of(student) == ADMISSION_PARALLEL


def admission_q(prefix: str = "") -> Q:
    """Условие «у ученика поступление» для запроса; `prefix` — путь до ученика.

    `admission_q()` — для `Student`, `admission_q("student__")` — для
    дочерних таблиц. Ученик без группы — выпускник, как в `parallel_of`.
    """
    return Q(**{f"{prefix}group__parallel": ADMISSION_PARALLEL}) | Q(**{f"{prefix}group__isnull": True})


def admission_students(queryset: QuerySet) -> QuerySet:
    """Оставить в наборе учеников только тех, у кого поступление."""
    return queryset.filter(admission_q())


def in_parallel(queryset: QuerySet, parallel, prefix: str = "") -> QuerySet:
    """Фильтр списка сотрудника по параллели; пусто или мусор — без фильтра."""
    try:
        number = int(parallel)
    except (TypeError, ValueError):
        return queryset
    if number not in ALL:
        return queryset
    if number == ADMISSION_PARALLEL:
        return queryset.filter(admission_q(prefix))
    return queryset.filter(**{f"{prefix}group__parallel": number})


@dataclass(frozen=True)
class Section:
    """Раздел ученика: адреса фронта и имена маршрутов сервера.

    `paths` — адреса экранов в меню и маршрутах фронта; `routes` — имена
    маршрутов DRF (`url_name`), которые принадлежат только этому разделу:
    для закрытой параллели шлюз отвечает на них 403.
    """

    code: str
    title: str
    parallels: frozenset[int]
    paths: tuple[str, ...] = ()
    routes: tuple[str, ...] = ()


#: Младшие параллели — учёба, олимпиады и спорт, без поступления
JUNIOR = frozenset(PARALLELS) - ADMISSION_ONLY

#: Разделы ученика по порядку меню. Раздел, которого у параллели нет,
#: не показывается вовсе — ни пунктом меню, ни «под замком» — и сервер
#: отвечает 403 на его маршруты. Экраны 11 класса не меняются: у них
#: олимпиады и спорт — вкладки «Портфолио», у 8–10 — отдельные разделы.
SECTIONS: tuple[Section, ...] = (
    # --- всем параллелям: учёба, календарь, профиль, помощник ---
    Section("home", "Главная", ALL, paths=("/dashboard",)),
    Section("schedule", "Расписание", ALL, paths=("/schedule",)),
    Section("grades", "Оценки", ALL, paths=("/grades",)),
    Section("calendar", "Календарь", ALL, paths=("/calendar",)),
    Section("profile", "Профиль", ALL, paths=("/profile",)),
    # материалы открывает ещё и отбор в олимпиадную группу (`materials.access`)
    Section("materials", "Материалы олимпиадной группы", ALL, paths=("/materials",)),
    # --- 8–10: олимпиады и спорт своими разделами ---
    Section("olympiads", "Олимпиады", JUNIOR, paths=("/olympiads",)),
    Section("sport", "Спорт", JUNIOR, paths=("/sport",)),
    # --- только 11: поступление ---
    Section(
        "journey",
        "Мой путь",
        ADMISSION_ONLY,
        paths=("/journey", "/onboarding"),
        routes=("journey-state", "journey-locks", "onboarding-state", "onboarding-answer", "onboarding-skip"),
    ),
    Section(
        "portfolio",
        "Портфолио",
        ADMISSION_ONLY,
        paths=("/my-data",),
        routes=(
            "portfolio",
            "portfolio-cv",
            "exam-goal-list",
            "exam-goal-detail",
            "exam-goals-attention",
            "attempt-list",
            "attempt-detail",
            "profile-admission-detail",
            "profile-exam-detail",
            "student-readiness",
            "readiness-config",
        ),
    ),
    Section(
        "selection",
        "Подбор вузов",
        ADMISSION_ONLY,
        paths=("/selection",),
        routes=(
            "selection-runs",
            "selection-start",
            "selection-active",
            "selection-run",
            "selection-explain",
            "match-my-universities",
            "match-open-programs",
            "match-what-if",
            "match-at-goal",
            "match-list-balance",
            "command-explain-match",
        ),
    ),
    Section(
        "catalog",
        "Каталог вузов",
        ADMISSION_ONLY,
        paths=("/catalog",),
        routes=(
            "catalog",
            "catalog-facets",
            "catalog-add",
            "catalog-remove",
            "catalog-priority",
            "catalog-tier",
            "catalog-pick",
            "university-list",
            "university-detail",
            "program-list",
            "program-detail",
            "round-list",
            "round-detail",
            "requirement-list",
            "requirement-detail",
        ),
    ),
    Section("favorites", "Избранное", ADMISSION_ONLY, paths=("/favorites",), routes=("favorites", "favorite-remove")),
    Section(
        "universities",
        "Мои вузы",
        ADMISSION_ONLY,
        paths=("/universities",),
        routes=("student-university-list", "student-university-detail"),
    ),
    Section(
        "plan",
        "План поступления",
        ADMISSION_ONLY,
        paths=("/plan",),
        routes=(
            "application-plan-list",
            "application-plan-detail",
            "application-plan-preview",
            "application-plan-tasks",
            "application-plan-apply-tasks",
            "plan-attention",
        ),
    ),
    Section(
        "scholarships",
        "Стипендии",
        ADMISSION_ONLY,
        paths=("/scholarships",),
        routes=(
            "scholarship-list",
            "scholarship-detail",
            "scholarship-overview",
            "scholarships-saved",
            "scholarship-save",
            "scholarships-pick",
            "scholarships-attention",
        ),
    ),
    Section(
        "career", "Профтест", ADMISSION_ONLY, paths=("/career",), routes=("career-state", "career-run", "career-agree")
    ),
    Section(
        "essays",
        "Эссе",
        ADMISSION_ONLY,
        paths=("/essays",),
        routes=(
            "essay-list",
            "essay-detail",
            "essay-add-version",
            "essay-submit",
            "essay-assist-log",
            "essay-reading-day",
            "essay-requirements",
            "essay-comment-list",
            "essay-comment-detail",
            "essay-doc-type-list",
            "essay-doc-type-detail",
            "essay-guide-list",
            "essay-guide-detail",
            "essay-example-list",
            "essay-example-detail",
            "essay-check-list",
            "essay-check-detail",
            "command-essay-questions",
        ),
    ),
    Section(
        "prep",
        "Подготовка к экзаменам",
        ADMISSION_ONLY,
        paths=("/prep",),
        routes=(
            "prep-center-exams",
            "prep-center-sections",
            "prep-center-topics",
            "prep-center-statistics",
            "prep-practice-start",
            "prep-practice-detail",
            "prep-practice-answer",
            "prep-practice-finish",
            "prep-mock-list",
            "prep-mock-detail",
            "prep-mock-start",
            "prep-my-runs",
            "prep-platform-mocks",
            "prep-theory-list",
            "prep-theory-detail",
            "prep-theory-file",
            "prep-passage-list",
            "prep-passage-detail",
            "prep-passage-audio",
            "prep-bank",
            "prep-question-list",
            "prep-question-detail",
        ),
    ),
    Section(
        "roadmap",
        "Роадмап и задачи",
        ADMISSION_ONLY,
        paths=("/roadmap",),
        routes=(
            "task-list",
            "task-detail",
            "task-my",
            "task-set-status",
            "task-comment-list",
            "task-comment-detail",
            "task-template-list",
            "task-template-detail",
            "roadmap-generate",
        ),
    ),
    Section(
        "achievements",
        "Достижения и XP",
        ADMISSION_ONLY,
        paths=("/achievements",),
        routes=("achievements", "game-state", "home-cues"),
    ),
    Section(
        "resources",
        "Ресурсы школы",
        ADMISSION_ONLY,
        paths=("/resources",),
        routes=("resource-list", "resource-detail", "resource-overview", "resource-read", "resource-category-list"),
    ),
)

#: Домены данных ученика по параллелям. Поступление, экзамены IELTS/SAT
#: и документы ведутся только у 11: у 8–10 их нет ни в кабинете ученика,
#: ни в карточке у сотрудников, ни в счётчиках Асем и Кымбат. Исключение —
#: пробники: их сотрудники ведут у всех (`MOCK_PARALLELS` ниже).
DOMAIN_PARALLELS: dict[str, frozenset[int]] = {
    "behavior": ALL,
    "talent": ALL,
    "sport": ALL,
    "admission": ADMISSION_ONLY,
    "exam": ADMISSION_ONLY,
    "documents": ADMISSION_ONLY,
}

#: Пробники IELTS и SAT (решение владельца, 30.09.2026) сотрудники ведут у
#: всех параллелей: файл пробника на группу 8–10, ручной ввод и история
#: пробников в карточке. Домен «экзамены» у 8–10 при этом закрыт: целей,
#: официальных попыток и текущего балла у них нет, а ученик 8–10 раздела
#: экзаменов не видит вовсе (`SECTIONS`, «Портфолио») — пробник вносит
#: и видит только сотрудник.
MOCK_PARALLELS: frozenset[int] = ALL
#: отказ, когда у ученика без экзаменов вносят официальную попытку
OFFICIAL_ATTEMPT_CLOSED = "У 8–10 параллели ведутся только пробники: официальных попыток и целей у них нет"

#: Что ученик 8–10 вносит о себе предложением: олимпиады и спорт.
#: У 11 состав предложений прежний — весь реестр `domains.py`.
JUNIOR_PROPOSALS: frozenset[str] = frozenset({"students.Activity", "students.Competition", "students.SportProfile"})
#: вид активности, который ученик 8–10 видит и вносит: прочие
#: достижения у него закрыты вместе с «Портфолио»
JUNIOR_ACTIVITY_CATEGORY = "olympiad"
#: документы у 8–10 — только сканы-подтверждения олимпиад и соревнований
#: («прочее»): паспорт, аттестат и остальной чек-лист поступления — у 11
JUNIOR_DOCUMENT_TYPE = "other"


def document_open(student, doc_type: str) -> bool:
    """Видит и грузит ли ученик документ этого вида — по параллели."""
    return has_admission(student) or doc_type == JUNIOR_DOCUMENT_TYPE


_BY_ROUTE: dict[str, Section] = {route: section for section in SECTIONS for route in section.routes}


def sections_for(parallel: int) -> list[Section]:
    """Разделы, открытые параллели, в порядке меню."""
    return [section for section in SECTIONS if parallel in section.parallels]


def student_paths(student) -> list[str]:
    """Адреса экранов, открытые ученику, — меню и маршруты фронта берут их отсюда."""
    parallel = parallel_of(student)
    return [path for section in sections_for(parallel) for path in section.paths]


def section_open(code: str, parallel: int) -> bool:
    """Открыт ли раздел ученика параллели: задачи-напоминания, например, — только с роадмапом."""
    return any(section.code == code and int(parallel) in section.parallels for section in SECTIONS)


def closed_section(route_name: str | None, student) -> Section | None:
    """Раздел, которому принадлежит маршрут, если он ученику закрыт; иначе None."""
    section = _BY_ROUTE.get(route_name or "")
    if section is None or parallel_of(student) in section.parallels:
        return None
    return section


def domain_open(domain_code: str, parallel: int) -> bool:
    """Ведётся ли домен у параллели. Домена нет в таблице — ведётся у всех."""
    return parallel in DOMAIN_PARALLELS.get(domain_code, ALL)


def domain_open_for(domain_code: str, student) -> bool:
    return domain_open(domain_code, parallel_of(student))


def domain_parallels(domain_code: str) -> frozenset[int]:
    return DOMAIN_PARALLELS.get(domain_code, ALL)


def mocks_open(parallel: int) -> bool:
    """Ведут ли сотрудники пробники у этой параллели."""
    return int(parallel) in MOCK_PARALLELS


def mocks_open_for(student) -> bool:
    return mocks_open(parallel_of(student))


def mock_groups(queryset: QuerySet) -> QuerySet:
    """Группы, у которых ведутся пробники, — выбор и списки экрана «Пробники»."""
    return queryset.filter(parallel__in=MOCK_PARALLELS)


def attempt_open(student, attempt_format: str) -> bool:
    """Можно ли завести ученику попытку этого формата.

    Официальная попытка — часть домена «экзамены» (только 11), пробник —
    всем параллелям из `MOCK_PARALLELS`.
    """
    if attempt_format == "mock":
        return mocks_open_for(student)
    return domain_open_for("exam", student)


def students_of_domain(queryset: QuerySet, domain_code: str, prefix: str = "") -> QuerySet:
    """Ученики, у которых домен ведётся: для Асем и Кымбат-экзаменов — только 11."""
    if domain_parallels(domain_code) == ADMISSION_ONLY:
        return queryset.filter(admission_q(prefix))
    return queryset


def may_propose(student, model_label: str) -> bool:
    """Может ли ученик внести предложение в эту таблицу — по параллели."""
    if has_admission(student):
        return True
    return model_label in JUNIOR_PROPOSALS
