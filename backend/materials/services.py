"""Что происходит с материалом: загрузка, проверка Арманом, отметки, жалобы.

XP начисляется после одобрения, а не при загрузке: иначе выгоднее залить
что попало. И начисляется за действие — «материал прошёл проверку», —
а не за оценку материала другими (инвариант №12).
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.models import Notification
from core.phrasing import counted
from engagement.models import XPKind
from engagement.scoring import award
from materials.files import check_count, inspect
from materials.models import (
    MaterialComment,
    MaterialFile,
    MaterialHelpful,
    MaterialRequest,
    MaterialStatus,
    StudyMaterial,
)
from students.models import Activity, ActivityCategory


def reviewers():
    """Кто проверяет материалы — владелец домена талантов."""
    from accounts.models import User
    from core.domains import DOMAINS

    return User.objects.filter(role=DOMAINS["talent"].role, is_active=True)


def notify(recipient, *, kind: str, text: str, link: str = "") -> Notification | None:
    """Уведомление человеку. Себе самому не пишем — это шум."""
    if recipient is None:
        return None
    return Notification.objects.create(recipient=recipient, kind=kind, text=text, link=link)


def notify_reviewers(*, kind: str, text: str, link: str = "", exclude=None) -> None:
    for user in reviewers():
        if exclude is not None and user.pk == exclude.pk:
            continue
        notify(user, kind=kind, text=text, link=link)


# --- Загрузка -------------------------------------------------------------


@transaction.atomic
def attach_files(material: StudyMaterial, uploads: list) -> list[MaterialFile]:
    """Приложить файлы к материалу, проверив каждый по содержимому."""
    check_count(material.files.count(), len(uploads))
    saved: list[MaterialFile] = []
    for upload in uploads:
        info = inspect(upload)
        row = MaterialFile(
            material=material,
            original_name=upload.name[:250],
            content_type=info.content_type,
            extension=info.extension,
            size=info.size,
            checksum=info.checksum,
        )
        row.file.save(upload.name, upload, save=False)
        row.save()
        saved.append(row)
    return saved


def announce_upload(material: StudyMaterial) -> None:
    """Сказать проверяющим, что появился новый материал."""
    notify_reviewers(
        kind=Notification.Kind.MATERIAL_PENDING,
        text=f"{material.author.full_name} загрузил материал «{material.title}» — ждёт проверки",
        link=f"/materials/review/{material.pk}",
    )


# --- Проверка Арманом -----------------------------------------------------


@transaction.atomic
def approve(material: StudyMaterial, *, actor) -> dict:
    """Одобрить материал: он попадает в библиотеку, автору идёт XP.

    XP — за действие «поделился разбором, и его приняли», а не за то,
    насколько материал понравился другим (инвариант №12).
    """
    material.status = MaterialStatus.APPROVED
    material.reject_reason = ""
    material.reviewed_by = actor
    material.reviewed_at = timezone.now()
    material.save(update_fields=["status", "reject_reason", "reviewed_by", "reviewed_at", "updated_at"])

    activity = _activity_for(material)
    event = award(
        material.author,
        kind=XPKind.MATERIAL_APPROVED,
        object_label="materials.StudyMaterial",
        object_id=str(material.pk),
        note=f"Материал «{material.title}» прошёл проверку",
    )

    closed = _close_request(material)
    notify(
        getattr(material.author, "user", None),
        kind=Notification.Kind.MATERIAL_REVIEWED,
        text=f"Ваш материал «{material.title}» одобрен и появился в библиотеке",
        link=f"/materials/{material.pk}",
    )
    return {
        "status": material.status,
        "xp": event.amount if event else 0,
        "activity": activity.pk if activity else None,
        "closed_request": closed,
        "detail": f"«{material.title}» в библиотеке. Автору начислено XP, запись добавлена в активности",
    }


def _activity_for(material: StudyMaterial) -> Activity | None:
    """Одобренный материал усиливает портфолио — это домен Армана.

    Второй раз ту же запись не заводим: материал могли отклонить
    и одобрить снова.
    """
    existing = Activity.all_objects.filter(
        student=material.author,
        category=ActivityCategory.PROJECT,
        title=f"Материал: {material.title}",
    ).first()
    if existing is not None:
        return existing
    return Activity.objects.create(
        student=material.author,
        category=ActivityCategory.PROJECT,
        subject=material.subject,
        title=f"Материал: {material.title}",
        date=timezone.localdate(),
        description=f"Разбор по теме «{material.topic}», прошёл проверку директора талантов",
        is_confirmed=True,
    )


def _close_request(material: StudyMaterial) -> int | None:
    """Запрос закрывается одобренным материалом, а не самой загрузкой."""
    request = material.request
    if request is None or request.status == MaterialRequest.Status.CLOSED:
        return None
    request.status = MaterialRequest.Status.CLOSED
    request.closed_at = timezone.now()
    request.save(update_fields=["status", "closed_at"])
    notify(
        getattr(request.author, "user", None),
        kind=Notification.Kind.MATERIAL_REQUEST,
        text=f"По вашему запросу «{request.topic}» появился материал «{material.title}»",
        link=f"/materials/{material.pk}",
    )
    return request.pk


@transaction.atomic
def reject(material: StudyMaterial, *, actor, reason: str) -> dict:
    """Отклонить с причиной. Автор её видит, в библиотеке материала нет."""
    material.status = MaterialStatus.REJECTED
    material.reject_reason = reason
    material.reviewed_by = actor
    material.reviewed_at = timezone.now()
    material.save(update_fields=["status", "reject_reason", "reviewed_by", "reviewed_at", "updated_at"])

    notify(
        getattr(material.author, "user", None),
        kind=Notification.Kind.MATERIAL_REVIEWED,
        text=f"Материал «{material.title}» не прошёл проверку: {reason}",
        link=f"/materials/{material.pk}",
    )
    return {"status": material.status, "detail": f"«{material.title}» отклонён, автор увидит причину"}


# --- Полезность, комментарии, жалобы --------------------------------------


@transaction.atomic
def mark_helpful(material: StudyMaterial, student) -> dict:
    """«Было полезно» — один голос от ученика.

    Публичного рейтинга авторов нет: счётчик нужен для сортировки
    библиотеки, а не для соревнования между детьми.
    """
    _mark, created = MaterialHelpful.objects.get_or_create(material=material, student=student)
    if not created:
        MaterialHelpful.objects.filter(material=material, student=student).delete()
        StudyMaterial.objects.filter(pk=material.pk).update(helpful_count=F("helpful_count") - 1)
        material.refresh_from_db(fields=["helpful_count"])
        return {"marked": False, "helpful_count": material.helpful_count, "detail": "Отметка снята"}

    StudyMaterial.objects.filter(pk=material.pk).update(helpful_count=F("helpful_count") + 1)
    material.refresh_from_db(fields=["helpful_count"])
    return {"marked": True, "helpful_count": material.helpful_count, "detail": "Спасибо, отметили"}


def announce_comment(comment: MaterialComment) -> None:
    """Автору материала и проверяющим — что под материалом появился вопрос."""
    material = comment.material
    author_user = getattr(material.author, "user", None)
    who = comment.author.full_name or comment.author.email
    if author_user is not None and author_user.pk != comment.author.pk:
        notify(
            author_user,
            kind=Notification.Kind.MATERIAL_COMMENT,
            text=f"{who} оставил вопрос под вашим материалом «{material.title}»",
            link=f"/materials/{material.pk}",
        )
    notify_reviewers(
        kind=Notification.Kind.MATERIAL_COMMENT,
        text=f"{who} оставил вопрос под материалом «{material.title}»",
        link=f"/materials/{material.pk}",
        exclude=comment.author,
    )


def announce_report(report) -> None:
    """Жалоба уходит проверяющим — разбирается человек, не система."""
    target = report.material or (report.comment.material if report.comment_id else None)
    title = target.title if target is not None else "материал"
    what = "комментарий" if report.comment_id else "материал"
    notify_reviewers(
        kind=Notification.Kind.MATERIAL_REPORT,
        text=f"Жалоба на {what} под «{title}»: {report.reason[:150]}",
        link="/materials/review",
    )


def queue_summary(pending: int, reports: int) -> str:
    """Строка над очередью проверки — числами, а не «есть новые»."""
    parts = []
    if pending:
        parts.append(counted(pending, ("материал ждёт", "материала ждут", "материалов ждут")) + " проверки")
    if reports:
        parts.append(counted(reports, ("жалоба", "жалобы", "жалоб")) + " не разобрано")
    return "; ".join(parts) if parts else "Очередь пуста — всё разобрано"
