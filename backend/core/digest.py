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
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.domains import Source, domain_of_role
from core.labels import acting_for_phrase, field_short, field_title, value_title
from core.models import AuditLog
from core.phrasing import counted, days_left, listing, people, tn
from suggestions.commands import title_of as command_title
from suggestions.models import Suggestion, SuggestionStatus

#: сколько дней вперёд считаем дедлайн «скорым» — про него стоит сказать
DEADLINE_HORIZON = 14

SOURCE_PHRASE = {
    Source.MANUAL: gettext_lazy("руками"),
    Source.IMPORT: gettext_lazy("загрузкой файла"),
    Source.AI: gettext_lazy("помощником"),
    Source.SYNC: gettext_lazy("фоновой сверкой"),
    Source.STUDENT_ONBOARDING: gettext_lazy("из анкеты ученика"),
    Source.STUDENT_PROPOSAL: gettext_lazy("предложением ученика"),
}

#: записи вне доменов директоров — по приложению модели
OUTSIDE_TITLES = {
    "academics": gettext_lazy("Учёба"),
    "students": gettext_lazy("Реестр учеников"),
    "accounts": gettext_lazy("Учётные записи"),
    "core": gettext_lazy("Служебные записи"),
    "universities": gettext_lazy("Справочник вузов"),
}


def _source_phrase(source: str) -> str:
    """«руками», «загрузкой файла» — на языке ответа; неизвестный источник — кодом."""
    return str(SOURCE_PHRASE.get(source, source))


def _area_title(domain_code: str, model_label: str) -> str:
    from core.domains import DOMAINS

    domain = DOMAINS.get(domain_code or "")
    if domain:
        return domain.title
    app = (model_label or "").split(".")[0]
    return str(OUTSIDE_TITLES.get(domain_code or app) or OUTSIDE_TITLES.get(app) or _("Прочее"))


#: «у одного ученика», «у двоих учеников» — после предлога «у» нужен родительный;
#: собирательные числительные есть только в русском
_PEOPLE_OF = {  # i18n-skip: только русский
    1: "одного ученика",
    2: "двоих учеников",
    3: "троих учеников",
    4: "четверых учеников",
}


def people_of(number: int) -> str:
    """«троих учеников», «7 учеников» — для фразы «у кого»."""
    if (translation.get_language() or "ru").startswith("ru") and number in _PEOPLE_OF:
        return _PEOPLE_OF[number]
    return tn(number, "{n} ученика|{n} учеников|{n} учеников")


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
            lines.append(
                _("У {students} обновилось: {field}").format(students=people_of(len(real)), field=title.lower())
            )
        else:
            lines.append(
                _("Правок в справочнике по позиции «{field}»: {count}").format(field=title, count=len(students))
            )
    return lines


def _source_line(entries) -> str:
    """«Из них загрузкой файла — 12, помощником — 3»."""
    rows = entries.values("source").annotate(n=Count("id")).order_by("-n")
    parts = [f"{_source_phrase(row['source'])} — {row['n']}" for row in rows if row["n"]]
    return _("Откуда правки: {sources}").format(sources=listing(parts)) if parts else ""


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
                "text": f"{title}: {counted(row.n, 'правка|правки|правок')}",
            }
        )
    if not rows:
        return "", payload
    total = len(rows)
    line = tn(
        total,
        "{n} предложение ждёт вашего решения|{n} предложения ждут вашего решения|{n} предложений ждут вашего решения",
    )
    return line, payload


def _student_added_line() -> str:
    """«Двое добавили себе вузы — ждут подтверждения»."""
    from core.parallels import admission_q
    from universities.models import AddedBy, StudentUniversity

    rows = StudentUniversity.objects.filter(admission_q("student__"), added_by=AddedBy.STUDENT, is_confirmed=False)
    students = {row.student_id for row in rows}
    if not students:
        return ""
    return _("{students} добавили себе вузы — записи ждут подтверждения").format(students=people(len(students)))


def _deadline_lines() -> list[str]:
    """«Через 5 дней дедлайн NYU, заявка готова у одного из четырёх»."""
    from core.parallels import admission_q
    from universities.models import ApplicationStatus, StudentUniversity

    today = timezone.localdate()
    horizon = today + timedelta(days=DEADLINE_HORIZON)
    rows = (
        StudentUniversity.objects.filter(
            admission_q("student__"),
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
        if total > 1:
            tail = _("заявка готова у {ready} из {total}").format(ready=ready, total=total)
        else:
            tail = _("заявка готова") if ready else _("заявка не готова")
        lines.append(
            _("{when} дедлайн {university}, {state}").format(
                when=days_left((deadline - today).days).capitalize(), university=university, state=tail
            )
        )
    return lines


def _recent(entries) -> list[dict]:
    """Последние правки строками — уже с человеческими подписями."""
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
        out.append(
            {
                "domain_title": _area_title(row.domain_code, row.model_label),
                "student_title": names.get(row.student_id, "") or (row.object_title or ""),
                "field_title": field_title(row.model_label, row.field_name),
                "field_short": field_short(row.model_label, row.field_name),
                "old_display": value_title(row.model_label, row.field_name, row.old_value),
                "new_display": value_title(row.model_label, row.field_name, row.new_value),
                "source_title": _source_phrase(row.source),
                "created_at": row.created_at,
                "student_id": row.student_id,
                "actor_name": (
                    (row.actor.full_name or row.actor.email) if row.actor_id else (row.actor_title or _("система"))
                ),
                # администратор действовал за домен — директор должен видеть это
                # и в сводке, а не только в истории карточки (фаза 35)
                "acting_for_title": acting_for_phrase(row.acting_for),
            }
        )
    return out


# fmt: off
DIGEST_RULES = (  # i18n-skip: промпт модели ИИ, язык ответа настраивается отдельно
    """Ты пересказываешь сводку дня директору школы.

Правила:
- бери ТОЛЬКО переданные факты, ничего не добавляй;
- числа и имена сохраняй как есть, ничего не округляй;
- никаких технических терминов и имён колонок;
- три-пять коротких строк, каждая с новой строки, без нумерации."""
)
# fmt: on


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
    """Правки людей по областям — кто и у скольких учеников; системные записи отдельно.

    Запись без автора (посев, сверка, фоновая задача) — не правка человека:
    она считается отдельной строкой, а не растворяется в «правках у одного ученика».
    """
    from accounts.models import User

    del days
    people_rows: dict[str, list] = defaultdict(list)
    system_rows: dict[str, int] = defaultdict(int)
    for model_label, student_id, domain_code, actor_id in entries.values_list(
        "model_label", "student_id", "domain_code", "actor_id"
    ):
        title = _area_title(domain_code, model_label)
        if actor_id is None:
            system_rows[title] += 1
        else:
            people_rows[title].append((student_id, actor_id))
    actor_ids = {row[1] for rows in people_rows.values() for row in rows}
    names = {
        pk: (name or email)
        for pk, name, email in User.objects.filter(pk__in=actor_ids).values_list("pk", "full_name", "email")
    }
    lines: list[str] = []
    for title, rows in sorted(people_rows.items(), key=lambda item: -len(item[1])):
        students = {row[0] for row in rows if row[0] is not None}
        by_actor: dict[str, int] = defaultdict(int)
        for _student, actor_id in rows:
            by_actor[names.get(actor_id, "")] += 1
        who = listing([f"{name} — {n}" for name, n in sorted(by_actor.items(), key=lambda kv: -kv[1])[:3] if name])
        edits = counted(len(rows), "правка|правки|правок")
        if students:
            line = _("{area}: {edits} у {students}").format(area=title, edits=edits, students=people_of(len(students)))
        else:
            line = _("{area}: {edits}").format(area=title, edits=edits)
        lines.append(line + (f" ({who})" if who else ""))
    if system_rows:
        parts = [f"{title.lower()} — {n}" for title, n in sorted(system_rows.items(), key=lambda kv: -kv[1])]
        lines.append(
            _("Записи без автора (посев, сверка, фоновые задачи): {count} — {areas}").format(
                count=sum(system_rows.values()), areas=listing(parts)
            )
        )
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
                tn(
                    len(rows),
                    "{domain}: {n} предложение ждёт решения"
                    "|{domain}: {n} предложения ждут решения"
                    "|{domain}: {n} предложений ждут решения",
                    domain=domain.title,
                )
            )
            payload.extend({**row, "domain_title": domain.title} for row in rows[:5])
    documents = StudentDocument.objects.filter(status=DocumentStatus.PENDING).count()
    if documents:
        lines.append(_("Документов на проверке: {count}").format(count=documents))
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
    window = _window(days)
    headline = (
        _("По школе {window}: {edits}, за неделю — {week}").format(
            window=window, edits=counted(total, "правка|правки|правок"), week=week_entries.count()
        )
        if total or week_entries.exists()
        else _("По школе {window} правок не было").format(window=window)
    )
    lines = _school_lines(day_entries, days)
    source_line = _source_line(day_entries)
    if source_line:
        lines.append(source_line)
    pending_lines, pending = _pending_all()
    return {
        "domain": "school",
        "domain_title": _("Вся школа"),
        "since": since,
        "headline": headline,
        "lines": lines or [_("Ничего нового — можно заняться тем, что запланировали")],
        "week_lines": _school_lines(week_entries, 7),
        "pending": pending,
        "pending_line": "; ".join(pending_lines),
        "pending_lines": pending_lines,
        "by_model": False,
        "recent": _recent(day_entries if total else week_entries),
        "academics": _academics_block(),
    }


def _window(days: int) -> str:
    """«за сутки», «за 3 дня»."""
    return _("за сутки") if days == 1 else tn(days, "за {n} день|за {n} дня|за {n} дней")


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
            "headline": _("У вашей роли нет своего домена — сводка не собирается"),
            "lines": [],
            "pending": [],
            "pending_line": "",
            "recent": [],
        }

    entries = AuditLog.objects.filter(domain_code=domain.code, created_at__gte=since)
    total = entries.count()
    window = _window(days)

    if total:
        headline = _("В домене «{domain}» {window}: {edits}").format(
            domain=domain.title, window=window, edits=counted(total, "правка|правки|правок")
        )
    else:
        headline = _("В домене «{domain}» {window} правок не было").format(domain=domain.title, window=window)

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
        lines = [_("Ничего нового — можно заняться тем, что запланировали")]

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
