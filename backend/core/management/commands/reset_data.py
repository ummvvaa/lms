"""Обнуление базы: ученики и/или справочник вузов.

Пользователей, роли и настройки не трогает никогда — иначе после очистки
в систему некому будет войти.

Записи аудита остаются: журнал не должен ссылаться в пустоту. Те из них,
что относятся к снесённым объектам, помечаются `object_deleted=True`,
и интерфейс перестаёт вести с них на несуществующие карточки.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

#: Что нужно набрать в терминале, чтобы очистка состоялась.
CONFIRM_PHRASE = "УДАЛИТЬ ДАННЫЕ"

#: Модели, чьи записи аудита после очистки указывают в пустоту.
STUDENT_LABELS = (
    "students.Student",
    "students.BehaviorProfile",
    "students.AdmissionProfile",
    "students.ExamProfile",
    "students.TalentProfile",
    "students.SportProfile",
    "students.ExamAttempt",
    "students.Activity",
    "students.Competition",
    "universities.StudentUniversity",
    "roadmap.Task",
    "roadmap.Essay",
    "roadmap.EssayVersion",
)
CATALOG_LABELS = (
    "universities.University",
    "universities.Program",
    "universities.AdmissionRound",
    "universities.AdmissionRequirement",
)


def total(model) -> int:
    """Сколько записей уйдёт, вместе с архивными.

    Обычный менеджер архив прячет, и план удаления занижал бы числа:
    человек читает «Ученики: 0» и не понимает, почему база не пустая.
    """
    return getattr(model, "all_objects", model.objects).count()


def student_counts() -> dict[str, int]:
    from materials.models import StudyMaterial
    from prep.models import MockRun, PracticeSession
    from roadmap.models import Essay, Task
    from students.models import Activity, Competition, ExamAttempt, Student, StudyGroup
    from universities.models import StudentUniversity

    return {
        "Ученики": total(Student),
        "Учебные группы": total(StudyGroup),
        "Вузы в списках учеников": total(StudentUniversity),
        "Попытки экзаменов": total(ExamAttempt),
        "Активности": total(Activity),
        "Соревнования": total(Competition),
        "Задачи": total(Task),
        "Эссе": total(Essay),
        "Тренировки": total(PracticeSession),
        "Прохождения моков": total(MockRun),
        "Материалы": total(StudyMaterial),
    }


def catalog_counts() -> dict[str, int]:
    from universities.models import AdmissionRequirement, AdmissionRound, Program, University

    return {
        "Вузы": total(University),
        "Программы": total(Program),
        "Требования": total(AdmissionRequirement),
        "Раунды подачи": total(AdmissionRound),
    }


def school_counts() -> dict[str, int]:
    """Банк заданий и справочники школы — уходят только с `--all`."""
    from directories.models import OlympiadSubject, SportType
    from materials.models import MaterialCollection
    from prep.models import MockExam, Question

    return {
        "Задания банка": total(Question),
        "Шаблоны моков": total(MockExam),
        "Подборки материалов": total(MaterialCollection),
        "Предметы олимпиад": total(OlympiadSubject),
        "Виды спорта": total(SportType),
    }


def mark_audit_deleted(labels) -> int:
    """Пометить записи журнала как относящиеся к удалённым объектам."""
    from core.models import AuditLog

    return AuditLog.objects.filter(model_label__in=list(labels), object_deleted=False).update(object_deleted=True)


@transaction.atomic
def wipe_students() -> None:
    """Снести всех учеников со всем, что на них висит."""
    from core.models import Notification, ReadinessSnapshot
    from students.models import Student, StudyGroup
    from suggestions.models import Suggestion

    # предложения ссылаются на учеников строками — без них в очереди
    # остались бы пакеты, применить которые уже не к кому
    Suggestion.objects.all().delete()
    ReadinessSnapshot.objects.all().delete()
    # уведомления — адресные сообщения о материалах и заявках учеников:
    # без самих учеников они ведут на несуществующие карточки
    Notification.objects.all().delete()
    # именно `all_objects`: обычный менеджер прячет архив, и ученик,
    # убранный в архив до очистки, пережил бы «полное» обнуление
    Student.all_objects.all().delete()
    StudyGroup.all_objects.all().delete()
    mark_audit_deleted(STUDENT_LABELS)


@transaction.atomic
def wipe_catalog() -> None:
    """Снести справочник вузов целиком."""
    from universities.models import StudentUniversity, University

    # архивная ссылка держит программу так же, как живая (PROTECT),
    # поэтому проверяем по `all_objects` — иначе вместо объяснения был бы 500
    if StudentUniversity.all_objects.exists():
        raise CommandError(
            "Справочник держат списки учеников. Сначала очистите учеников " "(--students) или запустите --all."
        )
    University.objects.all().delete()
    mark_audit_deleted(CATALOG_LABELS)


@transaction.atomic
def wipe_school_directories() -> None:
    """Снести банк заданий и справочники школы. Только вместе с `--all`:

    на задания ссылаются тренировки учеников, на предметы и виды спорта —
    их профили и материалы, поэтому сначала должны уйти сами ученики.
    """
    from directories.models import OlympiadSubject, SportType
    from materials.models import MaterialCollection
    from prep.models import MockExam, Question

    MockExam.objects.all().delete()
    Question.objects.all().delete()
    # подборки материалов принадлежат сотруднику, а не ученику, поэтому
    # они переживают удаление учеников — и держат предмет ссылкой PROTECT.
    # Без этой строки «полное» обнуление падало на первом же справочнике
    MaterialCollection.objects.all().delete()
    OlympiadSubject.objects.all().delete()
    SportType.objects.all().delete()


class Command(BaseCommand):
    help = "Очищает данные: учеников, справочник вузов или всё сразу. Пользователей не трогает"

    def add_arguments(self, parser):
        parser.add_argument("--students", action="store_true", help="Удалить учеников и всё, что на них висит")
        parser.add_argument("--catalog", action="store_true", help="Удалить вузы, программы, требования, раунды")
        parser.add_argument(
            "--all",
            action="store_true",
            help="Всё: учеников, справочник вузов, банк заданий и справочники школы",
        )
        parser.add_argument(
            "--confirm",
            default="",
            help=f"Подтверждающая фраза «{CONFIRM_PHRASE}» — чтобы запускать без вопроса в терминале",
        )

    def handle(self, *args, **options):
        students = options["students"] or options["all"]
        catalog = options["catalog"] or options["all"]
        if not (students or catalog):
            raise CommandError("Нечего удалять: укажите --students, --catalog или --all")

        plan: dict[str, int] = {}
        if students:
            plan.update(student_counts())
        if catalog:
            plan.update(catalog_counts())
        if options["all"]:
            plan.update(school_counts())

        self.stdout.write("Будет удалено безвозвратно:")
        for title, count in plan.items():
            self.stdout.write(f"  {title}: {count}")
        self.stdout.write("Пользователи, роли и настройки останутся нетронутыми.")

        given = options["confirm"]
        if not given:
            self.stdout.write(f"Наберите «{CONFIRM_PHRASE}», чтобы подтвердить:")
            given = input().strip()
        if given.strip() != CONFIRM_PHRASE:
            raise CommandError("Фраза не совпала — ничего не удалено")

        if students:
            wipe_students()
            self.stdout.write(self.style.SUCCESS("Ученики удалены"))
        if catalog:
            wipe_catalog()
            self.stdout.write(self.style.SUCCESS("Справочник вузов удалён"))
        if options["all"]:
            wipe_school_directories()
            self.stdout.write(self.style.SUCCESS("Банк заданий и справочники школы удалены"))
        self.stdout.write(self.style.SUCCESS("Готово. Записи журнала сохранены и помечены как удалённые"))
