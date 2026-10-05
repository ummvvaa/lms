"""Настраиваемые правила школы: пороги, окна, сроки, лимиты.

Всё, что школа решает сама — с какой посещаемости ученик в риске, какая
четвертная значит «отстаёт», за сколько дней искать «нет оценок», — это
настройка администратора, а не константа в коде и не переменная окружения
(решение владельца, 30.09.2026). Реестр ниже — единственное место, где
правило описано: подпись, единица, значение по умолчанию и границы.
Значение, которое поменял администратор, лежит строкой `core.SchoolRule`;
строки нет — действует значение по умолчанию.

Значение читается из базы на каждый вызов: поменял — действует со
следующего запроса, без перезапуска и без кэша, который надо сбрасывать.
Каждая правка и сброс пишутся в журнал: кто, когда, было → стало.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.domains import SCHOOL_SETTINGS, Source

#: модель в журнале: по ней история правил отличается от правок учеников
AUDIT_LABEL = "core.SchoolRule"

#: дробное правило хранится в той же целой колонке десятыми долями (1,5 → 15)
TENTHS = 10


@dataclass(frozen=True)
class Section:
    """Раздел экрана настроек: код для адреса, подпись и одна строка о том, что внутри."""

    code: str
    title: str
    note: str


ATTENDANCE = "attendance"
GRADES = "grades"
HOMEWORK = "homework"
CURATOR = "curator"
DEADLINES = "deadlines"
REMINDERS = "reminders"
FILES = "files"
MATCH = "match"
READINESS = "readiness"
PORTFOLIO = "portfolio"
XP = "xp"
AI = "ai"

SECTIONS: tuple[Section, ...] = (
    Section(
        ATTENDANCE,
        gettext_lazy("Посещаемость"),
        gettext_lazy("Процент посещаемости, «день без причины», напоминание учителю"),
    ),
    Section(
        GRADES,
        gettext_lazy("Оценки и журнал"),
        gettext_lazy("Кто отстаёт по предмету, окно итогов четверти, журналы без записей"),
    ),
    Section(
        HOMEWORK,
        gettext_lazy("Домашние задания"),
        gettext_lazy("Пределы файлов, оценки за ДЗ в четвертной, кто не сдаёт вовремя"),
    ),
    Section(
        CURATOR,
        gettext_lazy("Куратор"),
        gettext_lazy("Корзины «кого дёргать», резкий скачок в очереди, сроки документов"),
    ),
    Section(
        DEADLINES,
        gettext_lazy("Дедлайны и окна"),
        gettext_lazy("Что считается «скоро», «горит» и «давно» в кабинетах, на главной и у помощника"),
    ),
    Section(
        REMINDERS,
        gettext_lazy("Напоминания"),
        gettext_lazy("За сколько дней ученику приходят напоминания и появляются задачи"),
    ),
    Section(
        FILES,
        gettext_lazy("Файлы и подготовка"),
        gettext_lazy("Пределы материалов и аудио, размер тренировки, слабая тема"),
    ),
    Section(
        MATCH,
        gettext_lazy("Соответствие вузам"),
        gettext_lazy("Веса и планки процента соответствия, границы категорий подбора, потолок списка вузов"),
    ),
    Section(
        READINESS,
        gettext_lazy("Готовность"),
        gettext_lazy("Веса доменов в проценте готовности ученика, стартовые планки, цели и баллы внутри доменов"),
    ),
    Section(
        PORTFOLIO,
        gettext_lazy("Портфолио"),
        gettext_lazy("Веса разделов в проценте заполнения портфолио"),
    ),
    Section(
        XP,
        gettext_lazy("XP и уровни"),
        gettext_lazy("Сколько XP ученик получает за действие и сколько XP в одном уровне"),
    ),
    Section(
        AI,
        gettext_lazy("ИИ"),
        gettext_lazy("Сколько школа готова тратить на модель в месяц"),
    ),
)

SECTION_BY_CODE: dict[str, Section] = {section.code: section for section in SECTIONS}


@dataclass(frozen=True)
class Group:
    """Правила, которые имеют смысл только вместе: сохраняются и сбрасываются целиком."""

    code: str
    title: str
    hint: str
    section: str
    #: `sum` — значения в сумме дают `total`; `descending` — каждое следующее меньше предыдущего
    check: str = "sum"
    total: int = 100


#: Соответствие: веса позиций и границы категорий подбора
MATCH_WEIGHTS = "match_weights"
MATCH_TIERS = "match_tiers"
#: Готовность: веса доменов и баллы внутри поступления и спорта
READINESS_WEIGHTS = "readiness_weights"
READINESS_ADMISSION = "readiness_admission"
READINESS_SPORT = "readiness_sport"
#: Портфолио: веса разделов процента заполнения
PORTFOLIO_WEIGHTS = "portfolio_weights"

GROUPS: tuple[Group, ...] = (
    Group(
        MATCH_WEIGHTS,
        gettext_lazy("Веса позиций в проценте соответствия"),
        gettext_lazy(
            "Сколько весит каждая позиция требований программы. Пара экзаменов (IELTS или TOEFL, SAT или ACT) "
            "весит как одна позиция"
        ),
        MATCH,
    ),
    Group(
        MATCH_TIERS,
        gettext_lazy("Границы категорий подбора"),
        gettext_lazy(
            "С какого процента соответствия программа попадает в категорию; ниже границы reach — dream. "
            "Это категории соответствия требованиям, а не шансы поступления"
        ),
        MATCH,
        check="descending",
    ),
    Group(
        READINESS_WEIGHTS,
        gettext_lazy("Веса доменов в готовности"),
        gettext_lazy(
            "Сколько весит каждый домен в проценте готовности ученика. Вес домена без данных "
            "(например, спорта у неспортсмена) поровну расходится по остальным"
        ),
        READINESS,
    ),
    Group(
        READINESS_ADMISSION,
        gettext_lazy("Баллы внутри «Поступления»"),
        gettext_lazy("Из чего складываются 100 баллов домена «Поступление» в готовности"),
        READINESS,
    ),
    Group(
        READINESS_SPORT,
        gettext_lazy("Баллы внутри «Спорта»"),
        gettext_lazy("Из чего складываются 100 баллов домена «Спорт» в готовности"),
        READINESS,
    ),
    Group(
        PORTFOLIO_WEIGHTS,
        gettext_lazy("Веса разделов портфолио"),
        gettext_lazy(
            "Сколько весит каждый раздел в проценте заполнения портфолио. Это «сколько ученик о себе рассказал», "
            "а не готовность к подаче"
        ),
        PORTFOLIO,
    ),
)

GROUP_BY_CODE: dict[str, Group] = {group.code: group for group in GROUPS}

#: единица с формами числа через черту — экран склоняет её по значению («2 дня», «21 день»)
DAYS = gettext_lazy("день|дня|дней")
POINTS = gettext_lazy("балл|балла|баллов")
MB = gettext_lazy("МБ")
PIECES = gettext_lazy("шт.")


@dataclass(frozen=True)
class Rule:
    """Одно правило: что значит, в чём меряется, какое по умолчанию, в каких границах."""

    code: str
    title: str
    hint: str
    unit: str
    default: int | float
    minimum: int | float
    maximum: int | float
    section: str = ATTENDANCE
    #: `int` — число в границах; `bool` — «да» или «нет», хранится 1 и 0;
    #: `decimal` — дробное с шагом `step`, хранится десятыми долями
    kind: str = "int"
    step: float = 1
    #: код группы (`GROUPS`): такое правило не правится по одному
    group: str = ""


#: Посещаемость ниже порога — ученик в «Рисках», процент красным на экранах
ATTENDANCE_BELOW = "attendance_below"
#: Расчётная четвертная ниже — ученик отстаёт по предмету
QUARTER_GRADE_BELOW = "quarter_grade_below"
#: Средний ФО ниже этой доли от максимума — отстаёт по предмету «Только ФО»
FO_ONLY_BELOW = "fo_only_below"
#: За сколько дней искать учеников без оценок
NO_GRADES_DAYS = "no_grades_days"
#: Урок по уважительной причине снижает процент (0 минут, урок в знаменателе)
EXCUSED_LOWERS_ATTENDANCE = "excused_lowers_attendance"
#: Длина урока, у номера которого нет звонка в сетке группы
LESSON_MINUTES_DEFAULT = "lesson_minutes_default"
#: «День без причины»: не меньше стольких «н» и не меньше такой доли уроков дня
DAY_ABSENT_MIN = "day_absent_min"
DAY_ABSENT_SHARE = "day_absent_share"
#: Через сколько минут после звонка напоминать учителю о неотмеченном уроке
UNMARKED_REMIND_MINUTES = "unmarked_remind_minutes"
#: За сколько дней помощник считает посещаемость и когда профиль «давно не обновлялся»
ASSISTANT_ATTENDANCE_DAYS = "assistant_attendance_days"
PROFILE_STALE_DAYS = "profile_stale_days"
#: За сколько дней до конца четверти учителю открывается выставление итогов
FINALS_WINDOW_DAYS = "finals_window_days"
#: Окна «журнал без оценок» у Кымбат и «неотмеченные уроки» у куратора
EMPTY_JOURNAL_DAYS = "empty_journal_days"
UNMARKED_LESSONS_DAYS = "unmarked_lessons_days"
#: Сдача ДЗ: предел одного файла, видео и число файлов в сдаче
HOMEWORK_FILE_MB = "homework_file_mb"
HOMEWORK_VIDEO_MB = "homework_video_mb"
HOMEWORK_MAX_FILES = "homework_max_files"
#: Оценки за ДЗ входят в четвертную и с каким весом к оценке ФО
HOMEWORK_IN_QUARTER = "homework_in_quarter"
HOMEWORK_WEIGHT = "homework_weight"
#: «Не сдаёт ДЗ вовремя»: выполнение ниже порога или столько несданных
HOMEWORK_BEHIND_PCT = "homework_behind_pct"
HOMEWORK_BEHIND_MISSED = "homework_behind_missed"
#: Корзины куратора «кого дёргать» и резкий скачок в очереди
MOCK_STALE_DAYS = "mock_stale_days"
EXAM_SOON_DAYS = "exam_soon_days"
IELTS_GAP = "ielts_gap"
SAT_GAP = "sat_gap"
IELTS_JUMP = "ielts_jump"
SAT_JUMP = "sat_jump"
QUEUE_GAP_SHARE = "queue_gap_share"
#: Документ истекает: когда считать истекающим и когда уведомить куратора
DOCUMENT_EXPIRING_DAYS = "document_expiring_days"
DOCUMENT_NOTICE_DAYS = "document_notice_days"
#: Задача ученика «скоро срок» на главной куратора
CURATOR_TASK_SOON_DAYS = "curator_task_soon_days"
#: Общие окна сроков: одно число на все экраны, где слово значит одно и то же
DEADLINE_CLOSE_DAYS = "deadline_close_days"
DEADLINE_NEAR_DAYS = "deadline_near_days"
DEADLINE_SOON_DAYS = "deadline_soon_days"
DEADLINE_HORIZON_DAYS = "deadline_horizon_days"
DEADLINE_DASHBOARD_DAYS = "deadline_dashboard_days"
#: Два дедлайна в списке ученика стоят вплотную
DEADLINE_TIGHT_DAYS = "deadline_tight_days"
#: «Давно»: ученик не входил, раунд не сверяли, план не открывали
STUDENT_SILENT_DAYS = "student_silent_days"
ROUND_STALE_DAYS = "round_stale_days"
PLAN_IDLE_DAYS = "plan_idle_days"
#: Напоминания и задачи ученику
REMIND_EXAM_DAYS = "remind_exam_days"
REMIND_DEADLINE_DAYS = "remind_deadline_days"
REMIND_TASK_DAYS = "remind_task_days"
REMIND_EXAM_TASK_DAYS = "remind_exam_task_days"
REMIND_SCHOLARSHIP_DAYS = "remind_scholarship_days"
DOCUMENTS_TASK_DAYS = "documents_task_days"
NEXT_MOCK_DAYS = "next_mock_days"
#: Материалы олимпиадной группы, аудио заданий и тренировка
MATERIAL_FILE_MB = "material_file_mb"
MATERIAL_MAX_FILES = "material_max_files"
PREP_AUDIO_MB = "prep_audio_mb"
PRACTICE_SIZE = "practice_size"
PRACTICE_WEAK_SHARE = "practice_weak_share"
#: Месячный лимит расходов на модель, доллары; ноль — лимита нет
LLM_MONTHLY_LIMIT = "llm_monthly_limit"
#: Соответствие требованиям: веса позиций (сумма 100)
MATCH_W_GPA = "match_w_gpa"
MATCH_W_ENGLISH = "match_w_english"
MATCH_W_STANDARDIZED = "match_w_standardized"
MATCH_W_PORTFOLIO = "match_w_portfolio"
#: Нижние планки шкал: от них считается прогресс к порогу программы
MATCH_FLOOR_GPA = "match_floor_gpa"
MATCH_FLOOR_IELTS = "match_floor_ielts"
MATCH_FLOOR_TOEFL = "match_floor_toefl"
MATCH_FLOOR_SAT = "match_floor_sat"
MATCH_FLOOR_ACT = "match_floor_act"
#: Границы категорий подбора по проценту (по убыванию); ниже reach — dream
MATCH_TIER_SAFETY = "match_tier_safety"
MATCH_TIER_MATCH = "match_tier_match"
MATCH_TIER_REACH = "match_tier_reach"
#: Потолок списка вузов у одного ученика
STUDENT_LIST_LIMIT = "student_list_limit"
#: Готовность: веса доменов (сумма 100)
READINESS_W_EXAM = "readiness_w_exam"
READINESS_W_ADMISSION = "readiness_w_admission"
READINESS_W_TALENT = "readiness_w_talent"
READINESS_W_BEHAVIOR = "readiness_w_behavior"
READINESS_W_SPORT = "readiness_w_sport"
#: Стартовые планки: прогресс считается от них к личной цели ученика
READINESS_IELTS_FLOOR = "readiness_ielts_floor"
READINESS_SAT_FLOOR = "readiness_sat_floor"
#: Цели: сколько вузов, активностей и соревнований дают полный балл
READINESS_TARGET_UNIVERSITIES = "readiness_target_universities"
READINESS_TALENT_TARGET = "readiness_talent_target"
READINESS_SPORT_COMPETITIONS = "readiness_sport_competitions"
#: Баллы внутри домена «Поступление» (сумма 100)
READINESS_POINTS_LIST = "readiness_points_list"
READINESS_POINTS_COMMON_APP = "readiness_points_common_app"
READINESS_POINTS_ACCOUNT = "readiness_points_account"
READINESS_POINTS_READY = "readiness_points_ready"
#: Баллы внутри домена «Спорт» (сумма 100)
READINESS_POINTS_COMPETITIONS = "readiness_points_competitions"
READINESS_POINTS_CERTIFICATE = "readiness_points_certificate"
READINESS_POINTS_LEADERSHIP = "readiness_points_leadership"
#: Портфолио: веса разделов процента заполнения (сумма 100)
PORTFOLIO_W_PROFILE = "portfolio_w_profile"
PORTFOLIO_W_ACADEMICS = "portfolio_w_academics"
PORTFOLIO_W_ACHIEVEMENTS = "portfolio_w_achievements"
PORTFOLIO_W_OLYMPIADS = "portfolio_w_olympiads"
PORTFOLIO_W_SPORT = "portfolio_w_sport"
PORTFOLIO_W_DOCUMENTS = "portfolio_w_documents"
#: XP за действия ученика (инвариант №12: за баллы и оценки XP нет) и шаг уровня
XP_TASK_DONE = "xp_task_done"
XP_EXERCISE_SOLVED = "xp_exercise_solved"
XP_MOCK_TAKEN = "xp_mock_taken"
XP_PROFILE_SECTION = "xp_profile_section"
XP_ESSAY_SUBMITTED = "xp_essay_submitted"
XP_ONBOARDING_DONE = "xp_onboarding_done"
XP_HOMEWORK_ON_TIME = "xp_homework_on_time"
XP_MATERIAL_APPROVED = "xp_material_approved"
XP_LEVEL_STEP = "xp_level_step"

#: одна подсказка на все начисления: что значит ноль и чего здесь нет
XP_HINT = gettext_lazy(
    "Начисляется один раз за действие. 0 — за это действие XP не даётся. За баллы экзаменов и оценки XP нет"
)

RULES: tuple[Rule, ...] = (
    # --- Посещаемость ---
    Rule(
        ATTENDANCE_BELOW,
        gettext_lazy("Порог посещаемости"),
        gettext_lazy(
            "Ниже — ученик в «Рисках», процент выделен на экранах посещаемости, "
            "успеваемости группы, в карточке и в ответах помощника"
        ),
        "%",
        85,
        0,
        100,
    ),
    Rule(
        EXCUSED_LOWERS_ATTENDANCE,
        gettext_lazy("Пропуск по уважительной причине снижает процент посещаемости"),
        gettext_lazy(
            "«Да» — урок по уважительной причине идёт в процент как пропуск; «нет» — такой урок "
            "в процент не входит вовсе"
        ),
        "",
        1,
        0,
        1,
        kind="bool",
    ),
    Rule(
        LESSON_MINUTES_DEFAULT,
        gettext_lazy("Длина урока по умолчанию"),
        gettext_lazy(
            "Для урока, у номера которого нет звонка в сетке группы: столько минут он весит в проценте посещаемости"
        ),
        gettext_lazy("мин"),
        40,
        10,
        180,
    ),
    Rule(
        DAY_ABSENT_MIN,
        gettext_lazy("«День без причины»: пропущено уроков не меньше"),
        gettext_lazy(
            "День попадает в «Риски» как пропущенный без причины, если «н» за день не меньше этого числа "
            "и не меньше доли из правила ниже"
        ),
        gettext_lazy("урок|урока|уроков"),
        2,
        1,
        10,
    ),
    Rule(
        DAY_ABSENT_SHARE,
        gettext_lazy("«День без причины»: доля пропущенных уроков дня"),
        gettext_lazy(
            "Какая часть уроков дня должна быть пропущена без причины. 100 — только если пропущены все уроки дня"
        ),
        "%",
        60,
        1,
        100,
    ),
    Rule(
        UNMARKED_REMIND_MINUTES,
        gettext_lazy("Напоминание о неотмеченном уроке"),
        gettext_lazy(
            "Через сколько минут после звонка на урок учителю приходит напоминание отметить посещаемость. "
            "Проверка идёт раз в пять минут"
        ),
        gettext_lazy("мин"),
        10,
        5,
        120,
    ),
    Rule(
        ASSISTANT_ATTENDANCE_DAYS,
        gettext_lazy("Окно посещаемости у помощника"),
        gettext_lazy("За сколько последних дней помощник считает посещаемость, когда его спрашивают, кто в риске"),
        DAYS,
        30,
        7,
        120,
    ),
    Rule(
        PROFILE_STALE_DAYS,
        gettext_lazy("Профиль дисциплины давно не обновлялся"),
        gettext_lazy(
            "Если отметок уроков у ученика нет, а профиль дисциплины не правили дольше этого срока, "
            "помощник называет ученика"
        ),
        DAYS,
        14,
        1,
        90,
    ),
    # --- Оценки и журнал ---
    Rule(
        QUARTER_GRADE_BELOW,
        gettext_lazy("Порог четвертной оценки"),
        gettext_lazy("Расчётная четвертная ниже — помощник учителя называет ученика отстающим по предмету"),
        POINTS,
        4,
        2,
        5,
        section=GRADES,
    ),
    Rule(
        FO_ONLY_BELOW,
        gettext_lazy("Порог для предметов «Только ФО»"),
        gettext_lazy("Средний ФО ниже этой доли от максимума — отстаёт по предмету без четвертной"),
        "%",
        60,
        0,
        100,
        section=GRADES,
    ),
    Rule(
        NO_GRADES_DAYS,
        gettext_lazy("Окно «нет оценок»"),
        gettext_lazy("За сколько последних дней помощник учителя ищет учеников, которые были на уроках, но без оценок"),
        DAYS,
        14,
        1,
        90,
        section=GRADES,
    ),
    Rule(
        FINALS_WINDOW_DAYS,
        gettext_lazy("Окно итогов четверти"),
        gettext_lazy("За сколько дней до конца четверти учителю в журнале открывается выставление итогов"),
        DAYS,
        6,
        0,
        30,
        section=GRADES,
    ),
    Rule(
        EMPTY_JOURNAL_DAYS,
        gettext_lazy("Журнал без оценок"),
        gettext_lazy(
            "Журнал попадает в список Кымбат, если за столько последних дней уроки шли, а оценок не поставлено ни одной"
        ),
        DAYS,
        14,
        1,
        60,
        section=GRADES,
    ),
    Rule(
        UNMARKED_LESSONS_DAYS,
        gettext_lazy("Окно неотмеченных уроков у куратора"),
        gettext_lazy("За сколько последних дней куратор видит число уроков своей группы без отметки посещаемости"),
        DAYS,
        7,
        1,
        30,
        section=GRADES,
    ),
    # --- Домашние задания ---
    Rule(
        HOMEWORK_FILE_MB,
        gettext_lazy("Предел файла в сдаче ДЗ"),
        gettext_lazy("Один файл ученика или учителя — не больше; для видео свой предел ниже"),
        MB,
        50,
        1,
        500,
        section=HOMEWORK,
    ),
    Rule(
        HOMEWORK_VIDEO_MB,
        gettext_lazy("Предел видео в сдаче ДЗ"),
        gettext_lazy("Видео с телефона весит много — для него предел отдельный"),
        MB,
        500,
        10,
        2000,
        section=HOMEWORK,
    ),
    Rule(
        HOMEWORK_MAX_FILES,
        gettext_lazy("Файлов в одной сдаче ДЗ"),
        gettext_lazy("Сколько файлов ученик прикладывает к одной работе (фото, склеенные в PDF, — один файл)"),
        PIECES,
        10,
        1,
        50,
        section=HOMEWORK,
    ),
    Rule(
        HOMEWORK_IN_QUARTER,
        gettext_lazy("Оценки за ДЗ входят в четвертную"),
        gettext_lazy(
            "«Нет» — оценка за ДЗ стоит в журнале отдельной колонкой «ДЗ» и в четвертную не идёт; "
            "«да» — идёт в среднюю ФО с весом ниже"
        ),
        "",
        0,
        0,
        1,
        section=HOMEWORK,
        kind="bool",
    ),
    Rule(
        HOMEWORK_WEIGHT,
        gettext_lazy("Вес оценки за ДЗ в четвертной"),
        gettext_lazy(
            "Доля одной оценки ФО: 100 — как обычная оценка ФО, 50 — вдвое легче. Действует, "
            "только когда оценки за ДЗ входят в четвертную"
        ),
        "%",
        100,
        10,
        100,
        section=HOMEWORK,
    ),
    Rule(
        HOMEWORK_BEHIND_PCT,
        gettext_lazy("Порог «не сдаёт ДЗ вовремя»"),
        gettext_lazy("Выполнение ДЗ за четверть ниже — ученик в списке куратора «Не сдают ДЗ вовремя»"),
        "%",
        60,
        0,
        100,
        section=HOMEWORK,
    ),
    Rule(
        HOMEWORK_BEHIND_MISSED,
        gettext_lazy("Несданных ДЗ до списка «не сдаёт»"),
        gettext_lazy("Столько несданных заданий за четверть — ученик в списке куратора, даже если процент выше порога"),
        PIECES,
        2,
        1,
        50,
        section=HOMEWORK,
    ),
    # --- Куратор ---
    Rule(
        MOCK_STALE_DAYS,
        gettext_lazy("Mock Test давно не было"),
        gettext_lazy("Последний Mock Test старше этого срока или его не было вовсе — ученик в корзине куратора"),
        DAYS,
        30,
        1,
        180,
        section=CURATOR,
    ),
    Rule(
        EXAM_SOON_DAYS,
        gettext_lazy("Экзамен скоро"),
        gettext_lazy("Экзамен ближе этого срока, а балл далеко от цели — ученик в корзине «далеко от цели»"),
        DAYS,
        60,
        1,
        365,
        section=CURATOR,
    ),
    Rule(
        IELTS_GAP,
        gettext_lazy("Отставание от цели по IELTS"),
        gettext_lazy("До цели не хватает столько баллов или больше — балл считается далёким от цели"),
        POINTS,
        1.0,
        0.5,
        9.0,
        section=CURATOR,
        kind="decimal",
        step=0.5,
    ),
    Rule(
        SAT_GAP,
        gettext_lazy("Отставание от цели по SAT"),
        gettext_lazy("До цели не хватает столько баллов или больше — балл считается далёким от цели"),
        POINTS,
        100,
        10,
        800,
        section=CURATOR,
    ),
    Rule(
        IELTS_JUMP,
        gettext_lazy("Резкий скачок IELTS"),
        gettext_lazy(
            "Новый балл в очереди отличается от прежнего на столько или больше — "
            "строка подсвечена: проверить сертификат"
        ),
        POINTS,
        1.5,
        0.5,
        9.0,
        section=CURATOR,
        kind="decimal",
        step=0.5,
    ),
    Rule(
        SAT_JUMP,
        gettext_lazy("Резкий скачок SAT"),
        gettext_lazy(
            "Новый балл в очереди отличается от прежнего на столько или больше — "
            "строка подсвечена: проверить сертификат"
        ),
        POINTS,
        150,
        10,
        800,
        section=CURATOR,
    ),
    Rule(
        QUEUE_GAP_SHARE,
        gettext_lazy("Расхождение в очереди"),
        gettext_lazy("Новое значение отличается от прежнего на такую долю или больше — у строки чип «Расхождение»"),
        "%",
        20,
        1,
        100,
        section=CURATOR,
    ),
    Rule(
        DOCUMENT_EXPIRING_DAYS,
        gettext_lazy("Документ истекает"),
        gettext_lazy("Подтверждённый документ со сроком считается истекающим за столько дней до срока"),
        DAYS,
        60,
        1,
        365,
        section=CURATOR,
    ),
    Rule(
        DOCUMENT_NOTICE_DAYS,
        gettext_lazy("Уведомление о сроке документа"),
        gettext_lazy("За столько дней до срока документа куратору приходит уведомление"),
        DAYS,
        14,
        1,
        180,
        section=CURATOR,
    ),
    Rule(
        CURATOR_TASK_SOON_DAYS,
        gettext_lazy("Задача ученика «скоро срок»"),
        gettext_lazy("Задача со сроком в ближайшие столько дней стоит на главной куратора в «скоро срок»"),
        DAYS,
        2,
        0,
        30,
        section=CURATOR,
    ),
    # --- Дедлайны и окна ---
    Rule(
        DEADLINE_CLOSE_DAYS,
        gettext_lazy("Срок горит"),
        gettext_lazy(
            "До срока столько дней или меньше: чип срока у задачи на главной ученика, " "выделенный дедлайн стипендии"
        ),
        DAYS,
        7,
        1,
        30,
        section=DEADLINES,
    ),
    Rule(
        DEADLINE_NEAR_DAYS,
        gettext_lazy("Скорый дедлайн"),
        gettext_lazy("О дедлайне в ближайшие столько дней говорит дайджест и разбор списка вузов у помощника"),
        DAYS,
        14,
        1,
        60,
        section=DEADLINES,
    ),
    Rule(
        DEADLINE_SOON_DAYS,
        gettext_lazy("Ближайшие сроки"),
        gettext_lazy(
            "Окно «скоро»: срочные дедлайны в кабинете Асем и в планах, ближайшие стипендии, «Скоро» "
            "на главной 8–10, СОР и СОЧ у помощника учителя, красный цвет дедлайна у ученика"
        ),
        DAYS,
        30,
        1,
        120,
        section=DEADLINES,
    ),
    Rule(
        DEADLINE_HORIZON_DAYS,
        gettext_lazy("Горизонт кабинетов"),
        gettext_lazy(
            "На сколько дней вперёд кабинеты директоров и помощник показывают экзамены, олимпиады, старты "
            "и дедлайны; жёлтый цвет дедлайна у ученика"
        ),
        DAYS,
        60,
        1,
        365,
        section=DEADLINES,
    ),
    Rule(
        DEADLINE_DASHBOARD_DAYS,
        gettext_lazy("Горизонт дашборда поступления"),
        gettext_lazy("На сколько дней вперёд дашборд поступления собирает дедлайны вузов"),
        DAYS,
        120,
        30,
        730,
        section=DEADLINES,
    ),
    Rule(
        DEADLINE_TIGHT_DAYS,
        gettext_lazy("Дедлайны вплотную"),
        gettext_lazy("Два дедлайна в списке ученика ближе друг к другу, чем на столько дней, — помощник это отметит"),
        DAYS,
        3,
        0,
        30,
        section=DEADLINES,
    ),
    Rule(
        STUDENT_SILENT_DAYS,
        gettext_lazy("Ученик давно не входил"),
        gettext_lazy("Не входил дольше этого срока — попадает в число «молчащих» в кабинете Салтанат"),
        DAYS,
        30,
        1,
        365,
        section=DEADLINES,
    ),
    Rule(
        ROUND_STALE_DAYS,
        gettext_lazy("Раунд давно не сверяли"),
        gettext_lazy("Дедлайн раунда не сверяли с сайтом вуза дольше этого срока — он в счётчике кабинета Асем"),
        DAYS,
        30,
        1,
        365,
        section=DEADLINES,
    ),
    Rule(
        PLAN_IDLE_DAYS,
        gettext_lazy("Плана давно не касались"),
        gettext_lazy("В плане ученика ничего не двигалось дольше этого срока — на главной появляется сюжет про план"),
        DAYS,
        7,
        1,
        90,
        section=DEADLINES,
    ),
    # --- Напоминания ---
    Rule(
        REMIND_EXAM_DAYS,
        gettext_lazy("Напоминание об экзамене"),
        gettext_lazy("За столько дней до даты экзамена ученику приходит напоминание"),
        DAYS,
        14,
        1,
        90,
        section=REMINDERS,
    ),
    Rule(
        REMIND_DEADLINE_DAYS,
        gettext_lazy("Напоминание о дедлайне вуза"),
        gettext_lazy("За столько дней до дедлайна раунда ученику приходит напоминание"),
        DAYS,
        14,
        1,
        90,
        section=REMINDERS,
    ),
    Rule(
        REMIND_TASK_DAYS,
        gettext_lazy("Напоминание о задаче"),
        gettext_lazy("За столько дней до срока задачи ученику приходит напоминание"),
        DAYS,
        3,
        0,
        30,
        section=REMINDERS,
    ),
    Rule(
        REMIND_EXAM_TASK_DAYS,
        gettext_lazy("Задача о регистрации на экзамен"),
        gettext_lazy(
            "За столько дней до даты экзамена у ученика появляется задача о регистрации; "
            "то же окно — у списка целей Кымбат"
        ),
        DAYS,
        30,
        1,
        180,
        section=REMINDERS,
    ),
    Rule(
        REMIND_SCHOLARSHIP_DAYS,
        gettext_lazy("Напоминание о стипендии"),
        gettext_lazy("За столько дней до дедлайна стипендии приходит напоминание и появляется задача «Подать»"),
        DAYS,
        21,
        1,
        180,
        section=REMINDERS,
    ),
    Rule(
        DOCUMENTS_TASK_DAYS,
        gettext_lazy("Срок задачи о документах"),
        gettext_lazy("Задача «донести документы», которую ставит куратор или Асем, получает срок через столько дней"),
        DAYS,
        7,
        1,
        60,
        section=REMINDERS,
    ),
    Rule(
        NEXT_MOCK_DAYS,
        gettext_lazy("Следующий Mock Test"),
        gettext_lazy("Если дата следующего Mock Test не назначена, помощник советует назначить его через столько дней"),
        DAYS,
        21,
        1,
        120,
        section=REMINDERS,
    ),
    # --- Файлы и подготовка ---
    Rule(
        MATERIAL_FILE_MB,
        gettext_lazy("Предел файла материала"),
        gettext_lazy(
            "Один файл материала олимпиадной группы — не больше. Тот же предел у файла ДЗ, "
            "пока хранилище файлов ДЗ не подключено"
        ),
        MB,
        15,
        1,
        200,
        section=FILES,
    ),
    Rule(
        MATERIAL_MAX_FILES,
        gettext_lazy("Файлов в одном материале"),
        gettext_lazy("Сколько файлов можно приложить к одному материалу"),
        PIECES,
        10,
        1,
        50,
        section=FILES,
    ),
    Rule(
        PREP_AUDIO_MB,
        gettext_lazy("Предел аудио задания"),
        gettext_lazy("Аудиофайл к заданию Listening в банке заданий — не больше"),
        MB,
        20,
        1,
        200,
        section=FILES,
    ),
    Rule(
        PRACTICE_SIZE,
        gettext_lazy("Заданий в тренировке"),
        gettext_lazy("Сколько заданий в одной тренировке центра подготовки, если ученик не выбрал иначе"),
        PIECES,
        10,
        1,
        50,
        section=FILES,
    ),
    Rule(
        PRACTICE_WEAK_SHARE,
        gettext_lazy("Слабая тема"),
        gettext_lazy("Тема в тренажёре считается слабой, если доля верных ответов ниже"),
        "%",
        60,
        1,
        100,
        section=FILES,
    ),
    # --- Соответствие вузам ---
    Rule(
        MATCH_W_GPA,
        gettext_lazy("Вес GPA"),
        "",
        "%",
        30,
        0,
        100,
        section=MATCH,
        group=MATCH_WEIGHTS,
    ),
    Rule(
        MATCH_W_ENGLISH,
        gettext_lazy("Вес английского (IELTS или TOEFL)"),
        "",
        "%",
        30,
        0,
        100,
        section=MATCH,
        group=MATCH_WEIGHTS,
    ),
    Rule(
        MATCH_W_STANDARDIZED,
        gettext_lazy("Вес стандартного теста (SAT или ACT)"),
        "",
        "%",
        25,
        0,
        100,
        section=MATCH,
        group=MATCH_WEIGHTS,
    ),
    Rule(
        MATCH_W_PORTFOLIO,
        gettext_lazy("Вес портфолио"),
        "",
        "%",
        15,
        0,
        100,
        section=MATCH,
        group=MATCH_WEIGHTS,
    ),
    Rule(
        MATCH_TIER_SAFETY,
        gettext_lazy("Граница safety"),
        "",
        "%",
        90,
        1,
        100,
        section=MATCH,
        group=MATCH_TIERS,
    ),
    Rule(
        MATCH_TIER_MATCH,
        gettext_lazy("Граница match"),
        gettext_lazy("С этой же границы полоска позиции в карточке вуза перестаёт быть красной"),
        "%",
        70,
        1,
        100,
        section=MATCH,
        group=MATCH_TIERS,
    ),
    Rule(
        MATCH_TIER_REACH,
        gettext_lazy("Граница reach"),
        "",
        "%",
        45,
        1,
        100,
        section=MATCH,
        group=MATCH_TIERS,
    ),
    Rule(
        MATCH_FLOOR_GPA,
        gettext_lazy("Нижняя планка GPA"),
        gettext_lazy(
            "Балл на этой планке или ниже даёт 0 % по позиции; прогресс к порогу программы считается от неё, "
            "а не от нуля"
        ),
        POINTS,
        2.0,
        0.0,
        5.0,
        section=MATCH,
        kind="decimal",
        step=0.1,
    ),
    Rule(
        MATCH_FLOOR_IELTS,
        gettext_lazy("Нижняя планка IELTS"),
        gettext_lazy(
            "Балл на этой планке или ниже даёт 0 % по позиции; прогресс к порогу программы считается от неё, "
            "а не от нуля"
        ),
        POINTS,
        5.0,
        0.0,
        9.0,
        section=MATCH,
        kind="decimal",
        step=0.5,
    ),
    Rule(
        MATCH_FLOOR_TOEFL,
        gettext_lazy("Нижняя планка TOEFL"),
        gettext_lazy(
            "Балл на этой планке или ниже даёт 0 % по позиции; прогресс к порогу программы считается от неё, "
            "а не от нуля"
        ),
        POINTS,
        45,
        0,
        120,
        section=MATCH,
    ),
    Rule(
        MATCH_FLOOR_SAT,
        gettext_lazy("Нижняя планка SAT"),
        gettext_lazy(
            "Балл на этой планке или ниже даёт 0 % по позиции; прогресс к порогу программы считается от неё, "
            "а не от нуля"
        ),
        POINTS,
        800,
        400,
        1600,
        section=MATCH,
    ),
    Rule(
        MATCH_FLOOR_ACT,
        gettext_lazy("Нижняя планка ACT"),
        gettext_lazy(
            "Балл на этой планке или ниже даёт 0 % по позиции; прогресс к порогу программы считается от неё, "
            "а не от нуля"
        ),
        POINTS,
        12,
        1,
        36,
        section=MATCH,
    ),
    Rule(
        STUDENT_LIST_LIMIT,
        gettext_lazy("Потолок списка вузов"),
        gettext_lazy("Больше стольких программ в свой список ученик не добавит, пока не уберёт лишнее"),
        PIECES,
        15,
        1,
        50,
        section=MATCH,
    ),
    # --- Готовность ---
    Rule(
        READINESS_W_EXAM,
        gettext_lazy("Вес экзаменов"),
        "",
        "%",
        35,
        0,
        100,
        section=READINESS,
        group=READINESS_WEIGHTS,
    ),
    Rule(
        READINESS_W_ADMISSION,
        gettext_lazy("Вес поступления"),
        "",
        "%",
        25,
        0,
        100,
        section=READINESS,
        group=READINESS_WEIGHTS,
    ),
    Rule(
        READINESS_W_TALENT,
        gettext_lazy("Вес портфолио в готовности"),
        "",
        "%",
        20,
        0,
        100,
        section=READINESS,
        group=READINESS_WEIGHTS,
    ),
    Rule(
        READINESS_W_BEHAVIOR,
        gettext_lazy("Вес учебной дисциплины"),
        "",
        "%",
        10,
        0,
        100,
        section=READINESS,
        group=READINESS_WEIGHTS,
    ),
    Rule(
        READINESS_W_SPORT,
        gettext_lazy("Вес спорта"),
        "",
        "%",
        10,
        0,
        100,
        section=READINESS,
        group=READINESS_WEIGHTS,
    ),
    Rule(
        READINESS_POINTS_LIST,
        gettext_lazy("Список вузов собран"),
        gettext_lazy("Полный балл — когда в списке столько вузов, сколько задано целью; меньше — пропорционально"),
        POINTS,
        25,
        0,
        100,
        section=READINESS,
        group=READINESS_ADMISSION,
    ),
    Rule(
        READINESS_POINTS_COMMON_APP,
        gettext_lazy("Есть Common App"),
        "",
        POINTS,
        25,
        0,
        100,
        section=READINESS,
        group=READINESS_ADMISSION,
    ),
    Rule(
        READINESS_POINTS_ACCOUNT,
        gettext_lazy("Есть аккаунт подачи"),
        "",
        POINTS,
        10,
        0,
        100,
        section=READINESS,
        group=READINESS_ADMISSION,
    ),
    Rule(
        READINESS_POINTS_READY,
        gettext_lazy("Заявки готовы или поданы"),
        gettext_lazy("Полный балл — когда готовых, поданных или принятых заявок столько, сколько задано целью"),
        POINTS,
        40,
        0,
        100,
        section=READINESS,
        group=READINESS_ADMISSION,
    ),
    Rule(
        READINESS_POINTS_COMPETITIONS,
        gettext_lazy("Соревнования"),
        gettext_lazy("Полный балл — когда соревнований столько, сколько задано целью; меньше — пропорционально"),
        POINTS,
        60,
        0,
        100,
        section=READINESS,
        group=READINESS_SPORT,
    ),
    Rule(
        READINESS_POINTS_CERTIFICATE,
        gettext_lazy("Есть сертификат соревнования"),
        "",
        POINTS,
        25,
        0,
        100,
        section=READINESS,
        group=READINESS_SPORT,
    ),
    Rule(
        READINESS_POINTS_LEADERSHIP,
        gettext_lazy("Есть роль лидера"),
        "",
        POINTS,
        15,
        0,
        100,
        section=READINESS,
        group=READINESS_SPORT,
    ),
    Rule(
        READINESS_IELTS_FLOOR,
        gettext_lazy("Стартовая планка IELTS в готовности"),
        gettext_lazy("Прогресс по экзаменам считается от этой планки к личной цели ученика, а не от нуля"),
        POINTS,
        4.0,
        0.0,
        9.0,
        section=READINESS,
        kind="decimal",
        step=0.5,
    ),
    Rule(
        READINESS_SAT_FLOOR,
        gettext_lazy("Стартовая планка SAT в готовности"),
        gettext_lazy("Прогресс по экзаменам считается от этой планки к личной цели ученика, а не от нуля"),
        POINTS,
        800,
        400,
        1600,
        section=READINESS,
    ),
    Rule(
        READINESS_TARGET_UNIVERSITIES,
        gettext_lazy("Цель по списку вузов"),
        gettext_lazy("Столько вузов в списке и столько готовых заявок дают полный балл домена «Поступление»"),
        PIECES,
        3,
        1,
        20,
        section=READINESS,
    ),
    Rule(
        READINESS_TALENT_TARGET,
        gettext_lazy("Цель по активностям"),
        gettext_lazy("Столько активностей в портфолио дают 100 % домена «Портфолио» в готовности"),
        PIECES,
        8,
        1,
        50,
        section=READINESS,
    ),
    Rule(
        READINESS_SPORT_COMPETITIONS,
        gettext_lazy("Цель по соревнованиям"),
        gettext_lazy("Столько соревнований дают полный балл за соревнования в домене «Спорт»"),
        PIECES,
        3,
        1,
        20,
        section=READINESS,
    ),
    # --- Портфолио ---
    Rule(
        PORTFOLIO_W_PROFILE,
        gettext_lazy("Профиль поступления"),
        "",
        "%",
        20,
        0,
        100,
        section=PORTFOLIO,
        group=PORTFOLIO_WEIGHTS,
    ),
    Rule(
        PORTFOLIO_W_ACADEMICS,
        gettext_lazy("Академические результаты"),
        "",
        "%",
        25,
        0,
        100,
        section=PORTFOLIO,
        group=PORTFOLIO_WEIGHTS,
    ),
    Rule(
        PORTFOLIO_W_ACHIEVEMENTS,
        gettext_lazy("Достижения"),
        "",
        "%",
        20,
        0,
        100,
        section=PORTFOLIO,
        group=PORTFOLIO_WEIGHTS,
    ),
    Rule(
        PORTFOLIO_W_OLYMPIADS,
        gettext_lazy("Олимпиады"),
        "",
        "%",
        10,
        0,
        100,
        section=PORTFOLIO,
        group=PORTFOLIO_WEIGHTS,
    ),
    Rule(
        PORTFOLIO_W_SPORT,
        gettext_lazy("Спорт"),
        "",
        "%",
        10,
        0,
        100,
        section=PORTFOLIO,
        group=PORTFOLIO_WEIGHTS,
    ),
    Rule(
        PORTFOLIO_W_DOCUMENTS,
        gettext_lazy("Документы"),
        "",
        "%",
        15,
        0,
        100,
        section=PORTFOLIO,
        group=PORTFOLIO_WEIGHTS,
    ),
    # --- XP и уровни ---
    Rule(
        XP_TASK_DONE,
        gettext_lazy("XP за выполненную задачу роадмапа"),
        XP_HINT,
        "XP",
        10,
        0,
        1000,
        section=XP,
    ),
    Rule(
        XP_EXERCISE_SOLVED,
        gettext_lazy("XP за решённое упражнение"),
        XP_HINT,
        "XP",
        5,
        0,
        1000,
        section=XP,
    ),
    Rule(
        XP_MOCK_TAKEN,
        gettext_lazy("XP за Mock Test онлайн"),
        XP_HINT,
        "XP",
        25,
        0,
        1000,
        section=XP,
    ),
    Rule(
        XP_PROFILE_SECTION,
        gettext_lazy("XP за заполненный раздел профиля"),
        XP_HINT,
        "XP",
        15,
        0,
        1000,
        section=XP,
    ),
    Rule(
        XP_ESSAY_SUBMITTED,
        gettext_lazy("XP за эссе, отправленное на проверку"),
        XP_HINT,
        "XP",
        20,
        0,
        1000,
        section=XP,
    ),
    Rule(
        XP_ONBOARDING_DONE,
        gettext_lazy("XP за пройденный онбординг"),
        XP_HINT,
        "XP",
        30,
        0,
        1000,
        section=XP,
    ),
    Rule(
        XP_HOMEWORK_ON_TIME,
        gettext_lazy("XP за ДЗ, сданное в срок"),
        XP_HINT,
        "XP",
        5,
        0,
        1000,
        section=XP,
    ),
    Rule(
        XP_MATERIAL_APPROVED,
        gettext_lazy("XP за материал, прошедший проверку"),
        XP_HINT,
        "XP",
        25,
        0,
        1000,
        section=XP,
    ),
    Rule(
        XP_LEVEL_STEP,
        gettext_lazy("XP в одном уровне"),
        gettext_lazy(
            "Столько XP нужно на каждый следующий уровень. Уровень ученика пересчитывается по новому шагу сразу, "
            "набранные XP не меняются"
        ),
        "XP",
        100,
        10,
        10000,
        section=XP,
    ),
    # --- ИИ ---
    Rule(
        LLM_MONTHLY_LIMIT,
        gettext_lazy("Месячный лимит расходов на ИИ"),
        gettext_lazy(
            "В долларах за календарный месяц. Лимит исчерпан — операции с моделью отключаются "
            "с понятным текстом. 0 — без лимита"
        ),
        "$",
        0,
        0,
        100000,
        section=AI,
    ),
)

BY_CODE: dict[str, Rule] = {rule.code: rule for rule in RULES}

#: Переменные окружения, в которых эти правила жили до 05.10.2026. Код их больше
#: не читает: оставшаяся в `.env.prod` переменная молча ничего не делает, поэтому
#: `preflight` называет её по имени (пустое правило — настройка убрана совсем)
FORMER_ENV: dict[str, str] = {
    "ACADEMICS_DAY_MIN_ABSENT": DAY_ABSENT_MIN,
    "ACADEMICS_DAY_SHARE": DAY_ABSENT_SHARE,
    "CURATOR_MOCK_STALE_DAYS": MOCK_STALE_DAYS,
    "CURATOR_EXAM_SOON_DAYS": EXAM_SOON_DAYS,
    "CURATOR_IELTS_GAP": IELTS_GAP,
    "CURATOR_SAT_GAP": SAT_GAP,
    "CURATOR_IELTS_JUMP": IELTS_JUMP,
    "CURATOR_SAT_JUMP": SAT_JUMP,
    "CURATOR_DOCUMENT_EXPIRING_DAYS": DOCUMENT_EXPIRING_DAYS,
    "CURATOR_DOCUMENT_NOTICE_DAYS": DOCUMENT_NOTICE_DAYS,
    "REMIND_EXAM_DAYS": REMIND_EXAM_DAYS,
    "REMIND_DEADLINE_DAYS": REMIND_DEADLINE_DAYS,
    "REMIND_TASK_DAYS": REMIND_TASK_DAYS,
    "REMIND_EXAM_TASK_DAYS": REMIND_EXAM_TASK_DAYS,
    "REMIND_SCHOLARSHIP_DAYS": REMIND_SCHOLARSHIP_DAYS,
    "SCHOLARSHIP_SOON_DAYS": DEADLINE_SOON_DAYS,
    "MATERIAL_MAX_FILE_MB": MATERIAL_FILE_MB,
    "MATERIAL_MAX_FILES": MATERIAL_MAX_FILES,
    "LLM_MONTHLY_LIMIT": LLM_MONTHLY_LIMIT,
    "SUGGESTION_CONFIDENCE_THRESHOLD": "",
    "MATCH_W_GPA": MATCH_W_GPA,
    "MATCH_W_ENGLISH": MATCH_W_ENGLISH,
    "MATCH_W_STANDARDIZED": MATCH_W_STANDARDIZED,
    "MATCH_W_PORTFOLIO": MATCH_W_PORTFOLIO,
    "MATCH_FLOOR_GPA": MATCH_FLOOR_GPA,
    "MATCH_FLOOR_IELTS": MATCH_FLOOR_IELTS,
    "MATCH_FLOOR_TOEFL": MATCH_FLOOR_TOEFL,
    "MATCH_FLOOR_SAT": MATCH_FLOOR_SAT,
    "MATCH_FLOOR_ACT": MATCH_FLOOR_ACT,
    "MATCH_TIER_SAFETY": MATCH_TIER_SAFETY,
    "MATCH_TIER_MATCH": MATCH_TIER_MATCH,
    "MATCH_TIER_REACH": MATCH_TIER_REACH,
    "STUDENT_LIST_LIMIT": STUDENT_LIST_LIMIT,
    "READINESS_W_EXAM": READINESS_W_EXAM,
    "READINESS_W_ADMISSION": READINESS_W_ADMISSION,
    "READINESS_W_TALENT": READINESS_W_TALENT,
    "READINESS_W_BEHAVIOR": READINESS_W_BEHAVIOR,
    "READINESS_W_SPORT": READINESS_W_SPORT,
    "READINESS_IELTS_FLOOR": READINESS_IELTS_FLOOR,
    "READINESS_SAT_FLOOR": READINESS_SAT_FLOOR,
    "READINESS_TARGET_UNIVERSITIES": READINESS_TARGET_UNIVERSITIES,
    "READINESS_TALENT_TARGET": READINESS_TALENT_TARGET,
    "READINESS_SPORT_COMPETITIONS": READINESS_SPORT_COMPETITIONS,
    "PORTFOLIO_W_PROFILE": PORTFOLIO_W_PROFILE,
    "PORTFOLIO_W_ACADEMICS": PORTFOLIO_W_ACADEMICS,
    "PORTFOLIO_W_ACHIEVEMENTS": PORTFOLIO_W_ACHIEVEMENTS,
    "PORTFOLIO_W_OLYMPIADS": PORTFOLIO_W_OLYMPIADS,
    "PORTFOLIO_W_SPORT": PORTFOLIO_W_SPORT,
    "PORTFOLIO_W_DOCUMENTS": PORTFOLIO_W_DOCUMENTS,
    "XP_TASK_DONE": XP_TASK_DONE,
    "XP_EXERCISE_SOLVED": XP_EXERCISE_SOLVED,
    "XP_MOCK_TAKEN": XP_MOCK_TAKEN,
    "XP_PROFILE_SECTION": XP_PROFILE_SECTION,
    "XP_ESSAY_SUBMITTED": XP_ESSAY_SUBMITTED,
    "XP_ONBOARDING_DONE": XP_ONBOARDING_DONE,
    "XP_LEVEL_STEP": XP_LEVEL_STEP,
}


class RuleRejected(ValueError):
    """Значение не подходит правилу. Текст пригоден для показа человеку."""


def rule_of(code: str) -> Rule | None:
    return BY_CODE.get(code)


def group_of(code: str) -> Group | None:
    return GROUP_BY_CODE.get(code)


def members_of(code: str) -> list[Rule]:
    """Правила группы — в порядке реестра: по нему же проверяется «по убыванию»."""
    return [rule for rule in RULES if rule.group == code]


def _human(rule: Rule, stored: int) -> int | float:
    """Значение правила из колонки: дробное лежит десятыми долями."""
    return stored / TENTHS if rule.kind == "decimal" else stored


def _stored(rule: Rule, number: int | float) -> int:
    return round(number * TENTHS) if rule.kind == "decimal" else int(number)


def value(code: str) -> int | float:
    """Действующее значение правила: заданное администратором или по умолчанию."""
    from core.models import SchoolRule

    rule = BY_CODE[code]
    stored = SchoolRule.objects.filter(code=code).values_list("value", flat=True).first()
    return rule.default if stored is None else _human(rule, stored)


def values() -> dict[str, int | float]:
    """Все действующие значения одним запросом."""
    from core.models import SchoolRule

    stored = dict(SchoolRule.objects.filter(code__in=BY_CODE).values_list("code", "value"))
    return {rule.code: _human(rule, stored[rule.code]) if rule.code in stored else rule.default for rule in RULES}


#: как человек и экран пишут «да» и «нет»
YES = {"да", "true", "1", "yes"}  # i18n-skip: разбор ввода
NO = {"нет", "false", "0", "no"}  # i18n-skip: разбор ввода


def _number(rule: Rule, number: int | float) -> str:
    """Число правила для текста ошибки и журнала: дробное — с одним знаком."""
    return f"{number:.1f}" if rule.kind == "decimal" else str(int(number))


def check(rule: Rule, raw) -> int | float:
    """Проверить значение: число в границах правила; у «да/нет» — 1 или 0."""
    if rule.kind == "bool":
        word = str(raw).strip().lower()
        if raw is True or word in YES:
            return 1
        if raw is False or word in NO:
            return 0
        raise RuleRejected(_("«{rule}»: нужно «да» или «нет»").format(rule=rule.title))
    text = str(raw).strip() if isinstance(raw, int | float | str) and not isinstance(raw, bool) else ""
    number: int | float
    if rule.kind == "decimal":
        # дробную часть человек пишет и запятой, и точкой
        text = text.replace(",", ".")
        if not re.fullmatch(r"-?\d{1,6}(\.\d)?", text):
            raise RuleRejected(_("«{rule}»: нужно число с одним знаком после запятой").format(rule=rule.title))
        number = float(text)
        if _stored(rule, number) % _stored(rule, rule.step):
            raise RuleRejected(
                _("«{rule}»: значение с шагом {step}").format(rule=rule.title, step=_number(rule, rule.step))
            )
    else:
        if not re.fullmatch(r"-?\d{1,9}", text):
            raise RuleRejected(_("«{rule}»: нужно целое число").format(rule=rule.title))
        number = int(text)
    if not rule.minimum <= number <= rule.maximum:
        raise RuleRejected(
            _("«{rule}»: значение от {minimum} до {maximum}").format(
                rule=rule.title, minimum=_number(rule, rule.minimum), maximum=_number(rule, rule.maximum)
            )
        )
    return number


def words(rule: Rule, number: int | float) -> str:
    """Значение для журнала и экрана: у «да/нет» — словом.

    Слово пишется в журнал и читается оттуда как данные — не переводится.
    """
    if rule.kind == "bool":
        return "да" if number else "нет"  # i18n-skip: значение записи журнала в базе
    return _number(rule, number)


def _log(rule: Rule, old: int | float, new: int | float, *, actor) -> None:
    from core.models import AuditLog

    AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_role=getattr(actor, "role", "") or "",
        model_label=AUDIT_LABEL,
        object_id=rule.code,
        field_name=rule.code,
        domain_code=SCHOOL_SETTINGS.code,
        old_value=words(rule, old),
        new_value=words(rule, new),
        source=Source.MANUAL,
    )


@transaction.atomic
def set_value(code: str, raw, *, actor) -> int | float:
    """Задать значение. То же, что было, — записи в журнале нет."""
    from core.models import SchoolRule

    rule = BY_CODE.get(code)
    if rule is None:
        raise RuleRejected(_("Такого правила нет"))
    _alone(rule)
    number = check(rule, raw)
    old = value(code)
    SchoolRule.objects.update_or_create(code=code, defaults={"value": _stored(rule, number), "updated_by": actor})
    if _stored(rule, old) != _stored(rule, number):
        _log(rule, old, number, actor=actor)
    return number


@transaction.atomic
def reset(code: str, *, actor) -> int | float:
    """Вернуть значение по умолчанию: строка удаляется, правка — в журнал."""
    from core.models import SchoolRule

    rule = BY_CODE.get(code)
    if rule is None:
        raise RuleRejected(_("Такого правила нет"))
    _alone(rule)
    old = value(code)
    SchoolRule.objects.filter(code=code).delete()
    if _stored(rule, old) != _stored(rule, rule.default):
        _log(rule, old, rule.default, actor=actor)
    return rule.default


def _alone(rule: Rule) -> None:
    """Правило из группы по одному не правится: сумма или порядок разъедутся."""
    if rule.group:
        raise RuleRejected(
            _("«{rule}» сохраняется вместе с группой «{group}»").format(
                rule=rule.title, group=GROUP_BY_CODE[rule.group].title
            )
        )


def check_group(group: Group, numbers: dict[str, int | float]) -> None:
    """Условие группы на уже проверенных значениях: сумма или убывание."""
    ordered = [numbers[rule.code] for rule in members_of(group.code)]
    if group.check == "sum":
        total = sum(ordered)
        if total != group.total:
            raise RuleRejected(
                _("«{group}»: сумма должна быть {total}, сейчас {now}").format(
                    group=group.title, total=group.total, now=total
                )
            )
    elif any(later >= earlier for earlier, later in pairwise(ordered)):
        raise RuleRejected(
            _("«{group}»: каждое следующее значение должно быть меньше предыдущего").format(group=group.title)
        )


@transaction.atomic
def set_group(code: str, raw, *, actor) -> dict[str, int | float]:
    """Задать значения группы целиком: все правила разом, одной транзакцией."""
    from core.models import SchoolRule

    group = GROUP_BY_CODE.get(code)
    if group is None:
        raise RuleRejected(_("Такой группы правил нет"))
    members = members_of(code)
    if not isinstance(raw, dict) or set(raw) != {rule.code for rule in members}:
        raise RuleRejected(_("«{group}»: нужны значения всех правил группы").format(group=group.title))
    numbers = {rule.code: check(rule, raw[rule.code]) for rule in members}
    check_group(group, numbers)
    old = values()
    for rule in members:
        number = numbers[rule.code]
        SchoolRule.objects.update_or_create(
            code=rule.code, defaults={"value": _stored(rule, number), "updated_by": actor}
        )
        if _stored(rule, old[rule.code]) != _stored(rule, number):
            _log(rule, old[rule.code], number, actor=actor)
    return numbers


@transaction.atomic
def reset_group(code: str, *, actor) -> None:
    """Вернуть умолчания всей группы: строки удаляются, каждая правка — в журнал."""
    from core.models import SchoolRule

    if code not in GROUP_BY_CODE:
        raise RuleRejected(_("Такой группы правил нет"))
    members = members_of(code)
    old = values()
    SchoolRule.objects.filter(code__in=[rule.code for rule in members]).delete()
    for rule in members:
        if _stored(rule, old[rule.code]) != _stored(rule, rule.default):
            _log(rule, old[rule.code], rule.default, actor=actor)


def history(limit: int = 50) -> list[dict]:
    """Последние правки правил: кто, когда, было → стало."""
    from core.models import AuditLog

    rows = (
        AuditLog.objects.filter(model_label=AUDIT_LABEL).select_related("actor").order_by("-created_at", "-id")[:limit]
    )
    out = []
    for row in rows:
        rule = BY_CODE.get(row.field_name)
        who = (row.actor.full_name or row.actor.email) if row.actor_id else row.actor_title
        out.append(
            {
                "id": row.pk,
                "code": row.field_name,
                "section": rule.section if rule else "",
                "title": rule.title if rule else row.field_name,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "actor": who or "",
                "created_at": row.created_at,
            }
        )
    return out


def payload() -> dict:
    """Экран «Настройки школы»: разделы, правила с текущим значением и история правок."""
    from core.models import SchoolRule

    stored = {row.code: row for row in SchoolRule.objects.filter(code__in=BY_CODE).select_related("updated_by")}
    rules = []
    for rule in RULES:
        row = stored.get(rule.code)
        current = _human(rule, row.value) if row is not None else rule.default
        rules.append(
            {
                "code": rule.code,
                "title": rule.title,
                "hint": rule.hint,
                "unit": rule.unit,
                "section": rule.section,
                "kind": rule.kind,
                "value": current,
                "default": rule.default,
                "minimum": rule.minimum,
                "maximum": rule.maximum,
                "step": rule.step,
                "group": rule.group,
                "is_default": _stored(rule, current) == _stored(rule, rule.default),
            }
        )
    sections = [{"code": section.code, "title": section.title, "note": section.note} for section in SECTIONS]
    groups = [
        {
            "code": group.code,
            "title": group.title,
            "hint": group.hint,
            "section": group.section,
            "check": group.check,
            "total": group.total,
            "rules": [rule.code for rule in members_of(group.code)],
        }
        for group in GROUPS
    ]
    return {"sections": sections, "groups": groups, "rules": rules, "history": history()}
