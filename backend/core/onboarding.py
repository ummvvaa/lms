"""Панель «Начало работы»: что уже сделано и что делать дальше.

Шаги считаются по настоящему состоянию базы, а не по галочкам в профиле
пользователя: пустая школа должна честно показывать, что данных нет,
а заполненная — исчезать с глаз.

Каждая строка ведёт на экран, где шаг и выполняется. Пункт, который
некуда нажать, ничем не помогает.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.domains import DOMAINS, ROLE_ADMIN, ROLE_STUDENT, domain_of_role


@dataclass
class Step:
    """Один пункт чеклиста."""

    code: str
    title: str
    hint: str
    path: str
    done: bool
    #: сколько уже есть — «12 из 40», если счёт осмыслен
    count: int | None = None
    total: int | None = None
    action: str = ""


@dataclass
class Checklist:
    """Чеклист роли целиком."""

    role: str
    title: str
    steps: list[Step] = field(default_factory=list)

    @property
    def done(self) -> int:
        return sum(1 for s in self.steps if s.done)

    def as_dict(self) -> dict:
        return {
            "role": self.role,
            "title": self.title,
            "done": self.done,
            "total": len(self.steps),
            # панель исчезает сама, когда выполнено всё: постоянное
            # напоминание о сделанном — шум
            "complete": len(self.steps) > 0 and self.done == len(self.steps),
            "steps": [
                {
                    "code": s.code,
                    "title": s.title,
                    "hint": s.hint,
                    "path": s.path,
                    "done": s.done,
                    "count": s.count,
                    "total": s.total,
                    "action": s.action,
                }
                for s in self.steps
            ],
        }


def _students_step() -> Step:
    from students.models import Student

    count = Student.objects.count()
    return Step(
        code="students",
        title="Ученики заведены",
        hint="Пока в школе нет ни одного ученика, все экраны будут пустыми",
        path="/import",
        done=count > 0,
        count=count,
        action="Загрузить файл",
    )


def _filled_condition(model, model_spec):
    """«Хоть одно поле домена заполнено» — с оглядкой на тип колонки.

    Пустая строка есть только у текстовых полей; для числовой колонки
    сравнение с `""` — не «пусто», а ошибка приведения типа.
    """
    from django.db.models import CharField, Q, TextField

    condition = Q()
    for spec in model_spec.fields:
        field = model._meta.get_field(spec.name)
        if isinstance(field, CharField | TextField):
            condition |= ~Q(**{spec.name: ""})
        elif getattr(field, "null", False):
            condition |= Q(**{f"{spec.name}__isnull": False})
    return condition


def _profile_step(domain_code: str) -> Step:
    """Заполнены ли поля своего домена хоть у кого-то."""
    from django.apps import apps
    from django.db.models import Q

    from students.models import Student

    domain = DOMAINS[domain_code]
    model_spec = domain.models[0]
    model = apps.get_model(model_spec.label)

    condition = _filled_condition(model, model_spec)
    total = Student.objects.count()
    filled = model.objects.filter(condition).count() if total and condition != Q() else 0

    return Step(
        code="profiles",
        title=f"Данные домена «{domain.title}» загружены",
        hint="Загрузите свой файл и проверьте, что колонки распознались",
        path="/import",
        done=total > 0 and filled >= max(1, total // 2),
        count=filled,
        total=total,
        action="Загрузить файл",
    )


def _labels_step(domain_code: str) -> Step | None:
    """Проставлены ли внутренние ярлыки домена — если они у него есть."""
    from django.apps import apps

    domain = DOMAINS[domain_code]
    model_spec = domain.models[0]
    label_field = next((f for f in model_spec.fields if f.internal_label), None)
    if label_field is None:
        return None

    model = apps.get_model(model_spec.label)
    total = model.objects.count()
    filled = model.objects.exclude(**{label_field.name: ""}).count()
    return Step(
        code="labels",
        title=f"Статусы проставлены ({label_field.title.lower()})",
        hint="Статус ставится руками: формулы для него школа не задала",
        path="/table",
        done=total > 0 and filled == total,
        count=filled,
        total=total,
        action="Открыть таблицу",
    )


def _catalog_steps() -> list[Step]:
    from universities.models import AdmissionRequirement, Program, University

    universities = University.objects.count()
    programs = Program.objects.count()
    requirements = AdmissionRequirement.objects.count()
    unverified = University.objects.filter(is_verified=False).count()

    steps = [
        Step(
            code="universities",
            title="Вузы заведены",
            hint="Загрузите свой файл или заполните стартовый справочник одной кнопкой",
            path="/directory",
            done=universities > 0,
            count=universities,
            action="Открыть справочник",
        ),
        Step(
            code="requirements",
            title="Требования внесены",
            hint="Без порогов процент соответствия считать не из чего",
            path="/directory",
            done=programs > 0 and requirements >= programs,
            count=requirements,
            total=programs,
            action="Открыть справочник",
        ),
    ]
    if unverified:
        steps.append(
            Step(
                code="verified",
                title="Данные справочника подтверждены",
                hint="Сверьте пороги с сайтами вузов и снимите оранжевые плашки",
                path="/directory",
                done=False,
                count=universities - unverified,
                total=universities,
                action="Проверить",
            )
        )
    return steps


def _admin_steps() -> list[Step]:
    from accounts.models import User
    from students.models import StudyGroup

    users = User.objects.filter(is_active=True).count()
    groups = StudyGroup.objects.count()
    return [
        Step(
            code="users",
            title="Учётные записи директоров заведены",
            hint="Каждый директор ведёт свой домен — без записи он не войдёт",
            path="/users",
            done=users > 1,
            count=users,
            action="Завести пользователя",
        ),
        Step(
            code="groups",
            title="Учебные группы заведены",
            hint="По группам считаются дашборды и раскладываются ученики",
            path="/users",
            done=groups > 0,
            count=groups,
            action="Завести группу",
        ),
        _students_step(),
    ]


def _student_steps(student) -> list[Step]:
    from engagement.onboarding import QUESTIONS
    from universities.models import StudentUniversity

    session = getattr(student, "onboarding", None)
    answered = session.answers.count() if session is not None else 0
    total_questions = len(QUESTIONS)

    universities = StudentUniversity.objects.filter(student=student).count()
    tasks = student.tasks.count()

    return [
        Step(
            code="profile",
            title="Профиль заполнен",
            hint="Несколько коротких вопросов о себе — и кабинет наполнится",
            path="/onboarding",
            done=answered >= total_questions,
            count=answered,
            total=total_questions,
            action="Заполнить",
        ),
        Step(
            code="universities",
            title="Вузы выбраны",
            hint="В каталоге видно, куда вы проходите уже сейчас",
            path="/catalog",
            done=universities > 0,
            count=universities,
            action="Открыть каталог",
        ),
        Step(
            code="plan",
            title="План на год открыт",
            hint="Задачи собираются из ваших вузов и их дедлайнов",
            path="/roadmap",
            done=tasks > 0,
            count=tasks,
            action="Посмотреть план",
        ),
    ]


def build(user) -> Checklist:
    """Чеклист для вошедшего человека."""
    role = user.role
    if role == ROLE_STUDENT:
        student = getattr(user, "student", None)
        checklist = Checklist(role=role, title="С чего начать")
        if student is not None:
            checklist.steps = _student_steps(student)
        return checklist

    if role == ROLE_ADMIN:
        return Checklist(role=role, title="Начало работы", steps=_admin_steps())

    domain = domain_of_role(role)
    if domain is None:
        return Checklist(role=role, title="Начало работы")

    steps = [_students_step(), _profile_step(domain.code)]
    if domain.code == "admission":
        steps.extend(_catalog_steps())
    labels = _labels_step(domain.code)
    if labels is not None:
        steps.append(labels)
    return Checklist(role=role, title="Начало работы", steps=steps)
