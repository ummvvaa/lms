"""Раздача паролей списком (фаза 69).

В день запуска администратор выдаёт пароли двум сотням человек. Делать
это по одной строке нельзя, а делать пачкой опасно: **у того, кто уже
придумал себе пароль, выдача его сбросит**, и человек, работавший
в системе, окажется на входе с письмом, которого не ждал. Если так
промахнуться по всей школе, школа встанет.

Отсюда устройство. Сначала считаем, кого действие затронет, с разбивкой
по состояниям (`accounts.states`); те, у кого пароль уже задан,
**по умолчанию исключены** — включить их можно только отдельным
осознанным действием. Потом человек подтверждает числом затронутых.
И только потом пароли выпускаются, а список уходит книгой XLSX.

Само действие остаётся в журнале навсегда: кто, скольким и когда. Это
единственный след — пароли открытым текстом на сервере не хранятся.

Писем раздача **не шлёт** (решение владельца, фаза 70): пароль приходит
человеку из рук в руки, а не письмом на почту, которой он ещё не умеет
пользоваться. Единственный носитель — файл, и он уходит тому, кто нажал
кнопку: лист «Сотрудники» и по листу на учебную группу, чтобы куратору
можно было отдать его лист целиком.
"""

from __future__ import annotations

from django.db.models import QuerySet

from accounts import states, temporary
from accounts.models import User


def plan(queryset: QuerySet[User], *, include_ready: bool = False) -> dict:
    """Кого затронет выдача и что человек увидит в модалке.

    Ничего не меняет. `include_ready` — та самая галочка «включить и тех,
    кто уже сменил пароль»: по умолчанию снята, и такие записи в список
    не попадают вовсе.
    """
    live = queryset.filter(is_active=True)
    breakdown = states.counts(live)

    targets = live
    if not include_ready:
        targets = states.annotate(live).exclude(states.condition(states.READY))

    total = targets.count()
    protected = breakdown[states.READY] if not include_ready else 0
    return {
        "total": total,
        "include_ready": include_ready,
        # разбивка — по всей выборке, а не по затронутым: человек должен
        # видеть и тех, кого действие обойдёт, и понимать почему
        "breakdown": [{"code": code, "title": states.TITLES[code], "count": breakdown[code]} for code in states.ORDER],
        "protected": protected,
        "warning": (
            "У этих людей пароль уже задан — выдача его сбросит, и прежний перестанет работать"
            if breakdown[states.READY]
            else ""
        ),
        # подтверждение осмысленным вводом: набрать число затронутых —
        # значит прочитать его. Одна кнопка здесь стоила бы школе дня работы
        "confirm": str(total),
    }


def targets(queryset: QuerySet[User], *, include_ready: bool = False) -> QuerySet[User]:
    """Кому выдаём: живые записи, по умолчанию без уже заданных паролей."""
    live = queryset.filter(is_active=True)
    if include_ready:
        return live
    return states.annotate(live).exclude(states.condition(states.READY))


def issue(queryset: QuerySet[User], *, actor, include_ready: bool = False) -> dict:
    """Выдать пароли и вернуть строки для выгрузки.

    Пароли открытым текстом возвращаются ровно один раз — тому, кто
    нажал кнопку. В базе остаются только хеши.
    """
    people = list(targets(queryset, include_ready=include_ready).select_related("student__group"))
    rows = []
    for user in people:
        # письма здесь нет намеренно (фаза 70): пароль раздают из рук
        # в руки по файлу, а письмо на почту, которой человек ещё
        # не пользуется, уходит в никуда
        password = temporary.issue(user)
        student = getattr(user, "student", None)
        rows.append(
            {
                "full_name": user.full_name or "",
                "email": user.email,
                "password": password,
                "group": student.group.code if student is not None and student.group_id else "",
                "expires_at": user.temp_password_expires_at,
            }
        )
    _record(len(rows), actor=actor, include_ready=include_ready)
    return {
        "issued": len(rows),
        "rows": rows,
        "detail": (
            f"Пароли выданы: {len(rows)}"
            + (", включая тех, кто уже менял пароль" if include_ready else "")
            + ". Письма не рассылались — скачайте список"
        ),
    }


def _record(count: int, *, actor, include_ready: bool) -> None:
    """След в журнале: кто, скольким, когда. Паролей в нём нет."""
    from core.models import AuditLog

    AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_role=getattr(actor, "role", "") or "",
        model_label="accounts.User",
        object_id="",
        field_name="passwords_handed_out",
        old_value="",
        new_value=(
            f"выдано временных паролей: {count}" + (", включая тех, у кого пароль был задан" if include_ready else "")
        ),
    )


#: Колонки выгрузки: то, что администратор понесёт в класс на бумаге.
#: Группы в колонках нет с фазы 70 — группа стала листом
EXPORT_COLUMNS = ("ФИО", "Почта", "Временный пароль", "Срок действия ссылки")

#: Лист для всех, кто не ученик: директора, кураторы, администраторы
STAFF_SHEET = "Сотрудники"


def sheets_of(rows: list[dict]) -> list[tuple[str, list[dict]]]:
    """Разложить выданные пароли по листам: сотрудники и учебные группы.

    Лист называется кодом группы, и его отдают куратору целиком —
    поэтому чужих строк в нём быть не должно. Лист без строк не
    создаётся вовсе: пустая вкладка только заставляет искать.
    """
    staff: list[dict] = []
    groups: dict[str, list[dict]] = {}
    for row in rows:
        code = str(row.get("group") or "").strip()
        if code:
            groups.setdefault(code, []).append(row)
        else:
            staff.append(row)

    pages: list[tuple[str, list[dict]]] = []
    if staff:
        pages.append((STAFF_SHEET, staff))
    pages.extend((code, groups[code]) for code in sorted(groups))
    return pages


def export(rows: list[dict]):
    """Список выданных паролей книгой XLSX: лист на группу (фаза 70)."""
    from core.exports import Column, workbook_of_sheets
    from core.phrasing import until

    columns = [
        Column("ФИО", lambda r: r.get("full_name", ""), width=30),
        Column("Почта", lambda r: r.get("email", ""), width=32),
        Column("Временный пароль", lambda r: r.get("password", ""), width=20),
        # срок — датой: человек, получивший распечатку, должен видеть,
        # до какого момента она годна, без пересчёта в уме
        Column("Срок действия ссылки", lambda r: until(r.get("expires_at")), width=22),
    ]
    return workbook_of_sheets(
        filename="parolyi-uchenikov.xlsx",
        sheets=[(title, columns, page) for title, page in sheets_of(rows)],
    )
