"""Сохранённые фразы журнала — на языке того, кто читает.

Запись журнала расписания и событие по ученику хранятся готовой фразой
(`AuditLog.new_value`): журнал — след, его не переписывают. Пишется фраза
по-русски, из шаблона этого реестра. При показе (`core.labels.value_title`,
журнал расписания) фраза сверяется с шаблонами: подошла — подстановки
достаются из неё, и фраза собирается заново на языке читающего. Не подошла
(старая запись, данные) — показывается как есть.

Подстановки — данные: дата цифрами, название, имя, число. Слово языка в
подстановку не кладётся: русское «среду» внутри казахской фразы и было бы
непереводимым куском.
"""

from __future__ import annotations

import re
from functools import cache

from django.utils.translation import gettext, gettext_noop

#: шаблоны журнала расписания и событий по ученику
LESSON_SERIES_ADDED = gettext_noop("Добавлен урок: {subject} {cohort}, каждую неделю с {date}, {slot} урок")
LESSON_ADDED = gettext_noop("Добавлен разовый урок: {lesson}, {date}, {slot} урок")
LESSON_CHANGED = gettext_noop("Изменён урок {date}: {lesson}")
SERIES_CHANGED = gettext_noop("Изменена серия с {date}: {subject} {cohort}")
LESSON_COVER = gettext_noop("Замена: {lesson} {date} — {teacher}")
LESSON_MOVED = gettext_noop("Перенос: {lesson} на {date}, {slot} урок")
LESSON_CANCELLED = gettext_noop("Отменён урок: {lesson} {date}")
LESSON_RESTORED = gettext_noop("Урок возвращён как было: {lesson} {date}")
SERIES_DELETED = gettext_noop("Удалено: {title}, уроков: {count}, с {date}")
JOURNAL_TEACHER = gettext_noop("Журнал {subject} {cohort}: с {date} ведёт {teacher} вместо {old}")
JOURNAL_TEACHER_FIRST = gettext_noop("Журнал {subject} {cohort}: с {date} ведёт {teacher}")
COHORT_CHANGED = gettext_noop("Изменён состав {name}: учеников {count}, с {date}")
STREAM_CHANGED = gettext_noop("Изменён поток {name}")
GROUP_SPLIT = gettext_noop("Разделена группа {group}: {subject}, подгрупп: {count}")
STREAM_BUILT = gettext_noop("Собран поток {name}")
JOURNAL_SECTION = gettext_noop("Журнал {subject} {cohort}: раздел отчёта «{before}» → «{after}»")
YEAR_SETTINGS = gettext_noop("Изменены настройки учебного года")
RESULTS_CLOSED = gettext_noop("Закрыт приём итогов: {quarter}")
RESULTS_OPENED = gettext_noop("Открыт приём итогов: {quarter}")
ENGLISH_LEVEL = gettext_noop("{level} с {date}")
#: название четверти, которое школа получает по умолчанию при заведении года
QUARTER_TITLE = gettext_noop("{number} четверть")
MOCK_IMPORT = gettext_noop("{exam} · {date} · учитель {teacher}")
LINK_FROM_TABLE = gettext_noop("{document}: ссылка из таблицы поступления")
LINK_FROM_BLOCK = gettext_noop("{document}: ссылка из блока «Поступление»")
#: название плана в архиве (`roadmap.Plan.__str__`)
PLAN_TITLE = gettext_noop("План: {student} → {program}")

#: Названия и формулировки, которые школа получает по умолчанию (посев, миграции):
#: хранятся в базе как данные, но пока школа их не переименовала, читающему
#: показывается перевод. Своё название школы показывается как введено.
DEFAULTS = (
    gettext_noop("Общее"),
    gettext_noop("Звонки"),
    gettext_noop("Каникулы"),
    gettext_noop("Праздник"),
    gettext_noop("Осенние каникулы"),
    gettext_noop("Зимние каникулы"),
    gettext_noop("Весенние каникулы"),
    gettext_noop("Летние каникулы"),
    gettext_noop("низкая посещаемость"),
    gettext_noop("просел по пробным"),
    gettext_noop("не заходил в систему"),
    gettext_noop("пропустил дедлайн"),
    gettext_noop("нет контактов родителей"),
)

TEMPLATES = (
    LESSON_SERIES_ADDED,
    LESSON_ADDED,
    LESSON_CHANGED,
    SERIES_CHANGED,
    LESSON_COVER,
    LESSON_MOVED,
    LESSON_CANCELLED,
    LESSON_RESTORED,
    SERIES_DELETED,
    JOURNAL_TEACHER,
    JOURNAL_TEACHER_FIRST,
    COHORT_CHANGED,
    STREAM_CHANGED,
    GROUP_SPLIT,
    STREAM_BUILT,
    JOURNAL_SECTION,
    YEAR_SETTINGS,
    RESULTS_CLOSED,
    RESULTS_OPENED,
    ENGLISH_LEVEL,
    QUARTER_TITLE,
    MOCK_IMPORT,
    LINK_FROM_TABLE,
    LINK_FROM_BLOCK,
    PLAN_TITLE,
)


def store(template: str, **params: object) -> str:
    """Фраза для журнала: русский текст шаблона с подстановками."""
    return template.format(**{name: str(value) for name, value in params.items()})


@cache
def _patterns() -> tuple[tuple[str, re.Pattern], ...]:
    compiled = []
    # длинные шаблоны раньше: «Журнал … вместо {old}» не должен съесться коротким
    for template in sorted(TEMPLATES, key=len, reverse=True):
        pieces = re.split(r"\{(\w+)\}", template)
        regex = "".join(
            re.escape(piece) if index % 2 == 0 else f"(?P<{piece}>.+?)" for index, piece in enumerate(pieces)
        )
        compiled.append((template, re.compile(regex, re.S)))
    return tuple(compiled)


def localize(text: str) -> str:
    """Сохранённая фраза на активном языке; не из реестра — как есть.

    Подошёл шаблон — подстановки тоже переводятся, если это строка каталога
    («Паспорт» в названии документа-ссылки). Целиком строка каталога
    (подпись варианта, записанная в журнал; название по умолчанию) —
    переводится целиком. Остальное — данные людей, показываются как введены.
    """
    if not isinstance(text, str) or not text:
        return text
    for template, pattern in _patterns():
        match = pattern.fullmatch(text)
        if match:
            params = {name: gettext(value) for name, value in match.groupdict().items()}
            return gettext(template).format(**params)
    return gettext(text)
