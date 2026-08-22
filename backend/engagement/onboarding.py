"""Онбординг-квиз: восемь вопросов при первом входе.

Ответы кладутся в профили доменов, но не приравниваются к проверенным:
каждая строка остаётся в `OnboardingAnswer` со своим состоянием, и директор
соответствующего домена видит её отдельным списком.

В аудите такие правки идут с источником `student_onboarding` — по журналу
всегда видно, что число назвал ученик, а не сотрудник.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from core.audit import ValueRejected, apply_changes, coerce
from core.domains import Source, domain_of_field
from engagement.models import OnboardingAnswer, OnboardingSession, OnboardingStatus
from students.models import AdmissionProfile, ExamProfile, Student


@dataclass(frozen=True)
class Question:
    """Один вопрос квиза."""

    code: str
    title: str
    hint: str
    kind: str  # text | choice | number | decimal | bool
    #: `students.ExamProfile.ielts_current` — куда ляжет ответ
    target: str = ""
    options: tuple[tuple[str, str], ...] = ()
    placeholder: str = ""

    @property
    def domain_code(self) -> str:
        if not self.target:
            return ""
        label, field = self.target.rsplit(".", 1)
        domain = domain_of_field(label, field)
        return domain.code if domain else ""

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "title": self.title,
            "hint": self.hint,
            "kind": self.kind,
            "target": self.target,
            "domain": self.domain_code,
            "placeholder": self.placeholder,
            "options": [{"value": v, "title": t} for v, t in self.options],
        }


COUNTRIES = (
    ("Казахстан", "Казахстан"),
    ("Канада", "Канада"),
    ("США", "США"),
    ("Великобритания", "Великобритания"),
    ("Нидерланды", "Нидерланды"),
    ("Германия", "Германия"),
    ("Другая", "Другая страна"),
    ("Пока не решил", "Пока не решил"),
)

MAJORS = (
    ("Computer Science", "Computer Science"),
    ("Engineering", "Инженерия"),
    ("Economics", "Экономика и финансы"),
    ("Business", "Бизнес и менеджмент"),
    ("Mathematics", "Математика"),
    ("Другое", "Другое"),
    ("Пока не решил", "Пока не решил"),
)

COST_PRIORITY = (
    ("scholarship", "Нужна стипендия или грант"),
    ("moderate", "Готовы платить умеренно"),
    ("any", "Стоимость не главное"),
    ("unknown", "Ещё не обсуждали"),
)

#: Восемь вопросов из задания. Порядок — порядок шагов.
QUESTIONS: tuple[Question, ...] = (
    Question(
        "target_country",
        "В какую страну хотите поступать?",
        "Это можно поменять в любой момент.",
        "choice",
        target="students.AdmissionProfile.target_country",
        options=COUNTRIES,
    ),
    Question(
        "target_major",
        "Какое направление вам ближе?",
        "Если ещё выбираете — так и скажите, это нормально.",
        "choice",
        target="students.AdmissionProfile.target_major",
        options=MAJORS,
    ),
    Question(
        "grade",
        "В каком вы классе?",
        "Нужен, чтобы правильно расставить сроки.",
        "number",
        placeholder="11",
    ),
    Question(
        "english_score",
        "Какой у вас сейчас IELTS или TOEFL?",
        "Если ещё не сдавали — оставьте пустым.",
        "decimal",
        target="students.ExamProfile.ielts_current",
        placeholder="6.5",
    ),
    Question(
        "standardized_score",
        "Какой у вас сейчас SAT или ACT?",
        "Если ещё не сдавали — оставьте пустым.",
        "number",
        target="students.ExamProfile.sat_current",
        placeholder="1250",
    ),
    Question(
        "gpa",
        "Какой у вас примерный GPA?",
        "Достаточно приблизительно, точное значение сверит школа.",
        "decimal",
        target="students.ExamProfile.gpa",
        placeholder="3.6",
    ),
    Question(
        "cost_priority",
        "Насколько важна стоимость обучения?",
        "От этого зависит, что показывать первым.",
        "choice",
        options=COST_PRIORITY,
    ),
    Question(
        "has_university_list",
        "У вас уже есть список вузов?",
        "Если есть — соберём его вместе с директором по поступлению.",
        "bool",
    ),
)

BY_CODE = {q.code: q for q in QUESTIONS}


def get_session(student: Student) -> OnboardingSession:
    session, _ = OnboardingSession.objects.get_or_create(student=student)
    return session


def state(student: Student) -> dict:
    """Где ученик сейчас: что отвечено, какой вопрос следующий."""
    session = get_session(student)
    answers = {a.question: a.value for a in session.answers.all()}
    next_question = next((q for q in QUESTIONS if q.code not in answers), None)

    return {
        "status": session.status,
        "total": len(QUESTIONS),
        "answered": len(answers),
        "next": next_question.as_dict() if next_question else None,
        "questions": [q.as_dict() for q in QUESTIONS],
        "answers": answers,
        "completed_at": session.completed_at,
    }


def _profile_for(student: Student, label: str):
    models = {"students.AdmissionProfile": AdmissionProfile, "students.ExamProfile": ExamProfile}
    model = models.get(label)
    if model is None:
        return None
    instance, _ = model.objects.get_or_create(student=student)
    return instance


@transaction.atomic
def answer(student: Student, *, code: str, value: Any, actor=None) -> dict:
    """Записать ответ на один шаг.

    Значение сразу попадает в профиль — иначе ученик заполнил анкету,
    а кабинет остался пустым. Но строка в `OnboardingAnswer` помечена
    неподтверждённой, и директор увидит её в своём списке.
    """
    question = BY_CODE.get(code)
    if question is None:
        raise ValueError(f"Нет вопроса «{code}»")

    session = get_session(student)
    if session.status == OnboardingStatus.SKIPPED:
        session.status = OnboardingStatus.IN_PROGRESS
        session.save(update_fields=["status", "updated_at"])

    text = "" if value is None else str(value).strip()
    row, _ = OnboardingAnswer.objects.update_or_create(
        session=session,
        question=code,
        defaults={
            "value": text[:250],
            "target": question.target,
            "domain_code": question.domain_code,
            "is_confirmed": False,
            "confirmed_by": None,
            "confirmed_at": None,
        },
    )

    applied = False
    if question.target and text:
        label, field = question.target.rsplit(".", 1)
        instance = _profile_for(student, label)
        if instance is not None:
            try:
                clean = coerce(instance, field, text)
            except ValueRejected as error:
                raise ValueError(str(error)) from error
            apply_changes(instance, {field: clean}, actor=actor, source=Source.STUDENT_ONBOARDING)
            applied = True
    elif code == "grade" and text.isdigit():
        # класс живёт в реестровой карточке, домена у него нет
        apply_changes(student, {"grade": int(text)}, actor=actor, source=Source.STUDENT_ONBOARDING)
        applied = True

    if session.answers.count() >= len(QUESTIONS) and session.status != OnboardingStatus.COMPLETED:
        session.status = OnboardingStatus.COMPLETED
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "completed_at", "updated_at"])

        from engagement.models import XPKind
        from engagement.scoring import award

        award(student, kind=XPKind.ONBOARDING_DONE, object_label="onboarding", object_id=str(session.pk))

    return {"answer": row.pk, "applied_to_profile": applied, "state": state(student)}


def skip(student: Student) -> dict:
    """Отложить квиз. Вернуться к нему можно в любой момент."""
    session = get_session(student)
    if session.status != OnboardingStatus.COMPLETED:
        session.status = OnboardingStatus.SKIPPED
        session.save(update_fields=["status", "updated_at"])
    return state(student)


def pending_for(role: str) -> list[dict]:
    """Что ждёт подтверждения у директора этого домена."""
    from core.domains import domain_of_role

    domain = domain_of_role(role)
    rows = OnboardingAnswer.objects.filter(is_confirmed=False).exclude(value="").select_related("session__student")
    if domain is not None:
        rows = rows.filter(domain_code=domain.code)
    else:
        rows = rows.exclude(domain_code="")

    return [
        {
            "id": row.pk,
            "student": row.session.student_id,
            "student_name": row.session.student.full_name,
            "question": row.question,
            "question_title": BY_CODE[row.question].title if row.question in BY_CODE else row.question,
            "value": row.value,
            "target": row.target,
            "domain": row.domain_code,
            "created_at": row.created_at,
        }
        for row in rows.order_by("-created_at")
    ]


@transaction.atomic
def review(answer_id: int, *, decision: str, actor, value: str | None = None) -> dict:
    """Директор подтверждает слова ученика или правит их.

    Отклонение не стирает ответ: оно возвращает поле профиля к пустому,
    а сам ответ остаётся в истории — видно, что ученик отвечал.
    """
    row = OnboardingAnswer.objects.select_related("session__student").filter(pk=answer_id).first()
    if row is None:
        raise ValueError("Ответа нет")

    student = row.session.student
    if row.target:
        label, field = row.target.rsplit(".", 1)
        instance = _profile_for(student, label)
        if instance is not None:
            new_value = None
            if decision != "decline":
                new_value = coerce(instance, field, value if value is not None else row.value)
            apply_changes(instance, {field: new_value}, actor=actor, source=Source.MANUAL)

    if decision == "decline":
        row.is_confirmed = False
        row.confirmed_by = actor
        row.confirmed_at = timezone.now()
        row.value = ""
        row.save(update_fields=["is_confirmed", "confirmed_by", "confirmed_at", "value", "updated_at"])
        return {"id": row.pk, "status": "declined"}

    if value is not None:
        row.value = str(value)[:250]
    row.is_confirmed = True
    row.confirmed_by = actor
    row.confirmed_at = timezone.now()
    row.save(update_fields=["is_confirmed", "confirmed_by", "confirmed_at", "value", "updated_at"])
    return {"id": row.pk, "status": "confirmed", "value": row.value}
