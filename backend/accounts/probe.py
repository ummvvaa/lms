"""Одноразовые учётные записи для браузерного прогона.

Семь ролей, один домен почты `probe.local`, один пароль из окружения.
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

from __future__ import annotations

from django.db import transaction

#: Домен одноразовых записей. Всё с такой почтой — прогон, и только он.
PROBE_DOMAIN = "probe.local"

#: Переменная окружения с паролем. Один на все семь: записи живут минуты,
#: а семь переменных — семь мест, которые надо заполнить ради одного прогона.
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
    (f"admin@{PROBE_DOMAIN}", "admin", "Администратор Прогона"),
)


def is_probe_email(email: str | None) -> bool:
    """Одноразовая ли это почта. Регистр не важен."""
    return bool(email) and email.strip().lower().endswith(f"@{PROBE_DOMAIN}")


def probe_users():
    """Все записи прогона — и семь штатных, и заведённые им по ходу."""
    from accounts.models import User

    return User.objects.filter(email__iendswith=f"@{PROBE_DOMAIN}")


@transaction.atomic
def create_all(password: str) -> list:
    """Завести семь записей с общим паролем. Повторный вызов обновляет.

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
    return made


@transaction.atomic
def purge_all() -> dict[str, int]:
    """Удалить все записи прогона насовсем. Журнал остаётся с подписью.

    Порядок важен: сначала снимок автора в журнал, потом сессии, потом
    сами записи — каскад заберёт идентичности и уведомления, остальные
    ссылки обнулятся (`SET_NULL`).
    """
    from django.contrib.sessions.models import Session

    from accounts.models import LoginAttempt, MagicLinkToken
    from core.models import AuditLog

    users = list(probe_users())
    ids = {user.pk for user in users}

    signed = 0
    for user in users:
        title = f"{user.full_name or user.email} · одноразовая запись прогона"
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

    attempts = LoginAttempt.objects.filter(email__iendswith=f"@{PROBE_DOMAIN}").delete()[0]
    links = MagicLinkToken.objects.filter(email__iendswith=f"@{PROBE_DOMAIN}").delete()[0]
    removed = len(users)
    for user in users:
        user.delete()

    return {"users": removed, "sessions": sessions, "attempts": attempts, "links": links, "signed": signed}
