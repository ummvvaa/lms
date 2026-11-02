"""Действия кружков: правка кружка, запись и выход, задание, заметки, отметка по QR.

Вьюхи только разбирают запрос и проверяют право; что происходит с записью —
здесь, одним местом. Отметка по QR повторяет секции (`sport.services`):
тот же срок жизни кода из правил школы, то же окно «текущее и предыдущее»,
та же отложенная отметка до входа — со своей солью подписи, чтобы код
секции не отмечал на кружке и наоборот.
"""

from __future__ import annotations

import datetime as dt

from django.core import signing
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from clubs.models import Club, ClubEnrollment, ClubHomework, ClubMark, ClubMeeting, ClubNote, ClubParallel
from core.audit import record_event
from core.domains import Source
from core.parallels import PARALLELS, parallel_of
from sport import services as sport
from sport.models import MarkMethod

#: событие в журнале ученика: записался, вышел
EVENT = "club"
#: соль подписи токена QR кружка: код секции здесь не подходит
TOKEN_SALT = "clubs.club-mark"
#: ключ сессии браузера, где отметка кружка ждёт входа
HOLD_KEY = "club_scan_hold"
#: сколько ждёт отметка, отсканированная до входа, — как у секций
HOLD_SECONDS = sport.HOLD_SECONDS
#: поля кружка, правка которых идёт в журнал словами «было → стало»
JOURNALED = ("title", "description", "mentor_name", "mentor", "enroll_until", "marks_enabled")


class Refused(ValueError):
    """Так сделать нельзя — текст объясняет почему."""


def _title(user) -> str:
    return (getattr(user, "full_name", "") or getattr(user, "email", "") or "")[:250]


def _actor(user):
    return user if getattr(user, "pk", None) else None


def local_now() -> dt.datetime:
    return timezone.localtime()


def _at(day: dt.date, moment: dt.time) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, moment))


# --- Слова --------------------------------------------------------------------------------


def meeting_words(meeting: ClubMeeting) -> str:
    """«Пн 15:00–18:00»."""
    return f"{sport.short_day(meeting.weekday)} {meeting.starts:%H:%M}–{meeting.ends:%H:%M}"


def schedule_words(meetings) -> str:
    """«Пн, Чт 15:00–18:00», а если время разное — «Пн 15:00–18:00, Чт 16:00–17:00»."""
    rows = sorted(meetings, key=lambda m: (m.weekday, m.starts))
    if not rows:
        return ""
    times = {(m.starts, m.ends) for m in rows}
    if len(times) == 1:
        starts, ends = times.pop()
        return f"{', '.join(sport.short_day(m.weekday) for m in rows)} {starts:%H:%M}–{ends:%H:%M}"
    return ", ".join(meeting_words(m) for m in rows)


def time_words(meeting: ClubMeeting) -> str:
    return f"{meeting.starts:%H:%M}–{meeting.ends:%H:%M}"


def _when_words(moment) -> str:
    return timezone.localtime(moment).strftime("%d.%m.%Y %H:%M") if moment else ""


# --- Окно записи и параллели ---------------------------------------------------------------


def is_open(club: Club, now: dt.datetime | None = None) -> bool:
    """Открыта ли запись: пусто — всегда, дата — до неё включительно."""
    return club.enroll_until is None or (now or timezone.now()) <= club.enroll_until


def parallels_of(club: Club) -> list[int]:
    return sorted(row.parallel for row in club.parallels.all())


def allows(club: Club, parallel: int) -> bool:
    return parallel in parallels_of(club)


def clubs_for_parallel(parallel: int):
    """Живые кружки, куда записываются ученики этой параллели."""
    return Club.objects.filter(parallels__parallel=parallel).distinct()


def any_open_for(student) -> bool:
    """Есть ли кружок для параллели ученика — от этого зависит пункт «Кружки» в меню."""
    return clubs_for_parallel(parallel_of(student)).exists()


def active_rows():
    """Действующие записи живых учеников в живых кружках."""
    return ClubEnrollment.objects.filter(
        ended_at__isnull=True, student__archived_at__isnull=True, club__archived_at__isnull=True
    )


def active_of(student, club: Club) -> ClubEnrollment | None:
    return ClubEnrollment.objects.filter(student=student, club=club, ended_at__isnull=True).first()


# --- Кружок: заведение и правка у администратора -----------------------------------------


def _clock(raw) -> dt.time | None:
    try:
        return dt.time.fromisoformat(str(raw))
    except ValueError:
        return None


def clean_meetings(given) -> list[dict]:
    """Встречи из формы: день недели и время; день — не дважды."""
    if not isinstance(given, list) or not given:
        raise Refused(_("Добавьте хотя бы одну встречу"))
    out: list[dict] = []
    days: set[int] = set()
    for item in given:
        item = item if isinstance(item, dict) else {}
        try:
            weekday = int(item.get("weekday"))
        except (TypeError, ValueError):
            weekday = -1
        if not 0 <= weekday <= 6:
            raise Refused(_("Выберите день недели"))
        starts, ends = _clock(item.get("starts")), _clock(item.get("ends"))
        if starts is None or ends is None or ends <= starts:
            raise Refused(_("Конец встречи должен быть позже начала"))
        if weekday in days:
            raise Refused(_("В один день — одна встреча"))
        days.add(weekday)
        out.append({"weekday": weekday, "starts": starts, "ends": ends})
    return out


def clean_parallels(given) -> list[int]:
    if not isinstance(given, list):
        raise Refused(_("Отметьте параллели"))
    out = sorted({int(p) for p in given if str(p).isdigit() and int(p) in PARALLELS})
    if not out:
        raise Refused(_("Отметьте хотя бы одну параллель"))
    return out


def _snapshot(club: Club) -> dict[str, str]:
    return {
        "title": club.title,
        "description": club.description,
        "mentor_name": club.mentor_name,
        "mentor": _title(club.mentor) if club.mentor_id else "",
        "enroll_until": _when_words(club.enroll_until),
        "marks_enabled": _("включена") if club.marks_enabled else _("выключена"),
        "meetings": schedule_words(club.meetings.all()),
        "parallels": ", ".join(str(p) for p in parallels_of(club)),
    }


def journal_club(club: Club, field: str, old: str, new: str, *, actor) -> None:
    from core.models import AuditLog

    AuditLog.objects.create(
        actor=_actor(actor),
        actor_role=getattr(actor, "role", "") or "",
        model_label="clubs.Club",
        object_id=str(club.pk),
        field_name=field,
        old_value=old[:2000],
        new_value=new[:2000],
        source=Source.MANUAL,
    )


@transaction.atomic
def save_club(club: Club | None, data: dict, *, actor) -> Club:
    """Завести или поправить кружок одним сохранением. Каждое изменённое поле — в журнал.

    `data` уже разобрана вьюхой: `title`, `description`, `mentor_name`,
    `mentor` (учётка с ролью «Ментор» или `None`), `enroll_until`,
    `marks_enabled`, `meetings`, `parallels`.
    """
    with translation.override("ru"):
        created = club is None
        before = {} if created else _snapshot(club)
        club = club or Club(created_by=_actor(actor))
        for key in ("title", "description", "mentor_name", "mentor", "enroll_until", "marks_enabled"):
            if key in data:
                setattr(club, key, data[key])
        if not (club.title or "").strip():
            raise Refused(_("Напишите название кружка"))
        if not (club.mentor_name or "").strip():
            raise Refused(_("Напишите имя ментора"))
        club.save()
        if "meetings" in data:
            club.meetings.all().delete()
            ClubMeeting.objects.bulk_create(ClubMeeting(club=club, **row) for row in data["meetings"])
        if "parallels" in data:
            club.parallels.all().delete()
            ClubParallel.objects.bulk_create(ClubParallel(club=club, parallel=p) for p in data["parallels"])
        after = _snapshot(club)
        if created:
            journal_club(club, "created", "", f"{after['title']} · {after['meetings']}", actor=actor)
            return club
        for field, old in before.items():
            if old != after[field]:
                journal_club(club, field, old, after[field], actor=actor)
    return club


def archive_club(club: Club, *, actor) -> None:
    """В архив, без удаления: записи, отметки, задания и заметки остаются."""
    from core.archive import archive

    archive(club, actor=actor)


# --- Запись и выход ---------------------------------------------------------------------


def _event(student, text: str, *, actor) -> None:
    record_event(student=student, code=EVENT, text=text, actor=actor, source=Source.MANUAL)


def sport_overlaps(student, club: Club) -> list[str]:
    """Встречи кружка, которые идут одновременно с секциями ученика — со всеми его часами.

    Запись это не останавливает — ученик видит предупреждение и решает сам.
    """
    out = []
    for row in sport.active_list(student):
        if row.slot_id is None:
            continue
        slot = row.slot
        for meeting in club.meetings.all():
            if meeting.weekday == slot.weekday and meeting.starts < slot.ends and slot.starts < meeting.ends:
                out.append(
                    _("{day} {club} {club_time} и секция «{section}» {section_time}").format(
                        day=sport.short_day(meeting.weekday),
                        club=club.title,
                        club_time=time_words(meeting),
                        section=row.section.title,
                        section_time=f"{slot.starts:%H:%M}–{slot.ends:%H:%M}",
                    )
                )
    return out


@transaction.atomic
def enroll(*, student, club: Club, actor) -> tuple[ClubEnrollment, list[str]]:
    """Записать ученика сразу: мест без лимита, заявок нет. Второе — пересечения с секцией.

    Повторное нажатие у записанного ничего не меняет. Записаться можно,
    пока окно записи открыто, и только своей параллели.
    """
    locked = Club.objects.select_for_update().filter(pk=club.pk).first()
    if locked is None:
        raise Refused(_("Такого кружка нет"))
    current = ClubEnrollment.objects.select_for_update().filter(student=student, club=locked, ended_at__isnull=True)
    current = current.first()
    if current is not None:
        return current, []
    if not allows(locked, parallel_of(student)):
        raise Refused(_("Этот кружок не для вашей параллели"))
    if not is_open(locked):
        raise Refused(_("Запись закрыта"))
    row = ClubEnrollment.objects.create(student=student, club=locked, created_by=_actor(actor))
    with translation.override("ru"):
        _event(student, _("Кружок: записан — {title}").format(title=locked.title), actor=actor)
    return row, sport_overlaps(student, locked)


@transaction.atomic
def leave(*, student, club: Club, actor) -> ClubEnrollment:
    """Выйти: строка закрывается датой выхода, история остаётся. И при закрытой записи."""
    current = (
        ClubEnrollment.objects.select_for_update().filter(student=student, club=club, ended_at__isnull=True).first()
    )
    if current is None:
        raise Refused(_("Вы не записаны в этот кружок"))
    current.ended_at = timezone.now()
    current.ended_by = _actor(actor)
    current.save(update_fields=["ended_at", "ended_by"])
    with translation.override("ru"):
        _event(student, _("Кружок: вышел — {title}").format(title=club.title), actor=actor)
    return current


def today_for(student, now: dt.datetime | None = None) -> list[tuple[Club, ClubMeeting]]:
    """Кружки ученика со встречей сегодня — строка на главной."""
    now = now or local_now()
    clubs = Club.objects.filter(enrollments__student=student, enrollments__ended_at__isnull=True).distinct()
    out = []
    for club in clubs.prefetch_related("meetings"):
        for meeting in club.meetings.all():
            if meeting.weekday == now.date().weekday():
                out.append((club, meeting))
    out.sort(key=lambda pair: (pair[1].starts, pair[0].order))
    return out


# --- Задание ментора ----------------------------------------------------------------------


def _journal_homework(row: ClubHomework, field: str, old: str, new: str, *, actor) -> None:
    from core.models import AuditLog

    AuditLog.objects.create(
        actor=_actor(actor),
        actor_role=getattr(actor, "role", "") or "",
        model_label="clubs.ClubHomework",
        object_id=str(row.pk),
        field_name=field,
        old_value=old[:2000],
        new_value=new[:2000],
        source=Source.MANUAL,
    )


def _homework_words(row: ClubHomework) -> str:
    return f"{row.club.title}, {_('срок')} {row.due:%d.%m.%Y}: {row.text}"


@transaction.atomic
def publish_homework(*, club: Club, text: str, due: dt.date, upload=None, actor) -> ClubHomework:
    text = (text or "").strip()
    if not text:
        raise Refused(_("Напишите задание"))
    row = ClubHomework(club=club, text=text[:5000], due=due, created_by=_actor(actor))
    if upload is not None:
        row.file_name = upload.name[:200]
        row.file.save(upload.name, upload, save=False)
    row.save()
    with translation.override("ru"):
        _journal_homework(row, "published", "", _homework_words(row), actor=actor)
    return row


@transaction.atomic
def edit_homework(row: ClubHomework, *, text=None, due=None, upload=None, drop_file=False, actor) -> ClubHomework:
    with translation.override("ru"):
        before = _homework_words(row)
        if text is not None:
            text = text.strip()
            if not text:
                raise Refused(_("Напишите задание"))
            row.text = text[:5000]
        if due is not None:
            row.due = due
        if drop_file and row.file:
            row.file.delete(save=False)
            row.file_name = ""
        if upload is not None:
            if row.file:
                row.file.delete(save=False)
            row.file_name = upload.name[:200]
            row.file.save(upload.name, upload, save=False)
        row.save()
        after = _homework_words(row)
        if before != after:
            _journal_homework(row, "edited", before, after, actor=actor)
    return row


@transaction.atomic
def withdraw_homework(row: ClubHomework, *, actor) -> None:
    """Снять задание: оно уходит в архив, ученики кружка его больше не видят."""
    row.archived_at = timezone.now()
    row.save(update_fields=["archived_at"])
    with translation.override("ru"):
        _journal_homework(row, "withdrawn", _homework_words(row), "", actor=actor)


def visible_homework(club: Club):
    return ClubHomework.objects.filter(club=club).order_by("-due", "-created_at")


# --- Заметки ментора -------------------------------------------------------------------------


def add_note(*, club: Club, student, text: str, actor) -> ClubNote:
    text = (text or "").strip()
    if not text:
        raise Refused(_("Напишите заметку"))
    if active_of(student, club) is None:
        raise Refused(_("Ученик не записан в этот кружок"))
    return ClubNote.objects.create(
        club=club, student=student, text=text[:5000], author=_actor(actor), author_title=_title(actor)
    )


def archive_note(note: ClubNote) -> None:
    note.archived_at = timezone.now()
    note.save(update_fields=["archived_at"])


# --- Встреча и QR -------------------------------------------------------------------------


def meeting_on(club: Club, day: dt.date) -> ClubMeeting | None:
    return next((m for m in club.meetings.all() if m.weekday == day.weekday()), None)


def session_state(club: Club, day: dt.date, now: dt.datetime | None = None) -> str:
    """«none» — встречи в этот день нет, «soon» — не началась, «live» — идёт, «past» — закончилась."""
    now = now or local_now()
    meeting = meeting_on(club, day)
    if meeting is None:
        return "none"
    if now < _at(day, meeting.starts):
        return "soon"
    if now < _at(day, meeting.ends):
        return "live"
    return "past"


def _signer() -> signing.Signer:
    return signing.Signer(salt=TOKEN_SALT, sep=".")


def make_token(club: Club, day: dt.date, *, at: float | None = None) -> tuple[str, int]:
    """Токен «кружок.дата.окно.подпись»; окно и срок — как у секций (`sport.services.ttl`)."""
    seconds = sport.ttl()
    moment = at if at is not None else sport.seconds_now()
    window = int(moment // seconds)
    return _signer().sign(f"{club.pk}.{day:%Y%m%d}.{window}"), int(seconds - moment % seconds)


def read_token(token: str, *, at: float | None = None) -> tuple[int, dt.date] | None:
    """Кружок и дата из свежего токена; подделанный, чужой или старый — `None`."""
    try:
        raw = _signer().unsign(str(token or ""))
        club_id, day, window = raw.split(".")
        day_value = dt.datetime.strptime(day, "%Y%m%d").date()
        window_value = int(window)
        club_value = int(club_id)
    except (signing.BadSignature, ValueError):
        return None
    current = int((at if at is not None else sport.seconds_now()) // sport.ttl())
    if window_value not in (current, current - 1):
        return None
    return club_value, day_value


def scan_hold(session, club_id: int, day: dt.date) -> None:
    session[HOLD_KEY] = {"club": club_id, "date": day.isoformat(), "at": sport.seconds_now()}


def take_hold(session) -> tuple[int, dt.date] | None:
    hold = session.pop(HOLD_KEY, None)
    if not isinstance(hold, dict):
        return None
    try:
        if sport.seconds_now() - float(hold["at"]) > HOLD_SECONDS:
            return None
        return int(hold["club"]), dt.date.fromisoformat(str(hold["date"]))
    except (KeyError, TypeError, ValueError):
        return None


def brief(club: Club, day: dt.date) -> dict:
    """Подпись встречи для телефона — в том же виде, что у секции."""
    meeting = meeting_on(club, day)
    return {
        "section": club.title,
        "slot": meeting_words(meeting) if meeting else "",
        "day": meeting.get_weekday_display() if meeting else "",
        "starts": f"{meeting.starts:%H:%M}" if meeting else "",
        "ends": f"{meeting.ends:%H:%M}" if meeting else "",
        "grades": ", ".join(str(p) for p in parallels_of(club)),
        "address": "",
    }


def mark_by_scan(*, student, club_id: int, day: dt.date, now: dt.datetime | None = None) -> dict:
    """Отметка по свежему коду. Отметка выключена — для телефона это устаревший код."""
    now = now or local_now()
    club = Club.objects.prefetch_related("meetings", "parallels").filter(pk=club_id).first()
    if club is None or not club.marks_enabled or day != now.date() or meeting_on(club, day) is None:
        return {"state": "stale"}
    if active_of(student, club) is None:
        return {"state": "not_enrolled", "session": brief(club, day)}
    state = session_state(club, day, now)
    if state == "soon":
        meeting = meeting_on(club, day)
        return {"state": "not_started", "session": brief(club, day), "starts_at": _at(day, meeting.starts).isoformat()}
    if state == "past":
        return {"state": "ended", "session": brief(club, day)}
    with transaction.atomic():
        row, created = ClubMark.objects.get_or_create(
            student=student, club=club, date=day, defaults={"method": MarkMethod.QR, "marked_at": timezone.now()}
        )
    return {
        "state": "marked" if created else "already",
        "session": brief(club, day),
        "marked_at": timezone.localtime(row.marked_at).isoformat(),
    }


@transaction.atomic
def mark_manually(*, student, club: Club, day: dt.date, actor) -> tuple[ClubMark, bool]:
    """Ментор отмечает пришедшего без телефона: на встречу кружка, не в будущем."""
    if not club.marks_enabled:
        raise Refused(_("Отметка посещения в этом кружке выключена"))
    if meeting_on(club, day) is None:
        raise Refused(_("В этот день встречи нет"))
    if day > local_now().date():
        raise Refused(_("Встреча ещё не прошла"))
    if active_of(student, club) is None:
        raise Refused(_("Ученик не записан в этот кружок"))
    return ClubMark.objects.get_or_create(
        student=student,
        club=club,
        date=day,
        defaults={"method": MarkMethod.MANUAL, "marked_by": _actor(actor), "marked_by_title": _title(actor)},
    )


def unmark(*, student, club: Club, day: dt.date) -> int:
    deleted, _rows = ClubMark.objects.filter(student=student, club=club, date=day).delete()
    return deleted


def held_dates(club: Club, first: dt.date, last: dt.date, now: dt.datetime | None = None) -> list[dt.date]:
    """Прошедшие встречи кружка в промежутке: сегодняшняя — когда закончилась."""
    now = now or local_now()
    out = []
    day = first
    while day <= min(last, now.date()):
        if meeting_on(club, day) is not None and (day < now.date() or session_state(club, day, now) == "past"):
            out.append(day)
        day += dt.timedelta(days=1)
    return out


def month_percent(row: ClubEnrollment, now: dt.datetime | None = None) -> int | None:
    """Посещение за текущий месяц с даты записи; встреч не было — `None`."""
    now = now or local_now()
    first = max(now.date().replace(day=1), timezone.localtime(row.enrolled_at).date())
    dates = held_dates(row.club, first, now.date(), now)
    if not dates:
        return None
    came = ClubMark.objects.filter(student_id=row.student_id, club_id=row.club_id, date__in=dates).count()
    return round(100 * came / len(dates))
