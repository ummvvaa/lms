"""Точки входа: где в интерфейсе человек заводит, правит и убирает записи.

Право живёт в реестре доменов (`core.domains`). Здесь записано другое —
как в это право войти руками. Разница важная: право, в которое нельзя
войти с экрана, существует только для программиста. Так в фазе 30
оказалось, что директор спорта по таблице прав заводит соревнования,
а кнопки у него нет ни на одном экране; то же было с попытками
экзаменов, банком заданий и пробными.

Проверяет это `core/tests/test_entry_points.py`: он берёт **из самого
API** список того, что разрешено создавать, править и удалять, и требует
на каждое действие либо точку входа отсюда, либо запись в `NO_SCREEN`
с причиной, почему экрана быть не должно. Пустой клетки не бывает.

Это тот же приём, что и с реестром команд помощника: там объявленное
без обработчика однажды оказалось одиннадцатью кнопками из двенадцати.
Оговорка честная — запись здесь доказывает, что экран и запрос есть,
но не доказывает, что кнопка стоит на видном месте. Это ловят глаза.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    """Одно действие на одном экране."""

    #: адрес экрана во фронте — должен быть маршрутом в `App.tsx`
    screen: str
    #: хук или компонент, который выполняет запрос; тест проверяет, что он есть
    via: str
    #: кому действие доступно; пусто — тем же, кому право по реестру
    roles: tuple[str, ...] = ()


CREATE, UPDATE, DELETE = "create", "update", "delete"


#: `app_label.Model` → {действие: где оно живёт}
ENTRY_POINTS: dict[str, dict[str, Entry]] = {
    # --- Реестр школы ---
    "students.Student": {
        CREATE: Entry("/table", "AddStudent", ("admin",)),
        UPDATE: Entry("/students/:id", "StudentRegistryCard", ("admin",)),
        DELETE: Entry("/students/:id", "DeleteButton", ("admin",)),
    },
    "students.StudyGroup": {
        CREATE: Entry("/users", "StudyGroups", ("admin",)),
        UPDATE: Entry("/users", "useUpdateStudyGroup", ("admin",)),
        DELETE: Entry("/users", "StudyGroups", ("admin",)),
    },
    "students.ParentContact": {
        CREATE: Entry("/contacts", "useContactRows", ("director_behavior",)),
        UPDATE: Entry("/contacts", "useContactRows", ("director_behavior",)),
        DELETE: Entry("/contacts", "DeleteButton", ("director_behavior",)),
    },
    # --- Экзамены ---
    "students.ExamAttempt": {
        CREATE: Entry("/mocks", "useAttemptRows", ("director_exam",)),
        UPDATE: Entry("/students/:id", "useAttemptRows", ("director_exam",)),
        DELETE: Entry("/students/:id", "DeleteButton", ("director_exam",)),
    },
    "prep.Question": {
        CREATE: Entry("/mocks", "useQuestionRows", ("director_exam",)),
        UPDATE: Entry("/mocks", "useQuestionRows", ("director_exam",)),
        DELETE: Entry("/mocks", "DeleteButton", ("director_exam",)),
    },
    "prep.MockExam": {
        CREATE: Entry("/mocks", "useMockRows", ("director_exam",)),
        UPDATE: Entry("/mocks", "useMockRows", ("director_exam",)),
        DELETE: Entry("/mocks", "DeleteButton", ("director_exam",)),
    },
    # --- Таланты ---
    "students.Activity": {
        CREATE: Entry("/students/:id", "useActivityRows", ("director_talent",)),
        UPDATE: Entry("/students/:id", "useActivityRows", ("director_talent",)),
        DELETE: Entry("/students/:id", "DeleteButton", ("director_talent",)),
    },
    "directories.OlympiadSubject": {
        CREATE: Entry("/subjects", "useDirectoryActions", ("director_talent",)),
        UPDATE: Entry("/subjects", "useDirectoryActions", ("director_talent",)),
        DELETE: Entry("/subjects", "useDirectoryActions", ("director_talent",)),
    },
    "materials.StudyMaterial": {
        CREATE: Entry("/materials", "useMaterialActions", ("student", "director_talent")),
        UPDATE: Entry("/materials", "useMaterialActions", ("student", "director_talent")),
        DELETE: Entry("/materials", "useMaterialActions", ("student", "director_talent")),
    },
    "materials.MaterialCollection": {
        CREATE: Entry("/materials", "useMaterialActions", ("director_talent",)),
        UPDATE: Entry("/materials", "useMaterialActions", ("director_talent",)),
        DELETE: Entry("/materials", "useMaterialActions", ("director_talent",)),
    },
    "materials.MaterialRequest": {
        CREATE: Entry("/materials", "useMaterialActions", ("student",)),
        DELETE: Entry("/materials", "useMaterialActions", ("student", "director_talent")),
    },
    "materials.MaterialComment": {
        CREATE: Entry("/materials", "useMaterialActions", ("student", "director_talent")),
        DELETE: Entry("/materials", "useMaterialActions", ("student", "director_talent")),
    },
    "materials.MaterialReport": {
        CREATE: Entry("/materials", "useMaterialActions", ("student", "director_talent")),
        DELETE: Entry("/materials", "useMaterialActions", ("student",)),
    },
    # --- Спорт ---
    "students.Competition": {
        CREATE: Entry("/competitions", "useCompetitionRows", ("director_sport",)),
        UPDATE: Entry("/competitions", "useCompetitionRows", ("director_sport",)),
        DELETE: Entry("/competitions", "DeleteButton", ("director_sport",)),
    },
    "directories.SportType": {
        CREATE: Entry("/sport-types", "useDirectoryActions", ("director_sport",)),
        UPDATE: Entry("/sport-types", "useDirectoryActions", ("director_sport",)),
        DELETE: Entry("/sport-types", "useDirectoryActions", ("director_sport",)),
    },
    # --- Поступление ---
    "universities.University": {
        CREATE: Entry("/directory", "useCreateUniversity", ("director_admission",)),
        UPDATE: Entry("/directory", "useUpdateUniversity", ("director_admission",)),
        DELETE: Entry("/directory", "DeleteButton", ("director_admission",)),
    },
    "universities.Program": {
        CREATE: Entry("/directory", "useCreateProgram", ("director_admission",)),
        UPDATE: Entry("/directory", "useUpdateProgram", ("director_admission",)),
        DELETE: Entry("/directory", "DeleteButton", ("director_admission",)),
    },
    "universities.AdmissionRequirement": {
        CREATE: Entry("/directory", "useCreateRequirement", ("director_admission",)),
        UPDATE: Entry("/directory", "useUpdateRequirement", ("director_admission",)),
        DELETE: Entry("/directory", "DeleteButton", ("director_admission",)),
    },
    "universities.AdmissionRound": {
        CREATE: Entry("/directory", "useCreateRound", ("director_admission",)),
        UPDATE: Entry("/directory", "useUpdateRound", ("director_admission",)),
        DELETE: Entry("/directory", "DeleteButton", ("director_admission",)),
    },
    "universities.StudentUniversity": {
        CREATE: Entry("/students/:id", "useStudentUniversityRows", ("director_admission",)),
        UPDATE: Entry("/students/:id", "useStudentUniversityRows", ("director_admission",)),
        DELETE: Entry("/students/:id", "DeleteButton", ("director_admission",)),
    },
    # --- Сквозные: задачи и эссе ---
    "roadmap.Task": {
        CREATE: Entry("/students/:id", "useTaskRows"),
        UPDATE: Entry("/students/:id", "useTaskRows"),
        DELETE: Entry("/students/:id", "DeleteButton"),
    },
    "roadmap.TaskTemplate": {
        CREATE: Entry("/task-templates", "useTemplateRows"),
        UPDATE: Entry("/task-templates", "useTemplateRows"),
        DELETE: Entry("/task-templates", "DeleteButton"),
    },
    "roadmap.Essay": {
        CREATE: Entry("/students/:id", "useEssayRows"),
        UPDATE: Entry("/students/:id", "useEssayRows"),
        DELETE: Entry("/students/:id", "DeleteButton"),
    },
    "roadmap.TaskComment": {
        CREATE: Entry("/students/:id", "useRowComments"),
        DELETE: Entry("/students/:id", "useRowComments"),
    },
    "roadmap.EssayComment": {
        CREATE: Entry("/students/:id", "useRowComments"),
        DELETE: Entry("/students/:id", "useRowComments"),
    },
}


#: Действия, которых в интерфейсе нет намеренно. Причина обязательна:
#: пустая клетка в таблице прав — это дефект, а не умолчание.
NO_SCREEN: dict[tuple[str, str], str] = {
    ("students.Student", "delete_hard"): "ученик уходит в архив, физического удаления нет (инвариант №13)",
    (
        "materials.MaterialComment",
        UPDATE,
    ): "реплику под материалом не переписывают: её убирают и пишут заново — иначе ответ под ней теряет смысл",
    (
        "roadmap.TaskComment",
        UPDATE,
    ): "то же правило, что и под материалом: свою реплику убирают и пишут заново, чужую не трогают вовсе",
    (
        "roadmap.EssayComment",
        UPDATE,
    ): "замечание к эссе не переписывают: ученик мог его уже прочитать и переписать текст под него",
    (
        "materials.MaterialRequest",
        UPDATE,
    ): "запрос снимают и заводят заново: он уже мог собрать отклики, и подмена темы обесценила бы их",
    (
        "materials.MaterialReport",
        UPDATE,
    ): "жалобу не переписывают под уже начатым разбором — её отзывают и подают заново",
    (
        "students.BehaviorProfile",
        UPDATE,
    ): "поля профиля правятся в таблице и на карточке ученика, а не отдельным экраном профиля",
    ("students.AdmissionProfile", UPDATE): "то же: профиль — часть карточки ученика",
    ("students.ExamProfile", UPDATE): "то же: профиль — часть карточки ученика",
    ("students.TalentProfile", UPDATE): "то же: профиль — часть карточки ученика",
    ("students.SportProfile", UPDATE): "то же: профиль — часть карточки ученика",
    (
        "suggestions.Suggestion",
        DELETE,
    ): "предложение не удаляют, а отклоняют: отказ виден в списке и остаётся в журнале",
}


def entry_for(model_label: str, action: str) -> Entry | None:
    return ENTRY_POINTS.get(model_label, {}).get(action)


def excused(model_label: str, action: str) -> str:
    """Причина, по которой экрана нет. Пусто — причины не записано."""
    return NO_SCREEN.get((model_label, action), "")
