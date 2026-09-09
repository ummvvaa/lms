"""Письма родителям и ученикам (фаза 66): заготовка, а не отправка.

Решение владельца: **сервер писем не шлёт**. Кнопка собирает письмо
и открывает почтовый клиент того, кто её нажал. Причин две, и обе
важнее удобства рассылки:

* письмо уходит от живого человека, с его адреса и подписи, и остаётся
  у него в «отправленных» — родителю есть кому ответить;
* школа не превращается в рассыльщик: система не может ни подтвердить
  доставку, ни отозвать письмо, и делать вид, что может, нечестно.

Отсюда всё остальное. Отдельной сущности «письмо» нет — есть запись
в журнале «письмо открыто», и подписана она именно так: открыто, а не
отправлено. Подтвердить отправку нельзя, и обещать этого мы не будем.

Сборка `mailto:` — здесь, на сервере, а не на фронте: правила
экранирования одни, а кириллица в теме ломается тихо. Фронт получает
готовую строку и открывает её.
"""

from __future__ import annotations

from urllib.parse import quote

from core.audit import record_event
from engagement.models import MailKind, MailTemplate

#: Сколько адресов помещается в одно письмо. Больше — почтовые клиенты
#: и сами почтовые службы начинают резать список молча, поэтому режем мы,
#: явно и по кнопке «следующие»
ADDRESS_LIMIT = 50

#: Переменные шаблона по-русски: их пишет администратор, а не программист,
#: и `{student_name}` он писать не должен
VARIABLES: tuple[str, ...] = ("ученик", "группа", "просим", "срок", "куратор")


def fill(text: str, values: dict[str, str]) -> str:
    """Подставить переменные вида `{ученик}`.

    Незнакомая переменная остаётся как есть: молча подставить пустоту
    хуже, чем показать человеку, что в шаблоне опечатка.
    """
    out = text or ""
    for name in VARIABLES:
        out = out.replace("{" + name + "}", str(values.get(name, "") or ""))
    return out


def template_for(kind: str, language: str) -> MailTemplate | None:
    """Шаблон вида на языке группы; нет на её языке — берём русский."""
    kind = kind if kind in MailKind.values else MailKind.FREE
    row = MailTemplate.objects.filter(kind=kind, language=language, is_active=True).first()
    if row is not None:
        return row
    return MailTemplate.objects.filter(kind=kind, language="ru", is_active=True).first()


def compose(*, kind: str, language: str, values: dict[str, str]) -> dict:
    """Тема и текст письма — из шаблона, с подставленными переменными."""
    row = template_for(kind, language)
    if row is None:
        return {"subject": "", "body": "", "template": None}
    return {
        "subject": fill(row.subject, values),
        "body": fill(row.body, values),
        "template": row.pk,
        "language": row.language,
    }


def mailto(*, to: list[str] | None = None, bcc: list[str] | None = None, subject: str = "", body: str = "") -> str:
    """Собрать ссылку `mailto:` — с кириллицей в теме и в тексте.

    Экранируем по RFC 6068: в адресной части остаются только адреса,
    всё остальное уходит в запрос процентным кодированием UTF-8. Перевод
    строки в теле — `%0A`; без кодирования письмо приходит одной строкой.
    """
    to = [a for a in (to or []) if a]
    bcc = [a for a in (bcc or []) if a]
    parts = []
    if subject:
        parts.append("subject=" + quote(subject, safe=""))
    if bcc:
        parts.append("bcc=" + quote(",".join(bcc), safe=""))
    if body:
        parts.append("body=" + quote(body, safe=""))
    head = quote(",".join(to), safe="@,")
    query = ("?" + "&".join(parts)) if parts else ""
    return f"mailto:{head}{query}"


def batches(addresses: list[str], size: int = ADDRESS_LIMIT) -> list[list[str]]:
    """Разбить адреса на письма по `size`: длинный список клиенты режут молча."""
    clean = [a for a in addresses if a]
    return [clean[i : i + size] for i in range(0, len(clean), size)] or []


def note_opened(*, students, subject: str, recipients: int, actor) -> int:
    """Записать в журнал, что письмо открыли.

    Формулировка «письмо открыто» выбрана намеренно: система знает, что
    человек нажал кнопку, и не знает, что он письмо отправил. Писать
    «отправлено» значило бы обещать доставку, которой мы не видели.
    """
    written = 0
    for student in students:
        record_event(
            student=student,
            code="letter_opened",
            text=f"«{subject[:120]}», получателей: {recipients}",
            actor=actor,
        )
        written += 1
    return written
