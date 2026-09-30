"""Кого видит вошедший — одно правило на всю платформу и на помощника.

- руководители (администратор и пять директоров) — всех учеников школы;
- куратор — только свои группы;
- учитель — только учеников своих составов: группы и подгруппы из
  расписания, где он ведёт журнал, и состав урока на замене — в день урока;
- ученик — только себя.

Параллель видимость не сужает (решение владельца, 30.09.2026): Асем видит
и 8–10, но таблица поступления, сроки и счётчики поступления берут только
11 — это граница домена, а не видимости (`core/parallels.py`,
`admission_students`).

Одна функция на все вьюхи с данными учеников (фаза 60). До куратора правило
«ученик видит только себя» повторялось в каждом `get_queryset` своей строкой;
третья роль с границей видимости превратила бы это в два десятка мест,
где одно забытое условие и есть утечка. Чужой куратору ученик отсюда
не возвращается вовсе — дальше это 404, а не 403: по 403 видно, что
ученик существует.
"""

from __future__ import annotations

from django.db.models import QuerySet

from core.domains import ROLE_CURATOR, ROLE_STUDENT, ROLE_TEACHER

#: роли с границей видимости; у остальных (руководители) — вся школа
BOUNDED_ROLES = (ROLE_STUDENT, ROLE_CURATOR, ROLE_TEACHER)


def visible_students(user) -> QuerySet:
    """Ученики, которых человек вправе видеть."""
    from students.models import Student

    role = getattr(user, "role", "")
    if role == ROLE_STUDENT:
        student = getattr(user, "student", None)
        return Student.objects.filter(pk=student.pk) if student else Student.objects.none()
    if role == ROLE_CURATOR:
        from accounts.curators import curated_group_ids

        return Student.objects.filter(group_id__in=curated_group_ids(user))
    if role == ROLE_TEACHER:
        # учитель видит только учеников своих составов — тех, у кого он ведёт
        # журнал сегодня. Заметки, документы и поступление ему закрыты
        # шлюзом маршрутов, здесь только граница «свои ученики»
        from academics.teachers import taught_student_ids

        return Student.objects.filter(pk__in=taught_student_ids(user))
    return Student.objects.all()


def scope_to_user(qs: QuerySet, user, *, path: str = "student") -> QuerySet:
    """Сузить выборку до видимых человеку учеников.

    `path` — путь ORM от строки до ученика: пусто для самой модели `Student`,
    `student` для дочерних таблиц, `student__group` не нужен — группа
    берётся у ученика. Сотруднику без границы выборка возвращается как есть.
    """
    role = getattr(user, "role", "")
    if role not in BOUNDED_ROLES:
        return qs
    lookup = f"{path}__in" if path else "pk__in"
    return qs.filter(**{lookup: visible_students(user)})


def sees_student(user, student_id: int | None) -> bool:
    """Видит ли человек ученика с этим id. Пустой id — нет."""
    if student_id is None:
        return False
    return visible_students(user).filter(pk=student_id).exists()


def visible_ids(user, picked=None) -> list[int]:
    """Действующие ученики, о которых человеку можно спрашивать.

    `picked` — кого выбрали на экране: из выбора остаются только видимые,
    порядок выбора сохраняется. Без выбора — все видимые. Так кнопки
    помощника и операции получают одну границу с экранами, а не свою.
    """
    own = list(visible_students(user).filter(is_active=True).values_list("id", flat=True))
    if not picked:
        return own
    allowed = set(own)
    out: list[int] = []
    for pk in picked:
        try:
            number = int(pk)
        except (TypeError, ValueError):
            continue
        if number in allowed and number not in out:
            out.append(number)
    return out
