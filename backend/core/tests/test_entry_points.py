"""Страж фазы 31: право есть — значит, в интерфейсе есть, чем в него войти.

Список того, что можно завести, править и удалять, берётся **из самого
API**, а не из руками написанного перечня: обходим маршруты, находим
вьюсеты и смотрим, какие действия они разрешают. На каждое найденное
действие должна быть либо точка входа в `core.entry_points`, либо запись
в `NO_SCREEN` с причиной, почему экрана быть не должно.

Тот же класс дефекта уже ловили дважды: в фазе 7 из двенадцати кнопок
помощника работала одна, в фазе 30 у директора спорта было право заводить
соревнования и не было кнопки. Разница между «право есть» и «войти в него
нечем» глазами не видна — её видно только так.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.urls import get_resolver

from core.entry_points import CREATE, DELETE, ENTRY_POINTS, NO_SCREEN, UPDATE

ROOT = Path("/repo") if Path("/repo/deploy").is_dir() else Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontend" / "src"

#: Действия DRF и наши имена для них.
ACTIONS = {"create": CREATE, "update": UPDATE, "partial_update": UPDATE, "destroy": DELETE}


def _walk(resolver, prefix: str = ""):
    for pattern in resolver.url_patterns:
        if hasattr(pattern, "url_patterns"):
            yield from _walk(pattern, prefix + str(pattern.pattern))
        else:
            yield prefix + str(pattern.pattern), pattern.callback


def api_write_map() -> dict[str, set[str]]:
    """`{app_label.Model: {create, update, delete}}` — что разрешает API."""
    found: dict[str, set[str]] = {}
    for _path, callback in _walk(get_resolver()):
        actions = getattr(callback, "actions", None)
        view = getattr(callback, "cls", None)
        if not actions or view is None:
            continue
        queryset = getattr(view, "queryset", None)
        if queryset is None:
            continue
        model = queryset.model
        label = f"{model._meta.app_label}.{model._meta.object_name}"
        for action in actions.values():
            if action in ACTIONS:
                found.setdefault(label, set()).add(ACTIONS[action])
    return found


def frontend_sources() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in FRONTEND.rglob("*.ts*") if path.name != "schema.ts"}


def routes() -> set[str]:
    """Адреса экранов из `App.tsx` — то, что вообще можно открыть."""
    source = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    return set(re.findall(r'<Route path="([^"]+)"', source))


def test_every_writable_entity_has_a_way_in():
    """У каждого действия API есть точка входа или записанная причина её отсутствия."""
    missing: list[str] = []
    for label, actions in sorted(api_write_map().items()):
        for action in sorted(actions):
            if ENTRY_POINTS.get(label, {}).get(action):
                continue
            if NO_SCREEN.get((label, action)):
                continue
            missing.append(f"{label} · {action}")
    assert not missing, (
        "API разрешает действие, а войти в него с экрана нечем — "
        "постройте кнопку или запишите причину в NO_SCREEN: " + ", ".join(missing)
    )


def test_entry_points_lead_to_real_screens():
    """Объявленный экран должен быть настоящим маршрутом приложения."""
    known = routes()
    broken = [
        f"{label} · {action} → {entry.screen}"
        for label, actions in ENTRY_POINTS.items()
        for action, entry in actions.items()
        # `/students/:id` в роутере записан как `/students/:id`
        if entry.screen not in known
    ]
    assert not broken, f"экрана с таким адресом нет в App.tsx: {broken}"


def test_entry_points_name_code_that_exists():
    """Объявленный хук или компонент должен быть во фронте.

    Проверка не доказывает, что кнопка стоит на видном месте, — она
    доказывает, что запрос написан. Объявить точку входа и не построить
    её после этого нельзя молча.
    """
    sources = frontend_sources()
    body = "\n".join(sources.values())
    unknown = sorted(
        {
            f"{label} · {action} → {entry.via}"
            for label, actions in ENTRY_POINTS.items()
            for action, entry in actions.items()
            if not re.search(rf"\b{re.escape(entry.via)}\b", body)
        }
    )
    assert not unknown, f"во фронте нет такого хука или компонента: {unknown}"


def test_the_screen_actually_uses_what_it_declares():
    """Экран, объявленный точкой входа, должен ссылаться на свой код.

    Объявить «соревнования заводятся на /competitions», а запрос написать
    в другом месте — та же ложь, что и кнопка без обработчика.
    """
    sources = frontend_sources()
    # экран → его файл и всё, что он импортирует из своих же исходников
    screen_files = {path.stem: text for path, text in sources.items()}

    def reachable(screen: str) -> str:
        """Текст экрана вместе с текстом его собственных компонентов."""
        stem = screen.strip("/").split("/")[0]
        names = {
            "table": ("TableScreen", "StudentRegistry", "AddStudent"),
            "students": ("StudentCard", "StudentRows", "StudentRegistryCard", "RowComments"),
            "mocks": ("Mocks", "ExamResults", "QuestionBank"),
            "competitions": ("Competitions",),
            "contacts": ("Contacts", "StudentRows"),
            "materials": ("Materials", "MaterialCard"),
            "directory": ("Directory", "ProgramList", "DirectoryList"),
            "subjects": ("Subjects", "DirectoryList"),
            "sport-types": ("SportTypes", "DirectoryList"),
            "users": ("Users", "StudyGroups", "EnrollPanel"),
            "task-templates": ("TaskTemplates",),
            "my-data": ("MyData",),
        }.get(stem, ())
        return "\n".join(screen_files.get(name, "") for name in names)

    broken = sorted(
        {
            f"{label} · {action}: {entry.via} не встречается на экране {entry.screen}"
            for label, actions in ENTRY_POINTS.items()
            for action, entry in actions.items()
            if not re.search(rf"\b{re.escape(entry.via)}\b", reachable(entry.screen))
        }
    )
    assert not broken, broken


def test_no_screen_reasons_are_written_out():
    """У каждой пустой клетки есть причина словами, а не молчание."""
    empty = [key for key, reason in NO_SCREEN.items() if len(reason.strip()) < 20]
    assert not empty, f"причина не написана или слишком короткая: {empty}"


def test_the_guard_itself_catches_a_missing_button():
    """Проверка на проверку: убранная точка входа обязана ронять тест."""
    label = "students.Competition"
    saved = ENTRY_POINTS[label].pop(CREATE)
    try:
        with pytest.raises(AssertionError, match="войти в него с экрана нечем"):
            test_every_writable_entity_has_a_way_in()
    finally:
        ENTRY_POINTS[label][CREATE] = saved
