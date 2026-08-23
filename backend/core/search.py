"""Поиск по системе: ученики, вузы и программы в одном ответе.

Находит только то, что роли положено видеть: ученик ищет по справочнику
вузов и не находит ни одноклассников, ни их данных (инвариант №7).
Архивные записи не находятся — их вообще нет в интерфейсе (инвариант №13).

Результаты сгруппированы по типу: список вперемешку из людей и вузов
читать невозможно.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q

from core.domains import ROLE_STUDENT

#: Сколько строк отдаём в одной группе. Больше в выпадающий список
#: всё равно не помещается, а искать надо точнее.
GROUP_LIMIT = 8

#: Короче двух букв запрос ищет всю школу и не помогает никому.
MIN_QUERY = 2


@dataclass(frozen=True)
class Hit:
    """Одна найденная запись."""

    id: int
    title: str
    note: str
    path: str

    def as_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "note": self.note, "path": self.path}


def _students(query: str) -> list[Hit]:
    from students.models import Student

    rows = Student.objects.filter(
        Q(last_name__icontains=query)
        | Q(first_name__icontains=query)
        | Q(middle_name__icontains=query)
        | Q(email__icontains=query)
    ).select_related("group")[:GROUP_LIMIT]
    return [
        Hit(
            id=row.pk,
            title=row.full_name,
            note=f"{row.grade} класс" + (f" · группа {row.group.code}" if row.group_id else "") + f" · {row.email}",
            path=f"/students/{row.pk}",
        )
        for row in rows
    ]


def _universities(query: str, *, for_student: bool) -> list[Hit]:
    from universities.models import University

    rows = University.objects.filter(Q(name__icontains=query) | Q(country__icontains=query), is_active=True).order_by(
        "name"
    )[:GROUP_LIMIT]
    return [
        Hit(
            id=row.pk,
            title=row.name,
            note=row.country + ("" if row.is_verified else " · данные не подтверждены"),
            # ученику некуда идти в справочник: его вузы живут в каталоге
            path=f"/catalog?search={row.name}" if for_student else "/directory",
        )
        for row in rows
    ]


def _programs(query: str, *, for_student: bool) -> list[Hit]:
    from universities.models import Program

    rows = (
        Program.objects.filter(name__icontains=query, is_active=True, university__is_active=True)
        .select_related("university")
        .order_by("university__name", "name")[:GROUP_LIMIT]
    )
    return [
        Hit(
            id=row.pk,
            title=f"{row.university.name} — {row.name}",
            note=row.university.country + ("" if row.is_verified else " · данные не подтверждены"),
            path=f"/catalog?search={row.name}" if for_student else "/directory",
        )
        for row in rows
    ]


def search(query: str, *, role: str) -> dict:
    """Найти всё, что этой роли положено видеть."""
    query = (query or "").strip()
    if len(query) < MIN_QUERY:
        return {
            "query": query,
            "total": 0,
            "groups": [],
            "detail": f"Наберите хотя бы {MIN_QUERY} буквы",
        }

    is_student = role == ROLE_STUDENT
    groups = []

    if not is_student:
        # ученик не ищет одноклассников: чужой профиль ему закрыт целиком
        rows = _students(query)
        if rows:
            groups.append({"code": "students", "title": "Ученики", "rows": [r.as_dict() for r in rows]})

    universities = _universities(query, for_student=is_student)
    if universities:
        groups.append({"code": "universities", "title": "Вузы", "rows": [r.as_dict() for r in universities]})

    programs = _programs(query, for_student=is_student)
    if programs:
        groups.append({"code": "programs", "title": "Программы", "rows": [r.as_dict() for r in programs]})

    total = sum(len(g["rows"]) for g in groups)
    return {
        "query": query,
        "total": total,
        "groups": groups,
        "detail": "" if total else "Ничего не нашлось",
    }
