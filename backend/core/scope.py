"""Кого видит вошедший: ученик — себя, куратор — свои группы, сотрудник — всех.

Асем ведёт поступление, а оно есть только у 11: учеников 8–10 она не видит
нигде — ни в таблице, ни в карточке (404), ни в счётчиках (`core/parallels.py`).

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

#: директор, чей домен ведётся только у 11: 8–10 для него не существуют
ADMISSION_ONLY_ROLES = ("director_admission",)


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
    if role in ADMISSION_ONLY_ROLES:
        from core.parallels import admission_students

        return admission_students(Student.objects.all())
    return Student.objects.all()


def scope_to_user(qs: QuerySet, user, *, path: str = "student") -> QuerySet:
    """Сузить выборку до видимых человеку учеников.

    `path` — путь ORM от строки до ученика: пусто для самой модели `Student`,
    `student` для дочерних таблиц, `student__group` не нужен — группа
    берётся у ученика. Сотруднику без границы выборка возвращается как есть.
    """
    role = getattr(user, "role", "")
    if role not in (ROLE_STUDENT, ROLE_CURATOR, ROLE_TEACHER, *ADMISSION_ONLY_ROLES):
        return qs
    lookup = f"{path}__in" if path else "pk__in"
    return qs.filter(**{lookup: visible_students(user)})


def sees_student(user, student_id: int | None) -> bool:
    """Видит ли человек ученика с этим id. Пустой id — нет."""
    if student_id is None:
        return False
    return visible_students(user).filter(pk=student_id).exists()
