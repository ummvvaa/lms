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
    #: ученик заполнил о себе сам — это ещё не проверенный факт,
    #: и по журналу всегда видно, что число назвал он
    STUDENT_ONBOARDING = "student_onboarding"

    CHOICES = (
        (MANUAL, "Руками"),
        (IMPORT, "Импорт"),
        (AI, "ИИ"),
        (SYNC, "Фоновая сверка"),
        (STUDENT_ONBOARDING, "Анкета ученика"),
    )


@dataclass(frozen=True)
class FieldSpec:
    """Одно редактируемое поле домена.

    `title` — как поле называется человеку: «Текущий балл IELTS».
    `short` — то же для узких мест: заголовка колонки, чипа, строки журнала.
    Технического имени (`ielts_current`) человек не видит нигде: ни один
    экран не собирает подпись из имени переменной (инвариант №2).
    """

    name: str
    title: str
    #: короткая подпись для узких мест; пусто — берётся `title`
    short: str = ""
    #: внутренний ярлык — не отдаётся роли `student` (инвариант №7)
    internal_label: bool = False
    #: границы шкалы. Нужны, чтобы отказ звучал по-человечески:
    #: «указано 12.5, максимальный балл 9», а не «недопустимое значение».
    #: Живут здесь же, в реестре: колонка про них не знает, а дублировать
    #: их по вьюхам и по фронту нельзя (инвариант №2)
    minimum: float | None = None
    maximum: float | None = None
    #: как называется единица в подсказке: «балл», «%»
    unit: str = ""

    @property
    def short_title(self) -> str:
        """Короткая подпись; если её не задали — обычная."""
        return self.short or self.title

    @property
    def range_hint(self) -> str:
        """Человеческая подсказка о допустимых значениях.

        Единицу приклеиваем по-русски: «от 0 до 9 баллов», а не
        «от 0 до 9 балл» — иначе подсказка читается как машинный перевод.
        """
        if self.minimum is None and self.maximum is None:
            return ""
        tail = {"балл": " баллов", "%": "%", "ч": " часов"}.get(self.unit, f" {self.unit}" if self.unit else "")
        if self.minimum is not None and self.maximum is not None:
            return f"от {_number(self.minimum)} до {_number(self.maximum)}{tail}"
        if self.maximum is not None:
            return f"не больше {_number(self.maximum)}{tail}"
        return f"не меньше {_number(self.minimum)}{tail}"


def _number(value: float) -> str:
    """Число без хвостового нуля: 9.0 → 9, 4.5 → 4.5."""
    return str(int(value)) if float(value).is_integer() else str(value)


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
                    FieldSpec(
                        "attendance_percent",
                        "Посещаемость занятий",
                        short="Посещаемость",
                        minimum=0,
                        maximum=100,
                        unit="%",
                    ),
                    FieldSpec("remarks_count", "Замечания за поведение", short="Замечания", minimum=0, maximum=500),
                    FieldSpec(
                        "homework_percent",
                        "Выполнение домашних заданий",
                        short="Домашние задания",
                        minimum=0,
                        maximum=100,
                        unit="%",
                    ),
                    FieldSpec("status", "Статус по дисциплине", short="Статус", internal_label=True),
                    FieldSpec("comment", "Комментарий куратора", short="Комментарий"),
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
                    FieldSpec("target_country", "Целевая страна", short="Страна"),
                    FieldSpec("target_major", "Целевая специальность", short="Специальность"),
                    FieldSpec("has_common_app", "Аккаунт Common App заведён", short="Common App"),
                    FieldSpec("has_application_account", "Кабинет подачи заведён", short="Кабинет подачи"),
                    FieldSpec("status", "Статус по поступлению", short="Статус", internal_label=True),
                    FieldSpec("comment", "Комментарий по поступлению", short="Комментарий"),
                ),
            ),
            ModelSpec(
                label="universities.StudentUniversity",
                student_path="student",
                fields=(
                    FieldSpec("program", "Программа в списке ученика", short="Программа"),
                    FieldSpec("admission_round", "Раунд подачи", short="Раунд"),
                    FieldSpec("tier", "Категория вуза в списке", short="Категория"),
                    FieldSpec("application_status", "Статус заявки", short="Заявка"),
                    FieldSpec("note", "Примечание к вузу", short="Примечание"),
                ),
            ),
            ModelSpec(
                label="universities.University",
                fields=(
                    FieldSpec("name", "Название вуза", short="Вуз"),
                    FieldSpec("country", "Страна вуза", short="Страна"),
                    FieldSpec("website", "Сайт вуза", short="Сайт"),
                    FieldSpec("domain", "Домен сайта для сверки", short="Домен сайта"),
                ),
            ),
            ModelSpec(
                label="universities.Program",
                fields=(
                    FieldSpec("university", "Вуз программы", short="Вуз"),
                    FieldSpec("name", "Название программы", short="Программа"),
                    FieldSpec("level", "Уровень обучения", short="Уровень"),
                ),
            ),
            ModelSpec(
                label="universities.AdmissionRound",
                fields=(
                    FieldSpec("program", "Программа раунда", short="Программа"),
                    FieldSpec("round_type", "Тип раунда подачи", short="Раунд"),
                    FieldSpec("deadline", "Дедлайн подачи", short="Дедлайн"),
                    FieldSpec("source_url", "Ссылка на источник", short="Источник"),
                    FieldSpec("checked_at", "Дата последней сверки", short="Сверено"),
                ),
            ),
            ModelSpec(
                label="universities.AdmissionRequirement",
                fields=(
                    FieldSpec("program", "Программа требований", short="Программа"),
                    FieldSpec("min_gpa", "Минимальный GPA", short="GPA", minimum=0, maximum=5),
                    FieldSpec("min_ielts", "Минимальный балл IELTS", short="IELTS", minimum=0, maximum=9, unit="балл"),
                    FieldSpec(
                        "min_toefl", "Минимальный балл TOEFL", short="TOEFL", minimum=0, maximum=120, unit="балл"
                    ),
                    FieldSpec("min_sat", "Минимальный балл SAT", short="SAT", minimum=400, maximum=1600, unit="балл"),
                    FieldSpec("min_act", "Минимальный балл ACT", short="ACT", minimum=1, maximum=36, unit="балл"),
                    FieldSpec("required_subjects", "Требуемые предметы", short="Предметы"),
                    FieldSpec("portfolio_required", "Портфолио обязательно", short="Портфолио"),
                    FieldSpec("portfolio_note", "Что требуют от портфолио", short="Условия портфолио"),
                    FieldSpec("notes", "Примечания к требованиям", short="Примечания"),
                    FieldSpec("source_url", "Ссылка на источник", short="Источник"),
                    FieldSpec("checked_at", "Дата актуализации требований", short="Актуально на"),
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
                    FieldSpec("ielts_current", "Текущий балл IELTS", short="IELTS", minimum=0, maximum=9, unit="балл"),
                    FieldSpec(
                        "ielts_target", "Целевой балл IELTS", short="Цель IELTS", minimum=0, maximum=9, unit="балл"
                    ),
                    FieldSpec("sat_current", "Текущий балл SAT", short="SAT", minimum=400, maximum=1600, unit="балл"),
                    FieldSpec(
                        "sat_target", "Целевой балл SAT", short="Цель SAT", minimum=400, maximum=1600, unit="балл"
                    ),
                    FieldSpec(
                        "hours_per_week",
                        "Часов подготовки в неделю",
                        short="Часов в неделю",
                        minimum=0,
                        maximum=80,
                        unit="ч",
                    ),
                    FieldSpec("teacher", "Преподаватель по подготовке", short="Преподаватель"),
                    FieldSpec("gpa", "Средний балл аттестата", short="GPA", minimum=0, maximum=5),
                    FieldSpec("next_mock_date", "Дата следующего пробного экзамена", short="Следующий пробный"),
                ),
            ),
            ModelSpec(
                label="students.ExamAttempt",
                student_path="student",
                fields=(
                    FieldSpec("exam_type", "Вид экзамена", short="Экзамен"),
                    FieldSpec("attempt_format", "Формат сдачи", short="Формат"),
                    FieldSpec("source", "Откуда результат", short="Источник"),
                    FieldSpec("date", "Дата сдачи", short="Дата"),
                    FieldSpec(
                        "total_score", "Общий балл за экзамен", short="Общий балл", minimum=0, maximum=1600, unit="балл"
                    ),
                    FieldSpec("listening", "Балл за секцию Listening", short="Listening", minimum=0, maximum=30),
                    FieldSpec("reading", "Балл за секцию Reading", short="Reading", minimum=0, maximum=30),
                    FieldSpec("writing", "Балл за секцию Writing", short="Writing", minimum=0, maximum=30),
                    FieldSpec("speaking", "Балл за секцию Speaking", short="Speaking", minimum=0, maximum=30),
                    FieldSpec("math", "Балл за секцию Math", short="Math", minimum=0, maximum=800, unit="балл"),
                    FieldSpec("verbal", "Балл за секцию Verbal", short="Verbal", minimum=0, maximum=800, unit="балл"),
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
                    FieldSpec("main_track", "Основной трек талантов", short="Трек"),
                    FieldSpec("portfolio_status", "Статус портфолио", short="Портфолио", internal_label=True),
                    FieldSpec("comment", "Комментарий по талантам", short="Комментарий"),
                ),
            ),
            ModelSpec(
                label="directories.OlympiadSubject",
                fields=(
                    FieldSpec("name", "Название предмета", short="Предмет"),
                    FieldSpec("area", "Направление", short="Направление"),
                    FieldSpec("description", "Описание предмета", short="Описание"),
                    FieldSpec("is_active", "Показывать в списке выбора", short="В списке"),
                    FieldSpec("sort_order", "Порядок в списке", short="Порядок", minimum=0, maximum=999),
                ),
            ),
            ModelSpec(
                label="students.Activity",
                student_path="student",
                fields=(
                    FieldSpec("category", "Категория активности", short="Категория"),
                    FieldSpec("subject", "Предмет олимпиады", short="Предмет"),
                    FieldSpec("title", "Название активности", short="Активность"),
                    FieldSpec("date", "Дата активности", short="Дата"),
                    FieldSpec("description", "Описание активности", short="Описание"),
                    FieldSpec("proof_url", "Ссылка на подтверждение", short="Подтверждение"),
                    FieldSpec("is_confirmed", "Активность подтверждена", short="Подтверждено"),
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
                label="directories.SportType",
                fields=(
                    FieldSpec("name", "Название вида спорта", short="Вид спорта"),
                    FieldSpec("category", "Категория вида спорта", short="Категория"),
                    FieldSpec("description", "Описание вида спорта", short="Описание"),
                    FieldSpec("is_active", "Показывать в списке выбора", short="В списке"),
                    FieldSpec("sort_order", "Порядок в списке", short="Порядок", minimum=0, maximum=999),
                ),
            ),
            ModelSpec(
                label="students.SportProfile",
                student_path="student",
                fields=(
                    FieldSpec("sport_type", "Вид спорта", short="Спорт"),
                    FieldSpec("level", "Уровень занятий спортом", short="Уровень"),
                    FieldSpec("rank", "Спортивный разряд", short="Разряд"),
                    FieldSpec("leadership_role", "Лидерская роль в команде", short="Лидерская роль"),
                ),
            ),
            ModelSpec(
                label="students.Competition",
                student_path="student",
                fields=(
                    FieldSpec("name", "Название соревнования", short="Соревнование"),
                    FieldSpec("date", "Дата соревнования", short="Дата"),
                    FieldSpec("result", "Результат выступления", short="Результат"),
                    FieldSpec("has_certificate", "Есть сертификат", short="Сертификат"),
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

#: Сквозные модели: не принадлежат одному домену, права у них свои.
#: Задачи и эссе ведут и директор, и ученик — владельца-домена у них нет.
SHARED_MODELS = ("roadmap.Task", "roadmap.TaskTemplate", "roadmap.Essay", "roadmap.EssayVersion")

#: Кто вправе удалять записи модели, если владельца-домена у неё нет.
#: Доменные модели сюда не входят: право на них выводится из владения полями
#: (инвариант №1) — директор удаляет только в своём домене.
#: все пять директорских ролей — их удобно перечислять целиком
ALL_DIRECTORS: tuple[str, ...] = (
    "director_behavior",
    "director_admission",
    "director_exam",
    "director_talent",
    "director_sport",
)

DELETE_RULES: dict[str, tuple[str, ...]] = {
    # реестр школы ведёт администратор: ученика целиком сносит только он
    "students.Student": (ROLE_ADMIN,),
    "students.StudyGroup": (ROLE_ADMIN,),
    "accounts.User": (ROLE_ADMIN,),
    # задачи и эссе ведут все директора вместе с учеником — владельца нет
    "roadmap.Task": ALL_DIRECTORS,
    "roadmap.Essay": ALL_DIRECTORS,
    "roadmap.TaskTemplate": ALL_DIRECTORS,
    # банк заданий и пробные экзамены — хозяйство академического директора
    "prep.Question": ("director_exam",),
    "prep.MockExam": ("director_exam",),
}


# --- Служебные функции --------------------------------------------------


def domain_of_role(role: str) -> Domain | None:
    """Домен, которым владеет роль. Для `student`/`admin` домена нет."""
    for d in DOMAINS.values():
        if d.role == role:
            return d
    return None


def domain_of_model(model_label: str) -> Domain | None:
    """Домен-владелец модели целиком. Нужен для права на удаление записи."""
    for d in DOMAINS.values():
        if d.model(model_label) is not None:
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


def owns_model(role: str, model_label: str) -> bool:
    """Владеет ли роль моделью целиком — правом заводить и убирать её строки."""
    domain = domain_of_model(model_label)
    return domain is not None and domain.role == role


def can_delete(role: str, model_label: str) -> bool:
    """Может ли роль удалить запись этой модели.

    Ученик не удаляет ничего через общее правило: то немногое, что ему
    можно (свой вуз из списка, своя задача), разрешается точечно в API.
    """
    if role == ROLE_STUDENT:
        return False
    rule = DELETE_RULES.get(model_label)
    if rule is not None:
        return role in rule
    domain = domain_of_model(model_label)
    return domain is not None and domain.role == role


def deleters_of(model_label: str) -> tuple[str, ...]:
    """Роли, которым разрешено удаление, — для сообщения об отказе."""
    rule = DELETE_RULES.get(model_label)
    if rule is not None:
        return rule
    domain = domain_of_model(model_label)
    return (domain.role,) if domain else ()


def editable_fields(role: str, model_label: str) -> set[str]:
    """Поля модели, которые роль вправе редактировать."""
    d = domain_of_role(role)
    if d is None:
        return set()
    m = d.model(model_label)
    return set(m.field_names) if m else set()


def spec_of_field(model_label: str, field_name: str) -> FieldSpec | None:
    """Описание поля из реестра — по нему проверяются границы значения."""
    for d in DOMAINS.values():
        m = d.model(model_label)
        if m is None:
            continue
        for f in m.fields:
            if f.name == field_name:
                return f
    return None


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
