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
