"""Ежедневный дайджест изменений по домену директора.

Открывается при входе: что поменялось в вашем домене за сутки и что ждёт
вашего решения.

Дайджест отдаётся готовым текстом. Фронт его не собирает и не подставляет
в него имена колонок: человек читает «У троих учеников обновился текущий
балл IELTS», а не `ielts_current: 3` (фаза 17).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from core.domains import Source, domain_of_role
from core.labels import acting_for_phrase, field_short, field_title, value_title
from core.models import AuditLog
from core.phrasing import counted, days_left, listing, people, plural
from suggestions.commands import title_of as command_title
from suggestions.models import Suggestion, SuggestionStatus

#: сколько дней вперёд считаем дедлайн «скорым» — про него стоит сказать
DEADLINE_HORIZON = 14

SOURCE_PHRASE = {
    Source.MANUAL: "руками",
    Source.IMPORT: "загрузкой файла",
    Source.AI: "помощником",
    Source.SYNC: "фоновой сверкой",
    Source.STUDENT_ONBOARDING: "из анкеты ученика",
}


#: «у одного ученика», «у двоих учеников» — после предлога «у» нужен родительный
_PEOPLE_OF = {1: "одного ученика", 2: "двоих учеников", 3: "троих учеников", 4: "четверых учеников"}


def people_of(number: int) -> str:
    return _PEOPLE_OF.get(number) or counted(number, ("ученика", "учеников", "учеников"))


def _changes_lines(entries) -> list[str]:
    """«У троих учеников обновился текущий балл IELTS»."""
    grouped: dict[tuple[str, str], set] = defaultdict(set)
    for row in entries.values_list("model_label", "field_name", "student_id"):
        model_label, field_name, student_id = row
        grouped[(model_label, field_name)].add(student_id)

    ranked = sorted(grouped.items(), key=lambda item: -len(item[1]))
    lines: list[str] = []
    for (model_label, field_name), students in ranked[:6]:
        title = field_title(model_label, field_name)
        real = {s for s in students if s is not None}
        if real:
            lines.append(f"У {people_of(len(real))} обновилось: {title.lower()}")
        else:
            lines.append(f"Правок в справочнике по позиции «{title}»: {len(students)}")
    return lines


def _source_line(entries) -> str:
    """«Из них загрузкой файла — 12, помощником — 3»."""
    rows = entries.values("source").annotate(n=Count("id")).order_by("-n")
    parts = [f"{SOURCE_PHRASE.get(row['source'], row['source'])} — {row['n']}" for row in rows if row["n"]]
    return "Откуда правки: " + listing(parts) if parts else ""


def _pending_line(domain_code: str) -> tuple[str, list[dict]]:
    """Предложения, ждущие решения директора."""
    rows = list(
        Suggestion.objects.filter(domain_code=domain_code, status=SuggestionStatus.PENDING)
        .annotate(n=Count("changes"))
        .order_by("-created_at")[:10]
    )
    payload = []
    for row in rows:
        title = command_title(row.command) or row.get_source_type_display()
        payload.append(
            {
                "id": row.id,
                "title": title,
                "changes": row.n,
                "created_at": row.created_at,
                "text": f"{title}: {counted(row.n, ('правка', 'правки', 'правок'))}",
            }
        )
    if not rows:
        return "", payload
    total = len(rows)
    word = plural(total, ("предложение", "предложения", "предложений"))
    verb = "ждёт" if total == 1 else "ждут"
    return f"{total} {word} {verb} вашего решения", payload


def _student_added_line() -> str:
    """«Двое добавили себе вузы — ждут подтверждения»."""
    from universities.models import AddedBy, StudentUniversity

    rows = StudentUniversity.objects.filter(added_by=AddedBy.STUDENT, is_confirmed=False)
    students = {row.student_id for row in rows}
    if not students:
        return ""
    return f"{people(len(students))} добавили себе вузы — записи ждут подтверждения"


def _deadline_lines() -> list[str]:
    """«Через 5 дней дедлайн NYU, заявка готова у одного из четырёх»."""
    from universities.models import ApplicationStatus, StudentUniversity

    today = timezone.localdate()
    horizon = today + timedelta(days=DEADLINE_HORIZON)
    rows = (
        StudentUniversity.objects.filter(
            admission_round__deadline__gte=today,
            admission_round__deadline__lte=horizon,
        )
        .select_related("admission_round", "program", "program__university")
        .order_by("admission_round__deadline")
    )

    by_round: dict[int, list] = defaultdict(list)
    for row in rows:
        by_round[row.admission_round_id].append(row)

    ready_statuses = {ApplicationStatus.READY, ApplicationStatus.SUBMITTED, ApplicationStatus.ACCEPTED}
    lines: list[str] = []
    for applicants in list(by_round.values())[:5]:
        first = applicants[0]
        deadline = first.admission_round.deadline
        university = first.program.university.name
        ready = sum(1 for row in applicants if row.application_status in ready_statuses)
        total = len(applicants)
        tail = (
            f"заявка готова у {ready} из {total}" if total > 1 else ("заявка готова" if ready else "заявка не готова")
        )
        lines.append(f"{days_left((deadline - today).days).capitalize()} дедлайн {university}, {tail}")
    return lines


def _recent(entries) -> list[dict]:
    """Последние правки строками — уже с человеческими подписями."""
    from core.domains import DOMAINS
    from students.models import Student

    rows = list(entries.select_related("actor").order_by("-created_at")[:20])
    names = {
        pk: f"{last} {first}".strip()
        for pk, last, first in Student.all_objects.filter(
            pk__in={row.student_id for row in rows if row.student_id}
        ).values_list("pk", "last_name", "first_name")
    }
    out = []
    for row in rows:
        domain = DOMAINS.get(row.domain_code or "")
        out.append(
            {
                "domain_title": domain.title if domain else "",
                "student_title": names.get(row.student_id, "") or (row.object_title or ""),
                "field_title": field_title(row.model_label, row.field_name),
                "field_short": field_short(row.model_label, row.field_name),
                "old_display": value_title(row.model_label, row.field_name, row.old_value),
                "new_display": value_title(row.model_label, row.field_name, row.new_value),
                "source_title": SOURCE_PHRASE.get(row.source, row.source),
                "created_at": row.created_at,
                "student_id": row.student_id,
                "actor_name": (
                    (row.actor.full_name or row.actor.email) if row.actor_id else (row.actor_title or "система")
                ),
                # администратор действовал за домен — директор должен видеть это
                # и в сводке, а не только в истории карточки (фаза 35)
                "acting_for_title": acting_for_phrase(row.acting_for),
            }
        )
    return out


DIGEST_RULES = """Ты пересказываешь сводку дня директору школы.

Правила:
- бери ТОЛЬКО переданные факты, ничего не добавляй;
- числа и имена сохраняй как есть, ничего не округляй;
- никаких технических терминов и имён колонок;
- три-пять коротких строк, каждая с новой строки, без нумерации."""


def _model_digest(*, headline: str, lines: list[str], user, domain) -> list[str] | None:
    """Пересказать сводку моделью. Ключа нет — остаются строки правил."""
    from suggestions.llm import LLMUnavailable, complete

    try:
        response = complete(
            system=DIGEST_RULES,
            user=f"{headline}.\n" + "\n".join(lines),
            purpose="digest",
            actor=user,
            role=getattr(user, "role", ""),
            max_tokens=500,
        )
    except LLMUnavailable:
        return None

    written = [row.strip(" -•\t") for row in (response.content or "").splitlines() if row.strip()]
    return written or None


def _school_lines(entries, days: int) -> list[str]:
    """Правки по всей школе: по доменам, кто и у скольких учеников."""
    from core.domains import DOMAINS

    by_domain: dict[str, list] = defaultdict(list)
    for _model_label, _field_name, student_id, domain_code, actor_id, acting_for in entries.values_list(
        "model_label", "field_name", "student_id", "domain_code", "actor_id", "acting_for"
    ):
        by_domain[domain_code or ""].append((student_id, actor_id, acting_for))
    from accounts.models import User

    actor_ids = {row[1] for rows in by_domain.values() for row in rows if row[1]}
    names = {
        pk: (name or email)
        for pk, name, email in User.objects.filter(pk__in=actor_ids).values_list("pk", "full_name", "email")
    }
    lines: list[str] = []
    for code, rows in sorted(by_domain.items(), key=lambda item: -len(item[1])):
        domain = DOMAINS.get(code)
        title = domain.title if domain else "учёба и реестр"
        students = {row[0] for row in rows if row[0] is not None}
        by_actor: dict[str, int] = defaultdict(int)
        for _student, actor_id, _acting in rows:
            by_actor[names.get(actor_id, "система")] += 1
        who = listing([f"{name} — {n}" for name, n in sorted(by_actor.items(), key=lambda kv: -kv[1])[:3]])
        tail = f" у {people_of(len(students))}" if students else ""
        lines.append(f"{title}: {counted(len(rows), ('правка', 'правки', 'правок'))}{tail} ({who})")
    return lines


def _pending_all() -> tuple[list[str], list[dict]]:
    """Что ждёт решения по всей школе: предложения по доменам и документы на проверке."""
    from core.domains import DOMAINS
    from students.models import DocumentStatus, StudentDocument

    lines: list[str] = []
    payload: list[dict] = []
    for code, domain in DOMAINS.items():
        line, rows = _pending_line(code)
        if rows:
            lines.append(
                f"{domain.title}: {counted(len(rows), ('предложение', 'предложения', 'предложений'))} ждут решения"
            )
            payload.extend({**row, "domain_title": domain.title} for row in rows[:5])
    documents = StudentDocument.objects.filter(status=DocumentStatus.PENDING).count()
    if documents:
        lines.append(f"Документов на проверке: {documents}")
    return lines, payload


def _academics_block() -> dict:
    """Учёба за неделю: не отмечено, накладки, отчёты родителям по статусам."""
    from academics import calendar as school_calendar
    from academics import schedule
    from academics.models import ParentReport, ReportStatus

    calendar = school_calendar.load()
    day = school_calendar.today()
    start = school_calendar.week_start(day)
    unmarked = schedule.stale_unmarked(calendar, start, day)
    conflicts = schedule.conflicts_between(start, start + timedelta(days=6))
    latest = ParentReport.objects.order_by("-period_start").values_list("period_kind", "period_start", "title").first()
    reports = None
    if latest:
        rows = ParentReport.objects.filter(period_kind=latest[0], period_start=latest[1])
        reports = {
            "title": latest[2],
            "total": rows.count(),
            **{status: rows.filter(status=status).count() for status, _title in ReportStatus.choices},
            "statuses": [{"code": c, "title": t} for c, t in ReportStatus.choices],
        }
    return {
        "unmarked": len(unmarked),
        "unmarked_teachers": sorted(
            {(lesson.substitute or lesson.teacher).full_name or "" for lesson in unmarked} - {""}
        )[:6],
        "conflicts": len(conflicts),
        "reports": reports,
    }


def _school_digest(*, user, days: int) -> dict:
    """Дайджест администратора: вся школа за сутки и за неделю (решение владельца, 27.09.2026)."""
    now = timezone.now()
    since = now - timedelta(days=days)
    week_since = now - timedelta(days=7)
    day_entries = AuditLog.objects.filter(created_at__gte=since)
    week_entries = AuditLog.objects.filter(created_at__gte=week_since)
    total = day_entries.count()
    window = "за сутки" if days == 1 else f"за {counted(days, ('день', 'дня', 'дней'))}"
    headline = (
        f"По школе {window}: {counted(total, ('правка', 'правки', 'правок'))}, за неделю — {week_entries.count()}"
        if total or week_entries.exists()
        else f"По школе {window} правок не было"
    )
    lines = _school_lines(day_entries, days)
    source_line = _source_line(day_entries)
    if source_line:
        lines.append(source_line)
    pending_lines, pending = _pending_all()
    return {
        "domain": "school",
        "domain_title": "Вся школа",
        "since": since,
        "headline": headline,
        "lines": lines or ["Ничего нового — можно заняться тем, что запланировали"],
        "week_lines": _school_lines(week_entries, 7),
        "pending": pending,
        "pending_line": "; ".join(pending_lines),
        "pending_lines": pending_lines,
        "by_model": False,
        "recent": _recent(day_entries if total else week_entries),
        "academics": _academics_block(),
    }


def build(*, user, days: int = 1) -> dict:
    """Собрать дайджест для пользователя.

    Возвращает готовые к показу строки: `headline` — одна фраза, `lines` —
    короткая сводка, `pending` — что ждёт решения. Администратор видит
    всю школу по всем доменам.
    """
    from core.domains import ROLE_ADMIN

    if user.role == ROLE_ADMIN:
        return _school_digest(user=user, days=days)
    domain = domain_of_role(user.role)
    since = timezone.now() - timedelta(days=days)

    if domain is None:
        return {
            "domain": None,
            "domain_title": "",
            "since": since,
            "headline": "У вашей роли нет своего домена — сводка не собирается",
            "lines": [],
            "pending": [],
            "pending_line": "",
            "recent": [],
        }

    entries = AuditLog.objects.filter(domain_code=domain.code, created_at__gte=since)
    total = entries.count()
    window = "за сутки" if days == 1 else f"за {counted(days, ('день', 'дня', 'дней'))}"

    if total:
        headline = f"В домене «{domain.title}» {window}: {counted(total, ('правка', 'правки', 'правок'))}"
    else:
        headline = f"В домене «{domain.title}» {window} правок не было"

    lines = _changes_lines(entries)
    source_line = _source_line(entries)
    if source_line:
        lines.append(source_line)

    if domain.code == "admission":
        student_line = _student_added_line()
        if student_line:
            lines.append(student_line)
        lines.extend(_deadline_lines())

    pending_line, pending = _pending_line(domain.code)
    if pending_line:
        lines.insert(0, pending_line)

    if not lines:
        lines = ["Ничего нового — можно заняться тем, что запланировали"]

    written_by_model = False
    text = _model_digest(headline=headline, lines=lines, user=user, domain=domain)
    if text:
        lines, written_by_model = text, True

    return {
        "domain": domain.code,
        "domain_title": domain.title,
        "since": since,
        "headline": headline,
        "lines": lines,
        "pending": pending,
        "pending_line": pending_line,
        "by_model": written_by_model,
        "recent": _recent(entries),
    }
