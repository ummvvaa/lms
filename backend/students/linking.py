"""Связывание карточки ученика с учётной записью по почте.

Администратор заводит две разные вещи: запись о человеке в реестре школы
и учётную запись, которой он входит. Связывать их руками — лишний шаг,
о котором никто не догадается: в интерфейсе такого поля просто нет,
и ученик молча попадает в пустой кабинет.

Ключ — почта. `Student.email` и `User.email` уникальны оба, и входит
ученик той же почтой, которая записана в его карточке.
"""

from __future__ import annotations

from accounts.models import Role, User
from students.models import Student


def link_student(student: Student) -> User | None:
    """Привязать к карточке учётную запись с той же почтой, если она есть."""
    if student.user_id or not student.email:
        return student.user

    user = User.objects.filter(email__iexact=student.email, role=Role.STUDENT).first()
    if user is None or getattr(user, "student", None) is not None:
        return None

    student.user = user
    student.save(update_fields=["user", "updated_at"])
    return user


def link_user(user: User) -> Student | None:
    """Привязать к учётной записи карточку с той же почтой, если она есть.

    Обратная сторона той же связи: карточку могли завести раньше учётной
    записи, а могли и позже — порядок не должен ничего решать.
    """
    if user.role != Role.STUDENT or getattr(user, "student", None) is not None:
        return None

    student = Student.objects.filter(email__iexact=user.email, user__isnull=True).first()
    if student is None:
        return None

    student.user = user
    student.save(update_fields=["user", "updated_at"])
    return student
