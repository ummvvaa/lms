"""Расходы на модель: счётчик, месячный лимит, отчёт для администратора.

Провайдер цену в ответе не присылает — считаем сами по прейскуранту из
настроек. Прейскурант меняется без выката: цены у провайдеров живут своей
жизнью, а школа не должна из-за этого ждать релиза.

При исчерпании лимита операции отключаются с понятным текстом, а не молча:
директор должен понимать, почему кнопка перестала работать, и к кому идти.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone

from core.domains import ROLE_TITLES
from suggestions.models import LLMCall
from suggestions.providers import LLMUnavailable


class BudgetExceeded(LLMUnavailable):
    """Месячный лимит выбран. Текст пригоден для показа человеку.

    Наследуется от `LLMUnavailable` намеренно: для вызывающего кода это
    та же ситуация «модели сейчас нет» — он должен молча уйти на правила.
    Отдельный класс нужен только затем, чтобы API ответил 402 и объяснил
    причину, а не сделал вид, что ничего не случилось.
    """


@dataclass(frozen=True)
class Price:
    """Цена за миллион токенов."""

    input_per_million: Decimal
    output_per_million: Decimal


def _price_for(model: str) -> Price:
    """Прейскурант из настроек; для незнакомой модели — цена по умолчанию."""
    table = getattr(settings, "LLM_PRICES", {}) or {}
    row = table.get(model) or table.get("default") or {}
    return Price(
        input_per_million=Decimal(str(row.get("input", "3"))),
        output_per_million=Decimal(str(row.get("output", "15"))),
    )


def search_price() -> Decimal:
    """Цена тысячи поисковых запросов в долларах."""
    return Decimal(str(getattr(settings, "LLM_PRICE_SEARCH_PER_1000", "10") or "0"))


def cost_of(*, model: str, tokens_in: int, tokens_out: int, searches: int = 0) -> Decimal:
    """Стоимость одного вызова в долларах.

    Поиск оплачивается запросами, а не токенами, и в счёт провайдера
    приходит отдельной строкой — считаем его так же отдельно.
    """
    price = _price_for(model)
    million = Decimal("1000000")
    total = (Decimal(tokens_in) / million) * price.input_per_million + (
        Decimal(tokens_out) / million
    ) * price.output_per_million
    total += (Decimal(searches) / Decimal("1000")) * search_price()
    return total.quantize(Decimal("0.00001"))


def monthly_limit() -> Decimal:
    """Месячный лимит в долларах. Ноль — лимита нет."""
    return Decimal(str(getattr(settings, "LLM_MONTHLY_LIMIT", "0") or "0"))


def month_start(today: date | None = None) -> date:
    today = today or timezone.localdate()
    return today.replace(day=1)


def spent_this_month() -> Decimal:
    """Сколько уже потрачено с первого числа."""
    total = LLMCall.objects.filter(created_at__date__gte=month_start()).aggregate(total=Sum("cost"))["total"]
    return Decimal(total or 0)


def check_available() -> None:
    """Бросить `BudgetExceeded`, если месячный лимит выбран."""
    limit = monthly_limit()
    if limit <= 0:
        return
    spent = spent_this_month()
    if spent >= limit:
        raise BudgetExceeded(
            f"Месячный лимит расходов на модель выбран: потрачено ${spent:.2f} из ${limit:.2f}. "
            f"Операции с моделью отключены до первого числа. "
            f"Разбор и объяснения продолжают работать правилами — просто формулировки будут проще. "
            f"Поднять лимит может администратор в настройках"
        )


def is_available() -> bool:
    try:
        check_available()
    except BudgetExceeded:
        return False
    return True


def record(
    *,
    actor,
    role: str,
    purpose: str,
    provider: str,
    model: str,
    external_id: str = "",
    sent=None,
    received=None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    searches: int = 0,
    duration_ms: int = 0,
    is_ok: bool = True,
    error: str = "",
) -> LLMCall:
    """Записать вызов в журнал вместе со стоимостью."""
    import json

    return LLMCall.objects.create(
        actor=actor,
        role=role or getattr(actor, "role", "") or "",
        purpose=purpose,
        provider=provider,
        model=model,
        external_id=external_id,
        request_payload=json.dumps(sent, ensure_ascii=False)[:8000] if sent is not None else "",
        response_payload=json.dumps(received, ensure_ascii=False)[:8000] if received is not None else "",
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        searches=searches,
        cost=cost_of(model=model, tokens_in=tokens_in, tokens_out=tokens_out, searches=searches),
        duration_ms=duration_ms,
        is_ok=is_ok,
        error=error[:250],
    )


def report(*, days: int = 30) -> dict:
    """Экран расходов: сколько потрачено, кем и на что."""
    since = timezone.now() - timezone.timedelta(days=days)
    rows = LLMCall.objects.filter(created_at__gte=since)

    by_role = [
        {
            "role": row["role"] or "—",
            "role_title": ROLE_TITLES.get(row["role"], row["role"] or "не указана"),
            "calls": row["calls"],
            "cost": float(row["cost"] or 0),
        }
        for row in rows.values("role").annotate(calls=Count("id"), cost=Sum("cost")).order_by("-cost")
    ]
    by_purpose = [
        {
            "purpose": row["purpose"],
            "purpose_title": OPERATION_TITLES.get(row["purpose"], row["purpose"]),
            "calls": row["calls"],
            "cost": float(row["cost"] or 0),
            "tokens": int((row["tokens_in"] or 0) + (row["tokens_out"] or 0)),
        }
        for row in rows.values("purpose")
        .annotate(calls=Count("id"), cost=Sum("cost"), tokens_in=Sum("tokens_in"), tokens_out=Sum("tokens_out"))
        .order_by("-cost")
    ]

    limit = monthly_limit()
    spent = spent_this_month()
    left = limit - spent if limit > 0 else Decimal(0)
    failures = rows.filter(is_ok=False).count()

    return {
        "limit": float(limit),
        "spent_this_month": float(spent),
        "left": float(max(left, Decimal(0))),
        "percent": int(min(100, spent / limit * 100)) if limit > 0 else 0,
        "available": limit <= 0 or spent < limit,
        "days": days,
        "calls": rows.count(),
        "failures": failures,
        "by_role": by_role,
        "by_purpose": by_purpose,
        "detail": _headline(limit, spent, failures),
        "recent": [
            {
                "id": row.pk,
                "created_at": row.created_at,
                "actor_name": (row.actor.full_name or row.actor.email) if row.actor_id else "система",
                "role_title": ROLE_TITLES.get(row.role, row.role or "не указана"),
                "purpose_title": OPERATION_TITLES.get(row.purpose, row.purpose),
                "tokens": row.tokens_in + row.tokens_out,
                "cost": float(row.cost),
                "is_ok": row.is_ok,
                "error": row.error,
            }
            for row in rows.select_related("actor")[:100]
        ],
    }


def _headline(limit: Decimal, spent: Decimal, failures: int) -> str:
    if limit <= 0:
        return f"Месячный лимит не задан. С начала месяца потрачено ${spent:.2f}"
    if spent >= limit:
        return (
            f"Лимит выбран: ${spent:.2f} из ${limit:.2f}. Операции с моделью отключены, "
            f"разбор и объяснения работают правилами"
        )
    tail = f", неудачных вызовов: {failures}" if failures else ""
    return f"С начала месяца потрачено ${spent:.2f} из ${limit:.2f}{tail}"


#: Человеческие названия операций — их читает администратор на экране
#: расходов, и `parse_certificate` там не годится (фаза 17).
OPERATION_TITLES = {
    "paste_second_pass": "Разбор вставленного текста (второй проход)",
    "parse_university": "Разбор вуза по названию или ссылке",
    "parse_activity": "Разбор описания активности",
    "parse_certificate": "Распознавание грамоты",
    "parse_score_screenshot": "Распознавание скриншота с баллами",
    "explain_match": "Объяснение соответствия",
    "pick_universities": "Подбор вузов словами",
    "digest": "Дайджест на сегодня",
    "explain_list": "Объяснение списка учеников",
    "week_changes": "Что изменилось за неделю",
    "focus_today": "На кого смотреть сегодня",
    "bulk_tasks": "Массовая постановка задач",
    "prep_plan": "План подготовки к экзамену",
    "gap_to_tasks": "Пробелы портфолио в задачи",
    "parent_letter": "Черновик письма родителю",
    "check_balance": "Проверка баланса списка вузов",
    "essay_questions": "Вопросы по эссе",
    "assistant_chat": "Свободный вопрос помощнику",
    "assistant_quick": "Быстрая кнопка помощника",
    "import_reading": "Разбор загружаемого файла",
    "import_mapping": "Сопоставление колонок файла",
}
