"""Прогон всех операций с моделью — с ключом и без него.

Смысл команды один: увидеть своими глазами, что каждая операция что-то
отвечает, и что без ключа она отвечает тоже. «Проверили одну, остальные
наверное работают» — так в бою и обнаруживается, что разбор активности
падает на пустом справочнике предметов.

Запуск:
    manage.py check_llm                  — как настроено сейчас
    manage.py check_llm --offline        — принудительно без ключа

Ни одного живого ученика в запросах к модели. Проверка сама заводит
вымышленного ученика (`is_fictional`) с баллами, списком вузов и правкой
в журнале, гоняет операции только на нём и в конце стирает всё, что
завела: его карточку, предложения по нему и строки журнала о нём.
Операции по всей школе (сводка, «на кого смотреть», кнопка помощника)
зовутся с его номером, а пересказ дайджеста — на его строках. Журнал
вызовов модели остаётся: деньги потрачены, их учёт не стирается.
Если проверку прервали на середине, ученика найдёт `preflight`
и уберёт `purge_fictional`.

Ничего не применяет: операции, которые что-то меняют, отдают предложение,
а проверка его удаляет в конце (инвариант №3) — в очереди директора
проверочных строк не остаётся.
"""

from __future__ import annotations

import traceback
import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from suggestions import llm


@dataclass
class Result:
    """Что вышло у одной операции.

    `skipped` — не сбой: проверять было не на чем (пустая база). Смешивать
    это со сбоем нельзя, иначе прогон на пустой базе выглядит как поломка.
    """

    name: str
    ok: bool
    offline: bool
    note: str
    skipped: bool = False


class Command(BaseCommand):
    help = "Прогоняет все операции с моделью и печатает, что ответила каждая"

    def add_arguments(self, parser):
        parser.add_argument("--offline", action="store_true", help="Прогнать так, будто ключа нет")
        parser.add_argument("--program", type=int, default=0, help="Программа для сверки требований")
        parser.add_argument("--university", default="University of Toronto", help="Что разбирать в «разборе вуза»")

    def handle(self, *args, **options):
        if options["offline"]:
            with override_settings(LLM={**self._llm_settings(), "API_KEY": ""}):
                self._run(options)
            return
        self._run(options)

    @staticmethod
    def _llm_settings() -> dict:
        from django.conf import settings

        return dict(settings.LLM)

    def _run(self, options) -> None:
        state = llm.status()
        self.stdout.write(
            f"Провайдер: {state['provider']}, модель подключена: {'да' if state['configured'] else 'нет'}"
        )
        self.stdout.write(f"  {state['detail']}")

        program, actor = self._fixtures(options)
        student = self._fictional_student(actor)
        self.stdout.write(f"  Вымышленный ученик проверки: {student.full_name} (№ {student.pk}), будет стёрт в конце")
        self._made: set[int] = set()
        try:
            results = self._operations(student=student, program=program, actor=actor, options=options)
        finally:
            self.stdout.write(f"  {self._erase_fictional(student, self._made)}")

        self.stdout.write("")
        width = max(len(r.name) for r in results)
        for row in results:
            if row.skipped:
                mark = self.style.WARNING("нет  ")
                how = "       "
            else:
                mark = self.style.SUCCESS("ok   ") if row.ok else self.style.ERROR("сбой ")
                how = "правила" if row.offline else "модель "
            self.stdout.write(f"  {mark} {row.name.ljust(width)}  {how}  {row.note[:90]}")

        failed = [r for r in results if not r.ok]
        skipped = [r for r in results if r.skipped]
        self.stdout.write("")
        if failed:
            self.stdout.write(self.style.ERROR(f"Не отработали: {len(failed)} из {len(results)}"))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Отработали: {len(results) - len(skipped)} из {len(results)}")
                if skipped
                else self.style.SUCCESS(f"Отработали все: {len(results)}")
            )
        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"Проверять было не на чем: {len(skipped)}. Заведите хотя бы одну "
                    f"программу в справочнике — и запустите ещё раз"
                )
            )

        if state["configured"]:
            from suggestions.budget import spent_this_month

            self.stdout.write(f"Потрачено с первого числа: ${spent_this_month():.4f}")

    def _fixtures(self, options):
        """Программа справочника и от чьего имени звать. Учеников не берём."""
        from accounts.models import Role, User
        from universities.models import Program

        program = (
            Program.objects.filter(pk=options["program"]).first()
            if options["program"]
            else Program.objects.select_related("university").order_by("pk").first()
        )
        actor = (
            User.objects.filter(role=Role.DIRECTOR_ADMISSION).order_by("pk").first()
            or User.objects.filter(role=Role.ADMIN).order_by("pk").first()
        )
        return program, actor

    @staticmethod
    @transaction.atomic
    def _fictional_student(actor):
        """Завести вымышленного ученика со всем, что нужно операциям.

        Баллы, цели, мок, два вуза из справочника (reach и target) и одна
        правка в журнале домена поступления — чтобы сводке за неделю
        и балансу списка было о чём спросить модель. Одной транзакцией:
        сбой на середине не оставляет полкарточки.
        """
        from core.audit import record_change
        from students.models import (
            AdmissionProfile,
            AttemptFormat,
            BehaviorProfile,
            ExamAttempt,
            ExamProfile,
            ExamType,
            Student,
            TalentProfile,
        )
        from universities.models import Program, StudentUniversity, Tier

        today = timezone.localdate()
        student = Student.objects.create(
            last_name="Проверка",
            first_name="Модели",
            email=f"check-llm-{uuid.uuid4().hex[:10]}@fictional.invalid",
            graduation_year=today.year + 1,
            is_fictional=True,
        )
        BehaviorProfile.objects.create(student=student, attendance_percent=91)
        ExamProfile.objects.create(
            student=student,
            ielts_current=Decimal("6.0"),
            ielts_target=Decimal("7.0"),
            sat_current=1250,
            sat_target=1400,
            gpa=Decimal("3.60"),
        )
        admission = AdmissionProfile.objects.create(
            student=student, target_country="Канада", target_major="Computer Science"
        )
        TalentProfile.objects.create(student=student)
        ExamAttempt.objects.create(
            student=student,
            exam_type=ExamType.IELTS,
            attempt_format=AttemptFormat.MOCK,
            date=today - timedelta(days=20),
            total_score=Decimal("6.0"),
        )
        programs = Program.objects.select_related("university").order_by("pk")[:2]
        for program, tier in zip(programs, (Tier.REACH, Tier.TARGET), strict=False):
            StudentUniversity.objects.create(
                student=student, program=program, tier=tier, admission_round=program.rounds.order_by("deadline").first()
            )
        # правка в журнале: через единую точку записи, от имени того, кто
        # зовёт операции, — сводка за неделю увидит её в своём домене.
        # Значение уже в профиле: сохранение через сигнал дало бы вторую
        # строку без автора
        record_change(
            instance=admission, field_name="target_major", old_value="", new_value="Computer Science", actor=actor
        )
        return student

    @staticmethod
    def _erase_fictional(student, made: set[int]) -> str:
        """Стереть всё, что завела проверка: предложения, карточку, журнал о ней.

        Предложения — по ученику и те, номера которых вернули операции
        (разбор вуза, сверка требований): чужие строки очереди, заведённые
        людьми в ту же минуту, не трогаются.
        """
        from django.db.models import Q

        from core.models import AuditLog
        from students.models import Student
        from suggestions.models import Suggestion

        pk = student.pk
        suggestions, _ = Suggestion.objects.filter(Q(changes__student_id=pk) | Q(pk__in=made)).distinct().delete()
        Student.all_objects.filter(pk=pk, is_fictional=True).delete()
        journal, _ = AuditLog.objects.filter(student_id=pk).delete()
        return f"Вымышленный ученик стёрт; предложений и строк журнала убрано: {suggestions + journal}"

    def _operations(self, *, student, program, actor, options) -> list[Result]:
        from accounts.models import Role

        results: list[Result] = []

        def attempt(name: str, call) -> None:
            self.stdout.write(f"… {name}")
            try:
                payload = call()
            except Exception as error:  # печатаем и идём дальше: важна вся картина
                results.append(Result(name, False, False, f"{type(error).__name__}: {error}"))
                self.stdout.write(self.style.ERROR(traceback.format_exc(limit=2)))
                return
            if payload is None:
                results.append(Result(name, True, False, "нечего проверять: нет данных в базе", skipped=True))
                return
            if payload.get("suggestion"):
                # предложение проверки — не работа для директора: уйдёт в конце
                self._made.add(int(payload["suggestion"]))
            note = str(payload.get("detail") or payload.get("text") or payload.get("summary") or "ответ получен")
            results.append(Result(name, bool(payload.get("ok", True)), bool(payload.get("offline")), note))

        # --- разбор вставленного текста (работает и правилами) ---
        attempt("вставленный текст", lambda: self._paste(actor))

        # --- разбор вуза ---
        attempt("разбор вуза", lambda: self._parse_university(options["university"], actor))

        # --- сверка требований ---
        attempt("сверка требований", lambda: self._verify(program, actor))

        # --- разбор активности ---
        attempt("разбор активности", lambda: self._parse_activity(student, actor))

        # --- распознавание изображений ---
        attempt("распознавание фото", lambda: self._parse_image(student, actor))

        # --- подбор вузов и объяснение соответствия ---
        attempt("подбор вузов", lambda: self._pick(student))
        attempt("объяснение соответствия", lambda: self._explain(student, program, actor))

        # --- дайджест ---
        attempt("дайджест", lambda: self._digest(student, actor))

        # --- семь операций уровня управления ---
        from suggestions import operations

        ids = [student.pk] if student is not None else []
        role = getattr(actor, "role", Role.DIRECTOR_ADMISSION)
        management = (
            ("объясни список", lambda: operations.explain_list(student_ids=ids, actor=actor, role=role)),
            (
                "что изменилось за неделю",
                lambda: operations.week_changes(actor=actor, role=role, student_ids=ids),
            ),
            ("на кого смотреть сегодня", lambda: operations.focus_today(actor=actor, role=role, student_ids=ids)),
            (
                "задача выделенным",
                lambda: operations.bulk_tasks(
                    student_ids=ids, wish="собрать рекомендательные письма", actor=actor, role=role
                ),
            ),
            ("план подготовки", lambda: self._one(operations.prep_plan, student, actor, role)),
            ("пробелы портфолио", lambda: self._one(operations.gap_to_tasks, student, actor, role)),
            ("баланс списка", lambda: self._one(operations.check_balance, student, actor, role)),
        )
        for name, call in management:
            attempt(name, lambda call=call: self._outcome(call))

        # --- помощник в углу ---
        attempt("помощник: кнопка", lambda: self._assistant_quick(actor, ids))
        attempt("помощник: свободный ввод", lambda: self._assistant_free(actor, ids))
        return results

    # --- обёртки над операциями -------------------------------------------

    @staticmethod
    def _outcome(call):
        outcome = call()
        return outcome.as_dict() if hasattr(outcome, "as_dict") else outcome

    @staticmethod
    def _one(call, student, actor, role):
        if student is None:
            return None
        return call(student_id=student.pk, actor=actor, role=role)

    @staticmethod
    def _paste(actor):
        from suggestions.parsers import parse_scores

        # разделитель обязателен: «имя — балл». Так пишут в переписке,
        # и так же устроен разбор правилами
        rows = parse_scores("Иванов — IELTS 7.0\nПетров: SAT 1380")
        return {"ok": bool(rows), "offline": True, "detail": f"разобрано строк: {len(rows)}"}

    @staticmethod
    def _parse_university(text, actor):
        from suggestions.extraction import NeedsModel
        from suggestions.extraction import parse_university as run

        try:
            return run(text=text, actor=actor, role=getattr(actor, "role", "director_admission"))
        except NeedsModel as error:
            return {"ok": True, "offline": True, "detail": str(error)}

    @staticmethod
    def _verify(program, actor):
        if program is None:
            return None
        from suggestions.verify_requirements import CannotVerify, verify

        try:
            return verify(program_id=program.pk, actor=actor, role=getattr(actor, "role", "director_admission"))
        except CannotVerify as error:
            return {"ok": True, "offline": True, "detail": str(error)}

    @staticmethod
    def _parse_activity(student, actor):
        if student is None:
            return None
        from suggestions.extraction import NeedsModel
        from suggestions.extraction import parse_activity as run

        try:
            return run(
                text="Городская олимпиада по физике, второе место, март",
                student_id=student.pk,
                actor=actor,
                role="director_talent",
            )
        except NeedsModel as error:
            return {"ok": True, "offline": True, "detail": str(error)}

    @staticmethod
    def _parse_image(student, actor):
        if student is None:
            return None
        from suggestions.extraction import NeedsModel, parse_certificate

        # грамота с читаемым текстом: модель должна вернуть название,
        # и проверка доходит до предложения, а не до «не удалось прочитать»
        try:
            return parse_certificate(
                payload=sample_png(), media_type="image/png", student_id=student.pk, actor=actor, role="director_sport"
            )
        except NeedsModel as error:
            return {"ok": True, "offline": True, "detail": str(error)}

    @staticmethod
    def _pick(student):
        if student is None:
            return None
        from universities.picker import pick

        result = pick(student=student, text="инженерия в Канаде")
        return {
            "ok": True,
            "offline": result.offline,
            "detail": result.note or f"подобрано программ: {len(result.picks)}",
        }

    @staticmethod
    def _explain(student, program, actor):
        if student is None or program is None:
            return None
        from suggestions.explain import explain_student_program

        return explain_student_program(student_id=student.pk, program_id=program.pk, actor=actor)

    @staticmethod
    def _digest(student, actor):
        """Пересказ дайджеста — на строках вымышленного ученика.

        Настоящий дайджест собирается из журнала всей школы, поэтому
        проверяется только его вызов модели, а строки — проверочные.
        """
        if actor is None:
            return None
        from core.digest import _model_digest
        from suggestions.operations import offline_reason

        lines = [
            f"{student.full_name}: цель по специальности изменена на Computer Science",
            f"{student.full_name}: мок IELTS 6.0 при цели 7.0",
        ]
        written = _model_digest(headline="Сводка дня", lines=lines, user=actor, domain=None)
        return {
            "ok": True,
            "offline": written is None,
            "detail": f"строк в пересказе: {len(written)}" if written else offline_reason(),
        }

    @staticmethod
    def _assistant_quick(actor, ids):
        """Кнопка помощника — та, что работает по выбранным ученикам.

        «На кого смотреть сегодня» у директора смотрит на всю школу, поэтому
        берём кнопку по ученику или по списку, и список — вымышленный.
        """
        from suggestions import assistant

        role = getattr(actor, "role", "director_admission")
        buttons = [b for b in assistant.quick_for(role) if b.needs in ("student", "none") and b.code != "focus_today"]
        if not buttons:
            return None
        button = next((b for b in buttons if b.needs == "student"), buttons[0])
        payload = assistant.run_quick(button.code, actor=actor, role=role, student_ids=ids)
        return {"ok": True, "offline": payload.get("offline", True), "detail": payload.get("text", "")[:120]}

    @staticmethod
    def _assistant_free(actor, ids):
        from suggestions import assistant

        payload = assistant.free_text(
            text="Что мне сделать в первую очередь?",
            actor=actor,
            role=getattr(actor, "role", "director_admission"),
            student_ids=ids,
        )
        return {"ok": True, "offline": payload.get("offline", False), "detail": payload.get("text", "")[:120]}


#: Что написано на грамоте проверки: модель должна прочитать это, а не угадать.
SAMPLE_CERTIFICATE = (
    ("ДИПЛОМ", "B", 64),
    ("II степени", "B", 36),
    ("награждается ученик 11 класса", "", 26),
    ("за второе место", "", 26),
    ("в Республиканской олимпиаде по физике", "", 30),
    ("Алматы, 14 марта 2026 года", "", 24),
)


def sample_png() -> bytes:
    """Настоящий PNG грамоты с читаемым текстом — распознавание доходит до конца."""
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageFont

    from academics.pdf import FONT_FILES, FONTS

    width, height = 900, 560
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 16, width - 17, height - 17), outline=(20, 19, 15), width=4)
    top = 72
    for text, style, size in SAMPLE_CERTIFICATE:
        font = ImageFont.truetype(str(FONTS / FONT_FILES[style]), size)
        left, _, right, bottom = draw.textbbox((0, 0), text, font=font)
        draw.text(((width - (right - left)) / 2, top), text, font=font, fill=(20, 19, 15))
        top += bottom + 36
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()
