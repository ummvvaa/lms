"""Прогон всех операций с моделью — с ключом и без него.

Смысл команды один: увидеть своими глазами, что каждая операция что-то
отвечает, и что без ключа она отвечает тоже. «Проверили одну, остальные
наверное работают» — так в бою и обнаруживается, что разбор активности
падает на пустом справочнике предметов.

Запуск:
    manage.py check_llm                  — как настроено сейчас
    manage.py check_llm --offline        — принудительно без ключа
    manage.py check_llm --student 12     — на конкретном ученике

Ничего не применяет: операции, которые что-то меняют, отдают предложение,
и оно остаётся ждать человека (инвариант №3).
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass

from django.core.management.base import BaseCommand
from django.test import override_settings

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
        parser.add_argument("--student", type=int, default=0, help="Ученик, на котором проверять")
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

        student, program, actor = self._fixtures(options)
        if student is None:
            self.stdout.write(
                self.style.WARNING(
                    "В базе нет учеников — большую часть операций проверять не на чем. "
                    "Заведите хотя бы одного или загрузите файл"
                )
            )

        results = self._operations(student=student, program=program, actor=actor, options=options)

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
                    f"Проверять было не на чем: {len(skipped)}. Заведите ученика и хотя бы одну "
                    f"программу в справочнике — и запустите ещё раз"
                )
            )

        if state["configured"]:
            from suggestions.budget import spent_this_month

            self.stdout.write(f"Потрачено с первого числа: ${spent_this_month():.4f}")

    def _fixtures(self, options):
        """Ученик, программа и от чьего имени звать. Ничего не создаём."""
        from accounts.models import Role, User
        from students.models import Student
        from universities.models import Program

        student = (
            Student.objects.filter(pk=options["student"]).first()
            if options["student"]
            else Student.objects.order_by("pk").first()
        )
        program = (
            Program.objects.filter(pk=options["program"]).first()
            if options["program"]
            else Program.objects.select_related("university").order_by("pk").first()
        )
        actor = (
            User.objects.filter(role=Role.DIRECTOR_ADMISSION).order_by("pk").first()
            or User.objects.filter(role=Role.ADMIN).order_by("pk").first()
        )
        return student, program, actor

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
        attempt("дайджест", lambda: self._digest(actor))

        # --- восемь операций уровня управления ---
        from suggestions import operations

        ids = [student.pk] if student is not None else []
        role = getattr(actor, "role", Role.DIRECTOR_ADMISSION)
        management = (
            ("объясни список", lambda: operations.explain_list(student_ids=ids, actor=actor, role=role)),
            ("что изменилось за неделю", lambda: operations.week_changes(actor=actor, role=role)),
            ("на кого смотреть сегодня", lambda: operations.focus_today(actor=actor, role=role)),
            (
                "задача выделенным",
                lambda: operations.bulk_tasks(
                    student_ids=ids, wish="собрать рекомендательные письма", actor=actor, role=role
                ),
            ),
            ("план подготовки", lambda: self._one(operations.prep_plan, student, actor, role)),
            ("пробелы портфолио", lambda: self._one(operations.gap_to_tasks, student, actor, role)),
            ("письмо родителю", lambda: self._one(operations.parent_letter, student, actor, role)),
            ("баланс списка", lambda: self._one(operations.check_balance, student, actor, role)),
        )
        for name, call in management:
            attempt(name, lambda call=call: self._outcome(call))

        # --- помощник в углу ---
        attempt("помощник: кнопка", lambda: self._assistant_quick(actor))
        attempt("помощник: свободный ввод", lambda: self._assistant_free(actor))
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

        #: однопиксельный PNG: проверяем путь, а не качество распознавания
        pixel = bytes.fromhex(
            "89504e470d0a1a0a0000000d494844520000000100000001080600000"
            "01f15c4890000000a49444154789c6360000002000100ffff03000006000557bfabd4"
            "0000000049454e44ae426082"
        )
        try:
            return parse_certificate(
                payload=pixel, media_type="image/png", student_id=student.pk, actor=actor, role="director_sport"
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
    def _digest(actor):
        if actor is None:
            return None
        from core.digest import build

        payload = build(user=actor)
        return {"ok": True, "offline": True, "detail": f"строк в дайджесте: {len(payload.get('lines') or [])}"}

    @staticmethod
    def _assistant_quick(actor):
        from suggestions import assistant

        role = getattr(actor, "role", "director_admission")
        buttons = assistant.quick_for(role)
        if not buttons:
            return None
        payload = assistant.run_quick(buttons[0].code, actor=actor, role=role)
        return {"ok": True, "offline": payload.get("offline", True), "detail": payload.get("text", "")[:120]}

    @staticmethod
    def _assistant_free(actor):
        from suggestions import assistant

        payload = assistant.free_text(
            text="Что мне сделать в первую очередь?",
            actor=actor,
            role=getattr(actor, "role", "director_admission"),
        )
        return {"ok": True, "offline": payload.get("offline", False), "detail": payload.get("text", "")[:120]}
