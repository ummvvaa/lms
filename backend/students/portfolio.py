"""Портфолио ученика: процент заполнения, следующие шаги, чек-лист, CV.

Процент заполнения — это «сколько ученик о себе рассказал», а не
готовность к подаче: с Readiness Score его не путать. Считается по
заполненности разделов, веса — в настройках (`PORTFOLIO_WEIGHTS`),
школа меняет формулу без выката.

Внесённое учеником и ещё не подтверждённое тоже считается заполненным:
свою часть он сделал, решение директора не должно держать процент на нуле.
"""

from __future__ import annotations

from django.conf import settings

from core.domains import ROLE_STUDENT
from students.models import Activity, DocumentType, Student, StudentDocument

#: Типы документов, из которых складывается чек-лист готовности.
#: «Прочее» в готовность не входит: это ящик для остального.
REQUIRED_DOCUMENTS: tuple[str, ...] = (
    DocumentType.ATTESTAT,
    DocumentType.TRANSCRIPT,
    DocumentType.EXAM_CERTIFICATE,
    DocumentType.RECOMMENDATION,
    DocumentType.PASSPORT,
)

#: Поля профиля поступления, которые заполняет ученик о своей цели.
PROFILE_FIELDS = ("target_level", "target_year", "target_country", "target_major", "cost_priority")


def _pending_fields(student: Student, model_label: str) -> set[str]:
    """Поля, по которым висит нерешённое предложение ученика (фаза 37)."""
    from suggestions.models import SuggestionChange, SuggestionStatus

    return set(
        SuggestionChange.objects.filter(
            suggestion__role=ROLE_STUDENT,
            suggestion__status=SuggestionStatus.PENDING,
            student=student,
            model_label=model_label,
        ).values_list("field_name", flat=True)
    )


def _pending_new_categories(student: Student) -> set[str]:
    """Категории активностей, ждущих решения как новые записи."""
    from suggestions.models import SuggestionChange, SuggestionStatus

    return set(
        SuggestionChange.objects.filter(
            suggestion__role=ROLE_STUDENT,
            suggestion__status=SuggestionStatus.PENDING,
            student=student,
            model_label="students.Activity",
            field_name="category",
        )
        .exclude(new_object_key="")
        .values_list("new_value", flat=True)
    )


def documents_checklist(student: Student) -> list[dict]:
    """Чек-лист готовности документов: сразу видно, чего не хватает."""
    have = set(StudentDocument.objects.filter(student=student).values_list("doc_type", flat=True))
    return [{"code": code, "title": DocumentType(code).label, "done": code in have} for code in REQUIRED_DOCUMENTS]


def _sections(student: Student) -> list[dict]:
    """Разделы портфолио: доля заполненного и подсказка следующего шага."""
    weights = settings.PORTFOLIO_WEIGHTS

    admission = getattr(student, "admission", None)
    pending_admission = _pending_fields(student, "students.AdmissionProfile")
    profile_filled = sum(
        1 for f in PROFILE_FIELDS if getattr(admission, f, None) not in (None, "") or f in pending_admission
    )

    exam = getattr(student, "exam", None)
    pending_exam = _pending_fields(student, "students.ExamProfile")
    academic_items = (
        getattr(exam, "gpa", None) is not None or "gpa" in pending_exam,
        getattr(exam, "ielts_current", None) is not None or "ielts_current" in pending_exam,
        getattr(exam, "sat_current", None) is not None or "sat_current" in pending_exam,
        student.exam_attempts.filter(exam_type="ENT").exists(),
    )

    pending_new = _pending_new_categories(student)
    achievements = Activity.objects.filter(student=student).exclude(category="olympiad").exists() or bool(
        pending_new - {"olympiad"}
    )
    olympiads = Activity.objects.filter(student=student, category="olympiad").exists() or "olympiad" in pending_new

    sport = getattr(student, "sport", None)
    pending_sport = _pending_fields(student, "students.SportProfile")
    sport_told = getattr(sport, "sport_type_id", None) is not None or "sport_type" in pending_sport

    checklist = documents_checklist(student)
    documents_done = sum(1 for row in checklist if row["done"])

    return [
        {
            "code": "profile",
            "title": "Профиль поступления",
            "weight": weights["profile"],
            "value": profile_filled / len(PROFILE_FIELDS),
            "next": "Заполните цель: уровень, год, страну, специальность и бюджет",
            "tab": "overview",
        },
        {
            "code": "academics",
            "title": "Академические результаты",
            "weight": weights["academics"],
            "value": sum(academic_items) / len(academic_items),
            "next": "Внесите баллы: GPA, IELTS, SAT и результат ЕНТ",
            "tab": "overview",
        },
        {
            "code": "achievements",
            "title": "Достижения",
            "weight": weights["achievements"],
            "value": 1.0 if achievements else 0.0,
            "next": "Добавьте первое достижение: проект, конкурс или волонтёрство",
            "tab": "achievements",
        },
        {
            "code": "olympiads",
            "title": "Олимпиады",
            "weight": weights["olympiads"],
            "value": 1.0 if olympiads else 0.0,
            "next": "Отметьте участие в олимпиаде — даже школьный этап считается",
            "tab": "olympiads",
        },
        {
            "code": "sport",
            "title": "Спорт",
            "weight": weights["sport"],
            "value": 1.0 if sport_told else 0.0,
            "next": "Укажите вид спорта и уровень занятий",
            "tab": "sport",
        },
        {
            "code": "documents",
            "title": "Документы",
            "weight": weights["documents"],
            "value": documents_done / len(checklist),
            "next": "Загрузите недостающие документы из чек-листа",
            "tab": "documents",
        },
    ]


def state(student: Student) -> dict:
    """Портфолио целиком: процент, разделы, следующие шаги, чек-лист."""
    sections = _sections(student)
    total_weight = sum(s["weight"] for s in sections) or 1.0
    percent = round(sum(s["weight"] * s["value"] for s in sections) / total_weight * 100)

    next_steps = [
        {"text": s["next"], "tab": s["tab"]}
        for s in sorted(sections, key=lambda s: s["weight"], reverse=True)
        if s["value"] < 1.0
    ][:4]

    exam = getattr(student, "exam", None)
    ent = student.exam_attempts.filter(exam_type="ENT").order_by("-date").first()

    return {
        "percent": percent,
        "sections": [
            {
                "code": s["code"],
                "title": s["title"],
                "value": round(s["value"] * 100),
                "tab": s["tab"],
            }
            for s in sections
        ],
        "next_steps": next_steps,
        "documents": documents_checklist(student),
        "academics": {
            "gpa": str(exam.gpa) if getattr(exam, "gpa", None) is not None else None,
            "ielts": str(exam.ielts_current) if getattr(exam, "ielts_current", None) is not None else None,
            "sat": exam.sat_current if exam is not None else None,
            "ent": str(ent.total_score) if ent is not None and ent.total_score is not None else None,
        },
    }


def cv_html(student: Student) -> str:
    """Резюме из портфолио. Собирается по запросу, на сервере не хранится.

    Внутренних ярлыков здесь нет и быть не может: собираем только то,
    что ученик видит о себе сам (инвариант №7).
    """
    from students.models import Competition

    admission = getattr(student, "admission", None)
    exam = getattr(student, "exam", None)
    sport = getattr(student, "sport", None)

    def esc(value) -> str:
        return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if value is not None else ""

    rows: list[str] = []

    def section(title: str, items: list[str]) -> None:
        if not items:
            return
        rows.append(f"<h2>{esc(title)}</h2><ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>")

    goal = []
    if admission is not None:
        if admission.target_level:
            goal.append(esc(admission.get_target_level_display()))
        if admission.target_year:
            goal.append(f"год поступления — {admission.target_year}")
        if admission.target_major:
            goal.append(esc(admission.target_major))
        if admission.target_country:
            goal.append(esc(admission.target_country))
    section("Цель поступления", [" · ".join(goal)] if goal else [])

    scores = []
    if getattr(exam, "gpa", None) is not None:
        scores.append(f"GPA — {esc(exam.gpa)}")
    if getattr(exam, "ielts_current", None) is not None:
        scores.append(f"IELTS — {esc(exam.ielts_current)}")
    if getattr(exam, "sat_current", None) is not None:
        scores.append(f"SAT — {esc(exam.sat_current)}")
    ent = student.exam_attempts.filter(exam_type="ENT").order_by("-date").first()
    if ent is not None and ent.total_score is not None:
        scores.append(f"ЕНТ — {esc(ent.total_score)}")
    section("Академические результаты", scores)

    # в CV идут все внесённые активности: запись из предложения ученика
    # уже прошла решение директора, а галочка «подтверждена» — отдельная
    # отметка проверки доказательства, и её отсутствие не прячет строку
    # из портфолио — не должно прятать и из CV
    entered = Activity.objects.filter(student=student)
    section(
        "Достижения",
        [
            f"{esc(a.title)}" + (f" · {esc(a.date)}" if a.date else "") + f" · {esc(a.get_category_display())}"
            for a in entered.exclude(category="olympiad")[:20]
        ],
    )
    section(
        "Олимпиады",
        [
            f"{esc(a.title)}" + (f" · {esc(a.subject.name)}" if a.subject_id else "")
            for a in entered.filter(category="olympiad")[:20]
        ],
    )

    sport_lines = []
    if getattr(sport, "sport_type_id", None):
        line = esc(sport.sport_type.name)
        if sport.level:
            line += f" · {esc(sport.get_level_display())}"
        if sport.rank:
            line += f" · {esc(sport.rank)}"
        sport_lines.append(line)
    for row in Competition.objects.filter(student=student)[:10]:
        sport_lines.append(f"{esc(row.name)}" + (f" · {esc(row.result)}" if row.result else ""))
    section("Спорт", sport_lines)

    body = "".join(rows) or "<p>Портфолио пока пустое.</p>"
    head = (
        f"<h1>{esc(student.full_name)}</h1>"
        f"<p>{esc(settings.SCHOOL_NAME)} · {student.grade} класс · выпуск {student.graduation_year}</p>"
    )
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        f"<title>CV — {esc(student.full_name)}</title>"
        "<style>body{font-family:Georgia,serif;max-width:720px;margin:40px auto;line-height:1.5}"
        "h1{margin-bottom:4px}h2{margin-top:24px;border-bottom:1px solid #ccc}</style>"
        f"</head><body>{head}{body}</body></html>"
    )
