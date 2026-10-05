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
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

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
    """Месячный лимит в долларах — настройка школы. Ноль — лимита нет."""
    from core import school_rules

    return Decimal(school_rules.value(school_rules.LLM_MONTHLY_LIMIT))


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
            _(
                "Месячный лимит расходов на модель выбран: потрачено ${spent} из ${limit}. "
                "Операции с моделью отключены до первого числа. "
                "Разбор и объяснения продолжают работать правилами — просто формулировки будут проще. "
                "Поднять лимит может администратор в настройках"
            ).format(spent=f"{spent:.2f}", limit=f"{limit:.2f}")
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
            "role_title": ROLE_TITLES.get(row["role"], row["role"] or _("не указана")),
            "calls": row["calls"],
            "cost": float(row["cost"] or 0),
        }
        for row in rows.values("role").annotate(calls=Count("id"), cost=Sum("cost")).order_by("-cost")
    ]
    by_purpose = [
        {
            "purpose": row["purpose"],
            "purpose_title": str(OPERATION_TITLES.get(row["purpose"], row["purpose"])),
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
                "actor_name": (row.actor.full_name or row.actor.email) if row.actor_id else _("система"),
                "role_title": ROLE_TITLES.get(row.role, row.role or _("не указана")),
                "purpose_title": str(OPERATION_TITLES.get(row.purpose, row.purpose)),
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
        return _("Месячный лимит не задан. С начала месяца потрачено ${spent}").format(spent=f"{spent:.2f}")
    if spent >= limit:
        return _(
            "Лимит выбран: ${spent} из ${limit}. Операции с моделью отключены, "
            "разбор и объяснения работают правилами"
        ).format(spent=f"{spent:.2f}", limit=f"{limit:.2f}")
    if failures:
        return _("С начала месяца потрачено ${spent} из ${limit}, неудачных вызовов: {failures}").format(
            spent=f"{spent:.2f}", limit=f"{limit:.2f}", failures=failures
        )
    return _("С начала месяца потрачено ${spent} из ${limit}").format(spent=f"{spent:.2f}", limit=f"{limit:.2f}")


#: Человеческие названия операций — их читает администратор на экране
#: расходов, и `parse_certificate` там не годится (фаза 17).
OPERATION_TITLES = {
    "paste_second_pass": gettext_lazy("Разбор вставленного текста (второй проход)"),
    "parse_university": gettext_lazy("Разбор вуза по названию или ссылке"),
    "parse_activity": gettext_lazy("Разбор описания активности"),
    "parse_certificate": gettext_lazy("Распознавание грамоты"),
    "parse_score_screenshot": gettext_lazy("Распознавание скриншота с баллами"),
    "explain_match": gettext_lazy("Объяснение соответствия"),
    "pick_universities": gettext_lazy("Подбор вузов словами"),
    "digest": gettext_lazy("Дайджест на сегодня"),
    "explain_list": gettext_lazy("Объяснение списка учеников"),
    "week_changes": gettext_lazy("Что изменилось за неделю"),
    "focus_today": gettext_lazy("На кого смотреть сегодня"),
    "bulk_tasks": gettext_lazy("Массовая постановка задач"),
    "prep_plan": gettext_lazy("План подготовки к экзамену"),
    "gap_to_tasks": gettext_lazy("Пробелы портфолио в задачи"),
    "check_balance": gettext_lazy("Проверка баланса списка вузов"),
    "essay_questions": gettext_lazy("Вопросы по эссе"),
    "assistant_chat": gettext_lazy("Свободный вопрос помощнику"),
    "assistant_quick": gettext_lazy("Быстрая кнопка помощника"),
    "import_reading": gettext_lazy("Разбор загружаемого файла"),
    "import_mapping": gettext_lazy("Сопоставление колонок файла"),
    "scholarship_pick": gettext_lazy("Подбор стипендий под профиль"),
    "career_test": gettext_lazy("Разбор анкеты профтеста"),
}
