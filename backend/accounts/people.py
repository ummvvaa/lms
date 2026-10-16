"""Один человек на «Пользователях»: заведение и правка по роли.

Точка правды о человеке одна — экран «Пользователи» (решение владельца,
11.10.2026). Роль выбирается первой, и под неё заводится всё сразу одной
транзакцией: ученику — карточка `Student` с профилями и группой тем же кодом,
что «Завести учеников списком» (`students.enrollment.enroll_one`); учителю —
профиль с предметами; куратору — назначения групп с сегодняшней даты.

Правила, которые здесь держатся:

* ФИО ученика живёт в `Student` раздельно (фамилия, имя, отчество), а
  `User.full_name` — производное и переписывается при каждой правке; у
  сотрудников ФИО — в `User`;
* школьная почта ученика пишется в `User.email` и `Student.email` одним
  сервисом — связь карточки с учётной записью держится на ней;
* год выпуска считается от параллели группы и руками не вводится;
* без почты учётная запись получает логин «имя.фамилия»
  (`accounts.logins.make_login`); сотруднику логин можно задать и руками;
* логин следует за ФИО (решение владельца, 16.10.2026): сменились имя или
  фамилия у учётки без почты — логин пересчитывается тем же правилом и
  сохраняется вместе с ФИО, прежний больше не действует; пароль не меняется;
* личная почта, внесённая администратором, остаётся неподтверждённой, пока
  человек не откроет ссылку из письма, — иначе чужой адрес с опечаткой стал
  бы дверью в учётную запись;
* смена роли меняет только роль: данные прежней роли остаются, назначения
  куратора закрываются сегодняшним днём; ученика в сотрудника и обратно
  не переводят — это разные записи.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from accounts import magic_link, temporary
from accounts.curators import AssignmentRefused, active_assignments, assign
from accounts.logins import LOGIN_RE, fits, make_login, normalize
from accounts.models import IdentityProvider, LinkPurpose, Role, User
from accounts.naming import NameRejected, check_full_name
from accounts.services import create_user, link_email_identity
from core.audit import ValueRejected, apply_changes
from core.domains import ROLE_TITLES, domain_of_role
from core.parallels import graduation_year_for
from students.models import Student, StudyGroup

#: роли сотрудников — все, кроме ученика
STAFF_ROLES: tuple[str, ...] = tuple(role for role in Role.values if role != Role.STUDENT)


class PersonError(ValueError):
    """Завести или изменить нельзя — текст объясняет, что исправить."""


# --- Чтение ------------------------------------------------------------------


def detail(user: User) -> dict[str, Any]:
    """Всё о человеке для окна правки: общие поля и поля его роли."""
    from academics.models import TeacherProfile
    from academics.teachers import teaches, weekly_hours
    from students.phones import normalize_kz

    identity = user.identities.filter(provider=IdentityProvider.EMAIL_LINK).order_by("-confirmed_at", "-pk").first()
    payload: dict[str, Any] = {
        "phone": user.phone,
        "personal_email": identity.email if identity else "",
        "personal_email_confirmed": bool(identity and identity.confirmed_at),
        "role_change_note": role_change_note(user),
        "student": None,
        "teacher": None,
        "curator": None,
        "domain_title": "",
    }
    if user.role == Role.STUDENT:
        student = getattr(user, "student", None)
        if student is not None:
            payload["phone"] = normalize_kz(student.phone)
            payload["student"] = {
                "id": student.pk,
                "last_name": student.last_name,
                "first_name": student.first_name,
                "middle_name": student.middle_name,
                "email": student.email or "",
                "group": student.group_id,
                "group_code": student.group.code if student.group_id else "",
                "parallel": student.group.parallel if student.group_id else None,
                "graduation_year": student.graduation_year,
            }
        return payload
    if user.role == Role.TEACHER:
        profile = TeacherProfile.objects.filter(user=user).first()
        payload["teacher"] = {
            "subjects": list(profile.subjects.values_list("pk", flat=True)) if profile else [],
            "room": profile.room if profile else "",
            "teaches": teaches(user),
            "weekly_hours": weekly_hours(user),
        }
    elif user.role == Role.CURATOR:
        payload["curator"] = {
            "groups": [
                {"id": row.group_id, "code": row.group.code, "since": row.since}
                for row in active_assignments().filter(curator=user).select_related("group").order_by("group__code")
            ]
        }
    else:
        domain = domain_of_role(user.role)
        payload["domain_title"] = str(domain.title) if domain is not None else ""
    return payload


def role_change_note(user: User) -> str:
    """Что останется и что скроется, если этой учётной записи сменить роль."""
    if user.role == Role.STUDENT:
        return _("Ученика в сотрудника не переводят: карточка, оценки и портфолио — это другая запись")
    if user.role == Role.TEACHER:
        return _(
            "Профиль с предметами, журналы и уроки в расписании останутся; «Сегодня» и «Журналы» "
            "будут видны, пока у человека есть уроки"
        )
    if user.role == Role.CURATOR:
        count = active_assignments().filter(curator=user).count()
        return _(
            "Назначения групп ({count}) закроются сегодняшним днём, заметки и история подтверждений "
            "останутся в журнале"
        ).format(count=count)
    if user.role == Role.ADMIN:
        return _("Пользователи, настройки школы, импорт и архив закроются; записи в журнале останутся")
    domain = domain_of_role(user.role)
    return _("Домен «{domain}» станет чужим — его поля будут видны, но не правятся; записи в журнале останутся").format(
        domain=domain.title if domain is not None else ROLE_TITLES.get(user.role, user.role)
    )


# --- Заведение -----------------------------------------------------------------


def _name_parts(data: dict[str, Any]) -> tuple[str, str, str]:
    """Фамилия, имя, отчество из раздельных полей или из одной строки."""
    last = (data.get("last_name") or "").strip()
    first = (data.get("first_name") or "").strip()
    middle = (data.get("middle_name") or "").strip()
    if not last and not first and data.get("full_name"):
        parts = (data["full_name"] or "").split()
        last = parts[0] if parts else ""
        first = parts[1] if len(parts) > 1 else ""
        middle = " ".join(parts[2:])
    for value in (last, first, middle):
        try:
            check_full_name(value)
        except NameRejected as error:
            raise PersonError(str(error)) from error
    return last, first, middle


def _group(data: dict[str, Any], *, required: bool) -> StudyGroup | None:
    pk = data.get("group")
    if pk in (None, ""):
        if required:
            raise PersonError(_("Выберите учебную группу — без неё у ученика нет параллели и разделов"))
        return None
    group = StudyGroup.objects.filter(pk=pk).first()
    if group is None:
        raise PersonError(_("Такой учебной группы нет — заведите её на вкладке «Учебные группы»"))
    return group


def _phone(data: dict[str, Any]) -> str:
    from students.phones import normalize_kz

    return normalize_kz(data.get("phone") or "")[:20]


def _free_email(email: str, *, user: User | None = None, student: Student | None = None) -> None:
    users = User.objects.filter(email__iexact=email)
    students = Student.all_objects.filter(email__iexact=email)
    if user is not None:
        users = users.exclude(pk=user.pk)
    if student is not None:
        students = students.exclude(pk=student.pk)
    if users.exists() or students.exists():
        raise PersonError(_("Почта {email} уже занята другой учётной записью").format(email=email))


def _handle(data: dict[str, Any], *, user: User | None = None) -> tuple[str | None, str | None]:
    """«Почта или логин» сотрудника: с «@» — почта, иначе логин; пусто — логин выдастся сам."""
    raw = normalize(data.get("handle") or data.get("email") or "")
    if not raw:
        return None, None
    if "@" in raw:
        _free_email(raw, user=user)
        return raw, None
    if not LOGIN_RE.match(raw):
        raise PersonError(_("Логин — строчная латиница, цифры, точка и дефис: например, aliya.akhmetova"))
    taken = User.objects.filter(login__iexact=raw)
    if user is not None:
        taken = taken.exclude(pk=user.pk)
    if taken.exists():
        raise PersonError(_("Логин «{login}» уже занят").format(login=raw))
    return None, raw


@transaction.atomic
def create(data: dict[str, Any], *, actor=None, send_mail: bool = True) -> dict[str, Any]:
    """Завести человека по роли. Возвращает учётную запись и доступ (пароль или ссылку)."""
    role = data.get("role") or Role.STUDENT
    if role == Role.STUDENT:
        return _create_student(data, actor=actor, send_mail=send_mail)
    return _create_staff(data, role=role, actor=actor, send_mail=send_mail)


def _create_student(data: dict[str, Any], *, actor, send_mail: bool) -> dict[str, Any]:
    from students.enrollment import enroll_one

    if "group" not in data and not any(data.get(key) for key in ("last_name", "first_name")):
        # прежний вызов по одной почте (прогон, `api_probe`, массовое приглашение):
        # учётная запись без карточки, карточка привяжется по почте, доступ — ссылкой.
        # Окно «Пользователей» всегда шлёт группу и раздельное ФИО
        email = normalize(data.get("email") or data.get("handle") or "")
        if not email or "@" not in email:
            raise PersonError(_("Нужны фамилия, имя и группа ученика"))
        _free_email(email)
        user = create_user(email=email, full_name=(data.get("full_name") or "").strip(), role=Role.STUDENT)
        token, sent_to = magic_link.issue_for(user, purpose=LinkPurpose.INVITE, send=send_mail, actor=actor)
        return {"user": user, "invite_token": token, "invite_sent_to": sent_to}

    last, first, middle = _name_parts(data)
    if not last or not first:
        raise PersonError(_("Нужны фамилия и имя — без них ученика не найти в списке"))
    group = _group(data, required=True)
    email = normalize(data.get("email") or "") or None
    if email:
        if "@" not in email:
            raise PersonError(_("Почта «{email}» не похожа на адрес").format(email=email))
        _free_email(email)
    elif Student.all_objects.filter(group=group, last_name__iexact=last, first_name__iexact=first).exists():
        raise PersonError(_("Такой ученик в группе {group} уже заведён").format(group=group.code))

    made = enroll_one(
        last_name=last,
        first_name=first,
        middle_name=middle,
        email=email,
        group=group,
        phone=_phone(data),
        actor=actor,
        send_mail=send_mail,
    )
    user = User.objects.get(pk=made["user"])
    _personal_email(user, data)
    return {
        "user": user,
        "password": {
            "email": user.email,
            "login": user.handle,
            "full_name": user.full_name,
            "password": made["password"],
            "hours": temporary.ttl_hours(),
            "sent": made["sent"],
            "detail": _password_detail(user, sent=made["sent"]),
        },
    }


def _create_staff(data: dict[str, Any], *, role: str, actor, send_mail: bool) -> dict[str, Any]:
    # имя может быть пустым: массовое приглашение заводит запись по одной почте,
    # и человек допишет имя себе сам; окно «Пользователей» требует ФИО само
    full_name = " ".join(part for part in _name_parts(data) if part) or (data.get("full_name") or "").strip()
    email, login = _handle(data)
    if not email and not login and not full_name:
        raise PersonError(_("Нужны фамилия и имя — из них выдаётся логин"))
    phone = _phone(data)
    if email:
        user = create_user(
            email=email, full_name=full_name, role=role, sees_whole_school=bool(data.get("sees_whole_school"))
        )
        if phone:
            user.phone = phone
            user.save(update_fields=["phone"])
    else:
        if not login:
            last, first, _middle = _name_parts(data)
            login = make_login(first, last)
        user = User.objects.create_user(
            email=None,
            login=login,
            password=None,
            full_name=full_name,
            phone=phone,
            role=role,
            sees_whole_school=bool(data.get("sees_whole_school")),
        )
    _personal_email(user, data)
    _role_fields(user, data, actor=actor, fresh=True)

    if email:
        token, sent_to = magic_link.issue_for(user, purpose=LinkPurpose.INVITE, send=send_mail, actor=actor)
        return {"user": user, "invite_token": token, "invite_sent_to": sent_to}
    password = temporary.issue(user)
    return {
        "user": user,
        "password": {
            "email": None,
            "login": user.handle,
            "full_name": user.full_name,
            "password": password,
            "hours": temporary.ttl_hours(),
            "sent": False,
            "detail": _password_detail(user, sent=False),
        },
    }


def _password_detail(user: User, *, sent: bool) -> str:
    if sent:
        return _("Временный пароль для {login} выпущен и отправлен письмом").format(login=user.handle)
    return _("Временный пароль для {login} выпущен. Письма не было — передайте пароль лично").format(login=user.handle)


def _personal_email(user: User, data: dict[str, Any]) -> None:
    """Личная почта от администратора — неподтверждённая, письмо с подтверждением уходит человеку."""
    if "personal_email" not in data:
        return
    email = normalize(data.get("personal_email") or "")
    current = user.identities.filter(provider=IdentityProvider.EMAIL_LINK).order_by("-confirmed_at", "-pk").first()
    if not email:
        # снять можно только неподтверждённый адрес: подтверждённый — вход человека
        if current is not None and current.confirmed_at is None:
            current.delete()
        return
    if current is not None and current.email.lower() == email:
        return
    if "@" not in email:
        raise PersonError(_("Личная почта «{email}» не похожа на адрес").format(email=email))
    try:
        link_email_identity(user, email)
    except ValueError as error:
        raise PersonError(str(error)) from error
    if current is not None and current.email.lower() != email and current.confirmed_at is None:
        current.delete()


def _role_fields(user: User, data: dict[str, Any], *, actor, fresh: bool = False) -> None:
    """Поля роли сотрудника: предметы и кабинет учителя, группы куратора."""
    if user.role == Role.TEACHER:
        from academics.models import Subject, TeacherProfile

        if "subjects" in data or "room" in data or fresh:
            profile, _created = TeacherProfile.objects.get_or_create(user=user)
            if "room" in data:
                profile.room = str(data.get("room") or "")[:40]
                profile.save(update_fields=["room"])
            if "subjects" in data:
                ids = [int(pk) for pk in (data.get("subjects") or [])]
                profile.subjects.set(Subject.objects.filter(pk__in=ids))
    elif user.role == Role.CURATOR and "groups" in data:
        wanted = {int(pk) for pk in (data.get("groups") or [])}
        today = timezone.localdate()
        current = {row.group_id: row for row in active_assignments().filter(curator=user)}
        for group_id, row in current.items():
            if group_id not in wanted:
                _close_assignment(row, today)
        for group_id in wanted - set(current):
            group = StudyGroup.objects.filter(pk=group_id).first()
            if group is None:
                raise PersonError(_("Такой учебной группы нет — заведите её на вкладке «Учебные группы»"))
            try:
                assign(group=group, curator=user, since=today, actor=actor)
            except AssignmentRefused as error:
                raise PersonError(str(error)) from error


# --- Правка --------------------------------------------------------------------


@transaction.atomic
def update(user: User, data: dict[str, Any], *, actor=None) -> dict[str, Any]:
    """Изменить человека: общие поля, поля роли, роль. Возвращает, что сменился вход."""
    was_email = user.email
    if "role" in data and data["role"] != user.role:
        change_role(user, data["role"], actor=actor)

    if user.role == Role.STUDENT:
        moved = _update_student(user, data, actor=actor)
    else:
        moved = _update_staff(user, data, actor=actor)
    _personal_email(user, data)
    _role_fields(user, data, actor=actor)

    flags = {key: data[key] for key in ("sees_whole_school", "is_active") if key in data}
    if flags:
        _apply(user, flags, actor=actor)
    user.refresh_from_db()
    return {"login_changed": bool(was_email) and user.email != was_email, "was_email": was_email, "login_moved": moved}


def _apply(instance, changes: dict[str, Any], *, actor) -> None:
    try:
        apply_changes(instance, changes, actor=actor)
    except ValueRejected as error:
        raise PersonError(str(error)) from error


def _update_student(user: User, data: dict[str, Any], *, actor) -> dict[str, str] | None:
    student = getattr(user, "student", None)
    if student is None:
        # учётная запись без карточки: править можно только имя учётной записи
        changes = {}
        if "full_name" in data:
            try:
                changes["full_name"] = check_full_name(data["full_name"])
            except NameRejected as error:
                raise PersonError(str(error)) from error
        if changes:
            _apply(user, changes, actor=actor)
        return None
    named = (student.last_name, student.first_name)
    changes: dict[str, Any] = {}
    if any(key in data for key in ("last_name", "first_name", "middle_name", "full_name")):
        last, first, middle = _name_parts({**data, "full_name": data.get("full_name")})
        if "last_name" in data or data.get("full_name"):
            changes["last_name"] = last
        if "first_name" in data or data.get("full_name"):
            changes["first_name"] = first
        if "middle_name" in data or data.get("full_name"):
            changes["middle_name"] = middle
        if not (changes.get("last_name", student.last_name) and changes.get("first_name", student.first_name)):
            raise PersonError(_("Нужны фамилия и имя — без них ученика не найти в списке"))
    if "group" in data:
        group = _group(data, required=True)
        changes["group"] = group
        changes["graduation_year"] = graduation_year_for(group.parallel)
    if "email" in data:
        email = normalize(data.get("email") or "") or None
        if email:
            if "@" not in email:
                raise PersonError(_("Почта «{email}» не похожа на адрес").format(email=email))
            _free_email(email, user=user, student=student)
        changes["email"] = email
    if "phone" in data:
        changes["phone"] = _phone(data)
    if changes:
        _apply(student, changes, actor=actor)
        student.refresh_from_db()
    return sync_account(student, actor=actor, renamed=named != (student.last_name, student.first_name))


def _update_staff(user: User, data: dict[str, Any], *, actor) -> dict[str, str] | None:
    changes: dict[str, Any] = {}
    named: tuple[str, str] | None = None
    if "full_name" in data or "last_name" in data or "first_name" in data:
        last, first, middle = _name_parts(data)
        full_name = " ".join(part for part in (last, first, middle) if part) or (data.get("full_name") or "").strip()
        if not full_name:
            raise PersonError(_("Нужны фамилия и имя"))
        # прежнее ФИО — как записано, без проверки слов: её проходило новое
        was = (user.full_name or "").split()
        if (was[0] if was else "", was[1] if len(was) > 1 else "") != (last, first):
            named = (last, first)
        changes["full_name"] = full_name
    typed = False
    if "handle" in data or "email" in data:
        email, login = _handle(data, user=user)
        if email:
            changes["email"] = email
        elif login:
            # логин, вписанный руками в этом же сохранении, сильнее пересчёта
            typed = login != (user.login or "").lower()
            changes["login"] = login
        elif not user.login:
            raise PersonError(_("Нужна почта или логин — без них человеку нечем войти"))
    if "phone" in data:
        changes["phone"] = _phone(data)
    if changes:
        _apply(user, changes, actor=actor)
    if named is None or typed:
        return None
    return follow_name(user, first=named[1], last=named[0], actor=actor)


def follow_name(user: User, *, first: str, last: str, actor=None) -> dict[str, str] | None:
    """Логин следует за ФИО: пересчитать по имени и фамилии, если он из них не собран.

    Только у учётки без почты: кто входит по почте, тому логин не нужен.
    Запись прогона (`probe_…`) не трогается — по приставке её находит уборка.
    Смена пишется в журнал учётки обычной правкой поля: было → стало, кто.
    """
    if user.email or not user.login or user.is_probe or fits(user.login, first, last):
        return None
    was = user.login
    _apply(user, {"login": make_login(first, last, exclude=user.pk)}, actor=actor)
    return {"was": was, "now": user.login}


def sync_account(student: Student, *, actor=None, renamed: bool = False) -> dict[str, str] | None:
    """`User.full_name` и `User.email` ученика — производные от карточки, одно место записи.

    `renamed` — в этой правке сменились имя или фамилия: логин идёт за ними
    (`follow_name`). Возвращает смену логина, если она была.
    """
    user = student.user
    if user is None:
        return None
    changes: dict[str, Any] = {"full_name": student.full_name}
    if student.email and (user.email or "").lower() != student.email.lower():
        _free_email(student.email, user=user, student=student)
        changes["email"] = student.email
    _apply(user, changes, actor=actor)
    if not renamed:
        return None
    return follow_name(user, first=student.first_name, last=student.last_name, actor=actor)


def change_role(user: User, role: str, *, actor=None) -> None:
    """Сменить роль сотрудника: данные прежней роли остаются, назначения куратора закрываются."""
    if role not in Role.values:
        raise PersonError(_("Такой роли нет"))
    if Role.STUDENT in (user.role, role):
        raise PersonError(_("Ученика в сотрудника и сотрудника в ученика не переводят: заведите отдельную запись"))
    if user.role == Role.CURATOR:
        today = timezone.localdate()
        for row in active_assignments().filter(curator=user):
            _close_assignment(row, today)
    _apply(user, {"role": role}, actor=actor)


def _close_assignment(row, today) -> None:
    """Закрыть назначение сегодняшним днём; назначенное сегодня же — не действовало, строка уходит."""
    if row.since >= today:
        row.delete()
        return
    row.until = today
    row.save(update_fields=["until"])
