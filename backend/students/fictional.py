"""Вымышленные ученики: пометить, посчитать, вычистить (фаза 64).

До живых учеников база полна посевом прогона и пилотными карточками.
Отличаются они явным признаком `Student.is_fictional`, а не почтой:
почта `probe.local` — второй, независимый критерий, и он про учётные
записи прогона, а не про карточки. Пилотные записи на проде помечает
владелец командой `mark_fictional` по списку почт.

Чистка физическая — это единственное место, где ученик удаляется
насовсем, и потому она требует явного подтверждения, а на бою ещё
одного. Журнал остаётся: записи об удалённых помечаются, как при
обнулении (`reset_data`), чтобы интерфейс не вёл на пустые карточки.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from students.models import Student


def fictional() -> object:
    """Вымышленные ученики, включая архивных: чистить надо всех."""
    return Student.all_objects.filter(is_fictional=True)


def mark(*, emails: list[str] | None = None, domain: str = "") -> list[Student]:
    """Пометить учеников вымышленными по почтам или по домену почты."""
    rows = Student.all_objects.none()
    if emails:
        rows = rows | Student.all_objects.filter(email__in=[e.strip().lower() for e in emails if e.strip()])
    if domain:
        rows = rows | Student.all_objects.filter(email__iendswith=f"@{domain.lstrip('@')}")
    found = list(rows.distinct())
    Student.all_objects.filter(pk__in=[s.pk for s in found], is_fictional=False).update(is_fictional=True)
    return found


@dataclass
class Plan:
    """Что уйдёт при чистке — для сухого прогона и для отчёта."""

    students: int = 0
    accounts: int = 0
    probe_accounts: int = 0
    related: dict[str, int] = field(default_factory=dict)
    files: int = 0
    names: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [f"Учеников: {self.students}", f"Учётных записей учеников: {self.accounts}"]
        out += [f"{title}: {count}" for title, count in self.related.items() if count]
        out.append(f"Файлов документов: {self.files}")
        out.append(f"Одноразовых записей прогона: {self.probe_accounts}")
        return out


def plan() -> Plan:
    """Посчитать, что уйдёт. Ничего не меняет."""
    from accounts.probe import probe_users
    from roadmap.models import Essay, Task
    from students.models import CuratorNote, ExamAttempt, StudentDocument
    from suggestions.models import Suggestion
    from universities.models import StudentUniversity

    rows = fictional()
    ids = list(rows.values_list("pk", flat=True))
    return Plan(
        students=len(ids),
        accounts=rows.filter(user__isnull=False).count(),
        probe_accounts=probe_users().count(),
        related={
            "Попытки экзаменов": ExamAttempt.all_objects.filter(student_id__in=ids).count(),
            "Документы": StudentDocument.all_objects.filter(student_id__in=ids).count(),
            "Задачи": Task.all_objects.filter(student_id__in=ids).count(),
            "Эссе": Essay.all_objects.filter(student_id__in=ids).count(),
            "Заметки куратора": CuratorNote.all_objects.filter(student_id__in=ids).count(),
            "Вузы в списках": StudentUniversity.all_objects.filter(student_id__in=ids).count(),
            "Строки очереди": Suggestion.objects.filter(changes__student_id__in=ids).distinct().count(),
        },
        files=StudentDocument.all_objects.filter(student_id__in=ids).exclude(file="").count(),
        names=list(rows.order_by("last_name", "first_name").values_list("email", flat=True)[:50]),
    )


@transaction.atomic
def purge() -> Plan:
    """Удалить вымышленных учеников со всем, что на них ссылается, и probe-аккаунты."""
    from accounts import probe
    from accounts.models import User
    from core.management.commands.reset_data import STUDENT_LABELS, mark_audit_deleted
    from students.models import StudentDocument
    from suggestions.models import Suggestion

    outcome = plan()
    rows = fictional()
    ids = list(rows.values_list("pk", flat=True))
    user_ids = list(rows.filter(user__isnull=False).values_list("user_id", flat=True))

    # файлы с диска — руками: Django при удалении строки файл не трогает
    for document in StudentDocument.all_objects.filter(student_id__in=ids).exclude(file=""):
        document.file.delete(save=False)

    # строки очереди про этих учеников — целиком: пакет без ученика
    # применить не к кому
    Suggestion.objects.filter(changes__student_id__in=ids).distinct().delete()
    Student.all_objects.filter(pk__in=ids).delete()
    User.objects.filter(pk__in=user_ids).delete()
    mark_audit_deleted(STUDENT_LABELS)

    probe.purge_all()
    return outcome
