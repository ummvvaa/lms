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

from django.utils.translation import gettext, gettext_lazy, gettext_noop


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
        (MANUAL, gettext_lazy("Руками")),
        (IMPORT, gettext_lazy("Импорт")),
        (AI, gettext_lazy("ИИ")),
        (SYNC, gettext_lazy("Фоновая сверка")),
        (STUDENT_ONBOARDING, gettext_lazy("Анкета ученика")),
        (STUDENT_PROPOSAL, gettext_lazy("Предложил ученик")),
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
        return gettext("от {minimum} до {maximum} с шагом {step}").format(
            minimum=_plain(self.minimum), maximum=_plain(self.maximum), step=_plain(self.step)
        )


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


#: Единицы полей — коды, а не слова: по ним `range_hint` выбирает фразу,
#: а `core.audit` — как назвать границу. Человеку единица показывается
#: только внутри переведённой фразы
UNIT_SCORE = "балл"  # i18n-skip: код единицы, сравнивается в core.audit
UNIT_HOURS = "ч"  # i18n-skip: код единицы, человеку показывается фразой range_hint
UNIT_PERCENT = "%"

#: Подсказка о границах поля — фраза целиком по единице: в казахском
#: число и единица стоят по-своему, склеивать их нельзя
_RANGE_BOTH: dict[str, str] = {
    UNIT_SCORE: gettext_noop("от {minimum} до {maximum} баллов"),
    UNIT_PERCENT: gettext_noop("от {minimum} до {maximum}%"),
    UNIT_HOURS: gettext_noop("от {minimum} до {maximum} часов"),
    "": gettext_noop("от {minimum} до {maximum}"),
}
_RANGE_MAX: dict[str, str] = {
    UNIT_SCORE: gettext_noop("не больше {maximum} баллов"),
    UNIT_PERCENT: gettext_noop("не больше {maximum}%"),
    UNIT_HOURS: gettext_noop("не больше {maximum} часов"),
    "": gettext_noop("не больше {maximum}"),
}
_RANGE_MIN: dict[str, str] = {
    UNIT_SCORE: gettext_noop("не меньше {minimum} баллов"),
    UNIT_PERCENT: gettext_noop("не меньше {minimum}%"),
    UNIT_HOURS: gettext_noop("не меньше {minimum} часов"),
    "": gettext_noop("не меньше {minimum}"),
}
#: единица вне таблиц выше — подставляется словом, как пришла
_RANGE_ANY_UNIT = (
    gettext_noop("от {minimum} до {maximum} {unit}"),
    gettext_noop("не больше {maximum} {unit}"),
    gettext_noop("не меньше {minimum} {unit}"),
)


@dataclass(frozen=True)
class FieldSpec:
    """Одно редактируемое поле домена.

    `title` — как поле называется человеку: «Текущий балл IELTS».
    `short` — то же для узких мест: заголовка колонки, чипа, строки журнала.
    Технического имени (`ielts_current`) человек не видит нигде: ни один
    экран не собирает подпись из имени переменной (инвариант №2).

    В реестре подписи лежат исходной русской строкой (`title_ru`, `short_ru`,
    помечены `gettext_noop`), а `title` и `short` переводят их в момент
    чтения — на язык запроса. Готовая строка, а не ленивая: подписи уходят
    в `join`, в XLSX и в JSON, куда ленивая строка не годится.
    """

    name: str
    title_ru: str
    #: короткая подпись для узких мест; пусто — берётся `title`
    short_ru: str = ""
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

    @property
    def title(self) -> str:
        """Подпись поля на языке запроса."""
        return gettext(self.title_ru)

    @property
    def short(self) -> str:
        """Короткая подпись на языке запроса; пусто — её не задали."""
        return gettext(self.short_ru) if self.short_ru else ""

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
        if self.minimum is not None and self.maximum is not None:
            table, fallback = _RANGE_BOTH, _RANGE_ANY_UNIT[0]
        elif self.maximum is not None:
            table, fallback = _RANGE_MAX, _RANGE_ANY_UNIT[1]
        else:
            table, fallback = _RANGE_MIN, _RANGE_ANY_UNIT[2]
        template = table.get(self.unit, fallback)
        return gettext(template).format(
            minimum=_number(self.minimum) if self.minimum is not None else "",
            maximum=_number(self.maximum) if self.maximum is not None else "",
            unit=self.unit,
        )


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
    """Домен: роль-владелец и её модели.

    Название домена и имя владельца лежат исходной русской строкой
    (`title_ru`, `owner_ru`), а `title` и `owner_name` переводят их при
    чтении — как подписи полей в `FieldSpec`. Имя тоже переводится:
    по-английски его пишут латиницей (глоссарий, «Имена»).
    """

    code: str
    title_ru: str
    role: str
    owner_ru: str
    models: tuple[ModelSpec, ...] = field(default_factory=tuple)

    @property
    def title(self) -> str:
        """Название домена на языке запроса."""
        return gettext(self.title_ru)

    @property
    def owner_name(self) -> str:
        """Имя владельца домена на языке запроса."""
        return gettext(self.owner_ru)

    def model(self, label: str) -> ModelSpec | None:
        for m in self.models:
            if m.label.lower() == label.lower():
                return m
        return None


# --- Роли ---------------------------------------------------------------

ROLE_STUDENT = "student"
ROLE_ADMIN = "admin"
#: куратор: подтверждает внесённое учениками своих групп и вносит те же
#: данные за них сам (`CURATOR_RIGHTS`); доменом не владеет
ROLE_CURATOR = "curator"
#: учитель: отдельная учётная запись, видит только свои уроки и учеников
#: своих составов, ведёт посещаемость и оценки своих уроков (`academics`)
ROLE_TEACHER = "teacher"


class _Titles(dict):
    """Подписи ролей: значения — ленивые строки перевода.

    `ROLE_TITLES[код]` отдаёт ленивую строку — для объявлений на уровне
    класса (`accounts.models.User.Role`), где языка запроса ещё нет.
    `ROLE_TITLES.get(код)` отдаёт готовую строку на языке запроса: её
    склеивают через `join`, пишут в XLSX и в JSON, куда ленивая не годится.
    """

    def get(self, key, default=None):
        return str(self[key]) if key in self else default


ROLE_TITLES = _Titles(
    {
        ROLE_STUDENT: gettext_lazy("Ученик"),
        "director_behavior": gettext_lazy("Директор школы — профиль и дисциплина"),
        "director_admission": gettext_lazy("Директор по поступлению"),
        "director_exam": gettext_lazy("Академический директор"),
        "director_talent": gettext_lazy("Директор талантов"),
        "director_sport": gettext_lazy("Директор спорта"),
        ROLE_CURATOR: gettext_lazy("Куратор"),
        ROLE_TEACHER: gettext_lazy("Учитель"),
        ROLE_ADMIN: gettext_lazy("Администратор"),
    }
)

#: Использование платформы: события пишет каждый вошедший, читает только
#: администратор и директор школы. Клиентские действия не дают прав на данные.
USAGE_READERS: tuple[str, ...] = (ROLE_ADMIN, "director_behavior")
USAGE_WRITERS: tuple[str, ...] = tuple(ROLE_TITLES)


# --- Пять доменов -------------------------------------------------------

DOMAINS: dict[str, Domain] = {
    "behavior": Domain(
        code="behavior",
        title_ru=gettext_noop("Профиль и дисциплина"),
        role="director_behavior",
        owner_ru=gettext_noop("Салтанат"),
        models=(
            ModelSpec(
                label="students.BehaviorProfile",
                student_path="student",
                fields=(
                    FieldSpec(
                        "attendance_percent",
                        gettext_noop("Посещаемость занятий"),
                        short_ru=gettext_noop("Посещаемость"),
                        minimum=0,
                        maximum=100,
                        unit=UNIT_PERCENT,
                    ),
                    FieldSpec(
                        "remarks_count",
                        gettext_noop("Замечания за поведение"),
                        short_ru=gettext_noop("Замечания"),
                        minimum=0,
                        maximum=500,
                    ),
                    # «Выполнение ДЗ, %» не вносится руками с 30.09.2026: считается
                    # из сдач ДЗ (`homework.services.completion`)
                    FieldSpec(
                        "status",
                        gettext_noop("Статус по дисциплине"),
                        short_ru=gettext_noop("Статус"),
                        internal_label=True,
                    ),
                    # комментарий пишут о ученике, а не для него — как заметки
                    # куратора, ученику он не показывается (инвариант №7)
                    FieldSpec(
                        "comment",
                        gettext_noop("Комментарий куратора"),
                        short_ru=gettext_noop("Комментарий"),
                        internal_label=True,
                    ),
                ),
            ),
            # контакты родителей: несколько на ученика, поэтому строками
            # (инвариант №5). Ведёт их директор школы — это её домен
            # правила обзвона (фаза 49): список «кому позвонить» ведёт директор
            # школы. Условие берётся из закрытого набора, а слова, порог
            # и срочность школа меняет без выката
            ModelSpec(
                label="engagement.CallRule",
                fields=(
                    FieldSpec("code", gettext_noop("Код правила обзвона"), short_ru=gettext_noop("Код")),
                    FieldSpec("condition", gettext_noop("Условие для звонка"), short_ru=gettext_noop("Условие")),
                    FieldSpec("reason", gettext_noop("Причина одной фразой"), short_ru=gettext_noop("Причина")),
                    FieldSpec("urgency", gettext_noop("Срочность звонка"), short_ru=gettext_noop("Срочность")),
                    FieldSpec(
                        "threshold",
                        gettext_noop("Порог срабатывания"),
                        short_ru=gettext_noop("Порог"),
                        minimum=0,
                        maximum=100000,
                    ),
                    FieldSpec(
                        "order",
                        gettext_noop("Порядок в списке"),
                        short_ru=gettext_noop("Порядок"),
                        minimum=0,
                        maximum=999,
                    ),
                    FieldSpec("is_active", gettext_noop("Показывать правило"), short_ru=gettext_noop("Показывать")),
                ),
            ),
            ModelSpec(
                label="students.ParentContact",
                student_path="student",
                fields=(
                    FieldSpec("full_name", gettext_noop("ФИО родителя или опекуна"), short_ru=gettext_noop("ФИО")),
                    FieldSpec(
                        "relation", gettext_noop("Кем приходится ученику"), short_ru=gettext_noop("Кем приходится")
                    ),
                    FieldSpec("phone", gettext_noop("Телефон для связи"), short_ru=gettext_noop("Телефон")),
                    FieldSpec("email", gettext_noop("Почта для связи"), short_ru=gettext_noop("Почта")),
                    FieldSpec(
                        "preferred_channel",
                        gettext_noop("Предпочтительный способ связи"),
                        short_ru=gettext_noop("Как связываться"),
                    ),
                    FieldSpec("note", gettext_noop("Примечание о контакте"), short_ru=gettext_noop("Примечание")),
                    FieldSpec("is_primary", gettext_noop("Основной контакт"), short_ru=gettext_noop("Основной")),
                ),
            ),
        ),
    ),
    "admission": Domain(
        code="admission",
        title_ru=gettext_noop("Поступление"),
        role="director_admission",
        owner_ru=gettext_noop("Асем"),
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
                        gettext_noop("Телефон ученика"),
                        short_ru=gettext_noop("Телефон"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "common_app_email",
                        gettext_noop("Почта Common App"),
                        short_ru=gettext_noop("Почта Common App"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "drive_folder_url",
                        gettext_noop("Папка на Диске"),
                        short_ru=gettext_noop("Папка на Диске"),
                        student_proposable=True,
                    ),
                    # личная почта и срок паспорта — колонки таблицы Асем (фаза 71):
                    # почта — текст, с логином не связана; срок — своё поле,
                    # чтобы не теряться, когда ссылки на паспорт в таблице нет
                    FieldSpec(
                        "personal_email",
                        gettext_noop("Электронный адрес"),
                        short_ru=gettext_noop("Личная почта"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "passport_expires_at",
                        gettext_noop("Срок годности паспорта"),
                        short_ru=gettext_noop("Срок паспорта"),
                        student_proposable=True,
                    ),
                    # цели ученика: в таблице Асем таких колонок нет, и
                    # в карточке их тоже нет (фаза 70) — карточка «Цели
                    # поступления» убрана. Поля остаются: их спрашивает
                    # анкета первого входа, а читают подбор вузов,
                    # стипендии, профтест и резюме портфолио
                    FieldSpec(
                        "target_country",
                        gettext_noop("Целевая страна"),
                        short_ru=gettext_noop("Страна"),
                        student_proposable=True,
                        card="none",
                    ),
                    FieldSpec(
                        "target_major",
                        gettext_noop("Целевая специальность"),
                        short_ru=gettext_noop("Специальность"),
                        student_proposable=True,
                        card="none",
                    ),
                    FieldSpec(
                        "target_level",
                        gettext_noop("Уровень обучения цели"),
                        short_ru=gettext_noop("Уровень"),
                        student_proposable=True,
                        card="none",
                    ),
                    # служебные признаки — в таблице и фильтрах, в карточке нет:
                    # готовность и дашборд Асем их читают, а человеку в карточке
                    # они ничего не говорят. Импорт проставляет их по паролю
                    FieldSpec(
                        "has_common_app", gettext_noop("Аккаунт Common App заведён"), short_ru="Common App", card="none"
                    ),
                    FieldSpec(
                        "has_application_account",
                        gettext_noop("Кабинет подачи заведён"),
                        short_ru=gettext_noop("Кабинет подачи"),
                        card="none",
                    ),
                    FieldSpec(
                        "status",
                        gettext_noop("Статус по поступлению"),
                        short_ru=gettext_noop("Статус"),
                        internal_label=True,
                        card="none",
                    ),
                ),
            ),
            ModelSpec(
                label="universities.StudentUniversity",
                student_path="student",
                fields=(
                    FieldSpec(
                        "program", gettext_noop("Программа в списке ученика"), short_ru=gettext_noop("Программа")
                    ),
                    FieldSpec("admission_round", gettext_noop("Раунд подачи"), short_ru=gettext_noop("Раунд")),
                    FieldSpec("tier", gettext_noop("Категория вуза в списке"), short_ru=gettext_noop("Категория")),
                    FieldSpec("application_status", gettext_noop("Статус заявки"), short_ru=gettext_noop("Заявка")),
                    FieldSpec("note", gettext_noop("Примечание к вузу"), short_ru=gettext_noop("Примечание")),
                ),
            ),
            ModelSpec(
                label="universities.University",
                fields=(
                    FieldSpec("name", gettext_noop("Название вуза"), short_ru=gettext_noop("Вуз")),
                    FieldSpec("country", gettext_noop("Страна вуза"), short_ru=gettext_noop("Страна")),
                    FieldSpec("website", gettext_noop("Сайт вуза"), short_ru=gettext_noop("Сайт")),
                    FieldSpec("domain", gettext_noop("Домен сайта для сверки"), short_ru=gettext_noop("Домен сайта")),
                    FieldSpec(
                        "world_rank",
                        gettext_noop("Место в мировом рейтинге"),
                        short_ru=gettext_noop("Рейтинг"),
                        minimum=1,
                        maximum=5000,
                    ),
                    FieldSpec("data_source", gettext_noop("Откуда запись"), short_ru=gettext_noop("Источник")),
                    FieldSpec(
                        "is_verified", gettext_noop("Данные подтверждены"), short_ru=gettext_noop("Подтверждено")
                    ),
                ),
            ),
            ModelSpec(
                label="universities.Program",
                fields=(
                    FieldSpec("university", gettext_noop("Вуз программы"), short_ru=gettext_noop("Вуз")),
                    FieldSpec("name", gettext_noop("Название программы"), short_ru=gettext_noop("Программа")),
                    FieldSpec("level", gettext_noop("Уровень обучения"), short_ru=gettext_noop("Уровень")),
                    FieldSpec("data_source", gettext_noop("Откуда запись"), short_ru=gettext_noop("Источник")),
                    FieldSpec(
                        "is_verified", gettext_noop("Данные подтверждены"), short_ru=gettext_noop("Подтверждено")
                    ),
                ),
            ),
            ModelSpec(
                label="universities.AdmissionRound",
                fields=(
                    FieldSpec("program", gettext_noop("Программа раунда"), short_ru=gettext_noop("Программа")),
                    FieldSpec("round_type", gettext_noop("Тип раунда подачи"), short_ru=gettext_noop("Раунд")),
                    FieldSpec("deadline", gettext_noop("Дедлайн подачи"), short_ru=gettext_noop("Дедлайн")),
                    FieldSpec("source_url", gettext_noop("Ссылка на источник"), short_ru=gettext_noop("Источник")),
                    FieldSpec("checked_at", gettext_noop("Дата последней сверки"), short_ru=gettext_noop("Сверено")),
                    FieldSpec("data_source", gettext_noop("Откуда запись"), short_ru=gettext_noop("Источник")),
                    FieldSpec(
                        "is_verified", gettext_noop("Данные подтверждены"), short_ru=gettext_noop("Подтверждено")
                    ),
                ),
            ),
            ModelSpec(
                label="universities.AdmissionRequirement",
                fields=(
                    FieldSpec("program", gettext_noop("Программа требований"), short_ru=gettext_noop("Программа")),
                    FieldSpec("min_gpa", gettext_noop("Минимальный GPA"), short_ru="GPA", minimum=0, maximum=5),
                    FieldSpec(
                        "min_ielts",
                        gettext_noop("Минимальный балл IELTS"),
                        short_ru="IELTS",
                        minimum=0,
                        maximum=9,
                        unit=UNIT_SCORE,
                    ),
                    FieldSpec(
                        "min_toefl",
                        gettext_noop("Минимальный балл TOEFL"),
                        short_ru="TOEFL",
                        minimum=0,
                        maximum=120,
                        unit=UNIT_SCORE,
                    ),
                    FieldSpec(
                        "min_sat",
                        gettext_noop("Минимальный балл SAT"),
                        short_ru="SAT",
                        minimum=400,
                        maximum=1600,
                        unit=UNIT_SCORE,
                    ),
                    FieldSpec(
                        "min_act",
                        gettext_noop("Минимальный балл ACT"),
                        short_ru="ACT",
                        minimum=1,
                        maximum=36,
                        unit=UNIT_SCORE,
                    ),
                    FieldSpec(
                        "required_subjects", gettext_noop("Требуемые предметы"), short_ru=gettext_noop("Предметы")
                    ),
                    FieldSpec(
                        "portfolio_required", gettext_noop("Портфолио обязательно"), short_ru=gettext_noop("Портфолио")
                    ),
                    FieldSpec(
                        "portfolio_note",
                        gettext_noop("Что требуют от портфолио"),
                        short_ru=gettext_noop("Условия портфолио"),
                    ),
                    FieldSpec("notes", gettext_noop("Примечания к требованиям"), short_ru=gettext_noop("Примечания")),
                    FieldSpec("source_url", gettext_noop("Ссылка на источник"), short_ru=gettext_noop("Источник")),
                    FieldSpec(
                        "checked_at",
                        gettext_noop("Дата актуализации требований"),
                        short_ru=gettext_noop("Актуально на"),
                    ),
                    FieldSpec("data_source", gettext_noop("Откуда запись"), short_ru=gettext_noop("Источник")),
                    FieldSpec(
                        "is_verified", gettext_noop("Данные подтверждены"), short_ru=gettext_noop("Подтверждено")
                    ),
                ),
            ),
            # стипендии и гранты (фаза 44): справочник домена «Поступление».
            # Признак «не подтверждено» тот же, что у требований (инвариант №14)
            ModelSpec(
                label="universities.Scholarship",
                fields=(
                    FieldSpec("name", gettext_noop("Название стипендии"), short_ru=gettext_noop("Стипендия")),
                    FieldSpec("organizer", gettext_noop("Организатор стипендии"), short_ru=gettext_noop("Организатор")),
                    FieldSpec("country", gettext_noop("Страна стипендии"), short_ru=gettext_noop("Страна")),
                    FieldSpec("level", gettext_noop("Уровень обучения"), short_ru=gettext_noop("Уровень")),
                    FieldSpec(
                        "funding_type", gettext_noop("Тип финансирования"), short_ru=gettext_noop("Финансирование")
                    ),
                    FieldSpec(
                        "amount_min",
                        gettext_noop("Сумма финансирования от"),
                        short_ru=gettext_noop("Сумма от"),
                        minimum=0,
                    ),
                    FieldSpec(
                        "amount_max",
                        gettext_noop("Сумма финансирования до"),
                        short_ru=gettext_noop("Сумма до"),
                        minimum=0,
                    ),
                    FieldSpec("currency", gettext_noop("Валюта суммы"), short_ru=gettext_noop("Валюта")),
                    FieldSpec(
                        "for_international",
                        gettext_noop("Основание: для иностранцев"),
                        short_ru=gettext_noop("Иностранцам"),
                    ),
                    FieldSpec("for_merit", gettext_noop("Основание: за заслуги"), short_ru=gettext_noop("За заслуги")),
                    FieldSpec("for_need", gettext_noop("Основание: по нужде"), short_ru=gettext_noop("По нужде")),
                    FieldSpec(
                        "deadline", gettext_noop("Дедлайн подачи на стипендию"), short_ru=gettext_noop("Дедлайн")
                    ),
                    FieldSpec("url", gettext_noop("Ссылка на страницу стипендии"), short_ru=gettext_noop("Ссылка")),
                    FieldSpec(
                        "requirements", gettext_noop("Требования стипендии"), short_ru=gettext_noop("Требования")
                    ),
                    FieldSpec("description", gettext_noop("Описание стипендии"), short_ru=gettext_noop("Описание")),
                    FieldSpec("university", gettext_noop("Вуз стипендии"), short_ru=gettext_noop("Вуз")),
                    FieldSpec("is_active", gettext_noop("Показывать в каталоге"), short_ru=gettext_noop("В каталоге")),
                    FieldSpec("data_source", gettext_noop("Откуда запись"), short_ru=gettext_noop("Источник")),
                    FieldSpec(
                        "is_verified", gettext_noop("Данные подтверждены"), short_ru=gettext_noop("Подтверждено")
                    ),
                ),
            ),
        ),
    ),
    "exam": Domain(
        code="exam",
        title_ru=gettext_noop("Экзамены"),
        role="director_exam",
        owner_ru=gettext_noop("Кымбат"),
        models=(
            ModelSpec(
                label="students.ExamProfile",
                student_path="student",
                fields=(
                    FieldSpec(
                        "ielts_current",
                        gettext_noop("Текущий балл IELTS"),
                        short_ru="IELTS",
                        minimum=0,
                        maximum=9,
                        unit=UNIT_SCORE,
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "ielts_target",
                        gettext_noop("Целевой балл IELTS"),
                        short_ru=gettext_noop("Цель IELTS"),
                        minimum=0,
                        maximum=9,
                        unit=UNIT_SCORE,
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "sat_current",
                        gettext_noop("Текущий балл SAT"),
                        short_ru="SAT",
                        minimum=400,
                        maximum=1600,
                        unit=UNIT_SCORE,
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "sat_target",
                        gettext_noop("Целевой балл SAT"),
                        short_ru=gettext_noop("Цель SAT"),
                        minimum=400,
                        maximum=1600,
                        unit=UNIT_SCORE,
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "hours_per_week",
                        gettext_noop("Часов подготовки в неделю"),
                        short_ru=gettext_noop("Часов в неделю"),
                        minimum=0,
                        maximum=80,
                        unit=UNIT_HOURS,
                    ),
                    FieldSpec(
                        "teacher", gettext_noop("Преподаватель по подготовке"), short_ru=gettext_noop("Преподаватель")
                    ),
                    # GPA показывается один раз — в блоке «Поступление» (фаза 71):
                    # его читают подбор, соответствие, стипендии и готовность,
                    # а приносит таблица Асем. Поле и право остаются здесь, у Кымбат
                    FieldSpec(
                        "gpa",
                        gettext_noop("Средний балл аттестата"),
                        short_ru="GPA",
                        minimum=0,
                        maximum=5,
                        student_proposable=True,
                        card="none",
                    ),
                    FieldSpec(
                        "next_mock_date",
                        gettext_noop("Дата следующего Mock Test"),
                        short_ru=gettext_noop("Следующий Mock Test"),
                    ),
                ),
            ),
            ModelSpec(
                label="students.ExamAttempt",
                student_path="student",
                fields=(
                    FieldSpec(
                        "exam_type",
                        gettext_noop("Вид экзамена"),
                        short_ru=gettext_noop("Экзамен"),
                        student_proposable=True,
                    ),
                    FieldSpec("attempt_format", gettext_noop("Формат сдачи"), short_ru=gettext_noop("Формат")),
                    FieldSpec("source", gettext_noop("Откуда результат"), short_ru=gettext_noop("Источник")),
                    FieldSpec(
                        "date", gettext_noop("Дата сдачи"), short_ru=gettext_noop("Дата"), student_proposable=True
                    ),
                    # дата не указана в источнике (таблица Асем, фаза 65): снимается,
                    # когда ученик предлагает настоящую дату и её подтверждают
                    FieldSpec(
                        "date_unknown", gettext_noop("Дата сдачи не указана"), short_ru=gettext_noop("Дата уточняется")
                    ),
                    FieldSpec(
                        "total_score",
                        gettext_noop("Общий балл за экзамен"),
                        short_ru=gettext_noop("Общий балл"),
                        minimum=0,
                        maximum=1600,
                        unit=UNIT_SCORE,
                        student_proposable=True,
                    ),
                    # секции: у IELTS шкала 0–9 с шагом 0.5, у TOEFL 0–30 —
                    # здесь стоит общая граница, точную держат разбор файла
                    # и проверка предложения (`students.mocks`, D4 про шкалы)
                    FieldSpec(
                        "listening",
                        gettext_noop("Балл за секцию Listening"),
                        short_ru="Listening",
                        minimum=0,
                        maximum=30,
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "reading",
                        gettext_noop("Балл за секцию Reading"),
                        short_ru="Reading",
                        minimum=0,
                        maximum=30,
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "writing",
                        gettext_noop("Балл за секцию Writing"),
                        short_ru="Writing",
                        minimum=0,
                        maximum=30,
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "speaking",
                        gettext_noop("Балл за секцию Speaking"),
                        short_ru="Speaking",
                        minimum=0,
                        maximum=30,
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "math",
                        gettext_noop("Балл за секцию Math"),
                        short_ru="Math",
                        minimum=0,
                        maximum=800,
                        unit=UNIT_SCORE,
                    ),
                    FieldSpec(
                        "verbal",
                        gettext_noop("Балл за секцию Verbal"),
                        short_ru="Verbal",
                        minimum=0,
                        maximum=800,
                        unit=UNIT_SCORE,
                    ),
                ),
            ),
            # цели по экзаменам (фаза 39): ставит ученик предложением,
            # подтверждает академический директор; от дат растут календарь,
            # напоминания и автозадачи о регистрации
            ModelSpec(
                label="students.ExamGoal",
                student_path="student",
                fields=(
                    FieldSpec(
                        "exam", gettext_noop("Экзамен цели"), short_ru=gettext_noop("Экзамен"), student_proposable=True
                    ),
                    FieldSpec(
                        "target_score",
                        gettext_noop("Целевой балл экзамена"),
                        short_ru=gettext_noop("Цель"),
                        minimum=0,
                        maximum=1600,
                        unit=UNIT_SCORE,
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "exam_date",
                        gettext_noop("Дата экзамена"),
                        short_ru=gettext_noop("Дата экзамена"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "registration_date",
                        gettext_noop("Дата регистрации"),
                        short_ru=gettext_noop("Регистрация"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "note",
                        gettext_noop("Примечание к цели"),
                        short_ru=gettext_noop("Примечание"),
                        student_proposable=True,
                    ),
                ),
            ),
            ModelSpec(
                label="directories.ExamKind",
                fields=(
                    FieldSpec("name", gettext_noop("Название экзамена"), short_ru=gettext_noop("Экзамен")),
                    FieldSpec("min_score", gettext_noop("Минимум шкалы"), short_ru=gettext_noop("Минимум")),
                    FieldSpec("max_score", gettext_noop("Максимум шкалы"), short_ru=gettext_noop("Максимум")),
                    FieldSpec("description", gettext_noop("Описание экзамена"), short_ru=gettext_noop("Описание")),
                    FieldSpec(
                        "is_active", gettext_noop("Показывать в списке выбора"), short_ru=gettext_noop("В списке")
                    ),
                    FieldSpec(
                        "sort_order",
                        gettext_noop("Порядок в списке"),
                        short_ru=gettext_noop("Порядок"),
                        minimum=0,
                        maximum=999,
                    ),
                ),
            ),
        ),
    ),
    "talent": Domain(
        code="talent",
        title_ru=gettext_noop("Таланты"),
        role="director_talent",
        owner_ru=gettext_noop("Арман"),
        models=(
            ModelSpec(
                label="students.TalentProfile",
                student_path="student",
                fields=(
                    FieldSpec("main_track", gettext_noop("Основной трек талантов"), short_ru=gettext_noop("Трек")),
                    FieldSpec(
                        "portfolio_status",
                        gettext_noop("Статус портфолио"),
                        short_ru=gettext_noop("Портфолио"),
                        internal_label=True,
                    ),
                    FieldSpec(
                        "comment",
                        gettext_noop("Комментарий по талантам"),
                        short_ru=gettext_noop("Комментарий"),
                        internal_label=True,
                    ),
                ),
            ),
            # отбор в олимпиадную группу — решение директора талантов.
            # Реестровую карточку ученика ведёт администратор, но этот
            # признак принадлежит домену: право на него берётся отсюда
            ModelSpec(
                label="students.Student",
                student_path="",
                fields=(
                    FieldSpec(
                        "in_olympiad_group", gettext_noop("В олимпиадной группе"), short_ru=gettext_noop("Олимпиадник")
                    ),
                ),
            ),
            ModelSpec(
                label="directories.OlympiadSubject",
                fields=(
                    FieldSpec("name", gettext_noop("Название предмета"), short_ru=gettext_noop("Предмет")),
                    FieldSpec("area", gettext_noop("Направление"), short_ru=gettext_noop("Направление")),
                    FieldSpec("description", gettext_noop("Описание предмета"), short_ru=gettext_noop("Описание")),
                    FieldSpec(
                        "is_active", gettext_noop("Показывать в списке выбора"), short_ru=gettext_noop("В списке")
                    ),
                    FieldSpec(
                        "sort_order",
                        gettext_noop("Порядок в списке"),
                        short_ru=gettext_noop("Порядок"),
                        minimum=0,
                        maximum=999,
                    ),
                ),
            ),
            ModelSpec(
                label="students.Activity",
                student_path="student",
                fields=(
                    FieldSpec(
                        "category",
                        gettext_noop("Категория активности"),
                        short_ru=gettext_noop("Категория"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "subject",
                        gettext_noop("Предмет олимпиады"),
                        short_ru=gettext_noop("Предмет"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "title",
                        gettext_noop("Название активности"),
                        short_ru=gettext_noop("Активность"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "date", gettext_noop("Дата активности"), short_ru=gettext_noop("Дата"), student_proposable=True
                    ),
                    FieldSpec(
                        "description",
                        gettext_noop("Описание активности"),
                        short_ru=gettext_noop("Описание"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "proof_url",
                        gettext_noop("Ссылка на подтверждение"),
                        short_ru=gettext_noop("Подтверждение"),
                        student_proposable=True,
                    ),
                    # подтверждение — решение директора, ученик его не предлагает
                    FieldSpec(
                        "is_confirmed", gettext_noop("Активность подтверждена"), short_ru=gettext_noop("Подтверждено")
                    ),
                ),
            ),
        ),
    ),
    "sport": Domain(
        code="sport",
        title_ru=gettext_noop("Спорт"),
        role="director_sport",
        owner_ru=gettext_noop("Нурлыбек"),
        models=(
            ModelSpec(
                label="students.SportProfile",
                student_path="student",
                fields=(
                    FieldSpec(
                        "sport_type",
                        gettext_noop("Вид спорта"),
                        short_ru=gettext_noop("Спорт"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "level",
                        gettext_noop("Уровень занятий спортом"),
                        short_ru=gettext_noop("Уровень"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "rank",
                        gettext_noop("Спортивный разряд"),
                        short_ru=gettext_noop("Разряд"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "leadership_role",
                        gettext_noop("Лидерская роль в команде"),
                        short_ru=gettext_noop("Лидерская роль"),
                        student_proposable=True,
                    ),
                ),
            ),
            ModelSpec(
                label="directories.SportType",
                fields=(
                    FieldSpec("name", gettext_noop("Название вида спорта"), short_ru=gettext_noop("Вид спорта")),
                    FieldSpec("category", gettext_noop("Категория вида спорта"), short_ru=gettext_noop("Категория")),
                    FieldSpec("description", gettext_noop("Описание вида спорта"), short_ru=gettext_noop("Описание")),
                    FieldSpec(
                        "is_active", gettext_noop("Показывать в списке выбора"), short_ru=gettext_noop("В списке")
                    ),
                    FieldSpec(
                        "sort_order",
                        gettext_noop("Порядок в списке"),
                        short_ru=gettext_noop("Порядок"),
                        minimum=0,
                        maximum=999,
                    ),
                ),
            ),
            ModelSpec(
                label="students.Competition",
                student_path="student",
                fields=(
                    FieldSpec(
                        "name",
                        gettext_noop("Название соревнования"),
                        short_ru=gettext_noop("Соревнование"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "sport_type",
                        gettext_noop("Вид спорта соревнования"),
                        short_ru=gettext_noop("Вид спорта"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "level",
                        gettext_noop("Уровень соревнования"),
                        short_ru=gettext_noop("Уровень"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "date",
                        gettext_noop("Дата соревнования"),
                        short_ru=gettext_noop("Дата"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "result",
                        gettext_noop("Результат выступления"),
                        short_ru=gettext_noop("Результат"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "has_certificate",
                        gettext_noop("Есть сертификат"),
                        short_ru=gettext_noop("Сертификат"),
                        student_proposable=True,
                    ),
                    FieldSpec(
                        "proof_url",
                        gettext_noop("Ссылка на подтверждение"),
                        short_ru=gettext_noop("Подтверждение"),
                        student_proposable=True,
                    ),
                    # решение школы, а не факт об ученике: сам ученик его не предлагает
                    FieldSpec(
                        "show_in_card",
                        gettext_noop("Показывать соревнование в карточке ученика"),
                        short_ru=gettext_noop("В карточке"),
                    ),
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
        title_ru=gettext_noop("Документы"),
        role="director_admission",
        owner_ru=gettext_noop("Асем"),
        models=(
            ModelSpec(
                label="students.StudentDocument",
                student_path="student",
                fields=(
                    FieldSpec("doc_type", gettext_noop("Тип документа"), short_ru=gettext_noop("Тип")),
                    FieldSpec("title", gettext_noop("Название документа"), short_ru=gettext_noop("Название")),
                    FieldSpec("issued_date", gettext_noop("Дата выдачи документа"), short_ru=gettext_noop("Выдан")),
                    FieldSpec(
                        "expires_at", gettext_noop("Документ действует до"), short_ru=gettext_noop("Действует до")
                    ),
                    FieldSpec("note", gettext_noop("Примечание к документу"), short_ru=gettext_noop("Примечание")),
                    # проверка (фаза 62): статус ставится решением по очереди, причину
                    # читает ученик. Ярлыком не помечены — ученик видит и то, и другое
                    FieldSpec("status", gettext_noop("Проверка документа"), short_ru=gettext_noop("Проверка")),
                    FieldSpec(
                        "reject_reason", gettext_noop("Причина отклонения документа"), short_ru=gettext_noop("Причина")
                    ),
                ),
            ),
        ),
    ),
}

#: Настройки школы — то, что ведёт только администратор.
#:
#: «Сюжеты главной» до разбора кабинетов лежали в домене Салтанат, но это
#: не данные об ученике и не справочник дисциплины, а настройка кабинета
#: ученика: что показать на главной и куда повести. Владелец у поля
#: по-прежнему один (инвариант №1) — администратор. В `DOMAINS` блок
#: не входит намеренно: шесть доменов — это шесть директоров, по ним
#: строятся таблица, импорт, очереди и дайджест, а у настроек нет
#: ни учеников, ни очереди. Поиск владельца поля и модели блок видит
SCHOOL_SETTINGS = Domain(
    code="settings",
    title_ru=gettext_noop("Настройки школы"),
    role=ROLE_ADMIN,
    owner_ru=gettext_noop("Администратор"),
    models=(
        # условие берётся из закрытого набора, а слова и цвет школа
        # меняет без выката (фаза 49)
        ModelSpec(
            label="engagement.HomeCue",
            fields=(
                FieldSpec("code", gettext_noop("Код сюжета"), short_ru=gettext_noop("Код")),
                FieldSpec("condition", gettext_noop("Условие показа сюжета"), short_ru=gettext_noop("Условие")),
                FieldSpec("title", gettext_noop("Заголовок сюжета"), short_ru=gettext_noop("Заголовок")),
                FieldSpec("description", gettext_noop("Описание сюжета"), short_ru=gettext_noop("Описание")),
                FieldSpec("action_label", gettext_noop("Подпись кнопки сюжета"), short_ru=gettext_noop("Кнопка")),
                FieldSpec("action_path", gettext_noop("Куда ведёт кнопка сюжета"), short_ru=gettext_noop("Куда ведёт")),
                FieldSpec("tone", gettext_noop("Цвет карточки сюжета"), short_ru=gettext_noop("Цвет")),
                FieldSpec(
                    "order",
                    gettext_noop("Порядок в карусели"),
                    short_ru=gettext_noop("Порядок"),
                    minimum=0,
                    maximum=999,
                ),
                FieldSpec("is_active", gettext_noop("Показывать сюжет"), short_ru=gettext_noop("Показывать")),
            ),
        ),
        # бейджи учеников: условие — строка справочника, а не код. С 28.09.2026
        # ведёт администратор (решение владельца), раньше — директор школы
        ModelSpec(
            label="engagement.Badge",
            fields=(
                FieldSpec("code", gettext_noop("Код бейджа"), short_ru=gettext_noop("Код")),
                FieldSpec("name", gettext_noop("Название бейджа"), short_ru=gettext_noop("Бейдж")),
                FieldSpec("description", gettext_noop("Описание бейджа"), short_ru=gettext_noop("Описание")),
                FieldSpec("metric", gettext_noop("Что считает бейдж"), short_ru=gettext_noop("Считаем")),
                FieldSpec(
                    "threshold",
                    gettext_noop("Сколько нужно для бейджа"),
                    short_ru=gettext_noop("Порог"),
                    minimum=1,
                    maximum=100000,
                ),
                FieldSpec("icon", gettext_noop("Иконка бейджа"), short_ru=gettext_noop("Иконка")),
                FieldSpec(
                    "order", gettext_noop("Порядок в списке"), short_ru=gettext_noop("Порядок"), minimum=0, maximum=999
                ),
                FieldSpec("is_active", gettext_noop("Показывать бейдж"), short_ru=gettext_noop("Показывать")),
            ),
        ),
    ),
)


#: Учебная часть — блок вне `DOMAINS` с владельцем академического директора.
#: В домены не входит намеренно: таблица, импорт, очередь и дайджест
#: строятся по доменам учеников, а здесь уроки, отметки и оценки — их ведёт
#: учитель на своём уроке, куратор оформляет причины, Кымбат и администратор
#: правят расписание. Кто что пишет — решает `academics.rights`; реестр
#: даёт полям подписи и владельца, чтобы журнал помечал правку
#: администратора «за учёбу» как за любой чужой домен
ACADEMICS = Domain(
    code="academics",
    title_ru=gettext_noop("Учёба"),
    role="director_exam",
    owner_ru=gettext_noop("Кымбат"),
    models=(
        ModelSpec(
            label="academics.Lesson",
            fields=(
                FieldSpec("date", gettext_noop("Дата урока"), short_ru=gettext_noop("Дата")),
                FieldSpec("slot", gettext_noop("Номер урока"), short_ru=gettext_noop("Урок"), minimum=1, maximum=12),
                FieldSpec("room", gettext_noop("Кабинет урока"), short_ru=gettext_noop("Кабинет")),
                FieldSpec("teacher", gettext_noop("Учитель урока"), short_ru=gettext_noop("Учитель")),
                FieldSpec("substitute", gettext_noop("Замена учителя"), short_ru=gettext_noop("Замена")),
                FieldSpec("status", gettext_noop("Статус урока"), short_ru=gettext_noop("Статус")),
                FieldSpec("reason", gettext_noop("Причина изменения урока"), short_ru=gettext_noop("Причина")),
                FieldSpec("topic", gettext_noop("Тема урока"), short_ru=gettext_noop("Тема")),
                FieldSpec("homework", gettext_noop("Домашнее задание"), short_ru=gettext_noop("ДЗ")),
                FieldSpec("kind", gettext_noop("Вид оценивания на уроке"), short_ru=gettext_noop("Вид")),
                FieldSpec("number", gettext_noop("Номер СОР или СОЧ"), short_ru=gettext_noop("Номер")),
                FieldSpec("max_score", gettext_noop("Максимум баллов"), short_ru=gettext_noop("Максимум")),
                FieldSpec("marked_at", gettext_noop("Посещаемость сохранена"), short_ru=gettext_noop("Отмечен")),
            ),
        ),
        ModelSpec(
            label="academics.Attendance",
            student_path="student",
            fields=(
                FieldSpec("mark", gettext_noop("Отметка посещаемости на уроке"), short_ru=gettext_noop("Отметка")),
                FieldSpec("arrived_at", gettext_noop("Время прихода опоздавшего"), short_ru=gettext_noop("Пришёл в")),
            ),
        ),
        ModelSpec(
            label="academics.Grade",
            student_path="student",
            fields=(
                FieldSpec(
                    "value",
                    gettext_noop("Оценка за урок"),
                    short_ru=gettext_noop("Оценка"),
                    minimum=0,
                    maximum=100,
                    unit=UNIT_SCORE,
                ),
                FieldSpec("comment", gettext_noop("Комментарий к оценке"), short_ru=gettext_noop("Комментарий")),
            ),
        ),
        ModelSpec(
            label="academics.QuarterResult",
            student_path="student",
            fields=(
                FieldSpec("grade", gettext_noop("Итог четверти"), short_ru=gettext_noop("Итог"), minimum=2, maximum=5),
                FieldSpec("reason", gettext_noop("Причина отличия итога от расчёта"), short_ru=gettext_noop("Причина")),
            ),
        ),
        ModelSpec(
            label="academics.Excuse",
            student_path="student",
            fields=(
                FieldSpec("starts", gettext_noop("Уважительная причина с"), short_ru=gettext_noop("С")),
                FieldSpec("ends", gettext_noop("Уважительная причина по"), short_ru=gettext_noop("По")),
                FieldSpec("reason", gettext_noop("Уважительная причина"), short_ru=gettext_noop("Причина")),
                FieldSpec("document", gettext_noop("Документ уважительной причины"), short_ru=gettext_noop("Документ")),
            ),
        ),
        ModelSpec(
            label="academics.ParentReport",
            student_path="student",
            fields=(
                FieldSpec("status", gettext_noop("Статус отчёта родителям"), short_ru=gettext_noop("Статус отчёта")),
                FieldSpec(
                    "curator_word", gettext_noop("Слово куратора в отчёте"), short_ru=gettext_noop("Слово куратора")
                ),
            ),
        ),
    ),
)


def _owners() -> tuple[Domain, ...]:
    """Все владельцы полей: шесть доменов, настройки школы и учебная часть."""
    return (*DOMAINS.values(), SCHOOL_SETTINGS, ACADEMICS)


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
    # правила обзвона — у директора школы; сюжеты главной — настройка
    # школы, их ведёт администратор
    "engagement.HomeCue": (ROLE_ADMIN,),
    # бейджи — настройка школы: заводит и убирает администратор
    "engagement.Badge": (ROLE_ADMIN,),
    "engagement.CallRule": ("director_behavior",),
    # урок теории (D37, фаза 62): убирает академический директор. «Удаление» —
    # скрытие `is_active`, как у вопроса банка рядом: урок исчезает у ученика,
    # у директора остаётся в списке скрытым; архивной модели у него нет
    "prep.TheoryLesson": ("director_exam",),
}

#: Домены куратора: что он делает в чужом домене у учеников своих групп.
#:
#: Прав три, и они разные по смыслу:
#:
#: * `CONFIRMS` — подтверждает внесённое учеником (экзамены, документы);
#: * `WRITES` — ведёт домен сам, как владелец, но только по своим группам
#:   (дисциплина: посещаемость, замечания, контакты родителей);
#: * `ENTERS` — **вносит за ученика**: всё, что ученик может внести о себе,
#:   куратор вносит напрямую, без очереди. Граница — не домен целиком,
#:   а ровно ученическое: поля с флагом `student_proposable` и модели,
#:   которые ученик ведёт сам (`CURATOR_ENTERS_MODELS`). Служебные поля
#:   домена — статус поступления, комментарии директоров — сюда не входят.
#:
#: У домена прав может быть несколько: в экзаменах и документах путь ученика
#: остаётся («вносит — куратор подтверждает»), а рядом появляется второй
#: («куратор вносит — сразу настоящее»). Владелец домена остаётся владельцем
#: во всех случаях — он видит всю школу и ведёт справочники. Набор задан
#: константой в коде, а не строкой настройки: менять его чаще, чем раз
#: в год, некому (см. `docs/DECISIONS.md`).
CONFIRMS, WRITES, ENTERS = "confirms", "writes", "enters"

CURATOR_RIGHTS: dict[str, frozenset[str]] = {
    "exam": frozenset({CONFIRMS, ENTERS}),
    "documents": frozenset({CONFIRMS, ENTERS}),
    # дисциплину куратор ведёт сам по своим группам: посещаемость
    # за день, замечания и контакты родителей. Салтанат — по всей школе
    "behavior": frozenset({WRITES}),
    # таланты и спорт: вносит за ученика сам, но очередь этих доменов
    # не подтверждает — её решают Арман и Нурлыбек
    "admission": frozenset({ENTERS}),
    "talent": frozenset({ENTERS}),
    "sport": frozenset({ENTERS}),
}

#: Модели, которые ученик ведёт сам, без очереди предложений, — и поля,
#: которые он в них заполняет. Куратор вносит те же поля за него.
#: У «вуза в списке» это программа и категория (раунд, статус заявки
#: и примечание ведёт Асем); у документа — всё, кроме проверки
CURATOR_ENTERS_MODELS: dict[str, tuple[str, ...]] = {
    "universities.StudentUniversity": ("program", "tier"),
    "students.StudentDocument": ("doc_type", "title", "issued_date", "expires_at", "note"),
    # «показывать в карточке» ученик не ставит, но куратор своей группы —
    # ставит: соревнование он внёс сам и знает, весит ли оно для заявки
    "students.Competition": ("show_in_card",),
}

#: Ученическое, которое куратор всё же не вносит, — с причиной
CURATOR_DOES_NOT_ENTER: dict[tuple[str, str], str] = {  # i18n-skip: причина для разработчика, людям не показывается
    ("students.AdmissionProfile", "target_country"): "цели поступления спрашивает анкета первого входа",
    ("students.AdmissionProfile", "target_major"): "цели поступления спрашивает анкета первого входа",
    ("students.AdmissionProfile", "target_level"): "цели поступления спрашивает анкета первого входа",
    ("students.ExamProfile", "ielts_current"): "текущий балл считается по официальным попыткам",
    ("students.ExamProfile", "sat_current"): "текущий балл считается по официальным попыткам",
}

#: Записи, которые куратор убирает у учеников своих групп (в архив,
#: с подтверждением): то же, что заводит. Документ — исключение: его
#: куратор загружает и перезагружает, но не удаляет. Контакты родителей
#: стоят в `DELETE_RULES` с фазы 70
CURATOR_REMOVES: tuple[str, ...] = (
    "students.ExamAttempt",
    "students.ExamGoal",
    "students.Activity",
    "students.Competition",
    "universities.StudentUniversity",
)

#: Блок «Поступление» в карточке ученика — это таблица Асем, и владелец
#: блока правит в нём каждую строку. Две из них формально живут в домене
#: экзаменов: GPA и шесть попыток (IELTS-1..3, SAT-1..3). Владелец полей
#: от этого не меняется — Кымбат ведёт их по всей школе; Асем правит их
#: только как строки своей таблицы (попытки — с источником «таблица
#: поступления», границу держит `students.admission_block`). Тем же
#: исключением её таблица писала в экзамены при импорте
#: (`import_registry.ADMISSION_TABLE_EXTRA_DOMAINS`). Остальные строки
#: блока — профиль поступления и документы — и так её домены
ADMISSION_BLOCK_EXTRA: dict[str, tuple[str, ...]] = {
    "students.ExamProfile": ("gpa",),
    "students.ExamAttempt": ("exam_type", "total_score", "date", "date_unknown"),
}


def keeps_admission_block(role: str) -> bool:
    """Правит ли роль блок «Поступление» целиком: его владелец и администратор."""
    return role == DOMAINS["admission"].role or (role == ROLE_ADMIN and ADMIN_WRITES_ALL_DOMAINS)


#: Кто отмечает посещаемость по дням. Вносит её куратор — он видит группу
#: каждое утро; Салтанат, владелец домена, посещаемость читает: лист за день
#: и журнал за месяц. Администратор правит, как и любой домен. Процент
#: посещаемости в профиле за время «до системы» остаётся у Салтанат
ATTENDANCE_MARKERS: tuple[str, ...] = (ROLE_CURATOR, ROLE_ADMIN)


def marks_attendance(role: str) -> bool:
    return role in ATTENDANCE_MARKERS


#: Все домены куратора — чтобы экраны перечисляли их одним списком
CURATOR_DOMAINS: tuple[str, ...] = tuple(CURATOR_RIGHTS)
#: Только те, где он подтверждает: это и есть его очередь
CURATOR_CONFIRM_DOMAINS: tuple[str, ...] = tuple(c for c, r in CURATOR_RIGHTS.items() if CONFIRMS in r)
#: Те, которые он ведёт сам целиком
CURATOR_WRITE_DOMAINS: tuple[str, ...] = tuple(c for c, r in CURATOR_RIGHTS.items() if WRITES in r)
#: Те, где он вносит за ученика
CURATOR_ENTER_DOMAINS: tuple[str, ...] = tuple(c for c, r in CURATOR_RIGHTS.items() if ENTERS in r)


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
    return CONFIRMS in CURATOR_RIGHTS.get(domain_code, ())


def curator_writes(domain_code: str) -> bool:
    """Ведёт ли куратор этот домен сам целиком — по своим группам (дисциплина)."""
    return WRITES in CURATOR_RIGHTS.get(domain_code, ())


def curator_enters(domain_code: str) -> bool:
    """Вносит ли куратор в этом домене данные за ученика — напрямую, без очереди."""
    return ENTERS in CURATOR_RIGHTS.get(domain_code, ())


def curator_may_write(model_label: str, field_name: str) -> bool:
    """Вправе ли куратор писать в это поле у ученика своей группы.

    Границу «своя группа — чужая» здесь не считаем: её держит выборка
    (`core.scope`), одна на всю систему. Здесь — только про поле. Право
    одно на все сериализаторы, вьюхи и импорт:

    * домен, который куратор ведёт сам (`WRITES`), — любое поле;
    * домен, где он вносит за ученика (`ENTERS`), — ровно ученическое:
      поле с `student_proposable` или поле модели, которую ученик ведёт
      сам, — кроме названного в `CURATOR_DOES_NOT_ENTER`.
    """
    domain = domain_of_field(model_label, field_name)
    if domain is None:
        return False
    if curator_writes(domain.code):
        return True
    if not curator_enters(domain.code):
        return False
    if (model_label, field_name) in CURATOR_DOES_NOT_ENTER:
        return False
    if field_name in CURATOR_ENTERS_MODELS.get(model_label, ()):
        return True
    spec = spec_of_field(model_label, field_name)
    return bool(spec and spec.student_proposable)


def curator_entry_map() -> dict[str, dict]:
    """Что куратор вносит за ученика: модель → поля и право убрать запись.

    Карточка куратора строит по этой карте свои формы — фронт право
    не вычисляет и списков полей у себя не держит (инвариант №2).
    """
    result: dict[str, dict] = {}
    for code in CURATOR_ENTER_DOMAINS:
        for model in DOMAINS[code].models:
            fields = [f.name for f in model.fields if curator_may_write(model.label, f.name)]
            if fields:
                result[model.label] = {
                    "fields": fields,
                    "remove": can_delete(ROLE_CURATOR, model.label),
                    "owner": DOMAINS[code].owner_name,
                }
    return result


def curator_may_touch(model_label: str) -> bool:
    """Есть ли у куратора в этой модели хоть одно поле для записи.

    По этому вопросу вьюха решает, пускать ли куратора к созданию строки;
    какие именно поля пришли — проверяет `can_write` по каждому.
    """
    domain = domain_of_model(model_label)
    model = domain.model(model_label) if domain else None
    return model is not None and any(curator_may_write(model_label, f.name) for f in model.fields)


def domain_of_model(model_label: str) -> Domain | None:
    """Домен-владелец модели целиком. Нужен для права на удаление записи."""
    for d in _owners():
        if d.model(model_label) is not None:
            return d
    return None


def domain_of_field(model_label: str, field_name: str) -> Domain | None:
    """Домен-владелец конкретного поля конкретной модели."""
    for d in _owners():
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
    # строки блока «Поступление» из чужого домена — владельцу блока
    if role == DOMAINS["admission"].role and field_name in ADMISSION_BLOCK_EXTRA.get(model_label, ()):
        return True
    if role != ROLE_CURATOR:
        return False
    return curator_may_write(model_label, field_name)


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
    if role == ROLE_CURATOR:
        return model_label in CURATOR_REMOVES
    domain = domain_of_model(model_label)
    return domain is not None and domain.role == role


def deleters_of(model_label: str) -> tuple[str, ...]:
    """Роли, которым разрешено удаление, — для сообщения об отказе."""
    rule = DELETE_RULES.get(model_label)
    if rule is not None:
        return rule
    domain = domain_of_model(model_label)
    owners = (domain.role,) if domain else ()
    return owners + ((ROLE_CURATOR,) if model_label in CURATOR_REMOVES else ())


def editable_fields(role: str, model_label: str) -> set[str]:
    """Поля модели, которые роль вправе редактировать."""
    d = domain_of_role(role)
    if d is None:
        return set()
    m = d.model(model_label)
    return set(m.field_names) if m else set()


def spec_of_field(model_label: str, field_name: str) -> FieldSpec | None:
    """Описание поля из реестра — по нему проверяются границы значения."""
    for d in _owners():
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
    return {m.label for d in _owners() for m in d.models}


def owned_fields_map() -> dict[str, dict[str, str]]:
    """`{model_label: {field_name: domain_code}}` — плоский вид реестра."""
    out: dict[str, dict[str, str]] = {}
    for d in _owners():
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
