"""Блок «Поступление» в карточке ученика — один на все роли (фаза 70).

До 70-й блок собирался в двух местах и потому был разным: у куратора
одиннадцать строк, у Асем и администратора — три поля из реестра
доменов. Владелец домена видел меньше куратора, и это была не разница
прав, а разница кода.

Здесь он собирается один раз, и порядок строк — порядок колонок
таблицы Асем, той самой, которую она загружает импортом:

    телефон · почта · пароль от почты · пароль от Common App ·
    почта Common App · папка · паспорт со сроком · GPA ·
    IELTS-1..3 · SAT-1..3 · табель · рекомендация

ФИО в блоке нет: оно в шапке карточки. Ничего сверх колонок таблицы
тоже нет — правило фазы 70: что не в таблице, того в карточке нет.

Пароли здесь только признаком «есть / нет»: сам пароль отдаёт отдельный
показ, и каждый показ пишется в журнал ученика (фаза 65).
"""

from __future__ import annotations

from django.utils import translation
from django.utils.translation import gettext, gettext_noop
from django.utils.translation import gettext as _

from students.models import AttemptSource, CredentialKind, DocumentType, ExamAttempt, Student

#: Сколько попыток каждого экзамена в таблице Асем: IELTS-1..3, SAT-1..3.
#: Колонок ровно три, и блок показывает столько же — пустые прочерком
ATTEMPT_SLOTS = 3

#: Экзамены блока в порядке колонок таблицы
BLOCK_EXAMS = ("IELTS", "SAT")


def may_edit(user, student: Student) -> bool:
    """Кто правит поля профиля поступления прямо в блоке.

    Асем — владелец домена, администратор — по решению фазы 68, куратор —
    по своим группам (фаза 70): телефон и почту он уточняет у родителя
    первым и переписывать их через владельца домена незачем.
    """
    from core.domains import can_write
    from core.scope import sees_student

    role = getattr(user, "role", "")
    if role == "student":
        return False
    if role == "curator":
        return sees_student(user, student.pk)
    return can_write(role, "students.AdmissionProfile", "student_phone") and sees_student(user, student.pk)


def may_edit_whole(user, student: Student) -> bool:
    """Кто правит каждую строку блока: его владелец Асем и администратор.

    Куратору блок целиком не отдан: попытки и документы он вносит своим
    путём, с вкладок «Экзамены» и «Документы» (прямая запись куратора),
    а здесь правит только поля профиля. Право — из реестра доменов.
    """
    from core.domains import keeps_admission_block
    from core.scope import sees_student

    return keeps_admission_block(getattr(user, "role", "")) and sees_student(user, student.pk)


class BlockRefusal(Exception):
    """Отказ словами: что не так со значением строки блока."""


def save_attempt(student: Student, *, actor, exam: str, score, date=None, attempt_id=None) -> ExamAttempt:
    """Записать попытку из блока: поправить существующую или занять пустой слот.

    Попытка блока — строка таблицы поступления: официальная сдача
    с источником «таблица Асем». Правятся только такие; остальные попытки
    ученика ведёт домен экзаменов. Дата необязательна — как в таблице:
    без неё попытка помечается «дата уточняется».
    """
    from django.utils import timezone

    from core.audit import apply_changes, record_change
    from core.domains import Source, scale_of
    from students.models import AttemptFormat

    exam = str(exam or "").upper()
    if exam not in BLOCK_EXAMS:
        raise BlockRefusal(_("В блоке «Поступление» — попытки IELTS и SAT"))
    scale = scale_of(exam)
    if scale is not None and not scale.holds(score):
        raise BlockRefusal(_("Балл {exam} — {hint}").format(exam=exam, hint=scale.hint))
    table_rows = ExamAttempt.objects.filter(student=student, exam_type=exam, source=AttemptSource.ADMISSION_IMPORT)
    wanted = {"total_score": str(score).replace(",", ".")}
    if date:
        wanted |= {"date": date, "date_unknown": False}

    if attempt_id:
        attempt = table_rows.filter(pk=attempt_id).first()
        if attempt is None:
            raise BlockRefusal(_("Этой попытки нет среди строк таблицы поступления"))
        apply_changes(attempt, wanted, actor=actor, source=Source.MANUAL)
        return attempt

    if table_rows.count() >= ATTEMPT_SLOTS:
        raise BlockRefusal(
            _("Слотов {exam} в таблице {slots}, все заняты — поправьте существующую попытку").format(
                exam=exam, slots=ATTEMPT_SLOTS
            )
        )
    attempt = ExamAttempt.objects.create(
        student=student,
        exam_type=exam,
        attempt_format=AttemptFormat.OFFICIAL,
        source=AttemptSource.ADMISSION_IMPORT,
        date=date or timezone.localdate(),
        date_unknown=not date,
        total_score=wanted["total_score"],
    )
    # сигналы пишут правки, а не создание: заведение строки фиксируем сами
    record_change(instance=attempt, field_name="total_score", old_value="", new_value=attempt.total_score, actor=actor)
    return attempt


def save_link(student: Student, *, actor, code: str, url: str):
    """Ссылка на паспорт, табель или рекомендацию — документом-ссылкой.

    То же, что делает таблица поступления при загрузке: есть документ-ссылка
    этого типа — правится его адрес, нет — заводится новый. Внесённое
    владельцем блока проверки не ждёт: проверять самого себя незачем.
    """
    from django.core.exceptions import ValidationError
    from django.core.validators import URLValidator
    from django.utils import timezone

    from core.audit import apply_changes, record_change
    from core.domains import Source
    from students.documents import TABLE_DOCUMENTS
    from students.models import DocumentStatus, StudentDocument

    if code not in TABLE_DOCUMENTS:
        raise BlockRefusal(_("В блоке «Поступление» — ссылки на паспорт, табель и рекомендацию"))
    url = str(url or "").strip()
    try:
        URLValidator(schemes=("http", "https"))(url)
    except ValidationError as error:
        raise BlockRefusal(_("Нужна ссылка целиком, с https://")) from error

    existing = (
        StudentDocument.objects.filter(student=student, doc_type=code)
        .exclude(external_url="")
        .order_by("created_at", "id")
        .last()
    )
    if existing is not None:
        apply_changes(existing, {"external_url": url}, actor=actor, source=Source.MANUAL)
        return existing
    admission = getattr(student, "admission", None)
    document = StudentDocument.objects.create(
        student=student,
        doc_type=code,
        # название хранится в базе как данные — по-русски, как остальные данные школы
        title=_ru_title(gettext_noop("{document}: ссылка из блока «Поступление»"), code),
        external_url=url,
        expires_at=getattr(admission, "passport_expires_at", None) if code == DocumentType.PASSPORT else None,
        uploaded_by=actor,
        status=DocumentStatus.CONFIRMED,
        reviewed_at=timezone.now(),
        reviewed_by=actor,
    )
    record_change(instance=document, field_name="external_url", old_value="", new_value=url, actor=actor)
    record_change(instance=document, field_name="status", old_value="", new_value=DocumentStatus.CONFIRMED, actor=actor)
    return document


def _attempts(student: Student) -> dict[str, list[dict]]:
    """Попытки из таблицы Асем, разложенные по слотам экзамена.

    Из импорта, а не из всех попыток вообще: в блоке — колонки таблицы,
    а платформенные пробники живут в своём домене и в своей карточке.
    """
    rows: dict[str, list[dict]] = {exam: [] for exam in BLOCK_EXAMS}
    for row in ExamAttempt.objects.filter(student=student, source=AttemptSource.ADMISSION_IMPORT).order_by(
        "exam_type", "date", "created_at"
    ):
        slot = rows.get(row.exam_type)
        if slot is None or len(slot) >= ATTEMPT_SLOTS:
            continue
        slot.append(
            {
                "id": row.pk,
                "score": float(row.total_score) if row.total_score is not None else None,
                "date": row.date,
                # дату в таблице заполняют не всегда, и придумывать её мы
                # не стали: в карточке так и написано — «дата уточняется»
                "date_unknown": row.date_unknown,
            }
        )
    return rows


def build(user, student: Student) -> dict:
    """Собрать блок для этого человека. Ничего не меняет."""
    from core.domains import DOMAINS, can_write
    from core.scope import sees_student
    from students import credentials, documents
    from students.documents import TABLE_DOCUMENTS

    admission = getattr(student, "admission", None)
    exam_profile = getattr(student, "exam", None)
    present = credentials.state(student)
    doc_state = documents.state_of(Student.objects.filter(pk=student.pk))[student.pk]
    # срок паспорта — поле профиля (фаза 71); у документа он тоже есть,
    # но в таблице ссылки может не быть, а срок — есть
    passport_expires = getattr(admission, "passport_expires_at", None) or doc_state["cells"]["passport"]["expires_at"]
    role = getattr(user, "role", "")

    return {
        "owner": DOMAINS["admission"].owner_name,
        "student_phone": getattr(admission, "student_phone", "") or "",
        # «Электронный адрес» — личная почта из таблицы Асем (фаза 71):
        # текст в карточке, к входу в систему отношения не имеет
        "email": getattr(admission, "personal_email", "") or "",
        "common_app_email": getattr(admission, "common_app_email", "") or "",
        "drive_folder_url": getattr(admission, "drive_folder_url", "") or "",
        "passport_expires_at": passport_expires,
        # GPA показывается только здесь (фаза 71); поле и право — у Кымбат
        "gpa": float(exam_profile.gpa) if getattr(exam_profile, "gpa", None) is not None else None,
        "may_edit_gpa": role != "student"
        and can_write(role, "students.ExamProfile", "gpa")
        and sees_student(user, student.pk),
        "may_edit": may_edit(user, student),
        # карандаш у каждой строки: срок паспорта, попытки и ссылки на документы
        "may_edit_whole": may_edit_whole(user, student),
        "may_reveal": credentials.may_view(user, student),
        "may_edit_credentials": credentials.may_edit(user, student),
        "credentials": [
            {"kind": kind, "title": CredentialKind(kind).label, "present": present[kind]}
            for kind in CredentialKind.values
        ],
        "attempts": [{"exam": exam, "rows": _attempts(student)[exam], "slots": ATTEMPT_SLOTS} for exam in BLOCK_EXAMS],
        # документы-ссылки из таблицы: паспорт со сроком годности, табель
        # и рекомендация. Открываются в новой вкладке, пустое — прочерком
        "documents": [
            {
                "code": code,
                "title": DocumentType(code).label,
                **{
                    key: doc_state["cells"][code][key]
                    for key in ("state", "document", "is_link", "external_url", "expires_at")
                },
            }
            for code in TABLE_DOCUMENTS
        ],
    }


def _ru_title(template: str, doc_type: str) -> str:
    """Название документа-ссылки для базы: по-русски, как остальные данные школы."""
    with translation.override("ru"):
        return gettext(template).format(document=str(DocumentType(doc_type).label))
