"""Что происходит после решения по строке очереди и при передаче владельцу (фаза 62).

Один модуль на всё, что не является самим решением: доведение документа
до статуса, уведомления куратору и владельцу домена, передача строки
и её возврат. Зовётся из `engine` после того, как решение записано,
и из вьюх передачи — второго места, откуда идут уведомления по очереди, нет.

Кому что приходит:

* владелец домена решил строку из очереди куратора — куратору группы;
* владелец решил переданную куратором строку — тому, кто передал;
* куратор передал строку — владельцу домена строки (Кымбат — экзамены,
  Асем — документы): адресат от домена, а не всегда Кымбат;
* ученик перезагрузил документ после отклонения — куратору группы.
"""

from __future__ import annotations

from django.utils import timezone

from core.audit import record_event
from core.domains import DOMAINS, ROLE_CURATOR, ROLE_TITLES
from core.models import Notification
from suggestions.models import Suggestion, SuggestionSource, SuggestionStatus


class EscalationRefused(ValueError):
    """Передать или вернуть нельзя — текст объясняет почему."""


def owners_of(domain_code: str):
    """Живые учётные записи владельца домена — кому уходит переданное."""
    from accounts.models import User

    domain = DOMAINS.get(domain_code)
    if domain is None:
        return User.objects.none()
    return User.objects.filter(role=domain.role, is_active=True)


def owner_title(domain_code: str) -> str:
    """«Кымбат» или «Асем» — по реестру, не по строке в коде."""
    domain = DOMAINS.get(domain_code)
    return domain.owner_name if domain else ""


def _student_of(suggestion: Suggestion):
    change = suggestion.changes.select_related("student", "student__group").filter(student__isnull=False).first()
    return change.student if change else None


def _curator_of(student):
    from accounts.curators import curator_of

    if student is None or not student.group_id:
        return None
    assignment = curator_of(student.group)
    return assignment.curator if assignment else None


def _row_title(suggestion: Suggestion) -> str:
    """Чем была строка — для текста уведомления."""
    from core.labels import field_title

    if suggestion.source_type == SuggestionSource.DOCUMENT:
        from students.documents import document_of

        document = document_of(suggestion)
        return document.get_doc_type_display() if document else "документ"
    change = suggestion.changes.first()
    return field_title(change.model_label, change.field_name) if change else "строка"


def _notify(recipient, *, kind: str, template: str, link: str, **params) -> None:
    from materials.services import notify

    notify(recipient, kind=kind, template=template, link=link, **params)


def after_decision(suggestion: Suggestion, *, actor) -> None:
    """После решения: документ — до статуса, людям — уведомления."""
    if suggestion.role != "student":
        return
    if suggestion.source_type == SuggestionSource.DOCUMENT:
        from students.documents import after_decision as settle_document

        settle_document(suggestion, actor=actor)

    student = _student_of(suggestion)
    if student is None:
        return
    verb = (
        "подтвердил"
        if suggestion.status in (SuggestionStatus.APPLIED, SuggestionStatus.PARTIALLY_APPLIED)
        else "отклонил"
    )
    who = ROLE_TITLES.get(getattr(actor, "role", ""), "")
    link = f"/students/{student.pk}"

    # переданную строку решил владелец — отвечаем тому, кто передал
    if suggestion.escalated_by_id and getattr(actor, "pk", None) != suggestion.escalated_by_id:
        _notify(
            suggestion.escalated_by,
            kind=Notification.Kind.ESCALATION_ANSWERED,
            template="{who} {verb}: {what} · {student} — ответ на переданное",
            link=link,
            who=who,
            verb=verb,
            what=_row_title(suggestion),
            student=student.full_name,
        )
        return

    # строку из очереди куратора решил владелец домена — куратор должен знать
    if getattr(actor, "role", "") != ROLE_CURATOR:
        curator = _curator_of(student)
        if curator is not None and curator.pk != getattr(actor, "pk", None):
            _notify(
                curator,
                kind=Notification.Kind.QUEUE_DECIDED,
                template="{who} {verb}: {what} · {student} — из вашей очереди",
                link=link,
                who=who,
                verb=verb,
                what=_row_title(suggestion),
                student=student.full_name,
            )


def escalate(suggestion: Suggestion, *, actor, comment: str) -> Suggestion:
    """Передать строку владельцу её домена с комментарием."""
    comment = comment.strip()
    if not comment:
        raise EscalationRefused("Напишите, что смущает: владелец домена должен понять, зачем ему строка")
    if suggestion.status != SuggestionStatus.PENDING:
        raise EscalationRefused("Строка уже решена — передавать нечего")
    if suggestion.escalated_by_id:
        raise EscalationRefused("Строка уже передана")

    suggestion.escalated_by = actor
    suggestion.escalated_at = timezone.now()
    suggestion.escalation_comment = comment[:500]
    suggestion.save(update_fields=["escalated_by", "escalated_at", "escalation_comment"])

    student = _student_of(suggestion)
    owner = owner_title(suggestion.domain_code)
    for recipient in owners_of(suggestion.domain_code):
        _notify(
            recipient,
            kind=Notification.Kind.ESCALATION_REQUEST,
            template="Куратор {curator} передал: {what} · {student}. «{comment}»",
            link="/suggestions",
            curator=actor.full_name or actor.email,
            what=_row_title(suggestion),
            student=student.full_name if student else "",
            comment=comment[:120],
        )
    if student is not None:
        record_event(
            student=student, code="escalation", text=f"{owner}: {_row_title(suggestion)} — {comment}", actor=actor
        )
    return suggestion


def unescalate(suggestion: Suggestion, *, actor) -> Suggestion:
    """Вернуть строку себе — пока владелец не решил."""
    if suggestion.status != SuggestionStatus.PENDING:
        raise EscalationRefused("Владелец домена уже решил эту строку")
    if suggestion.escalated_by_id != getattr(actor, "pk", None):
        raise EscalationRefused("Вернуть можно только то, что передавали вы")
    suggestion.escalated_by = None
    suggestion.escalated_at = None
    suggestion.escalation_comment = ""
    suggestion.save(update_fields=["escalated_by", "escalated_at", "escalation_comment"])
    student = _student_of(suggestion)
    if student is not None:
        record_event(student=student, code="escalation_returned", text=_row_title(suggestion), actor=actor)
    return suggestion


def escalate_student(student, *, actor, domain_code: str, comment: str) -> int:
    """Передать вопрос по ученику без строки очереди: уведомление владельцу и журнал."""
    comment = comment.strip()
    if not comment:
        raise EscalationRefused("Напишите, что нужно от владельца домена")
    if domain_code not in DOMAINS:
        raise EscalationRefused("Такого домена нет")
    sent = 0
    for recipient in owners_of(domain_code):
        _notify(
            recipient,
            kind=Notification.Kind.ESCALATION_REQUEST,
            template="Куратор {curator} передал вопрос по {student}: «{comment}»",
            link=f"/students/{student.pk}",
            curator=actor.full_name or actor.email,
            student=student.full_name,
            comment=comment[:200],
        )
        sent += 1
    record_event(student=student, code="escalation", text=f"{owner_title(domain_code)}: {comment}", actor=actor)
    return sent


def document_reuploaded(document) -> None:
    """Ученик загрузил тот же тип после отклонения — куратору группы."""
    from students.models import DocumentStatus, StudentDocument

    earlier = (
        StudentDocument.objects.filter(
            student=document.student, doc_type=document.doc_type, status=DocumentStatus.REJECTED
        )
        .exclude(pk=document.pk)
        .exists()
    )
    if not earlier:
        return
    curator = _curator_of(document.student)
    if curator is None:
        return
    _notify(
        curator,
        kind=Notification.Kind.DOCUMENT_REUPLOADED,
        template="{student} перезагрузил документ «{doc}» после отклонения",
        link="/queue",
        student=document.student.full_name,
        doc=document.get_doc_type_display(),
    )
