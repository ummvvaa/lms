"""Онбординг-квиз: шесть вопросов при первом входе.

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
from django.utils.translation import gettext, gettext_lazy

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


#: значение пишется в профиль как данные и сравнивается с ним — не переводится;
#: переводится только подпись
COUNTRIES = (  # i18n-skip: значения — данные профиля, подписи переведены
    ("Казахстан", gettext_lazy("Казахстан")),
    ("Канада", gettext_lazy("Канада")),
    ("США", gettext_lazy("США")),
    ("Великобритания", gettext_lazy("Великобритания")),
    ("Нидерланды", gettext_lazy("Нидерланды")),
    ("Германия", gettext_lazy("Германия")),
    ("Другая", gettext_lazy("Другая страна")),
    ("Пока не решил", gettext_lazy("Пока не решил")),
)

MAJORS = (  # i18n-skip: значения — данные профиля, подписи переведены
    ("Computer Science", "Computer Science"),
    ("Engineering", gettext_lazy("Инженерия")),
    ("Economics", gettext_lazy("Экономика и финансы")),
    ("Business", gettext_lazy("Бизнес и менеджмент")),
    ("Mathematics", gettext_lazy("Математика")),
    ("Другое", gettext_lazy("Другое")),
    ("Пока не решил", gettext_lazy("Пока не решил")),
)

#: Вопросы из задания. Порядок — порядок шагов. Вопрос про стоимость
#: обучения убран в фазе 70 вместе с полем «приоритет стоимости».
QUESTIONS: tuple[Question, ...] = (
    Question(
        "target_country",
        gettext_lazy("В какую страну хотите поступать?"),
        gettext_lazy("Это можно поменять в любой момент."),
        "choice",
        target="students.AdmissionProfile.target_country",
        options=COUNTRIES,
    ),
    Question(
        "target_major",
        gettext_lazy("Какое направление вам ближе?"),
        gettext_lazy("Если ещё выбираете — так и скажите, это нормально."),
        "choice",
        target="students.AdmissionProfile.target_major",
        options=MAJORS,
    ),
    Question(
        "english_score",
        gettext_lazy("Какой у вас сейчас IELTS или TOEFL?"),
        gettext_lazy("Если ещё не сдавали — оставьте пустым."),
        "decimal",
        target="students.ExamProfile.ielts_current",
        placeholder="6.5",
    ),
    Question(
        "standardized_score",
        gettext_lazy("Какой у вас сейчас SAT или ACT?"),
        gettext_lazy("Если ещё не сдавали — оставьте пустым."),
        "number",
        target="students.ExamProfile.sat_current",
        placeholder="1250",
    ),
    Question(
        "gpa",
        gettext_lazy("Какой у вас примерный GPA?"),
        gettext_lazy("Достаточно приблизительно, точное значение сверит школа."),
        "decimal",
        target="students.ExamProfile.gpa",
        placeholder="3.6",
    ),
    Question(
        "has_university_list",
        gettext_lazy("У вас уже есть список вузов?"),
        gettext_lazy("Если есть — соберём его вместе с директором по поступлению."),
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
        raise ValueError(gettext("Нет вопроса «{code}»").format(code=code))

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


def may_review(role: str, domain_code: str) -> bool:
    """Кто решает по ответу: директор домена, куда ляжет ответ, и администратор.

    Ответ ученика — это значение поля домена, и подтверждает его владелец
    поля (инвариант №1). Директор другого домена и куратор (у него домена
    нет) решения не принимают, даже если ученик им виден.
    """
    from core.domains import ROLE_ADMIN, domain_of_role

    if role == ROLE_ADMIN:
        return True
    domain = domain_of_role(role)
    return domain is not None and domain.code == domain_code


def pending_for(role: str) -> list[dict]:
    """Что ждёт подтверждения у директора этого домена."""
    from core.domains import ROLE_ADMIN, domain_of_role

    domain = domain_of_role(role)
    rows = OnboardingAnswer.objects.filter(is_confirmed=False).exclude(value="").select_related("session__student")
    if domain is not None:
        rows = rows.filter(domain_code=domain.code)
    elif role == ROLE_ADMIN:
        rows = rows.exclude(domain_code="")
    else:
        # роль без домена (куратор) ответов не подтверждает — и списка не видит
        return []

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
        raise ValueError(gettext("Ответа нет"))
    if not may_review(getattr(actor, "role", ""), row.domain_code):
        raise PermissionError(gettext("Ответ подтверждает директор своего домена"))

    student = row.session.student
    if row.target:
        label, field = row.target.rsplit(".", 1)
        instance = _profile_for(student, label)
        if instance is not None:
            if decision != "decline":
                new_value = coerce(instance, field, value if value is not None else row.value)
            else:
                # «снять» — вернуть полю пустоту, а пустота у колонок разная:
                # число без `null=True` не бывает, а текст пустой строкой бывает.
                # `None` в текстовую колонку ронял запрос пятисоткой
                new_value = None if instance._meta.get_field(field).null else ""
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
