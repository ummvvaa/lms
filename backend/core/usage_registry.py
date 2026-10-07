"""Действия и экраны аналитики: один словарь подписей и безопасных ключей."""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext, gettext_noop

from core.domains import ALL_DIRECTORS, ROLE_ADMIN, ROLE_CURATOR, ROLE_STUDENT, ROLE_TEACHER, ROLE_TITLES, USAGE_READERS

ALL = tuple(ROLE_TITLES)
DIRECTORS = (ROLE_ADMIN, *ALL_DIRECTORS)
STAFF = (*DIRECTORS, ROLE_CURATOR, ROLE_TEACHER)
SCHOOL = (ROLE_ADMIN, "director_exam")
REPORTS = (*SCHOOL, "director_behavior", ROLE_CURATOR)
CLIENT_ACTIONS = ("screen.open", "tab.change", "filter.change")
BATCH_LIMIT = 100
FLUSH_INTERVAL_MS = 10000


@dataclass(frozen=True)
class Screen:
    """Канонический маршрут без идентификатора записи и строки запроса."""

    key: str
    title_ru: str
    roles: tuple[str, ...]

    @property
    def title(self) -> str:
        return gettext(self.title_ru)


SCREENS = (
    Screen("/login", gettext_noop("Вход"), ALL),
    Screen("/login/link", gettext_noop("Вход по ссылке"), ALL),
    Screen("/set-password", gettext_noop("Установка пароля"), ALL),
    Screen("/confirm-email", gettext_noop("Подтверждение почты"), ALL),
    Screen("/dashboard", gettext_noop("Главная"), ALL),
    Screen("/table", gettext_noop("Таблица"), DIRECTORS),
    Screen("/students/:id", gettext_noop("Карточка ученика"), STAFF),
    Screen("/import", gettext_noop("Импорт"), SCHOOL),
    Screen("/assistant", gettext_noop("Помощник"), DIRECTORS),
    Screen("/suggestions", gettext_noop("Предложения"), DIRECTORS),
    Screen("/suggestions/:id", gettext_noop("Предложение"), DIRECTORS),
    Screen("/digest", gettext_noop("Дайджест"), DIRECTORS),
    Screen("/users", gettext_noop("Пользователи"), (ROLE_ADMIN,)),
    Screen("/queue", gettext_noop("Очередь"), (ROLE_CURATOR,)),
    Screen("/students", gettext_noop("Ученики"), (ROLE_CURATOR,)),
    Screen("/tasks", gettext_noop("Задачи"), (ROLE_CURATOR,)),
    Screen("/my-groups", gettext_noop("Мои группы"), (ROLE_CURATOR,)),
    Screen("/documents", gettext_noop("Документы"), (ROLE_CURATOR,)),
    Screen("/journal", gettext_noop("Журнал изменений"), (ROLE_CURATOR,)),
    Screen("/attendance", gettext_noop("Посещаемость"), REPORTS),
    Screen("/directory", gettext_noop("Справочник"), DIRECTORS),
    Screen("/archive", gettext_noop("Архив"), (ROLE_ADMIN,)),
    Screen("/subjects", gettext_noop("Предметы"), DIRECTORS),
    Screen("/sport-types", gettext_noop("Виды спорта"), DIRECTORS),
    Screen("/exam-kinds", gettext_noop("Экзамены"), DIRECTORS),
    Screen("/materials", gettext_noop("Материалы"), (*DIRECTORS, ROLE_STUDENT)),
    Screen("/materials/:id", gettext_noop("Материал"), (*DIRECTORS, ROLE_STUDENT)),
    Screen("/olympiad-group", gettext_noop("Олимпиадная группа"), DIRECTORS),
    Screen("/spend", gettext_noop("Расходы на ИИ"), (ROLE_ADMIN,)),
    Screen("/school-settings", gettext_noop("Настройки школы"), (ROLE_ADMIN,)),
    Screen("/profile", gettext_noop("Профиль"), ALL),
    Screen("/schedule", gettext_noop("Расписание"), ALL),
    Screen("/journals", gettext_noop("Журналы"), STAFF),
    Screen("/journals/:id", gettext_noop("Журнал предмета"), STAFF),
    Screen("/lessons/:id", gettext_noop("Урок"), STAFF),
    Screen("/homework-review", gettext_noop("Проверка ДЗ"), STAFF),
    Screen("/homework-review/:id", gettext_noop("Проверка задания"), STAFF),
    Screen("/homework", gettext_noop("Домашние задания"), (ROLE_STUDENT,)),
    Screen("/homework/:id", gettext_noop("Домашнее задание"), (ROLE_STUDENT,)),
    Screen("/cohorts", gettext_noop("Подгруппы и потоки"), SCHOOL),
    Screen("/teachers", gettext_noop("Учителя"), SCHOOL),
    Screen("/grades", gettext_noop("Успеваемость"), (*REPORTS, ROLE_STUDENT)),
    Screen("/academic-year", gettext_noop("Учебный год"), SCHOOL),
    Screen("/reports", gettext_noop("Отчёты родителям"), REPORTS),
    Screen("/groups", gettext_noop("Группы"), DIRECTORS),
    Screen("/contacts", gettext_noop("Контакты родителей"), DIRECTORS),
    Screen("/task-templates", gettext_noop("Шаблоны задач"), DIRECTORS),
    Screen("/risks", gettext_noop("Риски"), DIRECTORS),
    Screen("/overview", gettext_noop("Сводный вид"), DIRECTORS),
    Screen("/deadlines", gettext_noop("Дедлайны"), DIRECTORS),
    Screen("/top30", gettext_noop("ТОП-30"), DIRECTORS),
    Screen("/mocks", gettext_noop("Mock Test онлайн"), DIRECTORS),
    Screen("/mock-imports", gettext_noop("Mock Test"), (*SCHOOL, ROLE_CURATOR)),
    Screen("/mock-imports/:id", gettext_noop("Результаты Mock Test"), (*SCHOOL, ROLE_CURATOR)),
    Screen("/tracks", gettext_noop("Треки"), DIRECTORS),
    Screen("/competitions", gettext_noop("Соревнования"), DIRECTORS),
    Screen("/journey", gettext_noop("Мой путь"), (ROLE_STUDENT,)),
    Screen("/calendar", gettext_noop("Календарь"), (ROLE_STUDENT,)),
    Screen("/selection", gettext_noop("Подбор вузов"), (ROLE_STUDENT,)),
    Screen("/selection/:id", gettext_noop("Результат подбора"), (ROLE_STUDENT,)),
    Screen("/favorites", gettext_noop("Избранное"), (ROLE_STUDENT,)),
    Screen("/plan", gettext_noop("План поступления"), (ROLE_STUDENT,)),
    Screen("/plan/:id", gettext_noop("План по вузу"), (ROLE_STUDENT,)),
    Screen("/my-data", gettext_noop("Портфолио"), (ROLE_STUDENT,)),
    Screen("/olympiads", gettext_noop("Олимпиады"), (ROLE_STUDENT,)),
    Screen("/sport", gettext_noop("Спорт"), (ROLE_STUDENT,)),
    Screen("/roadmap", gettext_noop("Роадмап"), (ROLE_STUDENT,)),
    Screen("/universities", gettext_noop("Мои вузы"), (ROLE_STUDENT,)),
    Screen("/catalog", gettext_noop("Каталог вузов"), (ROLE_STUDENT,)),
    Screen("/onboarding", gettext_noop("Анкета первого входа"), (ROLE_STUDENT,)),
    Screen("/prep", gettext_noop("Подготовка"), (ROLE_STUDENT,)),
    Screen("/essays", gettext_noop("Эссе"), (ROLE_STUDENT,)),
    Screen("/essay-content", gettext_noop("Конструктор эссе"), DIRECTORS),
    Screen("/scholarships", gettext_noop("Стипендии"), (ROLE_STUDENT,)),
    Screen("/scholarship-directory", gettext_noop("Справочник стипендий"), DIRECTORS),
    Screen("/resources", gettext_noop("Ресурсы"), (*DIRECTORS, ROLE_STUDENT)),
    Screen("/resources/:id", gettext_noop("Ресурс"), (*DIRECTORS, ROLE_STUDENT)),
    Screen("/career", gettext_noop("Профтест"), (ROLE_STUDENT,)),
    Screen("/career-questions", gettext_noop("Вопросы профтеста"), DIRECTORS),
    Screen("/home-cues", gettext_noop("Сюжеты главной"), (ROLE_ADMIN,)),
    Screen("/call-rules", gettext_noop("Правила обзвона"), DIRECTORS),
    Screen("/achievements", gettext_noop("Достижения"), (ROLE_STUDENT,)),
    Screen("/badges", gettext_noop("Достижения школы"), (ROLE_ADMIN,)),
    Screen("/usage", gettext_noop("Использование"), USAGE_READERS),
)
SCREENS_BY_KEY = {screen.key: screen for screen in SCREENS}


@dataclass(frozen=True)
class Action:
    """Серверное действие имеет закреплённый экран функции, клиентское — выбранный."""

    key: str
    title_ru: str
    screen: str | None = None
    source: str = "server"

    @property
    def title(self) -> str:
        return gettext(self.title_ru)


ACTIONS = (
    Action("screen.open", gettext_noop("Открытие экрана"), source="client"),
    Action("tab.change", gettext_noop("Переключение вкладки"), source="client"),
    Action("filter.change", gettext_noop("Изменение фильтра"), source="client"),
    Action("auth.login", gettext_noop("Вход в платформу"), "/login"),
    Action("access.link.issue", gettext_noop("Выдача ссылки пользователю"), "/users"),
    Action("access.student_link.issue", gettext_noop("Выдача ссылки ученику"), "/students/:id"),
    Action("access.invite.bulk", gettext_noop("Запуск рассылки приглашений"), "/users"),
    Action("journal.grade.set", gettext_noop("Изменение оценки"), "/journals/:id"),
    Action("journal.attendance.set", gettext_noop("Отметка посещаемости"), "/journals/:id"),
    Action("journal.final.set", gettext_noop("Сохранение итоговых оценок"), "/journals/:id"),
    Action("homework.submit", gettext_noop("Сдача домашнего задания"), "/homework/:id"),
    Action("homework.check", gettext_noop("Проверка домашнего задания"), "/homework-review/:id"),
    Action("import.wizard.apply", gettext_noop("Импорт через мастер"), "/import"),
    Action("import.students.apply", gettext_noop("Заведение учеников файлом"), "/users"),
    Action("import.contacts.apply", gettext_noop("Импорт контактов родителей"), "/import"),
    Action("import.competitions.apply", gettext_noop("Импорт соревнований"), "/import"),
    Action("import.requirements.apply", gettext_noop("Импорт требований вузов"), "/import"),
    Action("import.scholarships.apply", gettext_noop("Импорт стипендий"), "/import"),
    Action("import.questions.apply", gettext_noop("Импорт банка заданий"), "/import"),
    Action("import.mock.apply", gettext_noop("Импорт результатов Mock Test"), "/mock-imports"),
    Action("import.cohorts.apply", gettext_noop("Импорт составов подгрупп"), "/cohorts"),
    Action("import.schedule.apply", gettext_noop("Импорт расписания"), "/schedule"),
    Action("report.build", gettext_noop("Сборка отчётов родителям"), "/reports"),
    Action("report.edit", gettext_noop("Правка отчёта родителям"), "/reports"),
    Action("report.draft.start", gettext_noop("Подготовка текста отчёта"), "/reports"),
    Action("report.check", gettext_noop("Проверка отчётов родителям"), "/reports"),
    Action("report.refresh", gettext_noop("Обновление отчётов родителям"), "/reports"),
    Action("report.template.set", gettext_noop("Смена шаблона отчёта"), "/reports"),
    Action("report.sent.set", gettext_noop("Отметка об отправке отчёта"), "/reports"),
    Action("report.export.start", gettext_noop("Подготовка файлов отчётов"), "/reports"),
    Action("assistant.ask", gettext_noop("Вопрос помощнику"), "/assistant"),
    Action("assistant.text.parse", gettext_noop("Разбор текста помощником"), "/assistant"),
    Action("assistant.file.parse", gettext_noop("Разбор файла помощником"), "/assistant"),
    Action("assistant.match.explain", gettext_noop("Объяснение соответствия вузу"), "/assistant"),
    Action("assistant.essay.questions", gettext_noop("Вопросы для эссе"), "/assistant"),
    Action("assistant.operation.start", gettext_noop("Запуск операции помощника"), "/assistant"),
    Action("assistant.university.parse", gettext_noop("Разбор информации о вузе"), "/assistant"),
    Action("assistant.requirements.verify", gettext_noop("Проверка требований вузов"), "/assistant"),
    Action("assistant.activity.parse", gettext_noop("Разбор активности помощником"), "/assistant"),
    Action("assistant.image.parse", gettext_noop("Разбор изображения помощником"), "/assistant"),
    Action("export.download", gettext_noop("Скачивание выгрузки")),
)
ACTIONS_BY_KEY = {action.key: action for action in ACTIONS}

# Общий сборщик книг вызывают и шаблоны. Только эти успешные выгрузки
# считаются действием; pathname, Referer, query и содержание файла не читаются.
EXPORT_SCREENS = {
    "users-export": "/users",
    "users-handout-export": "/users",
    "users-credentials": "/users",
    "curator-students-export": "/students",
    "curator-documents-export": "/documents",
    "curator-journal-export": "/journal",
    "portfolio-cv": "/my-data",
    "mock-export": "/mock-imports/:id",
    "admission-export": "/import",
    "attendance-journal-export": "/attendance",
    "acad-attendance-export": "/attendance",
    "acad-school-grades-export": "/grades",
    "acad-group-grades-export": "/grades",
    "acad-journal-export": "/journals/:id",
    "acad-report-pdf": "/reports",
    "acad-reports-zip": "/reports",
    "acad-reports-export-file": "/reports",
    "usage-export": "/usage",
}


def client_screens(user) -> tuple[str, ...]:
    """Клиентские события ограничены ролью и тем же реестром параллелей, что меню."""
    allowed = [screen.key for screen in SCREENS if user.role in screen.roles]
    if user.role == ROLE_STUDENT:
        from core.parallels import SECTIONS, parallel_of

        parallel = parallel_of(getattr(user, "student", None))
        closed = [path for section in SECTIONS if parallel not in section.parallels for path in section.paths]
        allowed = [key for key in allowed if not any(key == path or key.startswith(path + "/") for path in closed)]
    return tuple(allowed)
