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


def student_counts() -> dict[str, int]:
    from alumni.models import Alumnus
    from prep.models import MockRun, PracticeSession
    from roadmap.models import Essay, Task
    from students.models import Activity, Competition, ExamAttempt, Student, StudyGroup
    from universities.models import StudentUniversity

    return {
        "Ученики": Student.objects.count(),
        "Учебные группы": StudyGroup.objects.count(),
        "Вузы в списках учеников": StudentUniversity.objects.count(),
        "Попытки экзаменов": ExamAttempt.objects.count(),
        "Активности": Activity.objects.count(),
        "Соревнования": Competition.objects.count(),
        "Задачи": Task.objects.count(),
        "Эссе": Essay.objects.count(),
        "Тренировки": PracticeSession.objects.count(),
        "Прохождения моков": MockRun.objects.count(),
        "Выпускники": Alumnus.objects.count(),
    }


def catalog_counts() -> dict[str, int]:
    from universities.models import AdmissionRequirement, AdmissionRound, Program, University

    return {
        "Вузы": University.objects.count(),
        "Программы": Program.objects.count(),
        "Требования": AdmissionRequirement.objects.count(),
        "Раунды подачи": AdmissionRound.objects.count(),
    }


def mark_audit_deleted(labels) -> int:
    """Пометить записи журнала как относящиеся к удалённым объектам."""
    from core.models import AuditLog

    return AuditLog.objects.filter(model_label__in=list(labels), object_deleted=False).update(object_deleted=True)


@transaction.atomic
def wipe_students() -> None:
    """Снести всех учеников со всем, что на них висит."""
    from core.models import ReadinessSnapshot
    from students.models import Student, StudyGroup
    from suggestions.models import Suggestion

    # предложения ссылаются на учеников строками — без них в очереди
    # остались бы пакеты, применить которые уже не к кому
    Suggestion.objects.all().delete()
    ReadinessSnapshot.objects.all().delete()
    Student.objects.all().delete()
    StudyGroup.objects.all().delete()
    mark_audit_deleted(STUDENT_LABELS)


@transaction.atomic
def wipe_catalog() -> None:
    """Снести справочник вузов целиком."""
    from universities.models import StudentUniversity, University

    if StudentUniversity.objects.exists():
        raise CommandError(
            "Справочник держат списки учеников. Сначала очистите учеников " "(--students) или запустите --all."
        )
    University.objects.all().delete()
    mark_audit_deleted(CATALOG_LABELS)


class Command(BaseCommand):
    help = "Очищает данные: учеников, справочник вузов или всё сразу. Пользователей не трогает"

    def add_arguments(self, parser):
        parser.add_argument("--students", action="store_true", help="Удалить учеников и всё, что на них висит")
        parser.add_argument("--catalog", action="store_true", help="Удалить вузы, программы, требования, раунды")
        parser.add_argument("--all", action="store_true", help="И учеников, и справочник")
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
        self.stdout.write(self.style.SUCCESS("Готово. Записи журнала сохранены и помечены как удалённые"))
