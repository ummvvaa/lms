"""Одноразовые учётные записи для браузерного прогона.

Девять ролей, один домен почты `probe.local`, один пароль из окружения.
Живут ровно столько, сколько идёт прогон: заводятся перед ним, после него
удаляются насовсем — вместе с сессиями, попытками входа и ссылками.
Это единственные учётные записи, которые система удаляет физически:
у настоящих на записи висит журнал правок и без автора он слепнет,
а здесь автор остаётся снимком (`AuditLog.actor_title`) — строка журнала
читается как раньше, только вести ей уже некуда.

Отличать их система умеет сама — по домену почты. Отдельное поле в модели
не нужно: `.local` — зарезервированный домен, настоящий человек с такой
почтой не заведётся, а всё, что прогон создал под этим доменом (ученики
списком, приглашённые), уходит той же уборкой.
"""

# i18n-skip-file: одноразовые записи прогона — имена и подпись в журнале хранятся как данные

from __future__ import annotations

from django.db import transaction

#: Домен одноразовых записей. Всё с такой почтой — прогон, и только он.
PROBE_DOMAIN = "probe.local"

#: Переменная окружения с паролем. Один на все девять: записи живут минуты,
#: а восемь переменных — восемь мест, которые надо заполнить ради одного прогона.
PASSWORD_VAR = "PROBE_PASSWORD"

#: Почта → роль → имя. Роли записаны значениями `accounts.models.Role`.
#: Фамилия «Прогон» видна в шапке и в журнале: спутать с настоящим
#: человеком такую запись нельзя даже глазами.
ACCOUNTS: tuple[tuple[str, str, str], ...] = (
    (f"student@{PROBE_DOMAIN}", "student", "Айгерим Прогон"),
    (f"behavior@{PROBE_DOMAIN}", "director_behavior", "Салтанат Прогон"),
    (f"admission@{PROBE_DOMAIN}", "director_admission", "Асем Прогон"),
    (f"exam@{PROBE_DOMAIN}", "director_exam", "Кымбат Прогон"),
    (f"talent@{PROBE_DOMAIN}", "director_talent", "Арман Прогон"),
    (f"sport@{PROBE_DOMAIN}", "director_sport", "Нурлыбек Прогон"),
    # куратор (фаза 60): группы ему назначает посев прогона через API
    (f"curator@{PROBE_DOMAIN}", "curator", "Асель Прогон"),
    # учитель: уроки ему заводит посев прогона расписанием
    (f"teacher@{PROBE_DOMAIN}", "teacher", "Айжан Прогон"),
    (f"admin@{PROBE_DOMAIN}", "admin", "Администратор Прогона"),
)


#: Логин одноразовой записи без почты — ученик 8–10 прогона. Подчёркивания
#: в логине, собранном из ФИО (`accounts.logins`), не бывает никогда:
#: настоящий человек под этот признак не попадёт, как и под `.local`
PROBE_LOGIN_PREFIX = "probe_"

#: Записи прогона без почты: логин → роль → имя
LOGIN_ACCOUNTS: tuple[tuple[str, str, str], ...] = ((f"{PROBE_LOGIN_PREFIX}junior", "student", "Ерлан Прогон"),)


def is_probe_email(email: str | None) -> bool:
    """Одноразовая ли это почта. Регистр не важен."""
    return bool(email) and email.strip().lower().endswith(f"@{PROBE_DOMAIN}")


def is_probe_login(login: str | None) -> bool:
    """Одноразовый ли это логин записи без почты."""
    return bool(login) and login.strip().lower().startswith(PROBE_LOGIN_PREFIX)


def probe_users():
    """Все записи прогона — и штатные, и заведённые им по ходу, с почтой и без."""
    from django.db.models import Q

    from accounts.models import User

    return User.objects.filter(Q(email__iendswith=f"@{PROBE_DOMAIN}") | Q(login__istartswith=PROBE_LOGIN_PREFIX))


@transaction.atomic
def create_all(password: str) -> list:
    """Завести восемь записей с общим паролем. Повторный вызов обновляет.

    Пароль ставится через общие правила школы: слишком короткий или
    распространённый отвергается так же, как у настоящего человека.
    """
    from accounts.models import Identity, IdentityProvider, Role, User
    from accounts.passwords import set_password
    from students.linking import link_user

    made: list[User] = []
    for email, role, full_name in ACCOUNTS:
        user, _ = User.objects.get_or_create(email=email, defaults={"role": role, "full_name": full_name})
        user.role = role
        user.full_name = full_name
        user.is_active = True
        # у директора школы флаг «видит всю школу» — как у настоящей Салтанат
        user.sees_whole_school = role == Role.DIRECTOR_BEHAVIOR
        user.is_staff = role == Role.ADMIN
        user.is_superuser = role == Role.ADMIN
        user.save()
        set_password(user, password)
        Identity.objects.get_or_create(
            provider=IdentityProvider.PASSWORD, email=email, defaults={"user": user, "is_primary": True}
        )
        # карточку ученика прогон мог завести раньше записи — связываем по почте
        link_user(user)
        made.append(user)
    # ученик 8–10 без почты: вход по логину, карточку ему заводит посев прогона
    for login, role, full_name in LOGIN_ACCOUNTS:
        user, _ = User.objects.get_or_create(login=login, defaults={"role": role, "full_name": full_name})
        user.role = role
        user.full_name = full_name
        user.is_active = True
        user.save()
        set_password(user, password)
        made.append(user)
    return made


@transaction.atomic
def purge_all() -> dict[str, int]:
    """Удалить все записи прогона насовсем. Журнал остаётся с подписью.

    Порядок важен: сначала снимок автора в журнал, потом сессии, потом
    сами записи — каскад заберёт идентичности и уведомления, остальные
    ссылки обнулятся (`SET_NULL`).
    """
    from django.contrib.sessions.models import Session
    from django.db.models import Q

    from accounts.models import LoginAttempt, MagicLinkToken
    from core.models import AuditLog

    users = list(probe_users())
    ids = {user.pk for user in users}

    signed = 0
    for user in users:
        title = f"{user.full_name or user.handle} · одноразовая запись прогона"
        signed += AuditLog.objects.filter(actor_id=user.pk, actor_title="").update(actor_title=title[:250])

    sessions = 0
    if ids:
        for session in Session.objects.all():
            try:
                owner = session.get_decoded().get("_auth_user_id")
            except Exception:  # битую сессию считаем ничьей
                owner = None
            if owner is not None and int(owner) in ids:
                session.delete()
                sessions += 1

    attempts = LoginAttempt.objects.filter(
        Q(email__iendswith=f"@{PROBE_DOMAIN}") | Q(email__istartswith=PROBE_LOGIN_PREFIX)
    ).delete()[0]
    links = MagicLinkToken.objects.filter(Q(email__iendswith=f"@{PROBE_DOMAIN}") | Q(user__in=users)).delete()[0]
    lessons = _drop_lessons_of(ids)
    removed = len(users)
    for user in users:
        user.delete()

    return {
        "users": removed,
        "sessions": sessions,
        "attempts": attempts,
        "links": links,
        "signed": signed,
        "lessons": lessons,
    }


def _drop_lessons_of(user_ids: set[int]) -> int:
    """Убрать журналы и уроки, где учитель — запись прогона.

    Учитель урока и журнала защищён от каскада (`PROTECT`): настоящего учителя
    с уроками удалить нельзя. Но уроки учителю прогона заводит только посев
    учебной части (`seed_probe_academics`), и вместе с записью прогона они
    уходят целиком — с отметками, оценками и причинами, которые висят на них.
    """
    if not user_ids:
        return 0
    from academics.models import Course, Lesson

    gone = Lesson.all_objects.filter(teacher_id__in=user_ids).delete()[0]
    Course.all_objects.filter(teacher_id__in=user_ids).delete()
    return gone
