"""План поступления по конкретной программе (фаза 41).

Задачи собираются под конкретную программу: её требования, тип раунда,
что уже есть в портфолио ученика и чего не хватает. Через предложение,
а не прямой записью (инвариант №3) — применяет сам ученик: это его план.

С ключом модели формулировки собирает модель на фактах справочника;
без ключа — правила, с пометкой об упрощённом режиме. Дедлайн задач
не копируется: он живёт в раунде плана (инвариант №4).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext

from core.i18n import language_of, render
from roadmap.models import ApplicationPlan, TaskCategory, TaskPriority
from suggestions.engine import apply_suggestion
from suggestions.models import Suggestion, SuggestionChange, SuggestionSource, SuggestionStatus

#: Порядок этапов плана — по нему фронт группирует задачи (по категории).
STAGE_ORDER = (
    TaskCategory.TEST,
    TaskCategory.ESSAY,
    TaskCategory.DOCUMENTS,
    TaskCategory.PORTFOLIO,
    TaskCategory.FINANCE,
    TaskCategory.UNIVERSITY,
)


def build_task_specs(plan: ApplicationPlan) -> list[dict]:
    """Список задач под программу — фактами справочника и портфолио.

    Только то, что реально относится к этой программе: разрывы по её
    требованиям, эссе, документы, подача в её раунд. Ничего не выдумываем
    сверх справочника (инвариант №10).

    Задачи ложатся ученику, а собираются в фоне: текст — на языке ученика.
    """
    with translation.override(language_of(plan.student.user)):
        return _task_specs(plan)


def _task_specs(plan: ApplicationPlan) -> list[dict]:
    from universities.matching import match

    student = plan.student
    program = plan.program
    university = program.university.name
    result = match(student, program)

    specs: list[dict] = []

    # 1. Разрывы по требованиям — задача на подготовку по каждому
    for criterion in result.unmet:
        if not criterion.countable or criterion.is_unknown:
            title = gettext("Сдать {exam} для {university}").format(exam=criterion.title, university=university)
        else:
            title = gettext("Поднять {gap} для {university}").format(gap=criterion.short_gap(), university=university)
        specs.append(
            {
                "title": title[:250],
                "category": TaskCategory.TEST,
                "priority": TaskPriority.HIGH,
                "description": gettext("Требование программы «{program}»: {requirement}").format(
                    program=program.name, requirement=criterion.phrase()
                ),
            }
        )

    # 2. Эссе — как минимум одно личное для этой программы
    specs.append(
        {
            "title": gettext("Написать эссе для {university}").format(university=university),
            "category": TaskCategory.ESSAY,
            "priority": TaskPriority.MEDIUM,
            "description": gettext("Personal statement под программу «{program}»").format(program=program.name),
        }
    )

    # 3. Документы — портфолио и обязательное портфолио, если требуется
    requirement = getattr(program, "requirement", None)
    if requirement is not None and requirement.portfolio_required:
        specs.append(
            {
                "title": gettext("Собрать портфолио для {university}").format(university=university),
                "category": TaskCategory.PORTFOLIO,
                "priority": TaskPriority.MEDIUM,
                "description": requirement.portfolio_note or gettext("Программа требует портфолио"),
            }
        )
    specs.append(
        {
            "title": gettext("Собрать документы для {university}").format(university=university),
            "category": TaskCategory.DOCUMENTS,
            "priority": TaskPriority.MEDIUM,
            "description": gettext("Аттестат, транскрипт, рекомендательные письма — проверьте чек-лист портфолио"),
        }
    )

    # 4. Финансы — если у программы есть требования (значит, подача платная/грант)
    specs.append(
        {
            "title": gettext("Разобраться с финансами и стипендиями для {university}").format(university=university),
            "category": TaskCategory.FINANCE,
            "priority": TaskPriority.LOW,
            "description": gettext("Стоимость обучения, стипендии и гранты этой программы"),
        }
    )

    # 5. Подача — привязана к раунду плана, срок берётся из дедлайна
    round_name = plan.admission_round.round_type if plan.admission_round_id else gettext("подача")
    specs.append(
        {
            "title": gettext("Подать заявку: {university} ({round})").format(university=university, round=round_name),
            "category": TaskCategory.UNIVERSITY,
            "priority": TaskPriority.HIGH,
            "description": gettext("Финальная подача в программу «{program}»").format(program=program.name),
            "use_round": True,
        }
    )
    return specs


def _phrase_with_model(plan: ApplicationPlan, specs: list[dict]) -> tuple[list[dict], bool]:
    """Дать модели переформулировать задачи по-человечески.

    Модель только формулирует — состав задач и их привязка к программе
    остаются нашими. Не получилось — возвращаем как есть.
    """
    from suggestions import llm

    if not llm.is_available():
        return specs, True

    facts = {
        "university": plan.program.university.name,
        "program": plan.program.name,
        "level": plan.program.get_level_display(),
        "round": plan.admission_round.round_type if plan.admission_round_id else "",
        "tasks": [{"title": s["title"], "category": s["category"]} for s in specs],
    }
    schema = {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}, "description": {"type": "string"}},
                    "required": ["title"],
                },
            }
        },
        "required": ["tasks"],
    }
    system = (  # i18n-skip: промпт ИИ — язык ответа модели настраивается отдельно
        "Ты помогаешь школьнику составить план поступления в конкретный вуз. "
        "Переформулируй названия и описания задач по-русски, коротко и конкретно, "
        "по фактам из запроса. Не добавляй и не убирай задачи, порядок сохрани. "
        "Вузы и требования не выдумывай."
    )
    try:
        answer = llm.complete(
            system=system,
            user=str(facts),
            purpose="plan_tasks",
            actor=plan.student.user,
            role="student",
            schema=schema,
            max_tokens=1200,
        )
        data = answer.parsed if isinstance(answer.parsed, dict) else {}
        tasks = data.get("tasks")
        if not isinstance(tasks, list) or len(tasks) != len(specs):
            return specs, True
        out = []
        for spec, phrased in zip(specs, tasks, strict=False):
            if not isinstance(phrased, dict) or not str(phrased.get("title") or "").strip():
                return specs, True
            out.append(
                {
                    **spec,
                    "title": str(phrased["title"])[:250],
                    "description": str(phrased.get("description") or spec["description"]),
                }
            )
        return out, False
    except llm.LLMUnavailable:
        return specs, True


@transaction.atomic
def generate(plan: ApplicationPlan) -> ApplicationPlan:
    """Собрать задачи плана в предложение, которое применит ученик."""
    plan.generation_status = ApplicationPlan.Generation.RUNNING
    plan.save(update_fields=["generation_status", "updated_at"])

    specs = build_task_specs(plan)
    specs, offline = _phrase_with_model(plan, specs)

    suggestion = Suggestion.objects.create(
        author=plan.student.user,
        role="student",
        domain_code="",
        source_type=SuggestionSource.PLAN,
        source_ref=f"plan:{plan.pk}",
        status=SuggestionStatus.PENDING,
    )
    for index, spec in enumerate(specs):
        key = f"task{index}"
        for field in ("title", "category", "priority", "description"):
            SuggestionChange.objects.create(
                suggestion=suggestion,
                student=plan.student,
                model_label="roadmap.Task",
                new_object_key=key,
                field_name=field,
                new_value=str(spec[field]),
                is_accepted=True,
            )

    # Статус остаётся «идёт»: готовым план считается, когда задачи уже
    # в базе, а не когда они собраны в предложение. Иначе экран успевал
    # увидеть «готово» с нулём задач, переставал опрашивать и застревал
    plan.pending_suggestion = suggestion
    plan.generation_offline = offline
    plan.save(update_fields=["pending_suggestion", "generation_offline", "updated_at"])
    return plan


def ensure_for_program(student, program, *, user) -> ApplicationPlan | None:
    """Завести план по программе, как только она попала в список ученика.

    Отдельной кнопки «создать план» больше нет: подтверждением стало само
    добавление вуза (фаза 48). Второе подтверждение превращалось в шаг,
    о котором никто не догадывался, — ровно поэтому у владельца после
    выбора двух вузов не появлялось ни плана, ни задач.

    Живой план по программе уже есть — возвращаем его, а не заводим второй.
    Убранный в архив там и остаётся: он ушёл вместе с программой, и его
    задачи — тоже. Вернули программу — собирается новый план по нынешним
    требованиям, а не поднимается прошлогодний.
    """
    from core import jobs
    from roadmap.tasks import generate_plan
    from universities.models import AdmissionRound

    existing = ApplicationPlan.objects.filter(student=student, program=program).first()
    if existing is not None:
        return existing

    admission_round = AdmissionRound.objects.filter(program=program).order_by("deadline").first()
    plan = ApplicationPlan.objects.create(
        student=student,
        program=program,
        admission_round=admission_round,
        generation_status=ApplicationPlan.Generation.RUNNING,
    )

    task = generate_plan.delay(plan.pk)
    jobs.start(
        user=user,
        kind="plan",
        title=render(language_of(user), "План по вузу «{university}»", university=program.university.name),
        task_id=task.id,
        link=f"/plan/{plan.pk}",
        retry_task="roadmap.generate_plan",
        retry_payload={"plan_id": plan.pk},
    )
    return plan


def archive_for_program(student, program, *, actor) -> int:
    """Убрать план вместе с программой: ушла программа — ушёл и план.

    Задачи уходят тем же номером удаления, что и план, поэтому возврат
    поднимает ровно их (механика мягкого удаления фазы 21).
    """
    from core.archive import archive

    plans = ApplicationPlan.objects.filter(student=student, program=program)
    removed = 0
    for plan in plans:
        archive(plan, actor=actor)
        removed += 1
    return removed


@transaction.atomic
def apply_plan(plan: ApplicationPlan, *, actor) -> dict:
    """Применить сгенерированное предложение и привязать задачи к плану.

    Задачи создаются обычным механизмом предложений (инвариант №3),
    а затем связываются с планом: их срок начинает жить в дедлайне
    раунда (инвариант №4).
    """
    from roadmap.models import Task

    suggestion = plan.pending_suggestion
    if suggestion is None:
        return {"applied": 0, "detail": gettext("Задачи ещё не сгенерированы")}

    result = apply_suggestion(suggestion, actor=actor)
    created_ids = [
        change.object_id
        for change in suggestion.changes.filter(model_label="roadmap.Task", is_applied=True)
        if change.object_id
    ]
    Task.objects.filter(pk__in=created_ids, plan__isnull=True).update(plan=plan)
    plan.updated_at = timezone.now()
    plan.save(update_fields=["updated_at"])
    return result
