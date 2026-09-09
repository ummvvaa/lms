"""Шифрование паролей учеников от почты и Common App (фаза 65).

Это единственные данные в системе, которые открывают чужие аккаунты:
их утечка — не «утечка информации», а доступ к почте ученика. Поэтому:

* в базе лежит только шифртекст Fernet (AES-128-CBC с подписью HMAC);
  дамп базы уносит его в том же виде;
* ключ — переменная окружения `CREDENTIALS_KEY`, в коде его нет; без
  ключа боевой контур не стартует, а `preflight` проверяет, что ключ
  расшифровывает контрольную запись (`core.KeyCheck`);
* открытый текст живёт ровно столько, сколько идёт один запрос
  «показать», и каждый показ пишется в журнал.

Потеря ключа означает потерю всех сохранённых паролей: восстановить
их из шифртекста нельзя, только спросить у учеников заново.
"""

from __future__ import annotations

from django.conf import settings

#: Фраза контрольной записи: по ней видно, что ключ тот самый.
CHECK_PHRASE = "bhs-credentials-key-check"


class KeyMissing(RuntimeError):
    """Ключа нет — шифровать и расшифровывать нечем."""


class KeyMismatch(RuntimeError):
    """Ключ есть, но шифртекст сделан другим ключом."""


def _fernet():
    from cryptography.fernet import Fernet

    key = getattr(settings, "CREDENTIALS_KEY", "") or ""
    if not key:
        raise KeyMissing("CREDENTIALS_KEY пуст")
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as error:
        raise KeyMissing("CREDENTIALS_KEY не похож на ключ Fernet") from error


def key_ready() -> bool:
    try:
        _fernet()
    except KeyMissing:
        return False
    return True


def encrypt(text: str) -> str:
    """Открытый текст → шифртекст (строка, годная для колонки)."""
    return _fernet().encrypt(text.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    """Шифртекст → открытый текст. Чужой ключ или битая запись — `KeyMismatch`."""
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as error:
        raise KeyMismatch("шифртекст сделан другим ключом или повреждён") from error


def ensure_key_check():
    """Контрольная запись: создаётся один раз ключом, который сейчас в окружении."""
    from core.models import KeyCheck

    row = KeyCheck.objects.first()
    if row is None:
        row = KeyCheck.objects.create(ciphertext=encrypt(CHECK_PHRASE))
    return row


def verify_key() -> tuple[bool, str]:
    """Ключ на месте и расшифровывает контрольную запись — для `preflight`."""
    from core.models import KeyCheck

    if not key_ready():
        return False, "CREDENTIALS_KEY пуст или не похож на ключ Fernet"
    row = KeyCheck.objects.first()
    if row is None:
        return False, "контрольной записи нет — выполните `manage.py credentials_key --init`"
    try:
        phrase = decrypt(row.ciphertext)
    except KeyMismatch:
        return False, "ключ не расшифровывает контрольную запись: это другой ключ, пароли учеников им не открыть"
    if phrase != CHECK_PHRASE:
        return False, "контрольная запись расшифровалась в чужую фразу"
    return True, f"контрольная запись от {row.created_at:%d.%m.%Y}"
