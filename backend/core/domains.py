"""Реестр владения полями — единственный источник правды.

Из этого файла питаются:

* права DRF (`core.permissions`) — можно ли роли писать в это поле;
* валидатор предложений (`suggestions.validators`) — строка с чужим полем отбрасывается;
* генерация колонок на фронте — через OpenAPI-схему и эндпойнт `/api/meta/domains/`.

Дублировать состав доменов где-либо ещё запрещено (инвариант №2).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


class Source:
    """Источник изменения доменного поля — пишется в AuditLog (инвариант №9)."""

    MANUAL = "manual"
    IMPORT = "import"
    AI = "ai"
    SYNC = "sync"

    CHOICES = (
        (MANUAL, "Руками"),
        (IMPORT, "Импорт"),
        (AI, "ИИ"),
        (SYNC, "Фоновая сверка"),
    )


@dataclass(frozen=True)
class FieldSpec:
    """Одно редактируемое поле домена."""

    name: str
    title: str
    #: внутренний ярлык — не отдаётся роли `student` (инвариант №7)
    internal_label: bool = False


@dataclass(frozen=True)
class ModelSpec:
    """Модель, поля которой принадлежат домену."""

    #: `app_label.ModelName`
    label: str
    fields: tuple[FieldSpec, ...]
    #: как от объекта этой модели дойти до ученика (путь ORM), None — модель не про ученика
    student_path: str | None = None

    @property
    def field_names(self) -> set[str]:
        return {f.name for f in self.fields}


@dataclass(frozen=True)
class Domain:
    """Домен: роль-владелец и её модели."""

    code: str
    title: str
    role: str
    owner_name: str
    emoji: str
    models: tuple[ModelSpec, ...] = field(default_factory=tuple)

    def model(self, label: str) -> ModelSpec | None:
        for m in self.models:
            if m.label.lower() == label.lower():
                return m
        return None


# --- Роли ---------------------------------------------------------------

ROLE_STUDENT = "student"
ROLE_ADMIN = "admin"

ROLE_TITLES = {
    ROLE_STUDENT: "Ученик",
    "director_behavior": "Директор школы — профиль и дисциплина",
    "director_admission": "Директор по поступлению",
    "director_exam": "Академический директор",
    "director_talent": "Директор талантов",
    "director_sport": "Директор спорта",
    ROLE_ADMIN: "Администратор",
}


# --- Пять доменов -------------------------------------------------------

DOMAINS: dict[str, Domain] = {
    "behavior": Domain(
        code="behavior",
        title="Профиль и дисциплина",
        role="director_behavior",
        owner_name="Салтанат",
        emoji="⚙️",
        models=(
            ModelSpec(
                label="students.BehaviorProfile",
                student_path="student",
                fields=(
                    FieldSpec("attendance_percent", "Посещаемость, %"),
                    FieldSpec("remarks_count", "Замечания"),
                    FieldSpec("homework_percent", "Выполнение заданий, %"),
                    FieldSpec("status", "Статус", internal_label=True),
                    FieldSpec("comment", "Комментарий куратора"),
                ),
            ),
        ),
    ),
    "admission": Domain(
        code="admission",
        title="Поступление",
        role="director_admission",
        owner_name="Асем",
        emoji="🎓",
        models=(
            ModelSpec(
                label="students.AdmissionProfile",
                student_path="student",
                fields=(
                    FieldSpec("target_country", "Целевая страна"),
                    FieldSpec("target_major", "Специальность"),
                    FieldSpec("has_common_app", "Common App"),
                    FieldSpec("has_application_account", "Application account"),
                    FieldSpec("status", "Статус", internal_label=True),
                    FieldSpec("comment", "Комментарий"),
                ),
            ),
            ModelSpec(
                label="universities.StudentUniversity",
                student_path="student",
                fields=(
                    FieldSpec("program", "Программа"),
                    FieldSpec("admission_round", "Раунд"),
                    FieldSpec("tier", "Категория"),
                    FieldSpec("application_status", "Статус заявки"),
                    FieldSpec("note", "Примечание"),
                ),
            ),
            ModelSpec(
                label="universities.University",
                fields=(
                    FieldSpec("name", "Название"),
                    FieldSpec("country", "Страна"),
                    FieldSpec("website", "Сайт"),
                    FieldSpec("domain", "Домен для сверки"),
                ),
            ),
            ModelSpec(
                label="universities.Program",
                fields=(
                    FieldSpec("university", "Вуз"),
                    FieldSpec("name", "Специальность"),
                    FieldSpec("level", "Уровень"),
                ),
            ),
            ModelSpec(
                label="universities.AdmissionRound",
                fields=(
                    FieldSpec("program", "Программа"),
                    FieldSpec("round_type", "Тип раунда"),
                    FieldSpec("deadline", "Дедлайн"),
                    FieldSpec("source_url", "Источник"),
                    FieldSpec("checked_at", "Последняя сверка"),
                ),
            ),
        ),
    ),
    "exam": Domain(
        code="exam",
        title="Экзамены",
        role="director_exam",
        owner_name="Кымбат",
        emoji="🎯",
        models=(
            ModelSpec(
                label="students.ExamProfile",
                student_path="student",
                fields=(
                    FieldSpec("ielts_current", "IELTS текущий"),
                    FieldSpec("ielts_target", "IELTS цель"),
                    FieldSpec("sat_current", "SAT текущий"),
                    FieldSpec("sat_target", "SAT цель"),
                    FieldSpec("hours_per_week", "Часов в неделю"),
                    FieldSpec("teacher", "Преподаватель"),
                    FieldSpec("gpa", "GPA"),
                    FieldSpec("next_mock_date", "Следующий мок"),
                ),
            ),
            ModelSpec(
                label="students.ExamAttempt",
                student_path="student",
                fields=(
                    FieldSpec("exam_type", "Экзамен"),
                    FieldSpec("attempt_format", "Формат"),
                    FieldSpec("date", "Дата"),
                    FieldSpec("total_score", "Общий балл"),
                    FieldSpec("listening", "Listening"),
                    FieldSpec("reading", "Reading"),
                    FieldSpec("writing", "Writing"),
                    FieldSpec("speaking", "Speaking"),
                    FieldSpec("math", "Math"),
                    FieldSpec("verbal", "Verbal"),
                ),
            ),
        ),
    ),
    "talent": Domain(
        code="talent",
        title="Таланты",
        role="director_talent",
        owner_name="Арман",
        emoji="🏆",
        models=(
            ModelSpec(
                label="students.TalentProfile",
                student_path="student",
                fields=(
                    FieldSpec("main_track", "Основной трек"),
                    FieldSpec("portfolio_status", "Статус портфолио", internal_label=True),
                    FieldSpec("comment", "Комментарий"),
                ),
            ),
            ModelSpec(
                label="students.Activity",
                student_path="student",
                fields=(
                    FieldSpec("category", "Категория"),
                    FieldSpec("title", "Название"),
                    FieldSpec("date", "Дата"),
                    FieldSpec("description", "Описание"),
                    FieldSpec("proof_url", "Подтверждение"),
                    FieldSpec("is_confirmed", "Подтверждено"),
                ),
            ),
        ),
    ),
    "sport": Domain(
        code="sport",
        title="Спорт",
        role="director_sport",
        owner_name="Нурлыбек",
        emoji="⚽️",
        models=(
            ModelSpec(
                label="students.SportProfile",
                student_path="student",
                fields=(
                    FieldSpec("sport_kind", "Вид спорта"),
                    FieldSpec("level", "Уровень"),
                    FieldSpec("rank", "Разряд"),
                    FieldSpec("leadership_role", "Лидерская роль"),
                ),
            ),
            ModelSpec(
                label="students.Competition",
                student_path="student",
                fields=(
                    FieldSpec("name", "Соревнование"),
                    FieldSpec("date", "Дата"),
                    FieldSpec("result", "Результат"),
                    FieldSpec("has_certificate", "Сертификат"),
                ),
            ),
        ),
    ),
}

#: Профильные модели один-к-одному со Student — на них держится инвариант №1.
PROFILE_MODELS = (
    "students.BehaviorProfile",
    "students.AdmissionProfile",
    "students.ExamProfile",
    "students.TalentProfile",
    "students.SportProfile",
)

#: Реестровые модели школы: заводит администратор, к пяти доменам не относятся.
REGISTRY_MODELS = ("students.Student", "students.StudyGroup", "accounts.User")


# --- Служебные функции --------------------------------------------------


def domain_of_role(role: str) -> Domain | None:
    """Домен, которым владеет роль. Для `student`/`admin` домена нет."""
    for d in DOMAINS.values():
        if d.role == role:
            return d
    return None


def domain_of_field(model_label: str, field_name: str) -> Domain | None:
    """Домен-владелец конкретного поля конкретной модели."""
    for d in DOMAINS.values():
        m = d.model(model_label)
        if m and field_name in m.field_names:
            return d
    return None


def can_write(role: str, model_label: str, field_name: str) -> bool:
    """Может ли роль писать в это поле (инвариант №1)."""
    d = domain_of_field(model_label, field_name)
    return d is not None and d.role == role


def editable_fields(role: str, model_label: str) -> set[str]:
    """Поля модели, которые роль вправе редактировать."""
    d = domain_of_role(role)
    if d is None:
        return set()
    m = d.model(model_label)
    return set(m.field_names) if m else set()


def internal_label_fields(model_label: str | None = None) -> set[str]:
    """Внутренние ярлыки, скрытые от ученика (инвариант №7).

    Возвращает имена полей; при указании модели — только её поля.
    """
    out: set[str] = set()
    for d in DOMAINS.values():
        for m in d.models:
            if model_label and m.label.lower() != model_label.lower():
                continue
            out |= {f.name for f in m.fields if f.internal_label}
    return out


def all_model_labels() -> set[str]:
    """Все модели, упомянутые в реестре."""
    return {m.label for d in DOMAINS.values() for m in d.models}


def owned_fields_map() -> dict[str, dict[str, str]]:
    """`{model_label: {field_name: domain_code}}` — плоский вид реестра."""
    out: dict[str, dict[str, str]] = {}
    for d in DOMAINS.values():
        for m in d.models:
            out.setdefault(m.label, {})
            for f in m.fields:
                out[m.label][f.name] = d.code
    return out


def iter_field_specs() -> Iterable[tuple[Domain, ModelSpec, FieldSpec]]:
    for d in DOMAINS.values():
        for m in d.models:
            for f in m.fields:
                yield d, m, f
