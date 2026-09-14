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
from decimal import Decimal, InvalidOperation


class Source:
    """Источник изменения доменного поля — пишется в AuditLog (инвариант №9)."""

    MANUAL = "manual"
    IMPORT = "import"
    AI = "ai"
    SYNC = "sync"
    #: ученик заполнил о себе сам — это ещё не проверенный факт,
    #: и по журналу всегда видно, что число назвал он
    STUDENT_ONBOARDING = "student_onboarding"
    #: предложение ученика, применённое директором (фаза 37): в журнале
    #: видно и кто подтвердил (актор), и кто назвал число (источник)
    STUDENT_PROPOSAL = "student_proposal"

    CHOICES = (
        (MANUAL, "Руками"),
        (IMPORT, "Импорт"),
        (AI, "ИИ"),
        (SYNC, "Фоновая сверка"),
        (STUDENT_ONBOARDING, "Анкета ученика"),
        (STUDENT_PROPOSAL, "Предложил ученик"),
    )


@dataclass(frozen=True)
class Scale:
    """Шкала балла: от, до, шаг. Держится здесь, читают три места кода."""

    minimum: Decimal
    maximum: Decimal
    step: Decimal

    def holds(self, value) -> bool:
        try:
            number = Decimal(str(value).replace(",", "."))
        except (InvalidOperation, ValueError):
            return False
        if number < self.minimum or number > self.maximum:
            return False
        return (number - self.minimum) % self.step == 0

    @property
    def hint(self) -> str:
        """«от 0 до 9 с шагом 0.5» — для отказа словами."""
        return f"от {_plain(self.minimum)} до {_plain(self.maximum)} с шагом {_plain(self.step)}"


def _plain(number: Decimal) -> str:
    text = format(number.normalize(), "f")
    return text


#: Шкалы экзаменов школы (D4, D17): общий балл и секция. Скрытых экзаменов
#: (TOEFL, ACT, Duolingo, HSK) здесь нет намеренно — у них остаётся общая
#: граница поля из `FieldSpec`, как и было.
SCALES: dict[tuple[str, bool], Scale] = {
    ("IELTS", False): Scale(Decimal("0"), Decimal("9"), Decimal("0.5")),
    ("IELTS", True): Scale(Decimal("0"), Decimal("9"), Decimal("0.5")),
    ("SAT", False): Scale(Decimal("400"), Decimal("1600"), Decimal("10")),
    ("SAT", True): Scale(Decimal("200"), Decimal("800"), Decimal("10")),
}

#: Поля-секции у попытки. Общий балл — всё остальное числовое.
SECTION_FIELDS: frozenset[str] = frozenset({"listening", "reading", "writing", "speaking", "math", "verbal"})

#: Какому экзамену принадлежит поле профиля: `ielts_current` — IELTS.
PROFILE_EXAM_PREFIXES: dict[str, str] = {"ielts_": "IELTS", "sat_": "SAT"}


def scale_of(exam: str, *, section: bool = False) -> Scale | None:
    """Шкала экзамена по коду. Нет в таблице — нет и шкалы (границы поля)."""
    return SCALES.get((str(exam or "").upper(), section))


def exam_of(instance, field_name: str) -> str:
    """Код экзамена для поля записи: у попытки — свой, у цели — из справочника,
    у профиля — по имени поля. Пусто — экзамен неизвестен."""
    label = f"{instance._meta.app_label}.{type(instance).__name__}"
    if label == "students.ExamAttempt":
        return str(getattr(instance, "exam_type", "") or "")
    if label == "students.ExamGoal":
        exam = getattr(instance, "exam", None) if getattr(instance, "exam_id", None) else None
        return str(getattr(exam, "name", "") or "")
    if label == "students.ExamProfile":
        for prefix, exam in PROFILE_EXAM_PREFIXES.items():
            if field_name.startswith(prefix):
                return exam
    return ""


def scale_for(instance, field_name: str) -> Scale | None:
    """Шкала конкретного поля конкретной записи — с учётом её экзамена."""
    exam = exam_of(instance, field_name)
    if not exam:
        return None
    return scale_of(exam, section=field_name in SECTION_FIELDS)


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
    #: ученик вправе предложить значение этого поля про себя (фаза 37).
    #: Предложение — не запись: решение принимает владелец домена.
    #: Оценочные ярлыки, статусы, посещаемость и дисциплина флага
    #: не получают никогда — ученик их не предлагает вовсе
    student_proposable: bool = False
    #: границы шкалы. Нужны, чтобы отказ звучал по-человечески:
    #: «указано 12.5, максимальный балл 9», а не «недопустимое значение».
    #: Живут здесь же, в реестре: колонка про них не знает, а дублировать
    #: их по вьюхам и по фронту нельзя (инвариант №2)
    minimum: float | None = None
    maximum: float | None = None
    #: как называется единица в подсказке: «балл», «%»
    unit: str = ""
    #: где поле показывается в карточке ученика (фаза 68). `main` — в блоке
    #: домена; `none` — в карточке не показывается вовсе, живёт в таблице,
    #: фильтрах и подборе. Правило одно (фаза 70): в карточке ровно то, что
    #: есть в таблице владельца домена, — отдельных карточек под поля,
    #: которых в таблице нет, больше не заводим
    card: str = "main"
    #: куратор пишет это поле у учеников своих групп, не владея доменом
    #: (фаза 70). Право поля, а не домена: телефон и почту Common App
    #: куратор уточняет первым, а внутренние признаки поступления —
    #: статус, «кабинет заведён» — остаются за Асем
    curator_writes: bool = False

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
    models: tuple[ModelSpec, ...] = field(default_factory=tuple)

    def model(self, label: str) -> ModelSpec | None:
        for m in self.models:
            if m.label.lower() == label.lower():
                return m
        return None


# --- Роли ---------------------------------------------------------------

ROLE_STUDENT = "student"
ROLE_ADMIN = "admin"
#: куратор (фаза 60): подтверждает данные учеников своих групп в доменах
#: из `CURATOR_DOMAINS`, доменом не владеет и ничего не вносит сам
ROLE_CURATOR = "curator"

ROLE_TITLES = {
    ROLE_STUDENT: "Ученик",
    "director_behavior": "Директор школы — профиль и дисциплина",
    "director_admission": "Директор по поступлению",
    "director_exam": "Академический директор",
    "director_talent": "Директор талантов",
    "director_sport": "Директор спорта",
    ROLE_CURATOR: "Куратор",
    ROLE_ADMIN: "Администратор",
}


# --- Пять доменов -------------------------------------------------------

DOMAINS: dict[str, Domain] = {
    "behavior": Domain(
        code="behavior",
        title="Профиль и дисциплина",
        role="director_behavior",
        owner_name="Салтанат",
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
            # контакты родителей: несколько на ученика, поэтому строками
            # (инвариант №5). Ведёт их директор школы — это её домен
            # вопросы профтеста — справочник домена: анкету ведёт директор
            # школы, а не программист (фаза 45)
            ModelSpec(
                label="engagement.CareerQuestion",
                fields=(
                    FieldSpec("code", "Код вопроса", short="Код"),
                    FieldSpec("text", "Текст вопроса анкеты", short="Вопрос"),
                    FieldSpec("hint", "Подсказка к вопросу", short="Подсказка"),
                    FieldSpec("kind", "Вид ответа", short="Ответ"),
                    FieldSpec("options", "Варианты ответа", short="Варианты"),
                    FieldSpec("order", "Порядок в анкете", short="Порядок", minimum=0, maximum=999),
                    FieldSpec("is_active", "Показывать в анкете", short="В анкете"),
                ),
            ),
            # бейджи (фаза 46): условие — строка справочника, а не код.
            # Ведёт их директор школы, как и анкету профтеста
            ModelSpec(
                label="engagement.Badge",
                fields=(
                    FieldSpec("code", "Код бейджа", short="Код"),
                    FieldSpec("name", "Название бейджа", short="Бейдж"),
                    FieldSpec("description", "Описание бейджа", short="Описание"),
                    FieldSpec("metric", "Что считает бейдж", short="Считаем"),
                    FieldSpec("threshold", "Сколько нужно для бейджа", short="Порог", minimum=1, maximum=100000),
                    FieldSpec("icon", "Иконка бейджа", short="Иконка"),
                    FieldSpec("order", "Порядок в списке", short="Порядок", minimum=0, maximum=999),
                    FieldSpec("is_active", "Показывать бейдж", short="Показывать"),
                ),
            ),
            # сюжеты главной и правила обзвона (фаза 49): кабинет ученика
            # и список «кому позвонить» ведёт директор школы — там же,
            # где анкета профтеста и бейджи. Условие берётся из закрытого
            # набора, а слова, порог и цвет школа меняет без выката
            ModelSpec(
                label="engagement.HomeCue",
                fields=(
                    FieldSpec("code", "Код сюжета", short="Код"),
                    FieldSpec("condition", "Условие показа сюжета", short="Условие"),
                    FieldSpec("title", "Заголовок сюжета", short="Заголовок"),
                    FieldSpec("description", "Описание сюжета", short="Описание"),
                    FieldSpec("action_label", "Подпись кнопки сюжета", short="Кнопка"),
                    FieldSpec("action_path", "Куда ведёт кнопка сюжета", short="Куда ведёт"),
                    FieldSpec("tone", "Цвет карточки сюжета", short="Цвет"),
                    FieldSpec("order", "Порядок в карусели", short="Порядок", minimum=0, maximum=999),
                    FieldSpec("is_active", "Показывать сюжет", short="Показывать"),
                ),
            ),
            ModelSpec(
                label="engagement.CallRule",
                fields=(
                    FieldSpec("code", "Код правила обзвона", short="Код"),
                    FieldSpec("condition", "Условие для звонка", short="Условие"),
                    FieldSpec("reason", "Причина одной фразой", short="Причина"),
                    FieldSpec("urgency", "Срочность звонка", short="Срочность"),
                    FieldSpec("threshold", "Порог срабатывания", short="Порог", minimum=0, maximum=100000),
                    FieldSpec("order", "Порядок в списке", short="Порядок", minimum=0, maximum=999),
                    FieldSpec("is_active", "Показывать правило", short="Показывать"),
                ),
            ),
            ModelSpec(
                label="students.ParentContact",
                student_path="student",
                fields=(
                    FieldSpec("full_name", "ФИО родителя или опекуна", short="ФИО"),
                    FieldSpec("relation", "Кем приходится ученику", short="Кем приходится"),
                    FieldSpec("phone", "Телефон для связи", short="Телефон"),
                    FieldSpec("email", "Почта для связи", short="Почта"),
                    FieldSpec("preferred_channel", "Предпочтительный способ связи", short="Как связываться"),
                    FieldSpec("note", "Примечание о контакте", short="Примечание"),
                    FieldSpec("is_primary", "Основной контакт", short="Основной"),
                ),
            ),
        ),
    ),
    "admission": Domain(
        code="admission",
        title="Поступление",
        role="director_admission",
        owner_name="Асем",
        models=(
            ModelSpec(
                label="students.AdmissionProfile",
                student_path="student",
                fields=(
                    # блок «Поступление» — ровно колонки таблицы Асем (фаза 68):
                    # телефон, почта Common App, папка на Диске. Пароли, GPA,
                    # попытки и документы-ссылки в блок приходят из своих
                    # моделей, а здесь — только поля профиля поступления
                    FieldSpec(
                        "student_phone",
                        "Телефон ученика",
                        short="Телефон",
                        student_proposable=True,
                        curator_writes=True,
                    ),
                    FieldSpec(
                        "common_app_email",
                        "Почта Common App",
                        short="Почта Common App",
                        student_proposable=True,
                        curator_writes=True,
                    ),
                    FieldSpec(
                        "drive_folder_url",
                        "Папка на Диске",
                        short="Папка на Диске",
                        student_proposable=True,
                        curator_writes=True,
                    ),
                    # личная почта и срок паспорта — колонки таблицы Асем (фаза 71):
                    # почта — текст, с логином не связана; срок — своё поле,
                    # чтобы не теряться, когда ссылки на паспорт в таблице нет
                    FieldSpec(
                        "personal_email",
                        "Электронный адрес",
                        short="Личная почта",
                        student_proposable=True,
                        curator_writes=True,
                    ),
                    FieldSpec(
                        "passport_expires_at",
                        "Срок годности паспорта",
                        short="Срок паспорта",
                        student_proposable=True,
                        curator_writes=True,
                    ),
                    # цели ученика: в таблице Асем таких колонок нет, и
                    # в карточке их тоже нет (фаза 70) — карточка «Цели
                    # поступления» убрана. Поля остаются: их спрашивает
                    # анкета первого входа, а читают подбор вузов,
                    # стипендии, профтест и резюме портфолио
                    FieldSpec("target_country", "Целевая страна", short="Страна", student_proposable=True, card="none"),
                    FieldSpec(
                        "target_major",
                        "Целевая специальность",
                        short="Специальность",
                        student_proposable=True,
                        card="none",
                    ),
                    FieldSpec(
                        "target_level",
                        "Уровень обучения цели",
                        short="Уровень",
                        student_proposable=True,
                        card="none",
                    ),
                    # служебные признаки — в таблице и фильтрах, в карточке нет:
                    # готовность и дашборд Асем их читают, а человеку в карточке
                    # они ничего не говорят. Импорт проставляет их по паролю
                    FieldSpec("has_common_app", "Аккаунт Common App заведён", short="Common App", card="none"),
                    FieldSpec("has_application_account", "Кабинет подачи заведён", short="Кабинет подачи", card="none"),
                    FieldSpec("status", "Статус по поступлению", short="Статус", internal_label=True, card="none"),
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
                    FieldSpec("world_rank", "Место в мировом рейтинге", short="Рейтинг", minimum=1, maximum=5000),
                    FieldSpec("data_source", "Откуда запись", short="Источник"),
                    FieldSpec("is_verified", "Данные подтверждены", short="Подтверждено"),
                ),
            ),
            ModelSpec(
                label="universities.Program",
                fields=(
                    FieldSpec("university", "Вуз программы", short="Вуз"),
                    FieldSpec("name", "Название программы", short="Программа"),
                    FieldSpec("level", "Уровень обучения", short="Уровень"),
                    FieldSpec("data_source", "Откуда запись", short="Источник"),
                    FieldSpec("is_verified", "Данные подтверждены", short="Подтверждено"),
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
                    FieldSpec("data_source", "Откуда запись", short="Источник"),
                    FieldSpec("is_verified", "Данные подтверждены", short="Подтверждено"),
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
                    FieldSpec("data_source", "Откуда запись", short="Источник"),
                    FieldSpec("is_verified", "Данные подтверждены", short="Подтверждено"),
                ),
            ),
            # стипендии и гранты (фаза 44): справочник домена «Поступление».
            # Признак «не подтверждено» тот же, что у требований (инвариант №14)
            ModelSpec(
                label="universities.Scholarship",
                fields=(
                    FieldSpec("name", "Название стипендии", short="Стипендия"),
                    FieldSpec("organizer", "Организатор стипендии", short="Организатор"),
                    FieldSpec("country", "Страна стипендии", short="Страна"),
                    FieldSpec("level", "Уровень обучения", short="Уровень"),
                    FieldSpec("funding_type", "Тип финансирования", short="Финансирование"),
                    FieldSpec("amount_min", "Сумма финансирования от", short="Сумма от", minimum=0),
                    FieldSpec("amount_max", "Сумма финансирования до", short="Сумма до", minimum=0),
                    FieldSpec("currency", "Валюта суммы", short="Валюта"),
                    FieldSpec("for_international", "Основание: для иностранцев", short="Иностранцам"),
                    FieldSpec("for_merit", "Основание: за заслуги", short="За заслуги"),
                    FieldSpec("for_need", "Основание: по нужде", short="По нужде"),
                    FieldSpec("deadline", "Дедлайн подачи на стипендию", short="Дедлайн"),
                    FieldSpec("url", "Ссылка на страницу стипендии", short="Ссылка"),
                    FieldSpec("requirements", "Требования стипендии", short="Требования"),
                    FieldSpec("description", "Описание стипендии", short="Описание"),
                    FieldSpec("university", "Вуз стипендии", short="Вуз"),
                    FieldSpec("is_active", "Показывать в каталоге", short="В каталоге"),
                    FieldSpec("data_source", "Откуда запись", short="Источник"),
                    FieldSpec("is_verified", "Данные подтверждены", short="Подтверждено"),
                ),
            ),
        ),
    ),
    "exam": Domain(
        code="exam",
        title="Экзамены",
        role="director_exam",
        owner_name="Кымбат",
        models=(
            ModelSpec(
                label="students.ExamProfile",
                student_path="student",
                fields=(
                    FieldSpec(
                        "ielts_current",
                        "Текущий балл IELTS",
                        short="IELTS",
                        minimum=0,
                        maximum=9,
                        unit="балл",
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "ielts_target",
                        "Целевой балл IELTS",
                        short="Цель IELTS",
                        minimum=0,
                        maximum=9,
                        unit="балл",
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "sat_current",
                        "Текущий балл SAT",
                        short="SAT",
                        minimum=400,
                        maximum=1600,
                        unit="балл",
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "sat_target",
                        "Целевой балл SAT",
                        short="Цель SAT",
                        minimum=400,
                        maximum=1600,
                        unit="балл",
                        student_proposable=True,
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
                    # GPA показывается один раз — в блоке «Поступление» (фаза 71):
                    # его читают подбор, соответствие, стипендии и готовность,
                    # а приносит таблица Асем. Поле и право остаются здесь, у Кымбат
                    FieldSpec(
                        "gpa",
                        "Средний балл аттестата",
                        short="GPA",
                        minimum=0,
                        maximum=5,
                        student_proposable=True,
                        card="none",
                    ),
                    FieldSpec("next_mock_date", "Дата следующего пробного экзамена", short="Следующий пробный"),
                ),
            ),
            ModelSpec(
                label="students.ExamAttempt",
                student_path="student",
                fields=(
                    FieldSpec("exam_type", "Вид экзамена", short="Экзамен", student_proposable=True),
                    FieldSpec("attempt_format", "Формат сдачи", short="Формат"),
                    FieldSpec("source", "Откуда результат", short="Источник"),
                    FieldSpec("date", "Дата сдачи", short="Дата", student_proposable=True),
                    # дата не указана в источнике (таблица Асем, фаза 65): снимается,
                    # когда ученик предлагает настоящую дату и её подтверждают
                    FieldSpec("date_unknown", "Дата сдачи не указана", short="Дата уточняется"),
                    FieldSpec(
                        "total_score",
                        "Общий балл за экзамен",
                        short="Общий балл",
                        minimum=0,
                        maximum=1600,
                        unit="балл",
                        student_proposable=True,
                    ),
                    # секции: у IELTS шкала 0–9 с шагом 0.5, у TOEFL 0–30 —
                    # здесь стоит общая граница, точную держат разбор файла
                    # и проверка предложения (`students.mocks`, D4 про шкалы)
                    FieldSpec(
                        "listening",
                        "Балл за секцию Listening",
                        short="Listening",
                        minimum=0,
                        maximum=30,
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "reading",
                        "Балл за секцию Reading",
                        short="Reading",
                        minimum=0,
                        maximum=30,
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "writing",
                        "Балл за секцию Writing",
                        short="Writing",
                        minimum=0,
                        maximum=30,
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "speaking",
                        "Балл за секцию Speaking",
                        short="Speaking",
                        minimum=0,
                        maximum=30,
                        student_proposable=True,
                    ),
                    FieldSpec("math", "Балл за секцию Math", short="Math", minimum=0, maximum=800, unit="балл"),
                    FieldSpec("verbal", "Балл за секцию Verbal", short="Verbal", minimum=0, maximum=800, unit="балл"),
                ),
            ),
            # цели по экзаменам (фаза 39): ставит ученик предложением,
            # подтверждает академический директор; от дат растут календарь,
            # напоминания и автозадачи о регистрации
            ModelSpec(
                label="students.ExamGoal",
                student_path="student",
                fields=(
                    FieldSpec("exam", "Экзамен цели", short="Экзамен", student_proposable=True),
                    FieldSpec(
                        "target_score",
                        "Целевой балл экзамена",
                        short="Цель",
                        minimum=0,
                        maximum=1600,
                        unit="балл",
                        student_proposable=True,
                    ),
                    FieldSpec("exam_date", "Дата экзамена", short="Дата экзамена", student_proposable=True),
                    FieldSpec("registration_date", "Дата регистрации", short="Регистрация", student_proposable=True),
                    FieldSpec("note", "Примечание к цели", short="Примечание", student_proposable=True),
                ),
            ),
            ModelSpec(
                label="directories.ExamKind",
                fields=(
                    FieldSpec("name", "Название экзамена", short="Экзамен"),
                    FieldSpec("min_score", "Минимум шкалы", short="Минимум"),
                    FieldSpec("max_score", "Максимум шкалы", short="Максимум"),
                    FieldSpec("description", "Описание экзамена", short="Описание"),
                    FieldSpec("is_active", "Показывать в списке выбора", short="В списке"),
                    FieldSpec("sort_order", "Порядок в списке", short="Порядок", minimum=0, maximum=999),
                ),
            ),
        ),
    ),
    "talent": Domain(
        code="talent",
        title="Таланты",
        role="director_talent",
        owner_name="Арман",
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
            # отбор в олимпиадную группу — решение директора талантов.
            # Реестровую карточку ученика ведёт администратор, но этот
            # признак принадлежит домену: право на него берётся отсюда
            ModelSpec(
                label="students.Student",
                student_path="",
                fields=(FieldSpec("in_olympiad_group", "В олимпиадной группе", short="Олимпиадник"),),
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
                    FieldSpec("category", "Категория активности", short="Категория", student_proposable=True),
                    FieldSpec("subject", "Предмет олимпиады", short="Предмет", student_proposable=True),
                    FieldSpec("title", "Название активности", short="Активность", student_proposable=True),
                    FieldSpec("date", "Дата активности", short="Дата", student_proposable=True),
                    FieldSpec("description", "Описание активности", short="Описание", student_proposable=True),
                    FieldSpec("proof_url", "Ссылка на подтверждение", short="Подтверждение", student_proposable=True),
                    # подтверждение — решение директора, ученик его не предлагает
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
        models=(
            ModelSpec(
                label="students.SportProfile",
                student_path="student",
                fields=(
                    FieldSpec("sport_type", "Вид спорта", short="Спорт", student_proposable=True),
                    FieldSpec("level", "Уровень занятий спортом", short="Уровень", student_proposable=True),
                    FieldSpec("rank", "Спортивный разряд", short="Разряд", student_proposable=True),
                    FieldSpec(
                        "leadership_role", "Лидерская роль в команде", short="Лидерская роль", student_proposable=True
                    ),
                ),
            ),
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
                label="students.Competition",
                student_path="student",
                fields=(
                    FieldSpec("name", "Название соревнования", short="Соревнование", student_proposable=True),
                    FieldSpec("sport_type", "Вид спорта соревнования", short="Вид спорта", student_proposable=True),
                    FieldSpec("level", "Уровень соревнования", short="Уровень", student_proposable=True),
                    FieldSpec("date", "Дата соревнования", short="Дата", student_proposable=True),
                    FieldSpec("result", "Результат выступления", short="Результат", student_proposable=True),
                    FieldSpec("has_certificate", "Есть сертификат", short="Сертификат", student_proposable=True),
                    FieldSpec("proof_url", "Ссылка на подтверждение", short="Подтверждение", student_proposable=True),
                ),
            ),
        ),
    ),
    # Документы (фаза 60). До этой фазы документы чек-листа не принадлежали
    # ни одному домену и не подтверждались: загружал ученик, читали все.
    # Владелец — Асем: документы собираются под поступление. Это второй
    # домен той же роли, поэтому стоит после пяти основных: `domain_of_role`
    # отвечает первым найденным — «Поступление», а этот домен находится
    # через `domains_of_role`. Профильной модели у него нет: документы —
    # строки с историей (инвариант №5), а не поля ученика. Очередь
    # подтверждения документов и их статус появятся в фазе 62
    "documents": Domain(
        code="documents",
        title="Документы",
        role="director_admission",
        owner_name="Асем",
        models=(
            ModelSpec(
                label="students.StudentDocument",
                student_path="student",
                fields=(
                    FieldSpec("doc_type", "Тип документа", short="Тип"),
                    FieldSpec("title", "Название документа", short="Название"),
                    FieldSpec("issued_date", "Дата выдачи документа", short="Выдан"),
                    FieldSpec("expires_at", "Документ действует до", short="Действует до"),
                    FieldSpec("note", "Примечание к документу", short="Примечание"),
                    # проверка (фаза 62): статус ставится решением по очереди, причину
                    # читает ученик. Ярлыком не помечены — ученик видит и то, и другое
                    FieldSpec("status", "Проверка документа", short="Проверка"),
                    FieldSpec("reject_reason", "Причина отклонения документа", short="Причина"),
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
SHARED_MODELS = (
    "roadmap.Task",
    "roadmap.TaskTemplate",
    "roadmap.Essay",
    "roadmap.EssayVersion",
    # ресурсы школы (фаза 45): памятку про экзамены пишет академический
    # директор, про заявки — директор по поступлению, про олимпиады —
    # директор талантов. Категория — справочник, который школа пополняет,
    # и привязывать право к его строке значило бы завести второй источник
    # владения: кто написал, видно в самой записи
    "materials.Resource",
    "materials.ResourceCategory",
)

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

#: Кто вправе заводить строки сквозных моделей. Владельца-домена у задач
#: и эссе нет, но предлагать их может любой директор — иначе массовую
#: постановку задач нечем было бы провести через предложение (инвариант №3).
SHARED_WRITERS: dict[str, tuple[str, ...]] = {
    "roadmap.Task": ALL_DIRECTORS,
    "roadmap.Essay": ALL_DIRECTORS,
    "materials.Resource": ALL_DIRECTORS,
    "materials.ResourceCategory": ALL_DIRECTORS,
}

#: Кто загружает файлы с данными — любые: поля учеников, контакты,
#: выступления, требования вузов, банк заданий. С фазы 35 это только
#: администратор: формат выгрузок у всех разный, и разбираться с чужими
#: файлами должен один человек, а не пятеро. Директора вносят данные
#: руками в таблице или вставкой текста. Это единственное место в системе,
#: где граница доменов пересекается: администратор пишет в чужой домен,
#: и каждая такая правка помечается в журнале доменом, за который он
#: действовал (`AuditLog.acting_for`). Право живёт здесь, а не во вьюхах
#: (инвариант №2): проверяют его пять разных загрузок и тест.
FILE_UPLOADERS: tuple[str, ...] = (ROLE_ADMIN,)

#: Пароли учеников от почты и Common App (фаза 65) — единственные данные,
#: которые открывают чужие аккаунты. Кто вправе их показать: директора,
#: администратор и куратор — своей группы (границу держит `core.scope`);
#: ученик видит и меняет только свои. Список один, читают его ручка
#: показа, блок карточки и тест-сторож.
CREDENTIAL_VIEWERS: tuple[str, ...] = (
    "director_behavior",
    "director_admission",
    "director_exam",
    "director_talent",
    "director_sport",
    ROLE_CURATOR,
    ROLE_ADMIN,
)
#: Кто записывает пароль и правит блок «Поступление» напрямую: Асем,
#: администратор и куратор своей группы. Ученик — свои пароли напрямую,
#: остальные поля блока предложением через очередь
CREDENTIAL_EDITORS: tuple[str, ...] = ("director_admission", ROLE_CURATOR, ROLE_ADMIN)
#: Кто загружает таблицу поступления
ADMISSION_IMPORTERS: tuple[str, ...] = ("director_admission", ROLE_ADMIN)

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
    # загрузку пробника убирает в архив куратор группы или Кымбат (фаза 63);
    # физического удаления нет — вместе с ней ушли бы баллы учеников
    "students.MockImport": ("director_exam", "curator"),
    # контакты родителей (фаза 70): заводит и убирает Салтанат по школе,
    # куратор — по своим группам, администратор — везде. Границу «своя
    # группа» держит выборка, здесь только роль
    "students.ParentContact": ("director_behavior", "curator", ROLE_ADMIN),
    # ресурсы школы ведут пять директоров вместе — как задачи и шаблоны
    "materials.Resource": ALL_DIRECTORS,
    "materials.ResourceCategory": ALL_DIRECTORS,
    # справочники конструктора эссе (фаза 43): ведёт директор по поступлению.
    # Без этих строк `can_delete` отвечал «удалять её может: никто», и запись
    # справочника нельзя было убрать вовсе — право было на экране и в таблице
    # прав, но не в реестре, из которого оно берётся
    "roadmap.EssayDocType": ("director_admission",),
    "roadmap.EssayGuide": ("director_admission",),
    "roadmap.EssayCheckQuestion": ("director_admission",),
    "roadmap.EssayExample": ("director_admission",),
    # справочники фазы 49: сюжеты главной и правила обзвона — у директора школы
    "engagement.HomeCue": ("director_behavior",),
    "engagement.CallRule": ("director_behavior",),
    # урок теории (D37, фаза 62): убирает академический директор. «Удаление» —
    # скрытие `is_active`, как у вопроса банка рядом: урок исчезает у ученика,
    # у директора остаётся в списке скрытым; архивной модели у него нет
    "prep.TheoryLesson": ("director_exam",),
}

#: Домены куратора: что он делает в чужом домене у учеников своих групп.
#:
#: С фазы 60 это было одно право — «подтверждает»: куратор принимает,
#: правит перед принятием и отклоняет с причиной то, что внесли о себе
#: его ученики. С фазы 66 прав два, и они разные по смыслу:
#:
#: * `CONFIRMS` — подтверждает внесённое учеником (экзамены, документы);
#: * `WRITES` — **вносит сам**, как владелец домена, но только по своим
#:   группам (дисциплина: посещаемость, замечания, контакты родителей).
#:
#: Смешивать их нельзя: «подтверждает» не даёт завести запись с нуля,
#: а «пишет» не ставит куратора в очередь подтверждений. Владелец домена
#: остаётся владельцем в обоих случаях — он видит всю школу и ведёт
#: справочники. Набор задан константой в коде, а не строкой настройки:
#: менять его чаще, чем раз в год, некому (см. `docs/DECISIONS.md`).
CONFIRMS, WRITES = "confirms", "writes"

CURATOR_RIGHTS: dict[str, str] = {
    "exam": CONFIRMS,
    "documents": CONFIRMS,
    # дисциплину куратор ведёт сам по своим группам (фаза 66): посещаемость
    # за день, замечания и контакты родителей. Салтанат — по всей школе
    "behavior": WRITES,
}

#: Все домены куратора — чтобы экраны перечисляли их одним списком
CURATOR_DOMAINS: tuple[str, ...] = tuple(CURATOR_RIGHTS)
#: Только те, где он подтверждает: это и есть его очередь
CURATOR_CONFIRM_DOMAINS: tuple[str, ...] = tuple(c for c, r in CURATOR_RIGHTS.items() if r == CONFIRMS)
#: Только те, где он вносит сам
CURATOR_WRITE_DOMAINS: tuple[str, ...] = tuple(c for c, r in CURATOR_RIGHTS.items() if r == WRITES)


# --- Служебные функции --------------------------------------------------


def domain_of_role(role: str) -> Domain | None:
    """Основной домен роли. Для `student`, `curator` и `admin` домена нет.

    У директора по поступлению доменов два (фаза 60): «Поступление»
    и «Документы». Основной — первый в реестре; все — `domains_of_role`.
    """
    for d in DOMAINS.values():
        if d.role == role:
            return d
    return None


def domains_of_role(role: str) -> list[Domain]:
    """Все домены роли — в порядке реестра, основной первым."""
    return [d for d in DOMAINS.values() if d.role == role]


def curator_confirms(domain_code: str) -> bool:
    """Подтверждает ли куратор данные этого домена у учеников своих групп."""
    return CURATOR_RIGHTS.get(domain_code) == CONFIRMS


def curator_writes(domain_code: str) -> bool:
    """Вносит ли куратор данные этого домена сам — по своим группам (фаза 66)."""
    return CURATOR_RIGHTS.get(domain_code) == WRITES


def curator_may_write(model_label: str, field_name: str) -> bool:
    """Вправе ли куратор писать в это поле у ученика своей группы.

    Границу «своя группа — чужая» здесь не считаем: её держит выборка
    (`core.scope`), одна на всю систему. Здесь — только про поле: право
    может быть у домена целиком (дисциплина) или у отдельного поля
    (фаза 70 — телефон, почта Common App и папка в блоке «Поступление»).
    """
    domain = domain_of_field(model_label, field_name)
    if domain is None:
        return False
    spec = spec_of_field(model_label, field_name)
    return curator_writes(domain.code) or bool(spec and spec.curator_writes)


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


#: Администратор видит и правит все домены (фаза 68) — решение владельца,
#: согласованное со школой. Право задано здесь одной строкой, а не
#: перечислением роли по сериализаторам. Каждая его правка помечается
#: в журнале «правил администратор за домен «…»» — владелец домена видит,
#: что значение внёс не он. Первичные данные за ученика администратор
#: не вносит: предложения, документы и анкета остаются учеником
#: (`accounts.permissions.ADMIN_CLOSED_ROUTES`)
ADMIN_WRITES_ALL_DOMAINS = True


def can_write(role: str, model_label: str, field_name: str) -> bool:
    """Может ли роль писать в это поле (инвариант №1).

    С фазы 66 у куратора есть домен, в который он пишет сам, — дисциплина.
    Владельцем он от этого не становится: справочники и вся школа остаются
    у Салтанат, а границу «свои ученики» держит выборка. С фазы 68
    администратор пишет во все домены — с пометкой в журнале.
    """
    d = domain_of_field(model_label, field_name)
    if d is None:
        return False
    if d.role == role:
        return True
    if role == ROLE_ADMIN and ADMIN_WRITES_ALL_DOMAINS:
        return True
    if role != ROLE_CURATOR:
        return False
    # право домена (дисциплина) или право отдельного поля (фаза 70)
    spec = spec_of_field(model_label, field_name)
    return curator_writes(d.code) or bool(spec and spec.curator_writes)


def can_upload_files(role: str) -> bool:
    """Может ли роль загружать файлы с данными (фаза 35 — только администратор)."""
    return role in FILE_UPLOADERS


def can_write_for(role: str, domain_code: str, model_label: str, field_name: str) -> bool:
    """Может ли роль писать в поле, действуя за домен `domain_code`.

    Директор — только в своё, как и `can_write`: домен в запросе ему
    ничего не добавляет. Администратор пишет за выбранный домен, и только
    в него: загрузка файла и вставка текста за «Экзамены» не тронут поле
    поступления. Это и есть та самая единственная точка пересечения
    доменов — она названа одной функцией, чтобы валидатор предложений,
    применение и импорт не расходились в том, что администратору можно.
    """
    # администратор с выбранным доменом (загрузка файла, вставка текста) —
    # только в этот домен, даже когда прямое право у него на всё (фаза 68):
    # файл «за экзамены» не должен молча тронуть поле поступления
    if role == ROLE_ADMIN and domain_code:
        owner = domain_of_field(model_label, field_name)
        return owner is not None and owner.code == domain_code
    if can_write(role, model_label, field_name):
        return True
    if not can_upload_files(role) or not domain_code:
        return False
    owner = domain_of_field(model_label, field_name)
    return owner is not None and owner.code == domain_code


def can_write_shared(role: str, model_label: str) -> bool:
    """Может ли роль предлагать строки сквозной модели (задачи, эссе)."""
    return role in SHARED_WRITERS.get(model_label, ())


def can_student_propose(model_label: str, field_name: str) -> bool:
    """Может ли ученик предложить значение этого поля — про себя (фаза 37).

    Предложение — не запись: применяет владелец домена. Внутренние ярлыки
    не предлагаются никогда, даже если у поля по ошибке появится флаг:
    инвариант №7 держится кодом, а не аккуратностью реестра.
    """
    spec = spec_of_field(model_label, field_name)
    if spec is None or spec.internal_label:
        return False
    return spec.student_proposable


def student_proposable_models() -> set[str]:
    """Модели, в которых у ученика есть хоть одно предлагаемое поле."""
    out: set[str] = set()
    for d in DOMAINS.values():
        for m in d.models:
            # предлагать можно только про себя: модель обязана вести к ученику
            if m.student_path is None:
                continue
            if any(f.student_proposable and not f.internal_label for f in m.fields):
                out.add(m.label)
    return out


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
