#!/usr/bin/env python3
"""Прогон API под каждой ролью — сырой JSON ловит то, чего не видно в интерфейсе.

Проверяет:
* чтение и запись чужого домена;
* доступ ученика к дашбордам директоров и чужим профилям;
* наличие внутренних ярлыков в ответах для роли `student` (инвариант №7).

Запуск: python3 e2e/api_probe.py [база]   (по умолчанию http://localhost:8000)
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
LOGIN_PATH = "/api/auth/login/"

def _password(name: str) -> str:
    """Пароль из окружения. Умолчаний нет: паролей в репозитории быть не должно."""
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Не задана переменная {name}. Возьмите её из e2e/.env")
    return value


#: одноразовые записи прогона: их заводит `create_probe_users`, пароль один
ACCOUNTS = {
    "student": ("student@probe.local", "PROBE_PASSWORD"),
    "director_behavior": ("behavior@probe.local", "PROBE_PASSWORD"),
    "director_admission": ("admission@probe.local", "PROBE_PASSWORD"),
    "director_exam": ("exam@probe.local", "PROBE_PASSWORD"),
    "director_talent": ("talent@probe.local", "PROBE_PASSWORD"),
    "director_sport": ("sport@probe.local", "PROBE_PASSWORD"),
    "curator": ("curator@probe.local", "PROBE_PASSWORD"),
    "teacher": ("teacher@probe.local", "PROBE_PASSWORD"),
    "admin": ("admin@probe.local", "PROBE_PASSWORD"),
}

#: внутренние ярлыки, которых не должно быть в ответах ученику (инвариант №7)
INTERNAL_FIELDS = ("status", "portfolio_status")
INTERNAL_VALUES = (
    "critical",
    "needs_supervision",
    "can_execute",
    "strong",
    "medium",
    "weak",
)


class Session:
    def __init__(self) -> None:
        self.jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar))

    def cookie(self, name: str) -> str:
        for c in self.jar:
            if c.name == name:
                return c.value
        return ""

    def upload(
        self,
        path: str,
        filename: str,
        payload: bytes,
        *,
        content_type: str = "text/csv",
        fields: dict | None = None,
    ) -> tuple[int, object]:
        """Настоящая multipart-загрузка: JSON-тело такие ручки не принимают вовсе."""
        boundary = "----probe-boundary"
        parts = b""
        for name, value in (fields or {}).items():
            parts += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        body = (
            parts
            + (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode()
            + payload
            + f"\r\n--{boundary}--\r\n".encode()
        )
        request = Request(f"{BASE}{path}", data=body, method="POST")
        request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        request.add_header("Referer", BASE)
        request.add_header("X-CSRFToken", self.cookie("csrftoken"))
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read().decode("utf-8", "replace")
                return response.status, (json.loads(raw) if raw else None)
        except HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            try:
                return error.code, json.loads(raw)
            except json.JSONDecodeError:
                return error.code, raw[:200]

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, object]:
        data = json.dumps(body).encode() if body is not None else None
        request = Request(f"{BASE}{path}", data=data, method=method)
        request.add_header("Content-Type", "application/json")
        request.add_header("Referer", BASE)
        if method not in ("GET", "HEAD", "OPTIONS"):
            request.add_header("X-CSRFToken", self.cookie("csrftoken"))
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read().decode("utf-8", "replace")
                try:
                    return response.status, (json.loads(raw) if raw else None)
                except json.JSONDecodeError:
                    # не-JSON ответы (файл CV) отдаём текстом: статус важнее тела
                    return response.status, raw[:200]
        except HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            try:
                return error.code, json.loads(raw)
            except json.JSONDecodeError:
                return error.code, raw[:200]


def login(role: str) -> Session | None:
    email, var = ACCOUNTS[role]
    return login_as(email, _password(var))


def login_as(email: str, password: str) -> Session | None:
    session = Session()
    session.call("GET", "/api/auth/me/")  # получаем csrftoken
    code, _ = session.call("POST", LOGIN_PATH, {"email": email, "password": password})
    return session if code == 200 else None


FAILS: list[str] = []


def check(condition: bool, message: str) -> None:
    mark = "ok  " if condition else "ДЕФЕКТ"
    print(f"  [{mark}] {message}")
    if not condition:
        FAILS.append(message)


def find_internal(payload: object, path: str = "") -> list[str]:
    """Ищет внутренние ярлыки в произвольном JSON."""
    hits: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{path}.{key}" if path else key
            if key in INTERNAL_FIELDS and isinstance(value, str) and value in INTERNAL_VALUES:
                hits.append(f"{here}={value}")
            hits += find_internal(value, here)
    elif isinstance(payload, list):
        for i, item in enumerate(payload[:5]):
            hits += find_internal(item, f"{path}[{i}]")
    return hits


def main() -> int:
    sessions = {}
    for role in ACCOUNTS:
        session = login(role)
        if session is None:
            print(f"!! не удалось войти под {role}")
            return 2
        sessions[role] = session

    student = sessions["student"]

    print("\n== Ученик: внутренние ярлыки в ответах (инвариант №7) ==")
    for path in (
        "/api/students/me/",
        "/api/meta/domains/",
        "/api/match/my-universities/",
        "/api/tasks/my/",
        "/api/contacts/",
    ):
        code, payload = student.call("GET", path)
        hits = find_internal(payload)
        check(not hits, f"{path} → без ярлыков (нашлось: {hits[:5]})" if hits else f"{path} → без ярлыков")

    print("\n== Ученик: чужие данные и дашборды ==")
    code, _ = student.call("GET", "/api/dashboards/admission/")
    check(code == 403, f"GET /api/dashboards/admission/ → {code}, ожидали 403")
    code, _ = student.call("GET", "/api/dashboards/overview/")
    check(code == 403, f"GET /api/dashboards/overview/ → {code}, ожидали 403")
    code, _ = student.call("GET", "/api/digest/")
    check(code in (200, 403), f"GET /api/digest/ → {code}")

    code, payload = student.call("GET", "/api/students/")
    if code == 200 and isinstance(payload, dict):
        check(payload.get("count", 0) <= 1, f"список учеников для ученика: {payload.get('count')} записей, ожидали ≤1")
    else:
        check(code == 403, f"GET /api/students/ → {code}")

    # чужой профиль: берём id, которого точно нет у ученика
    code, payload = sessions["director_exam"].call("GET", "/api/students/?page_size=5")
    ids = [row["id"] for row in payload.get("results", [])] if isinstance(payload, dict) else []
    code, me_payload = student.call("GET", "/api/students/me/")
    my_id = me_payload.get("id") if isinstance(me_payload, dict) else None
    foreign = next((i for i in ids if i != my_id), None)
    if foreign:
        code, _ = student.call("GET", f"/api/students/{foreign}/")
        check(code in (403, 404), f"чужая карточка /api/students/{foreign}/ → {code}, ожидали 403/404")
        code, _ = student.call("GET", f"/api/students/{foreign}/history/")
        check(code in (403, 404), f"чужая история → {code}, ожидали 403/404")

    print("\n== Ученик: запись ==")
    code, _ = student.call("POST", "/api/batch/save/", {"changes": []})
    check(code == 403, f"POST /api/batch/save/ → {code}, ожидали 403")
    if my_id:
        code, _ = student.call("PATCH", f"/api/profiles/exam/{my_id}/", {"ielts_current": "9.0"})
        check(code == 403, f"ученик правит свой exam-профиль → {code}, ожидали 403")

    print("\n== Контакты родителей: домен директора школы (фаза 30) ==")
    code, payload = sessions["director_exam"].call("GET", "/api/students/?page_size=1")
    contact_target = payload["results"][0]["id"] if isinstance(payload, dict) and payload.get("results") else None
    if contact_target:
        # заводит только владелец домена `behavior`
        code, _ = sessions["director_exam"].call(
            "POST",
            "/api/contacts/",
            {"student": contact_target, "full_name": "Чужая мама", "relation": "mother", "phone": "+7"},
        )
        check(code == 403, f"чужой директор заводит контакт → {code}, ожидали 403")

        code, created = sessions["director_behavior"].call(
            "POST",
            "/api/contacts/",
            {
                "student": contact_target,
                "full_name": "Проверкина Гульнара",
                "relation": "mother",
                "phone": "+7 701 000 00 00",
                "is_primary": True,
            },
        )
        check(code == 201, f"директор школы заводит контакт → {code}, ожидали 201")
        contact_id = created.get("id") if isinstance(created, dict) else None

        if contact_id:
            code, _ = sessions["director_behavior"].call(
                "PATCH", f"/api/contacts/{contact_id}/", {"phone": "+7 701 000 00 01"}
            )
            check(code == 200, f"правка контакта владельцем → {code}, ожидали 200")

            code, _ = sessions["director_sport"].call(
                "PATCH", f"/api/contacts/{contact_id}/", {"phone": "+7 000"}
            )
            check(code == 403, f"чужой директор правит контакт → {code}, ожидали 403")

            code, _ = student.call("PATCH", f"/api/contacts/{contact_id}/", {"phone": "+7 000"})
            check(code == 403, f"ученик правит свой контакт → {code}, ожидали 403")

            code, _ = sessions["director_behavior"].call("DELETE", f"/api/contacts/{contact_id}/")
            check(code == 200, f"удаление контакта владельцем → {code}, ожидали 200")

    print("\n== Новые точки входа: соревнования, результаты, банк (фаза 31) ==")
    if contact_target:
        code, made = sessions["director_sport"].call(
            "POST",
            "/api/competitions/",
            {"student": contact_target, "name": "Проверочный старт", "level": "city", "date": "2026-03-15"},
        )
        check(code == 201, f"директор спорта заводит соревнование → {code}, ожидали 201")
        competition = made.get("id") if isinstance(made, dict) else None
        if competition:
            # неотмеченное «в карточку» соревнование чужой директор не видит вовсе:
            # оно живёт на вкладке «Портфолио» и у директора спорта
            check(made.get("show_in_card") is False, "новое соревнование в карточке не показывается")
            code, _ = sessions["director_exam"].call("GET", f"/api/competitions/{competition}/")
            check(code == 404, f"чужой директор открывает неотмеченное соревнование → {code}, ожидали 404")
            code, _ = sessions["director_sport"].call(
                "PATCH", f"/api/competitions/{competition}/", {"show_in_card": True}
            )
            check(code == 200, f"директор спорта отмечает соревнование «в карточку» → {code}, ожидали 200")
            code, seen = sessions["director_exam"].call("GET", f"/api/competitions/{competition}/")
            check(code == 200, f"отмеченное соревнование видно чужому директору → {code}, ожидали 200")
            code, _ = sessions["director_exam"].call(
                "PATCH", f"/api/competitions/{competition}/", {"show_in_card": False}
            )
            check(code == 403, f"чужой директор снимает отметку «в карточку» → {code}, ожидали 403")
            code, _ = sessions["director_exam"].call(
                "PATCH", f"/api/competitions/{competition}/", {"result": "чужое"}
            )
            check(code == 403, f"чужой директор правит соревнование → {code}, ожидали 403")
            code, _ = sessions["director_sport"].call("DELETE", f"/api/competitions/{competition}/")
            check(code == 200, f"удаление соревнования владельцем → {code}, ожидали 200")

        code, bulk = sessions["director_exam"].call(
            "POST",
            "/api/attempts/bulk/",
            {
                "rows": [
                    {
                        "student": contact_target,
                        "exam_type": "IELTS",
                        "attempt_format": "mock",
                        "date": "2026-04-01",
                        "total_score": "6.5",
                    }
                ]
            },
        )
        check(
            code == 200 and isinstance(bulk, dict) and bulk.get("created") == 1,
            f"массовый ввод результатов → {code}, внесено {bulk.get('created') if isinstance(bulk, dict) else '—'}",
        )
        code, _ = sessions["director_sport"].call(
            "POST", "/api/attempts/bulk/", {"rows": [{"student": contact_target, "exam_type": "IELTS"}]}
        )
        check(code == 403, f"чужой директор вносит результаты пачкой → {code}, ожидали 403")

    # состав задания зависит от секции: у SAT Math — варианты, и верный ровно один
    choice = {
        "exam_type": "SAT",
        "section": "math",
        "topic": "Проверка",
        "difficulty": "medium",
        "text": "Текст",
        "options": [
            {"letter": "A", "text": "Да", "is_correct": True},
            {"letter": "B", "text": "Нет", "is_correct": False},
        ],
    }
    code, question = sessions["director_exam"].call("POST", "/api/prep/questions/", choice)
    check(code == 201, f"академический директор заводит задание → {code}, ожидали 201")
    code, _ = sessions["director_exam"].call(
        "POST", "/api/prep/questions/", {**choice, "exam_type": "IELTS", "section": "listening"}
    )
    check(code == 400, f"Listening без аудио не сохраняется → {code}, ожидали 400")
    code, _ = sessions["director_exam"].call(
        "POST", "/api/prep/questions/", {**choice, "exam_type": "IELTS", "section": "reading"}
    )
    check(code == 400, f"Reading без пассажа не сохраняется → {code}, ожидали 400")
    code, _ = sessions["director_exam"].call(
        "POST", "/api/prep/questions/", {**choice, "exam_type": "IELTS", "section": "writing"}
    )
    check(code == 400, f"Writing с вариантами не сохраняется → {code}, ожидали 400")
    code, essay = sessions["director_exam"].call(
        "POST",
        "/api/prep/questions/",
        {
            "exam_type": "IELTS",
            "section": "writing",
            "topic": "Проверка",
            "difficulty": "medium",
            "text": "Describe the chart.",
            "criteria": "Task response",
            "word_limit": 150,
        },
    )
    check(code == 201, f"Writing без вариантов заводится → {code}, ожидали 201")
    if isinstance(essay, dict) and essay.get("id"):
        check(essay.get("question_type") == "writing" and essay.get("options") == [], "у Writing нет вариантов")
        sessions["director_exam"].call("DELETE", f"/api/prep/questions/{essay['id']}/")
    code, passage = sessions["director_exam"].call(
        "POST",
        "/api/prep/passages/",
        {"exam_type": "IELTS", "section": "reading", "kind": "reading", "title": "Проверка", "body": "Text."},
    )
    check(code == 201, f"академический директор заводит пассаж → {code}, ожидали 201")
    if isinstance(passage, dict) and passage.get("id"):
        code, _ = sessions["director_talent"].call(
            "PATCH", f"/api/prep/passages/{passage['id']}/", {"title": "Чужое"}
        )
        check(code == 403, f"чужой директор правит пассаж → {code}, ожидали 403")
        code, _ = student.call("GET", "/api/prep/passages/")
        check(
            code == 200 and not (_.get("results") if isinstance(_, dict) else _),
            f"ученик списка пассажей не видит → {code}",
        )
        code, _ = sessions["director_exam"].call("DELETE", f"/api/prep/passages/{passage['id']}/")
        check(code in (200, 204), f"пассаж скрыт владельцем → {code}")
    for role in ("student", "director_sport", "curator"):
        code, _ = sessions[role].call("GET", "/api/prep/open-answers/")
        check(code == 403, f"{role} открывает очередь открытых ответов → {code}, ожидали 403")
    code, _ = sessions["director_exam"].call("GET", "/api/prep/open-answers/")
    check(code == 200, f"академический директор открывает очередь открытых ответов → {code}, ожидали 200")
    if isinstance(question, dict) and question.get("id"):
        code, _ = sessions["director_talent"].call(
            "PATCH", f"/api/prep/questions/{question['id']}/", {"topic": "Чужое"}
        )
        check(code == 403, f"чужой директор правит банк → {code}, ожидали 403")
        code, _ = sessions["director_exam"].call("DELETE", f"/api/prep/questions/{question['id']}/")
        check(code == 200, f"удаление задания владельцем → {code}, ожидали 200")

    print("\n== Блок «Поступление»: каждую строку правят Асем и администратор ==")
    if contact_target:
        body = {"exam": "IELTS", "score": "12"}  # балл вне шкалы: право проверяется раньше значения
        for role, expected in (("director_exam", 403), ("director_sport", 403), ("student", 403)):
            code, _ = sessions[role].call("POST", f"/api/students/{contact_target}/admission-block/attempt/", body)
            check(code in (expected, 404), f"{role} правит попытку блока → {code}, ожидали {expected}")
        for role in ("director_admission", "admin"):
            code, answer = sessions[role].call(
                "POST", f"/api/students/{contact_target}/admission-block/attempt/", body
            )
            check(code == 400, f"{role} допущен к попыткам блока, балл вне шкалы отклонён → {code}, ожидали 400")
            code, answer = sessions[role].call(
                "POST", f"/api/students/{contact_target}/admission-block/link/", {"code": "passport", "url": "не ссылка"}
            )
            check(code == 400, f"{role} допущен к ссылкам блока, не-ссылка отклонена → {code}, ожидали 400")

    print("\n== Выгрузка пользователей и предпросмотр ==")
    code, preview = sessions["admin"].call("GET", "/api/users/export/?preview=1")
    columns = preview.get("sheets", [{}])[0].get("columns", []) if isinstance(preview, dict) else []
    check(code == 200, f"администратор открывает предпросмотр выгрузки пользователей → {code}, ожидали 200")
    check(
        # логин — не пароль: у 8–10 без почты им входят, он и стоит рядом с почтой
        columns == ["ФИО", "Почта", "Логин", "Роль", "Группа", "Состояние пароля", "Активен"],
        f"колонки выгрузки пользователей без паролей и ссылок: {columns}",
    )
    for role in ("director_behavior", "curator", "student"):
        code, _ = sessions[role].call("GET", "/api/users/export/?preview=1")
        check(code == 403, f"{role} выгружает пользователей → {code}, ожидали 403")

    print("\n== Класс нигде не выбирается ==")
    code, templates = sessions["director_admission"].call("GET", "/api/task-templates/?page_size=1")
    first = (templates.get("results") or [{}])[0] if isinstance(templates, dict) else {}
    check("grade" not in first and "graduation_year" not in first, "у шаблона задач нет класса и выпуска")
    code, group = sessions["director_talent"].call("GET", "/api/olympiad-group/")
    check(
        code == 200 and "groups" in group and all("grade" not in row for row in group.get("students", [])),
        f"олимпиадная группа делится по группам, класса в ответе нет → {code}",
    )

    print("\n== Реестровая карточка: правит администратор (фаза 30) ==")
    if contact_target:
        code, _ = sessions["admin"].call("PATCH", f"/api/students/{contact_target}/", {})
        check(code == 200, f"администратор правит карточку → {code}, ожидали 200")
        code, _ = sessions["director_exam"].call("PATCH", f"/api/students/{contact_target}/", {"last_name": "Чужов"})
        check(code == 403, f"директор правит реестровую карточку → {code}, ожидали 403")

    print("\n== Директора: чужой домен ==")
    code, payload = sessions["director_exam"].call("GET", "/api/students/?page_size=1")
    target = payload["results"][0]["id"] if isinstance(payload, dict) and payload.get("results") else None
    if target:
        cases = [
            ("director_exam", "behavior", {"attendance_percent": 50}),
            ("director_behavior", "exam", {"ielts_current": "8.0"}),
            ("director_sport", "talent", {"main_track": "research"}),
            ("director_talent", "sport", {"sport_type": "Бокс"}),
        ]
        for role, domain, body in cases:
            code, _ = sessions[role].call("PATCH", f"/api/profiles/{domain}/{target}/", body)
            check(code == 403, f"{role} пишет в {domain} → {code}, ожидали 403")

        print("\n== Директора: чужой домен через батч ==")
        code, payload = sessions["director_exam"].call(
            "POST",
            "/api/batch/save/",
            {"changes": [{"student": target, "model": "students.BehaviorProfile", "field": "attendance_percent", "value": 42}]},
        )
        rejected = payload.get("rejected") if isinstance(payload, dict) else None
        check(
            code == 200 and payload.get("applied") == 0 and rejected,
            f"батч с чужим полем → applied={payload.get('applied') if isinstance(payload, dict) else code}, rejected={rejected}",
        )

        print("\n== Директора: чтение чужого домена разрешено ==")
        code, payload = sessions["director_sport"].call("GET", f"/api/students/{target}/")
        check(code == 200 and "exam" in (payload or {}), f"чужой домен читается: {code}")

    print("\n== Директора: дашборды ==")
    for role in ("director_behavior", "director_admission", "director_exam", "director_talent", "director_sport"):
        for code_name in ("behavior", "admission", "exam", "talent", "sport"):
            status, _ = sessions[role].call("GET", f"/api/dashboards/{code_name}/")
            if status != 200:
                check(False, f"{role} → /api/dashboards/{code_name}/ вернул {status}")
    print("  (молчание выше означает, что все дашборды директорам открылись)")

    print("\n== Конфликт двух ролей на одном ученике ==")
    if target:
        a = sessions["director_exam"]
        b = sessions["director_exam"]
        a.call("POST", "/api/batch/save/", {"changes": [{"student": target, "model": "students.ExamProfile", "field": "teacher", "value": "Первый"}]})
        code, payload = b.call(
            "POST",
            "/api/batch/save/",
            {"changes": [{"student": target, "model": "students.ExamProfile", "field": "teacher", "value": "Второй", "expected": "Устаревшее"}]},
        )
        conflicts = payload.get("conflicts") if isinstance(payload, dict) else None
        check(bool(conflicts), f"устаревший expected даёт конфликт: {payload}")

    print("\n== Ошибки валидации ==")
    if target:
        code, payload = sessions["director_exam"].call(
            "POST",
            "/api/batch/save/",
            {"changes": [{"student": target, "model": "students.ExamProfile", "field": "ielts_current", "value": "не число"}]},
        )
        readable = isinstance(payload, dict) and (payload.get("rejected") or code == 400)
        check(bool(readable), f"нечисловой балл отклоняется внятно: {code} {payload}")

    print("\n== Раздел материалов: олимпиадная группа (фаза 19) ==")
    section = (
        "/api/materials/",
        "/api/material-requests/",
        "/api/material-collections/",
        "/api/material-comments/",
    )
    code, state = student.call("GET", "/api/materials-state/")
    in_group = bool(isinstance(state, dict) and state.get("has_access"))
    for path in section:
        code, _ = student.call("GET", path)
        if in_group:
            check(code == 200, f"ученик в группе: {path} → {code}, ожидали 200")
        else:
            check(code == 404, f"ученик вне группы: {path} → {code}, ожидали 404")

    # чужой директор не отбирает в олимпиадную группу (инвариант №1)
    if target:
        code, _ = sessions["director_exam"].call(
            "POST", "/api/olympiad-group/pick/", {"student": target, "member": True}
        )
        check(code == 403, f"чужой директор отбирает в группу → {code}, ожидали 403")
        code, _ = sessions["director_talent"].call(
            "POST", "/api/olympiad-group/pick/", {"student": target, "member": True}
        )
        check(code == 200, f"директор талантов отбирает в группу → {code}, ожидали 200")
        # и возвращаем как было: прогон не должен менять состояние школы
        sessions["director_talent"].call(
            "POST", "/api/olympiad-group/pick/", {"student": target, "member": False}
        )

    # с фазы 26 раздел есть только у директора талантов: остальным
    # директорам его нет вовсе — ни списка, ни очереди проверки.
    # Администратор с фазы 68 правит все домены и раздел видит
    code, state = sessions["admin"].call("GET", "/api/materials-state/")
    check(bool(isinstance(state, dict) and state.get("has_access")), "администратор видит раздел материалов (фаза 68)")
    for role in ("director_behavior", "director_admission", "director_exam", "director_sport"):
        code, state = sessions[role].call("GET", "/api/materials-state/")
        has_access = bool(isinstance(state, dict) and state.get("has_access"))
        check(not has_access, f"{role}: раздел материалов не должен быть открыт")
        for path in (*section, "/api/materials/queue/"):
            code, _ = sessions[role].call("GET", path)
            check(code == 404, f"{role}: {path} → {code}, ожидали 404")

    code, _ = sessions["director_talent"].call("GET", "/api/materials/queue/")
    check(code == 200, f"очередь проверки у директора талантов → {code}, ожидали 200")

    print("\n== Ученик вносит, директор подтверждает (фаза 37) ==")
    code, made = student.call(
        "POST",
        "/api/suggestions/propose/",
        {"rows": [{"model": "students.ExamProfile", "field": "ielts_current", "value": "7.0"}]},
    )
    check(code == 201, f"ученик предлагает свой балл → {code}, ожидали 201")
    proposal = made.get("suggestions", [None])[0] if isinstance(made, dict) else None

    code, _ = student.call(
        "POST",
        "/api/suggestions/propose/",
        {"rows": [{"model": "students.AdmissionProfile", "field": "status", "value": "A"}]},
    )
    check(code == 400, f"ученик предлагает оценочный ярлык → {code}, ожидали 400")

    if foreign:
        code, _ = student.call(
            "POST",
            "/api/suggestions/propose/",
            {
                "rows": [
                    {"model": "students.ExamProfile", "field": "ielts_current", "value": "9.0", "student": foreign}
                ]
            },
        )
        check(code == 400, f"ученик предлагает про чужого → {code}, ожидали 400")

    code, queue = sessions["director_exam"].call("GET", "/api/suggestions/from-students/")
    seen = isinstance(queue, dict) and any(row.get("id") == proposal for row in queue.get("results", []))
    check(bool(seen), f"очередь академического директора видит предложение → {code}")

    code, queue = sessions["director_sport"].call("GET", "/api/suggestions/from-students/")
    stray = isinstance(queue, dict) and any(row.get("id") == proposal for row in queue.get("results", []))
    check(not stray, "у директора спорта чужого предложения в очереди нет")

    if proposal:
        # с фазы 68 администратор подтверждает наравне с владельцем; здесь
        # только смотрим, что строка ему открыта, — решение оставляем Кымбат,
        # чтобы проверить её путь ниже
        code, _ = sessions["admin"].call("GET", f"/api/suggestions/{proposal}/")
        check(code == 200, f"администратор видит предложение ученика → {code}")

        code, done = sessions["director_exam"].call(
            "POST", f"/api/suggestions/{proposal}/review/", {"decision": "confirm"}
        )
        check(
            code == 200 and isinstance(done, dict) and done.get("applied") == 1,
            f"владелец домена подтверждает → {code}, применено {done.get('applied') if isinstance(done, dict) else '—'}",
        )
        # возвращаем как было: прогон не должен менять состояние школы
        code, _ = sessions["director_exam"].call("POST", f"/api/suggestions/{proposal}/revert/", {})
        check(code == 200, f"откат предложения владельцем → {code}, ожидали 200")

    code, journey = student.call("GET", "/api/journey/")
    check(
        code == 200 and isinstance(journey, dict) and journey.get("total") == 5,
        f"лестница шагов ученика → {code}, шагов {journey.get('total') if isinstance(journey, dict) else '—'}",
    )
    for role in ("director_exam", "admin"):
        code, _ = sessions[role].call("GET", "/api/journey/")
        check(code == 403, f"{role}: лестница — экран ученика → {code}, ожидали 403")

    print("\n== Портфолио и документы (фаза 38) ==")
    code, body = student.call("GET", "/api/portfolio/")
    check(
        code == 200 and isinstance(body, dict) and "percent" in body and len(body.get("documents", [])) == 5,
        f"портфолио ученика → {code}, процент {body.get('percent') if isinstance(body, dict) else '—'}",
    )
    hits = find_internal(body)
    check(not hits, f"портфолио без внутренних ярлыков (нашлось: {hits[:3]})" if hits else "портфолио без ярлыков")
    code, _ = sessions["director_exam"].call("GET", "/api/portfolio/")
    check(code == 403, f"портфолио у директора → {code}, ожидали 403")
    code, _ = student.call("GET", "/api/portfolio/cv/")
    check(code == 200, f"экспорт CV у ученика → {code}, ожидали 200")
    code, _ = sessions["admin"].call("GET", "/api/portfolio/cv/")
    check(code == 403, f"экспорт CV у администратора → {code}, ожидали 403")
    code, _ = student.call("GET", "/api/documents/")
    check(code == 200, f"список документов у ученика → {code}, ожидали 200")
    code, _ = sessions["director_sport"].call("POST", "/api/documents/", {"doc_type": "attestat"})
    check(code == 403, f"сотрудник загружает документ ученика → {code}, ожидали 403")

    print("\n== Цели по экзаменам и календарь (фаза 39) ==")
    # С фазы 48 школа показывает два экзамена. Ученику справочник отдаёт
    # только список выбора, поэтому строки остальных смотрим у их владельца.
    # Архивный экзамен (фаза 59) не появляется ни у ученика, ни у владельца,
    # ни в плитках подготовки
    code, kinds = student.call("GET", "/api/exam-kinds/")
    shown = {row.get("name") for row in kinds.get("results", [])} if isinstance(kinds, dict) else set()
    check(code == 200 and shown == {"SAT", "IELTS"}, f"в списке выбора два экзамена → {code}: {sorted(shown)}")
    code, all_kinds = sessions["director_exam"].call("GET", "/api/exam-kinds/?page_size=100")
    names = {row.get("name") for row in all_kinds.get("results", [])} if isinstance(all_kinds, dict) else set()
    check(code == 200 and "ЕНТ" not in names and "TOEFL" in names, f"архивный экзамен не показан владельцу → {code}: {sorted(names)}")
    code, center = student.call("GET", "/api/prep/center/exams/")
    tiles = {row.get("exam_type") for row in center.get("exams", [])} if isinstance(center, dict) else set()
    check(code == 200 and "ENT" not in tiles, f"архивного экзамена нет в плитках подготовки → {code}: {sorted(tiles)}")

    code, body = student.call("GET", "/api/calendar/")
    check(
        code == 200 and isinstance(body, dict) and "events" in body and "nearest" in body,
        f"календарь ученика → {code}",
    )
    # с фазы 49 у директора свой календарь: события его учеников с числом
    # сдающих. Личных задач конкретного ребёнка в нём нет
    code, body = sessions["director_exam"].call("GET", "/api/calendar/")
    kinds = {event["kind"] for event in body["events"]} if isinstance(body, dict) else set()
    check(code == 200 and "task" not in kinds, f"школьный календарь у директора → {code}, виды: {sorted(kinds)}")

    code, _ = student.call("GET", "/api/match/at-goal/")
    check(code == 200, f"«если сдашь на цель» → {code}, ожидали 200")

    code, _ = sessions["director_exam"].call("GET", "/api/exam-goals/attention/")
    check(code == 200, f"списки целей у академического директора → {code}, ожидали 200")
    code, _ = sessions["director_sport"].call("GET", "/api/exam-goals/attention/")
    check(code == 403, f"списки целей у директора спорта → {code}, ожидали 403")

    code, made = student.call(
        "POST",
        "/api/suggestions/propose/",
        {
            "rows": [
                {"model": "students.ExamGoal", "field": "exam", "value": "IELTS", "new_object_key": "g"},
                {"model": "students.ExamGoal", "field": "target_score", "value": "7.5", "new_object_key": "g"},
            ]
        },
    )
    check(code == 201, f"ученик предлагает цель по экзамену → {code}, ожидали 201")
    goal_suggestion = made.get("suggestions", [None])[0] if isinstance(made, dict) else None
    if goal_suggestion:
        code, done = sessions["director_exam"].call(
            "POST", f"/api/suggestions/{goal_suggestion}/review/", {"decision": "confirm"}
        )
        check(code == 200, f"академический директор подтверждает цель → {code}")
        code, goals = sessions["director_exam"].call("GET", "/api/exam-goals/")
        rows_ = goals.get("results", []) if isinstance(goals, dict) else []
        made_goal = next((r for r in rows_ if r.get("exam_name") == "IELTS"), None)
        check(made_goal is not None, "цель появилась в списке целей")
        if made_goal:
            code, _ = sessions["director_sport"].call(
                "PATCH", f"/api/exam-goals/{made_goal['id']}/", {"target_score": "9"}
            )
            check(code == 403, f"чужой директор правит цель → {code}, ожидали 403")
            # возвращаем как было: прогон не должен менять состояние школы
            code, _ = sessions["director_exam"].call("DELETE", f"/api/exam-goals/{made_goal['id']}/")
            check(code == 200, f"владелец убирает цель прогона → {code}, ожидали 200")

    print("\n== Подбор вузов и избранное (фаза 40) ==")
    import time as _time

    code, run = student.call("POST", "/api/selection/runs/start/", {"major": ""})
    if code == 409:
        # с прошлого раза мог остаться считающийся прогон — берём его
        code, active = student.call("GET", "/api/selection/runs/active/")
        run = active.get("run") if isinstance(active, dict) else None
        code = 201 if run else code
    check(code == 201 and isinstance(run, dict), f"ученик запускает подбор → {code}")
    run_id = run.get("id") if isinstance(run, dict) else None
    if run_id:
        state = {}
        for _ in range(30):
            code, state = student.call("GET", f"/api/selection/runs/{run_id}/")
            if isinstance(state, dict) and state.get("status") != "running":
                break
            _time.sleep(1)
        check(
            isinstance(state, dict) and state.get("status") == "done",
            f"прогон досчитался → {state.get('status') if isinstance(state, dict) else '—'}",
        )
        if isinstance(state, dict) and state.get("status") == "done":
            check(bool(state.get("methodology")), "объяснение «как считаются проценты» приложено")
            check("funnel" in state and state["funnel"]["catalog"] >= state["funnel"]["filtered"], "воронка сходится")
            strategy = state.get("strategy", {})
            text = " ".join(str(v) for v in strategy.values()).lower()
            check("шанс" not in text.replace("не шанс", ""), "стратегия не называет процент шансом")
        code, _ = sessions["director_exam"].call("GET", f"/api/selection/runs/{run_id}/")
        check(code == 403, f"прогон подбора у директора → {code}, ожидали 403")

    code, listing = student.call("GET", "/api/favorites/")
    check(code == 200, f"избранное ученика → {code}, ожидали 200")
    code, _ = sessions["director_admission"].call("GET", "/api/favorites/")
    check(code == 403, f"избранное у директора → {code}, ожидали 403")

    print("\n== План поступления по вузу (фаза 41) ==")
    # берём любую программу из справочника, если она есть
    code, progs = student.call("GET", "/api/programs/?page_size=1")
    program = None
    if isinstance(progs, dict) and progs.get("results"):
        program = progs["results"][0]["id"]
    if program:
        code, plan = student.call("POST", "/api/application-plans/", {"program": program})
        made = code in (201, 409)
        check(made, f"ученик создаёт план по вузу → {code}")
        plan_id = plan.get("id") if isinstance(plan, dict) else None
        if code == 409:
            code, listing = student.call("GET", "/api/application-plans/")
            rows_ = listing.get("results", []) if isinstance(listing, dict) else []
            plan_id = rows_[0]["id"] if rows_ else None
        if plan_id:
            import time as _t
            for _ in range(20):
                code, state = student.call("GET", f"/api/application-plans/{plan_id}/")
                if isinstance(state, dict) and state.get("generation_status") != "running":
                    break
                _t.sleep(1)
            check(
                isinstance(state, dict) and state.get("generation_status") == "done",
                f"задачи плана собрались → {state.get('generation_status') if isinstance(state, dict) else '—'}",
            )
            code, _ = student.call("POST", f"/api/application-plans/{plan_id}/apply_tasks/", {})
            check(code == 200, f"ученик применяет задачи плана → {code}")
            code, grouped = student.call("GET", f"/api/application-plans/{plan_id}/tasks/")
            check(isinstance(grouped, dict) and len(grouped.get("stages", [])) > 0, "задачи сгруппированы по этапам")
            # директор не создаёт план ученика, но читает
            code, _ = sessions["director_admission"].call("GET", "/api/application-plans/")
            check(code == 200, f"директор читает планы → {code}")
            code, _ = sessions["director_admission"].call("POST", "/api/application-plans/", {"program": program})
            check(code in (403, 405), f"директор создаёт план → {code}, ожидали 403/405")
            code, _ = sessions["director_admission"].call("GET", "/api/application-plans/attention/")
            check(code == 200, f"сводка планов у директора по поступлению → {code}")
            code, _ = sessions["director_sport"].call("GET", "/api/application-plans/attention/")
            check(code == 403, f"сводка планов у директора спорта → {code}, ожидали 403")
            # уборка: план прогона в архив
            student.call("DELETE", f"/api/application-plans/{plan_id}/")

    print("\n== Центр подготовки (фаза 42) ==")
    code, exams = student.call("GET", "/api/prep/center/exams/")
    tiles = {row.get("exam_type") for row in exams.get("exams", [])} if isinstance(exams, dict) else set()
    check(code == 200 and tiles == {"SAT", "IELTS"}, f"плитки видимых экзаменов → {code}: {sorted(tiles)}")
    code, stats = student.call("GET", "/api/prep/center/IELTS/statistics/")
    check(code == 200 and isinstance(stats, dict) and "forecast" in stats, f"статистика ученика → {code}")
    code, _ = sessions["director_exam"].call("GET", "/api/prep/center/exams/")
    check(code == 403, f"центр у директора → {code}, ожидали 403")

    code, made = sessions["director_exam"].call(
        "POST", "/api/prep/theory/", {"exam_type": "IELTS", "title": "Probe lesson", "level": "basic"}
    )
    check(code == 201, f"академический директор заводит теорию → {code}")
    lesson = made.get("id") if isinstance(made, dict) else None
    code, _ = sessions["director_sport"].call("POST", "/api/prep/theory/", {"exam_type": "IELTS", "title": "X"})
    check(code == 403, f"чужой директор заводит теорию → {code}, ожидали 403")
    code, listing = student.call("GET", "/api/prep/theory/?exam_type=IELTS")
    rows_ = listing.get("results", []) if isinstance(listing, dict) else (listing if isinstance(listing, list) else [])
    check(any(r.get("id") == lesson for r in rows_), "ученик видит теорию")
    if lesson:
        # уборка урока прогона
        sessions["director_exam"].call("DELETE", f"/api/prep/theory/{lesson}/")

    print("\n== Конструктор эссе (фаза 43) ==")
    code, types = student.call("GET", "/api/essay-doc-types/")
    rows_ = types.get("results", []) if isinstance(types, dict) else (types if isinstance(types, list) else [])
    check(code == 200 and len(rows_) >= 9, f"типы документов эссе → {code}, штук {len(rows_)}")
    dt_id = rows_[0]["id"] if rows_ else None
    # остатки прошлого прогона: незавершённый прогон оставлял тип с тем же
    # кодом, и все следующие падали на «уже существует» — прогон обязан
    # начинаться с чистого листа сам, а не после ручной уборки
    leftover = next((r for r in rows_ if r.get("code") == "probe_type"), None)
    if leftover:
        code, _ = sessions["director_admission"].call("DELETE", f"/api/essay-doc-types/{leftover['id']}/")
        check(code in (200, 204), f"остаток прошлого прогона убран → {code}")
    code, made = sessions["director_admission"].call(
        "POST", "/api/essay-doc-types/", {"code": "probe_type", "name": "Probe type"}
    )
    check(code == 201, f"директор по поступлению заводит тип → {code}")
    probe_type = made.get("id") if isinstance(made, dict) else None
    code, _ = sessions["director_sport"].call("POST", "/api/essay-doc-types/", {"code": "x", "name": "X"})
    check(code == 403, f"чужой директор заводит тип → {code}, ожидали 403")

    code, essay = student.call(
        "POST", "/api/essays/", {"essay_type": "personal_statement", "doc_type": dt_id, "title": "Probe essay"}
    )
    check(code == 201, f"ученик заводит эссе → {code}")
    essay_id = essay.get("id") if isinstance(essay, dict) else None
    if essay_id:
        check(isinstance(essay, dict) and essay.get("effective_word_limit"), "лимит слов пришёл из типа")
        code, log = student.call("GET", f"/api/essays/{essay_id}/assist-log/")
        check(code == 200 and isinstance(log, dict), f"лог помощника у ученика → {code}")
        if foreign:
            # чужой ученик не видит переписку — проверим на своём эссе под другим учеником нельзя,
            # достаточно что директор (куратор-роль) видит
            code, _ = sessions["director_admission"].call("GET", f"/api/essays/{essay_id}/assist-log/")
            check(code == 200, f"куратор видит переписку по эссе → {code}")
    code, _ = student.call("GET", "/api/essays/reading-of-the-day/")
    check(code == 200, f"чтение дня → {code}")
    # уборка типа прогона: молчаливый отказ здесь однажды оставил запись,
    # и все следующие прогоны падали на «уже существует»
    if probe_type:
        code, _ = sessions["director_admission"].call("DELETE", f"/api/essay-doc-types/{probe_type}/")
        check(code in (200, 204), f"тип прогона удалён → {code}")

    print("\n== Стипендии (фаза 44) ==")
    code, made = sessions["director_admission"].call(
        "POST",
        "/api/scholarships/",
        {
            "name": "Probe Scholarship",
            "funding_type": "full",
            "country": "Канада",
            "for_international": True,
            "deadline": "2027-03-01",
            "amount_max": "12000",
            "currency": "USD",
        },
    )
    check(code == 201, f"директор по поступлению заводит стипендию → {code}")
    schol = made.get("id") if isinstance(made, dict) else None
    code, _ = sessions["director_sport"].call("POST", "/api/scholarships/", {"name": "X", "funding_type": "full"})
    check(code == 403, f"чужой директор заводит стипендию → {code}, ожидали 403")
    code, _ = sessions["admin"].call("POST", "/api/scholarships/", {"name": "Y", "funding_type": "full"})
    check(code == 403, f"администратор заводит стипендию → {code}, ожидали 403")

    code, listing = student.call("GET", "/api/scholarships/")
    rows_ = listing.get("results", []) if isinstance(listing, dict) else []
    check(code == 200 and any(r.get("id") == schol for r in rows_), f"ученик видит каталог стипендий → {code}")
    row = next((r for r in rows_ if r.get("id") == schol), {})
    check(bool(row.get("deadline_state")), f"состояние срока приходит словами: «{row.get('deadline_state')}»")
    check(bool(row.get("amount_title")), f"сумма приходит подписью: «{row.get('amount_title')}»")

    code, overview = student.call("GET", "/api/scholarship-overview/")
    check(code == 200 and isinstance(overview, dict) and "funding" in overview, f"числа над каталогом → {code}")

    if schol:
        code, _ = student.call("POST", f"/api/scholarships-saved/{schol}/")
        check(code in (200, 201), f"ученик сохраняет стипендию → {code}")
        code, saved_ = student.call("GET", "/api/scholarships-saved/")
        check(
            isinstance(saved_, dict) and any(r.get("id") == schol for r in saved_.get("results", [])),
            "сохранённая стипендия в своём списке",
        )
        code, cal = student.call("GET", "/api/calendar/")
        events = cal.get("events", []) if isinstance(cal, dict) else []
        check(any(e.get("kind") == "scholarship" for e in events), "дедлайн стипендии попал в календарь")

    code, pick = student.call("POST", "/api/scholarships-pick/", {})
    known = {r.get("id") for r in rows_}
    picks = pick.get("picks", []) if isinstance(pick, dict) else []
    check(code == 200, f"подбор стипендий у ученика → {code}")
    check(all(p.get("id") in known for p in picks), "подбор не называет стипендий мимо справочника (инвариант №10)")
    code, _ = sessions["director_admission"].call("POST", "/api/scholarships-pick/", {})
    check(code == 403, f"подбор у директора → {code}, ожидали 403")

    code, _ = sessions["director_admission"].call("GET", "/api/scholarships-attention/")
    check(code == 200, f"сводка по стипендиям у директора по поступлению → {code}")
    code, _ = sessions["director_sport"].call("GET", "/api/scholarships-attention/")
    check(code == 403, f"сводка по стипендиям у директора спорта → {code}, ожидали 403")
    # файл шлём настоящим multipart: с телом JSON запрос отбился бы разбором (415)
    # раньше, чем дошёл до проверки права, и проверка ничего не значила бы
    code, answer = sessions["director_admission"].upload("/api/scholarships-import/", "list.csv", b"name\n")
    check(code == 403, f"загрузка стипендий файлом у директора → {code}, ожидали 403")
    code, _ = sessions["admin"].upload("/api/scholarships-import/", "list.csv", b"\xef\xbb\xbfname\nProbe\n")
    check(code == 200, f"загрузка стипендий файлом у администратора → {code}")

    if schol:
        # уборка: стипендия прогона и отметка ученика
        student.call("DELETE", f"/api/scholarships-saved/{schol}/")
        sessions["director_admission"].call("DELETE", f"/api/scholarships/{schol}/")

    print("\n== Ресурсы и профтест (фаза 45) ==")
    code, cats = student.call("GET", "/api/resource-categories/")
    rows_ = cats.get("results", []) if isinstance(cats, dict) else (cats if isinstance(cats, list) else [])
    check(code == 200 and len(rows_) >= 7, f"категории материалов посеяны → {code}, штук {len(rows_)}")
    category = rows_[0]["id"] if rows_ else None

    code, made = sessions["director_exam"].call(
        "POST",
        "/api/resources/",
        {"title": "Probe resource", "category": category, "summary": "Проверочная памятка", "reading_minutes": 3},
    )
    check(code == 201, f"академический директор пишет памятку → {code}")
    resource = made.get("id") if isinstance(made, dict) else None
    code, _ = student.call("POST", "/api/resources/", {"title": "X", "category": category})
    check(code == 403, f"ученик пишет памятку → {code}, ожидали 403")

    code, listing = student.call("GET", "/api/resources/")
    rows_ = listing.get("results", []) if isinstance(listing, dict) else []
    check(code == 200 and any(r.get("id") == resource for r in rows_), f"ученик читает раздел → {code}")
    if resource:
        code, marked = student.call("POST", f"/api/resources/{resource}/read/")
        check(code == 200 and marked.get("is_read") is True, f"отметка «прочитано» у ученика → {code}")
        code, _ = sessions["director_exam"].call("POST", f"/api/resources/{resource}/read/")
        check(code == 403, f"отметка «прочитано» у директора → {code}, ожидали 403")
    code, overview = student.call("GET", "/api/resources/overview/")
    check(code == 200 and isinstance(overview, dict) and "categories" in overview, f"счётчики раздела → {code}")

    code, questions = student.call("GET", "/api/career-questions/")
    rows_ = questions.get("results", []) if isinstance(questions, dict) else []
    check(code == 200 and len(rows_) >= 6, f"вопросы профтеста посеяны → {code}, штук {len(rows_)}")
    # анкету ведёт директор по поступлению (переехала от директора школы):
    # чужой директор и прежний владелец читают, но не пишут
    for role in ("director_exam", "director_behavior"):
        code, _ = sessions[role].call("GET", "/api/career-questions/")
        check(code == 200, f"{role} читает анкету профтеста → {code}")
        code, _ = sessions[role].call("POST", "/api/career-questions/", {"code": "x", "text": "X"})
        check(code == 403, f"{role} правит анкету → {code}, ожидали 403")
    asem45 = sessions["director_admission"]
    # строка прошлого прогона, если уборка не дошла: код вопроса уникален
    code, stale45 = asem45.call("GET", "/api/career-questions/?page_size=200")
    for row in stale45.get("results", []) if isinstance(stale45, dict) else []:
        if row.get("code") == "probe_career_question":
            asem45.call("DELETE", f"/api/career-questions/{row['id']}/")
    # выключенным: в анкету ученика вопрос прогона попасть не должен
    code, made45 = asem45.call(
        "POST",
        "/api/career-questions/",
        {"code": "probe_career_question", "text": "Вопрос прогона", "is_active": False},
    )
    check(code == 201, f"директор по поступлению заводит вопрос профтеста → {code}")
    question_id = made45.get("id") if isinstance(made45, dict) else None
    if question_id:
        code, _ = asem45.call("PATCH", f"/api/career-questions/{question_id}/", {"hint": "подсказка прогона"})
        check(code == 200, f"директор по поступлению правит вопрос → {code}")
        code, _ = sessions["director_behavior"].call(
            "PATCH", f"/api/career-questions/{question_id}/", {"hint": "чужая правка"}
        )
        check(code == 403, f"директор школы правит чужой вопрос → {code}, ожидали 403")
        code, _ = sessions["director_behavior"].call("DELETE", f"/api/career-questions/{question_id}/")
        check(code == 403, f"директор школы удаляет чужой вопрос → {code}, ожидали 403")
        code, _ = asem45.call("DELETE", f"/api/career-questions/{question_id}/")
        check(code == 204, f"директор по поступлению удаляет вопрос → {code}, ожидали 204")

    code, career = student.call("GET", "/api/career/")
    check(code == 200 and isinstance(career, dict), f"состояние профтеста у ученика → {code}")
    if isinstance(career, dict) and not career.get("available"):
        check(bool(career.get("detail")), "профтест без ключа объясняет, почему недоступен")
        code, _ = student.call(
            "POST", "/api/career/run/", {"answers": [{"question": r["code"], "value": "математика"} for r in rows_]}
        )
        check(code == 503, f"прохождение без ключа → {code}, ожидали 503")
    code, _ = sessions["director_behavior"].call("GET", "/api/career/")
    check(code == 403, f"профтест у директора → {code}, ожидали 403")

    if resource:
        # уборка: памятка прогона
        student.call("DELETE", f"/api/resources/{resource}/read/")
        sessions["director_exam"].call("DELETE", f"/api/resources/{resource}/")

    print("\n== Достижения (фаза 46) ==")
    # квиз снят с продукта (27.09.2026): адресов больше нет
    code, _ = student.call("GET", "/api/prep/quiz/")
    check(code == 404, f"адрес квиза закрыт → {code}, ожидали 404")
    code, badges = student.call("GET", "/api/achievements/")
    rows_ = badges.get("badges", []) if isinstance(badges, dict) else []
    check(code == 200 and len(rows_) >= 10, f"бейджи посеяны → {code}, штук {len(rows_)}")
    check(all(row.get("condition") for row in rows_), "у каждого бейджа видно условие, даже у закрытого")
    check(all("из" in row.get("progress", "") for row in rows_), "у каждого бейджа виден прогресс")

    code, made = sessions["admin"].call(
        "POST", "/api/badges/", {"code": "probe_badge", "name": "Probe badge", "metric": "tasks_done", "threshold": 3}
    )
    check(code == 201, f"администратор заводит бейдж → {code}")
    badge_id = made.get("id") if isinstance(made, dict) else None
    code, refused = sessions["admin"].call(
        "POST", "/api/badges/", {"code": "ielts_seven", "name": "IELTS 7", "metric": "ielts_score", "threshold": 7}
    )
    check(code == 400, f"бейдж за балл экзамена → {code}, ожидали 400 (инвариант №12)")
    code, _ = sessions["director_behavior"].call(
        "POST", "/api/badges/", {"code": "x", "name": "X", "metric": "tasks_done"}
    )
    check(code == 403, f"директор школы бейджи больше не ведёт → {code}, ожидали 403")
    if badge_id:
        code, _ = sessions["admin"].call("DELETE", f"/api/badges/{badge_id}/")
        check(code in (200, 204), f"бейдж прогона удалён → {code}")

    print("\n== Правила обзвона: справочник владельца (фаза 53) ==")
    # D27: справочник читал любой вошедший, потому что вьюха наследовала
    # права у соседней. Ученику нельзя видеть ни фразы, которыми школа
    # описывает его самого, ни пороги срабатывания (инвариант №7)
    marker = "проба фазы 53: просел по пробным"
    code, made = sessions["director_behavior"].call(
        "POST",
        "/api/call-rules/",
        {"code": "probe_call_rule", "condition": "inactive", "reason": marker, "urgency": "today", "threshold": 21},
    )
    check(code == 201, f"директор школы заводит правило обзвона → {code}")
    rule_id = made.get("id") if isinstance(made, dict) else None

    code, listing = sessions["director_behavior"].call("GET", "/api/call-rules/")
    rows_ = listing.get("results", []) if isinstance(listing, dict) else []
    check(code == 200 and any(r.get("id") == rule_id for r in rows_), f"владелец читает свой справочник → {code}")

    # администратор с фазы 68 ведёт справочники всех доменов
    code, _ = sessions["admin"].call("GET", "/api/call-rules/")
    check(code == 200, f"администратор читает правила обзвона → {code}")
    for role in ("student", "director_admission", "director_exam", "director_talent", "director_sport"):
        code, body = sessions[role].call("GET", "/api/call-rules/")
        check(code == 403, f"{role} читает правила обзвона → {code}, ожидали 403")
        check(marker not in json.dumps(body, ensure_ascii=False), f"{role}: формулировки правила нет в ответе")
        if rule_id:
            code, _ = sessions[role].call("GET", f"/api/call-rules/{rule_id}/")
            check(code == 403, f"{role} читает карточку правила → {code}, ожидали 403")
            code, _ = sessions[role].call("PATCH", f"/api/call-rules/{rule_id}/", {"threshold": 1})
            check(code == 403, f"{role} правит правило → {code}, ожидали 403")
            code, _ = sessions[role].call("DELETE", f"/api/call-rules/{rule_id}/")
            check(code == 403, f"{role} удаляет правило → {code}, ожидали 403")

    # та же фраза не должна всплыть и на ученических ручках в обход справочника:
    # справочник закрыт, но фраза могла бы приехать внутри чужого ответа
    for path in (
        "/api/home/cues/",
        "/api/journey/",
        "/api/journey/locks/",
        "/api/game/me/",
        "/api/students/me/",
        "/api/achievements/",
        "/api/notifications/",
        "/api/tasks/my/",
        "/api/resources/",
        "/api/jobs/",
        "/api/career/",
    ):
        code, body = student.call("GET", path)
        check(
            marker not in json.dumps(body, ensure_ascii=False),
            f"{path} → формулировки правила обзвона нет",
        )
    code, _ = student.call("GET", "/api/cabinet/")
    check(code == 403, f"кабинет руководителя у ученика → {code}, ожидали 403")

    # сюжеты карусели ученику по-прежнему открыты: правка касается не их
    code, cues = student.call("GET", "/api/home-cues/")
    check(code == 200, f"ученик читает сюжеты карусели → {code}, ожидали 200")

    # сам справочник сюжетов — настройка школы: ведёт администратор, директорам
    # он закрыт и на чтение, включая прежнего владельца — директора школы
    keeper = sessions["admin"]
    code, stale_cues = keeper.call("GET", "/api/home-cues/?page_size=200")
    check(code == 200, f"администратор читает сюжеты главной → {code}")
    for row in stale_cues.get("results", []) if isinstance(stale_cues, dict) else []:
        if row.get("code") == "probe_home_cue":
            keeper.call("DELETE", f"/api/home-cues/{row['id']}/")
    # выключенным: на главную ученика сюжет прогона попасть не должен
    code, made_cue = keeper.call(
        "POST",
        "/api/home-cues/",
        {
            "code": "probe_home_cue",
            "condition": "no_universities",
            "title": "Сюжет прогона",
            "action_label": "Открыть",
            "action_path": "/universities",
            "is_active": False,
        },
    )
    check(code == 201, f"администратор заводит сюжет главной → {code}")
    cue_id = made_cue.get("id") if isinstance(made_cue, dict) else None
    for role in ("director_behavior", "director_admission", "director_exam", "director_talent", "director_sport"):
        code, _ = sessions[role].call("GET", "/api/home-cues/")
        check(code == 403, f"{role} читает сюжеты главной → {code}, ожидали 403")
        code, _ = sessions[role].call(
            "POST",
            "/api/home-cues/",
            {
                "code": f"probe_foreign_{role}",
                "condition": "no_universities",
                "title": "Чужой сюжет",
                "action_label": "Открыть",
                "action_path": "/universities",
                "is_active": False,
            },
        )
        check(code == 403, f"{role} заводит сюжет главной → {code}, ожидали 403")
        if cue_id:
            code, _ = sessions[role].call("PATCH", f"/api/home-cues/{cue_id}/", {"title": "Чужая правка"})
            check(code == 403, f"{role} правит сюжет главной → {code}, ожидали 403")
    code, _ = student.call("POST", "/api/home-cues/", {"code": "probe_student_cue", "title": "X"})
    check(code == 403, f"ученик заводит сюжет главной → {code}, ожидали 403")
    if cue_id:
        code, _ = keeper.call("PATCH", f"/api/home-cues/{cue_id}/", {"title": "Сюжет прогона, правка"})
        check(code == 200, f"администратор правит сюжет главной → {code}")
        code, _ = keeper.call("DELETE", f"/api/home-cues/{cue_id}/")
        check(code == 204, f"администратор удаляет сюжет главной → {code}, ожидали 204")

    if rule_id:
        code, _ = sessions["director_behavior"].call("DELETE", f"/api/call-rules/{rule_id}/")
        check(code in (200, 204), f"правило прогона удалено → {code}")

    print("\n== Куратор: границы своих групп (фаза 60) ==")
    curator = sessions["curator"]
    admin = sessions["admin"]

    # группы куратору назначает администратор — как в жизни и как в посеве.
    # Прогон может идти и без Playwright: тогда назначения ещё нет, и первую
    # группу куратор получает здесь же. Уборка снимет назначение вместе с записью
    code, cabinet = curator.call("GET", "/api/cabinet/")
    if isinstance(cabinet, dict) and not cabinet.get("groups"):
        # именно ту группу, где учится ученик прогона: очередь ниже проверяется
        # на его предложении, а в чужой группе куратор его и не должен видеть
        code, rows = admin.call("GET", f"/api/students/?search={ACCOUNTS['student'][0]}")
        card = (rows.get("results") or [None])[0] if isinstance(rows, dict) else None
        first = {"id": card["group"], "code": card.get("group_code", "")} if card and card.get("group") else None
        code, people = admin.call("GET", "/api/users/?role=curator")
        # с фазы 69 список — объект со строками и счётчиками чипов
        rows_of = people.get("results", []) if isinstance(people, dict) else []
        who = next((row for row in rows_of if row.get("email") == ACCOUNTS["curator"][0]), None)
        if first and who:
            code, _ = admin.call(
                "POST",
                "/api/curator-assignments/",
                {"group": first["id"], "curator": who["id"], "since": _dt.date.today().isoformat()},
            )
            check(code == 201, f"администратор назначает куратора группе {first['code']} → {code}")

    code, cabinet = curator.call("GET", "/api/cabinet/")
    own_groups = {row["code"] for row in cabinet.get("groups", [])} if isinstance(cabinet, dict) else set()
    check(code == 200 and own_groups, f"кабинет куратора → {code}, групп {len(own_groups)}")

    code, groups = curator.call("GET", "/api/groups/?page_size=100")
    seen_groups = {row["code"] for row in groups.get("results", [])} if isinstance(groups, dict) else set()
    check(seen_groups == own_groups, f"список групп — только свои: {sorted(seen_groups)}")

    code, all_groups = admin.call("GET", "/api/groups/?page_size=100")
    other_group = next(
        (row for row in all_groups.get("results", []) if row["code"] not in own_groups),
        None,
    ) if isinstance(all_groups, dict) else None

    code, mine = curator.call("GET", "/api/students/?page_size=500")
    my_ids = [row["id"] for row in mine.get("results", [])] if isinstance(mine, dict) else []
    code, everyone = admin.call("GET", "/api/students/?page_size=500")
    all_ids = [row["id"] for row in everyone.get("results", [])] if isinstance(everyone, dict) else []
    stranger = next((i for i in all_ids if i not in my_ids), None)
    check(bool(my_ids) and len(my_ids) < len(all_ids), f"куратор видит своих: {len(my_ids)} из {len(all_ids)}")

    if my_ids:
        code, card = curator.call("GET", f"/api/students/{my_ids[0]}/")
        has_labels = isinstance(card, dict) and "status" in card.get("behavior", {})
        check(code == 200 and has_labels, f"карточка своего ученика целиком, с ярлыками → {code}")
        code, _ = curator.call("GET", f"/api/students/{my_ids[0]}/history/")
        check(code == 200, f"история правок своего ученика → {code}")
        # куратор вносит за ученика всё ученическое — напрямую, по своим группам;
        # текущий балл считается по попыткам и руками не вносится никем
        code, _ = curator.call("PATCH", f"/api/profiles/exam/{my_ids[0]}/", {"ielts_current": "9.0"})
        check(code == 403, f"куратор вносит текущий балл руками → {code}, ожидали 403")
        code, before = curator.call("GET", f"/api/profiles/exam/{my_ids[0]}/")
        old_target = before.get("sat_target") if isinstance(before, dict) else None
        code, saved = curator.call("PATCH", f"/api/profiles/exam/{my_ids[0]}/", {"sat_target": "1490"})
        check(code == 200, f"куратор ставит цель SAT своему ученику → {code}")
        check(
            isinstance(saved, dict) and "sat_target" in saved.get("entered_by_curator", []),
            "значение подписано «внёс куратор»",
        )
        curator.call("PATCH", f"/api/profiles/exam/{my_ids[0]}/", {"sat_target": old_target})
        code, made = curator.call(
            "POST",
            "/api/attempts/",
            {"student": my_ids[0], "exam_type": "SAT", "date": "2026-03-14", "total_score": "1400"},
        )
        check(code == 201 and made.get("attempt_format") == "official", f"куратор вносит официальную попытку → {code}")
        if code == 201:
            code, gone = curator.call("DELETE", f"/api/attempts/{made['id']}/")
            check(code == 200 and "в архиве" in str(gone), f"и убирает её в архив → {code}")
        code, _ = curator.call("PATCH", f"/api/profiles/admission/{my_ids[0]}/", {"status": "critical"})
        check(code == 403, f"служебное поле домена куратору закрыто → {code}, ожидали 403")

    if stranger is not None:
        for path in (
            f"/api/students/{stranger}/",
            f"/api/students/{stranger}/history/",
            f"/api/profiles/behavior/{stranger}/",
        ):
            code, _ = curator.call("GET", path)
            check(code == 404, f"чужая группа {path} → {code}, ожидали 404 (не 403)")
        code, _ = curator.call("PATCH", f"/api/profiles/exam/{stranger}/", {"sat_target": "1490"})
        check(code == 404, f"куратор вносит данные чужому ученику → {code}, ожидали 404")
        code, _ = curator.call(
            "POST", "/api/attempts/", {"student": stranger, "exam_type": "SAT", "date": "2026-03-14", "total_score": "1400"}
        )
        check(code == 404, f"куратор заводит попытку чужому ученику → {code}, ожидали 404")

    for path in (
        "/api/prep/theory/",
        "/api/prep/questions/",
        "/api/users/",
        "/api/archive/",
        "/api/table/" if False else "/api/dashboards/exam/",
        "/api/digest/",
        "/api/commands/",
        "/api/task-templates/",
    ):
        code, _ = curator.call("GET", path)
        check(code == 403, f"справочники и настройки куратору: {path} → {code}, ожидали 403")

    # списки выбора для форм куратора читаются, вести справочник он не может
    for path in ("/api/exam-kinds/", "/api/subjects/", "/api/universities/"):
        code, _ = curator.call("GET", path)
        check(code == 200, f"список выбора для форм куратора: {path} → {code}")
        code, _ = curator.call("POST", path, {"name": "Проба куратора"})
        check(code == 403, f"куратор ведёт справочник {path} → {code}, ожидали 403")

    code, _ = curator.call("POST", "/api/batch/save/", {"changes": []})
    check(code == 403, f"куратор правит таблицу → {code}, ожидали 403")
    if other_group is not None:
        code, _ = curator.call("GET", f"/api/groups/{other_group['id']}/")
        check(code == 404, f"чужая группа в справочнике групп → {code}, ожидали 404")

    print("\n== Куратор: очередь, двойное подтверждение, имя не утекает ==")
    code, made = student.call(
        "POST",
        "/api/suggestions/propose/",
        {"rows": [{"model": "students.ExamProfile", "field": "ielts_current", "value": "7.5"}]},
    )
    curator_proposal = made.get("suggestions", [None])[0] if isinstance(made, dict) else None
    check(code == 201, f"ученик группы куратора предлагает балл → {code}")

    if curator_proposal:
        code, queue = curator.call("GET", "/api/suggestions/from-students/")
        seen = isinstance(queue, dict) and any(row.get("id") == curator_proposal for row in queue.get("results", []))
        check(bool(seen), f"очередь куратора видит предложение своего ученика → {code}")

        code, _ = curator.call("POST", f"/api/suggestions/{curator_proposal}/review/", {"decision": "decline"})
        check(code == 400, f"отклонение без причины → {code}, ожидали 400")

        code, done = curator.call("POST", f"/api/suggestions/{curator_proposal}/review/", {"decision": "confirm"})
        check(
            code == 200 and isinstance(done, dict) and done.get("applied") == 1,
            f"куратор подтверждает первым → {code}",
        )

        code, conflict = sessions["director_exam"].call(
            "POST", f"/api/suggestions/{curator_proposal}/review/", {"decision": "confirm"}
        )
        detail = conflict.get("detail", "") if isinstance(conflict, dict) else ""
        check(code == 409, f"второе подтверждение → {code}, ожидали 409")
        check("Уже подтверждено" in detail and "Куратор" in detail, f"409 называет, кем и когда: «{detail[:80]}»")
        check(
            isinstance(conflict, dict) and conflict.get("suggestion", {}).get("id") == curator_proposal,
            "409 возвращает обновлённую строку очереди",
        )

        code, mine_rows = student.call("GET", "/api/suggestions/mine/")
        text = json.dumps(mine_rows, ensure_ascii=False)
        check("Асель" not in text and "curator@probe.local" not in text, "имя куратора не утекает ученику")

        code, _ = sessions["director_exam"].call("POST", f"/api/suggestions/{curator_proposal}/revert/", {})
        check(code == 200, f"откат владельцем домена → {code}")
        code, _ = curator.call("POST", f"/api/suggestions/{curator_proposal}/revert/", {})
        check(code == 403, f"откат куратором → {code}, ожидали 403")

    code, _ = curator.call("PATCH", f"/api/groups/{cabinet['groups'][0]['id']}/", {"curator": "Кто-то"}) if own_groups else (403, None)
    check(code == 403, f"куратор правит группу → {code}, ожидали 403")
    if other_group is not None:
        code, body = admin.call("PATCH", f"/api/groups/{other_group['id']}/", {"curator": "Текстом"})
        check(code == 400, f"старое текстовое поле куратора → {code}, ожидали 400")
        code, row = admin.call("GET", f"/api/groups/{other_group['id']}/")
        check(isinstance(row, dict) and "curator" not in row, "поля «куратор» у группы больше нет в ответе")

    print("\n== Кабинет куратора: корзины, задачи, выгрузка (фаза 61) ==")
    code, overview = curator.call("GET", "/api/curator/overview/")
    check(code == 200 and isinstance(overview, dict), f"главная куратора → {code}")
    code, table = curator.call("GET", "/api/curator/students/")
    check(code == 200 and isinstance(table, dict), f"таблица учеников → {code}")

    # выбор группы сверяется с назначениями (фаза 80): чужой и несуществующий код
    # заменяется первой своей группой — не пустым кабинетом и не чужими данными
    if isinstance(overview, dict) and overview.get("groups"):
        own_codes = [row["code"] for row in overview["groups"]]
        for alien in ("AMSTERDAM", "NO-SUCH-GROUP"):
            if alien in own_codes:
                continue
            code, picked = curator.call("GET", f"/api/curator/overview/?group={alien}")
            ok = code == 200 and isinstance(picked, dict)
            check(ok and picked.get("group") == own_codes[0], f"чужой выбор «{alien}» → первая своя группа {own_codes[0]}")
            check(
                ok and [row["code"] for row in picked.get("groups", [])] == own_codes,
                f"при чужом выборе «{alien}» группы в шапке — только назначенные",
            )
            code, listed = curator.call("GET", f"/api/curator/students/?group={alien}")
            rows = listed.get("results", []) if isinstance(listed, dict) else []
            check(
                code == 200 and all(row.get("group") == own_codes[0] for row in rows),
                f"ученики при чужом выборе «{alien}» — только своей группы",
            )
        check(overview.get("group") == "all", "без выбора кабинет открыт по всем своим группам")

    if isinstance(overview, dict) and isinstance(table, dict):
        home = {row["code"]: row["count"] for row in overview.get("buckets", [])}
        chips = {row["code"]: row["count"] for row in table.get("buckets", [])}
        check(home == chips, f"корзины на главной и в чипах совпадают: {home} против {chips}")

        # то же число, посчитанное третьим путём: по строкам таблицы
        by_rows = {}
        for row in table.get("results", []):
            for code_ in row.get("buckets", []):
                by_rows[code_] = by_rows.get(code_, 0) + 1
        check(
            all(home.get(code_, 0) == by_rows.get(code_, 0) for code_ in home),
            f"корзины сходятся и по строкам таблицы: {by_rows}",
        )

        # четыре числа-кнопки ведут туда, где с ними что-то делают
        numbers = {row["code"]: row for row in overview.get("numbers", [])}
        # с фазы 62 два числа — про документы; «пробник» и «просрочено» остались в корзинах и задачах
        check(set(numbers) == {"queue", "nogoal", "docs", "expiring"}, f"четыре числа главной: {sorted(numbers)}")
        check(all(row.get("to") for row in numbers.values()), "у каждого числа есть, куда вести")

    # карточка ученика: пять вкладок одним ответом, чужая — 404
    my_students = table.get("results", []) if isinstance(table, dict) else []
    if my_students:
        first_id = my_students[0]["id"]
        code, card = curator.call("GET", f"/api/curator/students/{first_id}/")
        check(code == 200, f"карточка своего ученика → {code}")
        check(
            all(key in card for key in ("exams", "mocks", "universities", "portfolio", "tasks", "buckets")),
            "карточка собирает все вкладки одним ответом",
        )
        check(
            set(row["code"] for row in card.get("buckets", [])) == set(my_students[0]["buckets"]),
            "корзины в карточке те же, что в строке таблицы",
        )
    if stranger:
        code, _ = curator.call("GET", f"/api/curator/students/{stranger}/")
        check(code == 404, f"карточка чужого ученика → {code}, ожидали 404")

    # задача всей группе — по одной на каждого ученика
    if isinstance(cabinet, dict) and cabinet.get("groups"):
        group_code = cabinet["groups"][0]["code"]
        size = cabinet["groups"][0]["students"]
        code, made = curator.call(
            "POST", "/api/curator/tasks/", {"group": group_code, "title": "Проба: собрать документы"}
        )
        created = made.get("created") if isinstance(made, dict) else 0
        check(code == 201 and created == size, f"задача группе {group_code} → создано {created}, учеников {size}")
        check(
            len(set(made.get("students", []))) == created,
            "каждому ученику своя задача, а не одна общая",
        )

        code, listing = curator.call("GET", "/api/curator/tasks/?filter=open")
        rows_ = listing.get("results", []) if isinstance(listing, dict) else []
        mine_task = next((row for row in rows_ if row["title"] == "Проба: собрать документы"), None)
        check(mine_task is not None, "поставленная задача видна в списке куратора")

        if mine_task:
            # ученик видит свою задачу и знает, что она от куратора, но не имя
            code, my_tasks = student.call("GET", "/api/tasks/my/")
            text = json.dumps(my_tasks, ensure_ascii=False)
            own = [row for row in my_tasks if row.get("title") == "Проба: собрать документы"] if isinstance(my_tasks, list) else []
            if own:
                check(own[0].get("origin") == "curator", f"ученик видит «от куратора»: {own[0].get('origin_title')}")
                check("Асель" not in text and "curator@probe.local" not in text, "имя куратора ученику не видно")
                # чужие задачи в его списке не появляются
                check(
                    all(row.get("student") in (None, own[0].get("student")) for row in my_tasks),
                    "в списке ученика только его задачи",
                )

            code, _ = curator.call("POST", f"/api/curator/tasks/{mine_task['id']}/status/", {"status": "cancelled"})
            check(code == 200, f"куратор отменяет задачу → {code}")
            code, after = curator.call("GET", "/api/curator/tasks/?filter=cancelled")
            check(
                any(row["id"] == mine_task["id"] for row in after.get("results", [])),
                "отменённая задача ушла в свой фильтр",
            )

    # выгрузка: настоящая книга, а не HTML с ошибкой
    code, sheet = curator.call("GET", "/api/curator/students/export/")
    check(code == 200, f"выгрузка учеников → {code}")

    # поиск вернулся куратору и сузился до своих групп (фаза 61)
    from urllib.parse import quote as _quote

    code, found = curator.call("GET", f"/api/search/?q={_quote('Прогон')}")
    groups_ = found.get("groups", []) if isinstance(found, dict) else []
    rows_ = next((g["rows"] for g in groups_ if g["code"] == "students"), [])
    check(code == 200, f"поиск куратора → {code}")
    check(all("/students/" in row["path"] for row in rows_), "поиск ведёт в карточки учеников")
    if stranger:
        check(all(row["id"] != stranger for row in rows_), "чужого ученика поиск куратора не находит")

    # кабинет куратора закрыт остальным ролям
    for role in ("director_exam", "admin", "student"):
        code, _ = sessions[role].call("GET", "/api/curator/overview/")
        check(code == 403, f"{role} открывает кабинет куратора → {code}, ожидали 403")

    print("\n== Куратор: документы, заметки, передача владельцу (фаза 62) ==")
    PDF = b"%PDF-1.4\n%probe\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    asem = sessions["director_admission"]
    kymbat = sessions["director_exam"]

    # документ ученика встаёт в очередь «Документы» — к куратору и Асем, не к Кымбат
    code, doc = student.upload(
        "/api/documents/", "passport.pdf", PDF, content_type="application/pdf", fields={"doc_type": "passport"}
    )
    doc_id = doc.get("id") if isinstance(doc, dict) else None
    check(code == 201 and doc_id and doc.get("status") == "pending", f"ученик загружает паспорт → {code}, статус «ждёт проверки»")
    code, queue = curator.call("GET", "/api/suggestions/from-students/")
    rows_ = queue.get("results", []) if isinstance(queue, dict) else []
    doc_row = next((row for row in rows_ if (row.get("document") or {}).get("id") == doc_id), None)
    check(doc_row is not None and doc_row.get("domain") == "documents", "документ в очереди куратора строкой домена «Документы»")
    code, kq = kymbat.call("GET", "/api/suggestions/from-students/")
    check(
        not any((row.get("document") or {}).get("id") == doc_id for row in kq.get("results", [])),
        "Кымбат документов в очереди не видит: не её домен",
    )

    if doc_row:
        # передача владельцу строки — Асем; без комментария не уходит
        code, _ = curator.call("POST", f"/api/suggestions/{doc_row['id']}/escalate/", {"comment": ""})
        check(code == 400, f"передача без комментария → {code}, ожидали 400")
        code, _ = curator.call("POST", f"/api/suggestions/{doc_row['id']}/escalate/", {"comment": "Проба: не тот паспорт?"})
        check(code == 200, f"куратор передаёт документ Асем → {code}")
        code, queue = curator.call("GET", "/api/suggestions/from-students/")
        check(
            any(row["id"] == doc_row["id"] for row in queue.get("escalated", []))
            and not any(row["id"] == doc_row["id"] for row in queue.get("results", [])),
            "переданное ушло из очереди куратора в «Передано владельцу»",
        )
        code, aq = asem.call("GET", "/api/suggestions/from-students/")
        top = (aq.get("results") or [{}])[0] if isinstance(aq, dict) else {}
        check(
            top.get("id") == doc_row["id"] and top.get("escalated") and "Асель" in (top.get("escalated_by_name") or ""),
            "у Асем переданное сверху, с именем куратора и комментарием",
        )
        code, _ = curator.call("POST", f"/api/suggestions/{doc_row['id']}/review/", {"decision": "confirm"})
        check(code == 409, f"куратор решает переданное → {code}, ожидали 409")
        code, _ = curator.call("POST", f"/api/suggestions/{doc_row['id']}/unescalate/", {})
        check(code == 200, f"куратор возвращает строку себе → {code}")
        code, _ = asem.call("POST", f"/api/suggestions/{doc_row['id']}/escalate/", {"comment": "x"})
        check(code == 403, f"Асем передаёт строку → {code}, ожидали 403")
        code, _ = curator.call("POST", f"/api/suggestions/{doc_row['id']}/review/", {"decision": "confirm"})
        check(code == 200, f"куратор подтверждает документ → {code}")
        code, mine_docs = student.call("GET", "/api/documents/")
        text = json.dumps(mine_docs, ensure_ascii=False)
        own_doc = next((row for row in mine_docs.get("results", []) if row["id"] == doc_id), {})
        check(own_doc.get("status") == "confirmed", f"ученик видит статус «подтверждён»: {own_doc.get('status_title')}")
        check("Асель" not in text and "curator@probe.local" not in text, "имя проверившего ученику не показывается")
        code, _ = curator.call("DELETE", f"/api/documents/{doc_id}/")
        check(code in (403, 405), f"куратор удаляет документ → {code}, ожидали отказ")
        code, _ = curator.call("GET", f"/api/documents/{doc_id}/file/")
        check(code == 200, f"файл своего ученика куратору → {code}")

    # чужой ученик в чужой группе: файл отвечает 404, не 403
    code, all_groups = admin.call("GET", "/api/groups/?page_size=100")
    if not any(row["code"] == "ZURICH" for row in all_groups.get("results", [])):
        admin.call("POST", "/api/groups/", {"code": "ZURICH", "parallel": 11})
    stranger_email = "stranger62@probe.local"
    code, enrolled = admin.call(
        "POST",
        "/api/enrollment/apply/",
        {"rows": [{"full_name": "Чужой Прогон", "email": stranger_email, "group": "ZURICH"}]},
    )
    password = (
        next((row.get("password") for row in enrolled.get("rows", []) if row.get("email") == stranger_email), None)
        if isinstance(enrolled, dict)
        else None
    )
    if not password:
        # повторный прогон: карточка осталась, а запись убрала уборка — заводим заново, как администратор
        code, people = admin.call("GET", f"/api/users/?search={stranger_email}")
        found = people.get("results", []) if isinstance(people, dict) else []
        who = next((row for row in found if row.get("email") == stranger_email), None)
        if who is None:
            code, who = admin.call("POST", "/api/users/", {"email": stranger_email, "full_name": "Чужой Прогон", "role": "student"})
            who = who if code == 201 and isinstance(who, dict) else None
        if who:
            code, issued = admin.call("POST", f"/api/users/{who['id']}/temp-password/", {})
            password = issued.get("password") if isinstance(issued, dict) else None
    stranger_session = login_as(stranger_email, password) if password else None
    if stranger_session:
        stranger_session.call("POST", "/api/auth/password/change/", {"current_password": password, "new_password": _password("PROBE_PASSWORD")})
        code, sdoc = stranger_session.upload(
            "/api/documents/", "attestat.pdf", PDF, content_type="application/pdf", fields={"doc_type": "attestat"}
        )
        sdoc_id = sdoc.get("id") if isinstance(sdoc, dict) else None
        check(code == 201 and sdoc_id, f"ученик чужой группы загружает документ → {code}")
        if sdoc_id:
            code, _ = curator.call("GET", f"/api/documents/{sdoc_id}/file/")
            check(code == 404, f"файл ученика чужой группы куратору → {code}, ожидали 404")
            code, _ = asem.call("GET", f"/api/documents/{sdoc_id}/file/")
            check(code == 200, f"тот же файл Асем → {code}")
            code, _ = student.call("GET", f"/api/documents/{sdoc_id}/file/")
            check(code == 404, f"файл чужого ученика ученику → {code}, ожидали 404")
    else:
        check(False, "не удалось войти учеником чужой группы для проверки файла")

    # заметки: куратор пишет, Кымбат и Салтанат читают, Асем и ученик — нет
    if my_ids:
        code, note = curator.call("POST", "/api/notes/", {"student": my_ids[0], "text": "Проба: заметка куратора"})
        note_id = note.get("id") if isinstance(note, dict) else None
        check(code == 201 and note_id, f"куратор пишет заметку → {code}")
        # администратор читает заметки с фазы 68
        for role, expected in (("director_exam", 200), ("director_behavior", 200), ("director_admission", 403), ("student", 403), ("admin", 200)):
            code, _ = sessions[role].call("GET", f"/api/notes/?student={my_ids[0]}")
            check(code == expected, f"{role} читает заметки → {code}, ожидали {expected}")
        code, _ = student.call("GET", "/api/notes/")
        check(code == 403, f"ученик открывает список заметок → {code}, ожидали 403")
        for path in ("/api/students/me/", "/api/portfolio/", "/api/tasks/my/", "/api/journey/"):
            code, payload = student.call("GET", path)
            check("заметка куратора" not in json.dumps(payload, ensure_ascii=False), f"{path}: заметки куратора нет")
        code, _ = kymbat.call("POST", "/api/notes/", {"student": my_ids[0], "text": "x"})
        check(code == 403, f"Кымбат пишет заметку → {code}, ожидали 403")
        if note_id:
            code, _ = curator.call("DELETE", f"/api/notes/{note_id}/")
            check(code in (200, 204), f"куратор убирает заметку в архив → {code}")

        # звонок родителям: с текстом — заметка и журнал
        code, called = curator.call("POST", f"/api/curator/students/{my_ids[0]}/call/", {"text": "Проба: звонок"})
        check(code == 200 and isinstance(called, dict) and called.get("noted"), f"итог звонка → {code}")
        code, journal = curator.call("GET", "/api/curator/journal/")
        rows_ = journal.get("results", []) if isinstance(journal, dict) else []
        check(code == 200 and any("Звонок родителям" in (row.get("what") or "") for row in rows_), "звонок виден в журнале куратора")

        # передача с карточки без строки — уведомление владельцу
        code, _ = curator.call("POST", f"/api/curator/students/{my_ids[0]}/escalate/", {"domain": "exam", "comment": "Проба: вопрос"})
        check(code == 200, f"передача Кымбат с карточки → {code}")
        code, kn = kymbat.call("GET", "/api/notifications/")
        check(any("передал вопрос" in row.get("text", "") for row in kn.get("rows", [])), "Кымбат получила уведомление с комментарием куратора")

    # владелец решил строку из очереди куратора — куратору уведомление
    code, made = student.call(
        "POST", "/api/suggestions/propose/", {"rows": [{"model": "students.ExamProfile", "field": "sat_current", "value": "1400"}]}
    )
    decided = made.get("suggestions", [None])[0] if isinstance(made, dict) else None
    if decided:
        code, _ = kymbat.call("POST", f"/api/suggestions/{decided}/review/", {"decision": "confirm"})
        check(code == 200, f"Кымбат решает строку из очереди куратора → {code}")
        code, cn = curator.call("GET", "/api/notifications/")
        check(any("из вашей очереди" in row.get("text", "") for row in cn.get("rows", [])), "куратор получил уведомление о решении Кымбат")

    for role in ("director_exam", "admin", "student"):
        code, _ = sessions[role].call("GET", "/api/curator/documents/")
        check(code == 403, f"{role} открывает документы куратора → {code}, ожидали 403")

    print("\n== Пробники файлом и секции IELTS (фаза 63) ==")
    csv_ielts = (
        "ФИО,Listening,Reading,Writing,Speaking,Балл\n"
        f"{'Прогон Айгерим'},6.0,6.0,6.0,6.0,6.0\n"
    ).encode()
    mock_date = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()

    # текущий балл до загрузки: пробник его не тронет
    kymbat63 = sessions["director_exam"]
    code, before = curator.call("GET", "/api/curator/students/")
    mine_row = next((row for row in before.get("results", []) if "Прогон" in row.get("full_name", "")), {})
    ielts_before = mine_row.get("ielts_current")

    # файлом пробники грузят Кымбат и администратор; куратор вносит баллы руками
    code, made = kymbat63.upload(
        "/api/mock-imports/apply/",
        "probe-ielts.csv",
        csv_ielts,
        fields={"exam_type": "IELTS", "group": "CHICAGO", "date": mock_date, "teacher": "Учитель прогона"},
    )
    mock_id = made.get("import") if isinstance(made, dict) else None
    check(code in (201, 400), f"Кымбат загружает пробник → {code}")
    if code == 400:
        # повторный прогон на живой базе: пробник за эту дату уже есть
        code, listing = kymbat63.call("GET", "/api/mock-imports/?group=all")
        mock_id = (listing.get("results") or [{}])[0].get("id") if isinstance(listing, dict) else None

    code, after = curator.call("GET", "/api/curator/students/")
    mine_after = next((row for row in after.get("results", []) if "Прогон" in row.get("full_name", "")), {})
    check(
        mine_after.get("ielts_current") == ielts_before,
        f"официальный балл не сдвинулся от пробника: было {ielts_before}, стало {mine_after.get('ielts_current')}",
    )

    # куратору раздел пробников файлом закрыт целиком
    code, _ = curator.call("GET", "/api/mock-imports/?group=all")
    check(code == 403, f"куратор открывает список пробников → {code}, ожидали 403")
    code, _ = curator.upload(
        "/api/mock-imports/preview/",
        "probe-own.csv",
        csv_ielts,
        fields={"exam_type": "IELTS", "group": "CHICAGO", "date": mock_date, "teacher": "Учитель прогона"},
    )
    check(code == 403, f"куратор грузит пробник в свою группу → {code}, ожидали 403")

    if mock_id:
        code, page = kymbat63.call("GET", f"/api/mock-imports/{mock_id}/")
        check(code == 200 and "average" in page, f"страница результатов → {code}")
        code, _ = kymbat63.call("GET", f"/api/mock-imports/{mock_id}/file/")
        check(code == 200, f"исходник пробника → {code}")
        code, _ = curator.call("GET", f"/api/mock-imports/{mock_id}/")
        check(code == 403, f"куратор открывает результаты пробника → {code}, ожидали 403")

        # ученику раздел закрыт целиком, и среднего нет ни в одном его ответе
        code, _ = student.call("GET", f"/api/mock-imports/{mock_id}/")
        check(code == 403, f"ученик открывает результаты пробника → {code}, ожидали 403")
        code, _ = student.call("GET", "/api/mock-imports/")
        check(code == 403, f"ученик открывает список пробников → {code}, ожидали 403")
        code, _ = student.call("GET", f"/api/mock-imports/{mock_id}/file/")
        check(code == 403, f"ученик скачивает исходник → {code}, ожидали 403")
        for path in ("/api/students/me/", "/api/attempts/", "/api/portfolio/", "/api/tasks/my/"):
            code, payload = student.call("GET", path)
            text = json.dumps(payload, ensure_ascii=False)
            check("average" not in text, f"{path}: среднего по группе нет")

    # мок-попытку ученик не создаёт и не правит
    code, mine_attempts = student.call("GET", "/api/attempts/?attempt_format=mock&page_size=50")
    rows_ = mine_attempts.get("results", []) if isinstance(mine_attempts, dict) else []
    if rows_:
        first_mock = rows_[0]
        check(first_mock.get("is_mock") is True, "ученик видит пометку «пробник школы»")
        code, _ = student.call("PATCH", f"/api/attempts/{first_mock['id']}/", {"total_score": "9.0"})
        check(code in (403, 404, 405), f"ученик правит мок-попытку → {code}, ожидали отказ")
        code, refused = student.call(
            "POST",
            "/api/suggestions/propose/",
            {
                "rows": [
                    {
                        "model": "students.ExamAttempt",
                        "field": "total_score",
                        "value": "9.0",
                        "object_id": str(first_mock["id"]),
                    }
                ]
            },
        )
        reasons = json.dumps(refused, ensure_ascii=False) if isinstance(refused, dict) else ""
        check(code == 400 and "пробника школы" in reasons, f"ученик предлагает правку пробника → {code}")
    code, _ = student.call("POST", "/api/attempts/", {"student": 0, "exam_type": "IELTS", "attempt_format": "mock"})
    check(code in (403, 400), f"ученик заводит мок-попытку → {code}, ожидали отказ")

    # пробник руками: куратор заводит мок-попытку своему ученику и правит её
    if mine_row.get("id"):
        code, by_hand = curator.call(
            "POST",
            "/api/attempts/",
            {
                "student": mine_row["id"],
                "exam_type": "SAT",
                "attempt_format": "mock",
                "date": mock_date,
                "total_score": "1200",
            },
        )
        check(code == 201 and by_hand.get("is_mock") is True, f"куратор вносит пробник руками → {code}")
        if code == 201:
            code, _ = curator.call("PATCH", f"/api/attempts/{by_hand['id']}/", {"total_score": "1250"})
            check(code == 200, f"куратор правит свой пробник → {code}")
            code, _ = curator.call("DELETE", f"/api/attempts/{by_hand['id']}/")
            check(code in (200, 204), f"куратор убирает свой пробник → {code}")

    code, boss = kymbat.call("GET", "/api/mock-imports/?group=all")
    check(code == 200, f"Кымбат видит пробники всей школы → {code}")
    code, _ = sessions["director_talent"].upload(
        "/api/mock-imports/preview/",
        "probe.csv",
        csv_ielts,
        fields={"exam_type": "IELTS", "group": "CHICAGO", "date": mock_date, "teacher": "Кто-то"},
    )
    check(code == 403, f"чужой директор грузит пробник → {code}, ожидали 403")

    print("\n== Повтор и конфликт — ни одной 500 (фаза 64) ==")
    # вторая цель по тому же экзамену — словами, а не падением (D24)
    for attempt in range(2):
        code, _ = student.call(
            "POST",
            "/api/suggestions/propose/",
            {
                "rows": [
                    {"model": "students.ExamGoal", "field": "exam", "value": "SAT", "new_object_key": "g64"},
                    {"model": "students.ExamGoal", "field": "target_score", "value": "1400", "new_object_key": "g64"},
                ]
            },
        )
        check(code < 500, f"ученик предлагает цель SAT, попытка {attempt + 1} → {code}")
    code, queue = kymbat.call("GET", "/api/suggestions/from-students/")
    goal_rows = [row for row in queue.get("results", []) if any(c.get("field") == "target_score" for c in row.get("changes", []))]
    for row in goal_rows[:2]:
        code, body = kymbat.call("POST", f"/api/suggestions/{row['id']}/review/", {"decision": "confirm"})
        check(code < 500, f"Кымбат подтверждает цель → {code} (повтор отклоняется словами, не 500)")
    # балл вне шкалы — отказ при подаче (D4, D17)
    code, refused = student.call(
        "POST",
        "/api/suggestions/propose/",
        {"rows": [{"model": "students.ExamProfile", "field": "ielts_current", "value": "12.5"}]},
    )
    check(code == 400 and "шкала" in json.dumps(refused, ensure_ascii=False).lower(), f"IELTS 12.5 отбит со шкалой → {code}")
    # повтор задачи по шаблону — 400 словами (D35)
    code, templates = sessions["director_behavior"].call("GET", "/api/task-templates/")
    # список бывает и объектом со строками, и голым списком, и пустым:
    # на чистой базе шаблонов нет вовсе, и обращение по индексу роняло прогон
    rows_tpl = templates.get("results") if isinstance(templates, dict) else templates
    tpl = rows_tpl[0] if isinstance(rows_tpl, list) and rows_tpl else {}
    if isinstance(tpl, dict) and tpl.get("id") and my_ids:
        body = {"student": my_ids[0], "title": tpl.get("title", "Задача"), "category": tpl.get("category", "documents"), "template": tpl["id"]}
        first, _ = sessions["director_behavior"].call("POST", "/api/tasks/", body)
        second, answer = sessions["director_behavior"].call("POST", "/api/tasks/", body)
        check(first < 500 and second == 400, f"повтор задачи по шаблону → {first}, затем {second} (ожидали 400)")
    # ученик пишет дважды одно и то же — документ, эссе, контакт, ответ анкеты
    for path, payload in (
        ("/api/essays/", {"title": "Эссе прогона 64", "essay_type": "personal_statement"}),
        ("/api/essays/", {"title": "Эссе прогона 64", "essay_type": "personal_statement"}),
    ):
        code, _ = student.call("POST", path, payload)
        check(code < 500, f"POST {path} повтором → {code}")

    print("\n== Фоновые операции и замки (фаза 47) ==")
    code, mine_jobs = student.call("GET", "/api/jobs/")
    check(code == 200 and isinstance(mine_jobs, dict), f"список фоновых операций → {code}")
    code, locks = student.call("GET", "/api/journey/locks/")
    rows_ = locks.get("locks", []) if isinstance(locks, dict) else []
    check(code == 200 and len(rows_) >= 2, f"замки разделов у ученика → {code}, штук {len(rows_)}")
    check(
        all(row.get("reason") and row.get("action") for row in rows_),
        "у каждого замка есть причина словами и следующий шаг",
    )
    code, staff_locks = sessions["director_exam"].call("GET", "/api/journey/locks/")
    check(
        code == 200 and staff_locks.get("locks") == [],
        "у сотрудника замков нет: его разделы закрыты доменом, а не шагом",
    )

    # долгая операция заводит плашку и уходит в фон
    code, started = sessions["director_exam"].call(
        "POST", "/api/commands/paste/", {"text": "IELTS 7.0", "command": "paste_as_is"}
    )
    check(code == 202, f"разбор текста уходит в фон → {code}")
    import time as _t

    seen = None
    for _ in range(15):
        code, listing = sessions["director_exam"].call("GET", "/api/jobs/")
        rows_ = listing.get("results", []) if isinstance(listing, dict) else []
        if rows_:
            seen = rows_[0]
            break
        _t.sleep(1)
    if seen is not None:
        check(bool(seen.get("title")), f"у операции есть название: «{seen.get('title')}»")
        code, _ = sessions["director_exam"].call("POST", f"/api/jobs/{seen['id']}/dismiss/")
        check(code == 200, f"плашка прячется крестиком → {code}")
    else:
        # операция успела закончиться раньше опроса — тогда о ней сказал колокольчик
        code, notes = sessions["director_exam"].call("GET", "/api/notifications/")
        rows_ = notes.get("results", []) if isinstance(notes, dict) else (notes if isinstance(notes, list) else [])
        check(
            any("готово" in str(row.get("text", "")) for row in rows_),
            "об окончании операции сказал колокольчик",
        )

    print("\n== Пароли учеников и таблица поступления (фаза 65) ==")
    # пароль ученика — единственные данные, открывающие чужой аккаунт:
    # проверяем не «работает ли показ», а «нет ли пароля где-то ещё»
    asem = sessions["director_admission"]
    curator65 = sessions["curator"]
    code, mine65 = curator65.call("GET", "/api/students/?page_size=500")
    curated = mine65.get("results", []) if isinstance(mine65, dict) else []
    if curated:
        victim = curated[0]["id"]
        secret65 = "Probe-Parol-65"
        code, _ = asem.call(
            "POST", f"/api/students/{victim}/credentials/set/", {"kind": "email", "password": secret65}
        )
        check(code == 200, f"Асем записывает пароль ученика → {code}")

        code, state65 = curator65.call("GET", f"/api/students/{victim}/credentials/")
        check(code == 200, f"куратор видит «есть / нет» по паролям → {code}")
        check(secret65 not in json.dumps(state65, ensure_ascii=False), "в состоянии паролей нет самого пароля")

        # обход ответов: пароля нет нигде, кроме одного маршрута
        leaked = []
        for role_name, session65 in sessions.items():
            for path65 in (
                f"/api/students/{victim}/",
                "/api/students/?page_size=500",
                f"/api/curator/students/{victim}/",
                "/api/curator/students/",
                f"/api/profiles/admission/{victim}/",
                f"/api/students/{victim}/history/",
                "/api/suggestions/",
                f"/api/documents/?student={victim}",
            ):
                code, body65 = session65.call("GET", path65)
                if code >= 400:
                    continue
                if secret65 in json.dumps(body65, ensure_ascii=False):
                    leaked.append(f"{role_name} {path65}")
        check(not leaked, f"пароль не встречается в ответах API: {leaked[:3]}")

        # показ работает и пишет журнал
        code, before65 = asem.call("GET", f"/api/students/{victim}/history/")
        rows_before = before65 if isinstance(before65, list) else before65.get("results", [])
        seen_before = sum(1 for row in rows_before if "Показан пароль" in str(row.get("field_title", "")))
        code, shown65 = asem.call("POST", f"/api/students/{victim}/credentials/reveal/", {"kind": "email"})
        check(code == 200 and shown65.get("password") == secret65, f"показ отдаёт пароль → {code}")
        code, after65 = asem.call("GET", f"/api/students/{victim}/history/")
        rows_after = after65 if isinstance(after65, list) else after65.get("results", [])
        seen_after = sum(1 for row in rows_after if "Показан пароль" in str(row.get("field_title", "")))
        check(seen_after == seen_before + 1, "каждый показ пишется в журнал ученика")

        # пароль видят все пять директоров — так записано в реестре
        # (`CREDENTIAL_VIEWERS`): решение владельца, а не случайность
        code, _ = sessions["director_sport"].call(
            "POST", f"/api/students/{victim}/credentials/reveal/", {"kind": "email"}
        )
        check(code == 200, f"директор из списка реестра показывает пароль → {code}")
        # а чужой ученик — нет: ему чужая карточка не видна вовсе
        code, _ = student.call("POST", f"/api/students/{victim}/credentials/reveal/", {"kind": "email"})
        check(code == 404, f"ученик показывает чужой пароль → {code}, ожидали 404")
        code, _ = student.call("GET", f"/api/students/{victim}/credentials/")
        check(code == 404, f"ученик смотрит чужие пароли → {code}, ожидали 404")

    # ученик правит блок «Поступление» только через очередь
    code, _ = student.call("PATCH", f"/api/profiles/admission/{my_id}/", {"student_phone": "+77010000000"})
    check(code in (403, 404, 405), f"ученик правит блок напрямую → {code}, ожидали отказ")
    code, proposed65 = student.call(
        "POST",
        "/api/suggestions/propose/",
        {"rows": [{"model": "students.AdmissionProfile", "field": "student_phone", "value": "+77010000000"}]},
    )
    check(code < 400, f"ученик предлагает свой телефон очередью → {code}")

    # мастер импорта открыт администратору и академическому директору;
    # остальные директора и ученик — отказ словами, куратору мастера нет вовсе
    refusal65 = "Файлы загружают администратор и академический директор"
    code, _ = student.call("GET", "/api/admission-imports/")
    check(code == 403, f"ученик у мастера импорта → {code}, ожидали 403")
    for role_name in ("admin", "director_exam"):
        code, _ = sessions[role_name].call("GET", "/api/admission-imports/")
        check(code == 200, f"{role_name} видит загрузки мастера → {code}")
    for role_name in ("director_admission", "director_behavior", "director_talent", "director_sport"):
        code, body = sessions[role_name].call("GET", "/api/admission-imports/")
        check(code == 403, f"{role_name} у мастера импорта → {code}, ожидали 403")
        check(
            refusal65 in json.dumps(body, ensure_ascii=False),
            f"{role_name}: отказ объяснён словами",
        )
        code, _ = sessions[role_name].call("GET", "/api/admission-imports/template/")
        check(code == 403, f"{role_name} качает шаблон мастера → {code}, ожидали 403")
        for step in ("preview", "apply"):
            code, _ = sessions[role_name].call("POST", f"/api/admission-imports/{step}/", {})
            check(code == 403, f"{role_name}: {step} мастера → {code}, ожидали 403")
    for path in ("/api/admission-imports/", "/api/admission-imports/template/"):
        code, _ = sessions["curator"].call("GET", path)
        check(code == 404, f"куратор: GET {path} → {code}, ожидали 404")
    for step in ("preview", "apply"):
        code, _ = sessions["curator"].call("POST", f"/api/admission-imports/{step}/", {})
        check(code == 404, f"куратор: {step} мастера → {code}, ожидали 404")

    print("\n== Дисциплина у куратора (фаза 66) ==")
    saltanat = sessions["director_behavior"]
    curator66 = sessions["curator"]
    code, mine66 = curator66.call("GET", "/api/students/?page_size=500")
    curated66 = mine66.get("results", []) if isinstance(mine66, dict) else []
    code, all66 = admin.call("GET", "/api/students/?page_size=500")
    everyone66 = all66.get("results", []) if isinstance(all66, dict) else []
    mine_ids = {row["id"] for row in curated66}
    foreign = next((row for row in everyone66 if row["id"] not in mine_ids), None)

    if curated66:
        target = curated66[0]
        code, sheet = curator66.call("GET", f"/api/attendance/?group={target.get('group')}&date={_dt.date.today()}")
        check(code in (200, 404), f"куратор открывает лист посещаемости → {code}")

        # отметка дня закрыта: посещаемость ведётся по урокам, лист дня — на чтение
        check(isinstance(sheet, dict) and sheet.get("may_mark") is False, "лист дня у куратора на чтение")
        code, groups66 = curator66.call("GET", "/api/attendance/")
        rows66 = groups66.get("groups", []) if isinstance(groups66, dict) else []
        if rows66:
            gid = rows66[0]["id"]
            code, _ = curator66.call(
                "POST",
                "/api/attendance/save/",
                {
                    "group": gid,
                    "date": str(_dt.date.today()),
                    "rows": [{"student": target["id"], "present": False, "reason": "проба"}],
                },
            )
            check(code == 403, f"куратор отмечает день → {code}, ожидали 403: посещаемость по урокам")
            code, by_lessons = curator66.call("GET", f"/api/acad/attendance/?group={target.get('group')}")
            check(code == 200 and "rows" in by_lessons, f"посещаемость по урокам своей группы → {code}")
            code, card66 = curator66.call("GET", f"/api/curator/students/{target['id']}/")
            block = card66.get("behavior", {}) if isinstance(card66, dict) else {}
            check("attendance_lessons" in block, "посещаемость в карточке считается по урокам")
            check(block.get("may_write") is True, "куратор вправе вести дисциплину своей группы")

        # замечание словами
        code, made66 = curator66.call(
            "POST", f"/api/students/{target['id']}/remarks/", {"text": "Проба пера: замечание"}
        )
        check(code == 201, f"куратор пишет замечание → {code}")
        code, listed = curator66.call("GET", f"/api/students/{target['id']}/remarks/")
        check(
            any("Проба пера" in str(row.get("text")) for row in listed.get("rows", [])),
            "замечание видно словами, а не счётчиком",
        )

    # чужая группа куратору закрыта
    if foreign is not None:
        code, _ = curator66.call(
            "POST",
            "/api/attendance/save/",
            {
                "group": foreign.get("group"),
                "date": str(_dt.date.today()),
                "rows": [{"student": foreign["id"], "present": False}],
            },
        )
        check(code == 403, f"куратор пишет отметку дня чужой группы → {code}, ожидали 403")
        code, _ = curator66.call("GET", f"/api/acad/attendance/?group={foreign.get('group')}")
        check(code == 404, f"посещаемость по урокам чужой группы → {code}, ожидали 404")
        code, _ = curator66.call("POST", f"/api/students/{foreign['id']}/remarks/", {"text": "чужому"})
        check(code == 404, f"куратор пишет замечание чужому → {code}, ожидали 404")

        # Салтанат ведёт любого
        code, groups_all = saltanat.call("GET", "/api/attendance/")
        rows_all = groups_all.get("groups", []) if isinstance(groups_all, dict) else []
        if rows_all:
            code, _ = saltanat.call(
                "POST",
                "/api/attendance/save/",
                {
                    "group": foreign.get("group"),
                    "date": str(_dt.date.today()),
                    "rows": [{"student": foreign["id"], "present": True}],
                },
            )
            # отметка дня закрыта всем; директор школы читает лист и журнал
            check(code == 403, f"директор школы отметку дня не вносит → {code}, ожидали 403")
            code, sheet = saltanat.call("GET", f"/api/attendance/?group={foreign.get('group')}")
            check(code == 200 and sheet.get("may_mark") is False, f"лист директору школы — на чтение → {code}")
            code, journal = saltanat.call("GET", f"/api/attendance/journal/?group={foreign.get('group')}")
            check(code == 200 and "rows" in journal, f"журнал за месяц у директора школы → {code}, ожидали 200")
            code, preview = saltanat.call(
                "GET", f"/api/attendance/journal/export/?group={foreign.get('group')}&preview=1"
            )
            check(
                code == 200 and preview.get("sheets", [{}])[0].get("columns", [""])[0] == "Ученик",
                f"предпросмотр выгрузки журнала → {code}",
            )

    # ученик посещаемость не правит и замечаний не видит
    code, _ = student.call("GET", "/api/attendance/")
    check(code == 403, f"ученик открывает посещаемость → {code}, ожидали 403")
    if my_id:
        code, _ = student.call("GET", f"/api/students/{my_id}/remarks/")
        check(code == 403, f"ученик читает свои замечания → {code}, ожидали 403")
        code, _ = student.call(
            "POST",
            "/api/attendance/save/",
            {"group": 1, "date": str(_dt.date.today()), "rows": []},
        )
        check(code == 403, f"ученик пишет посещаемость → {code}, ожидали 403")

    # писем в продукте нет (27.09.2026): адреса закрыты и куратору, и администратору
    code, _ = curator66.call("POST", "/api/letters/compose/", {"students": []})
    # шлюз куратора отвечает 403 раньше, чем Django скажет 404 о снятом адресе
    check(code in (403, 404), f"заготовка письма закрыта → {code}, ожидали 403 или 404")
    code, _ = admin.call("GET", "/api/letters/templates/")
    check(code == 404, f"шаблоны писем закрыты → {code}, ожидали 404")

    print("\n== Правка учётной записи и удаление навсегда (фаза 67) ==")
    # правку и удаление ведёт администратор; остальным закрыто наглухо
    code, users67 = admin.call("GET", "/api/users/")
    rows67 = users67 if isinstance(users67, list) else users67.get("results", [])
    victim = next((r for r in rows67 if str(r.get("email", "")).endswith("@probe.local")), None)

    if victim is not None:
        code, edited = admin.call("PATCH", f"/api/users/{victim['id']}/", {"full_name": "Проба Правки"})
        check(code == 200, f"администратор правит ФИО → {code}")
        check(edited.get("full_name") == "Проба Правки", "новое имя вернулось в ответе")

        # занятая почта — отказ словами, а не пятисотка
        other = next((r for r in rows67 if r["id"] != victim["id"]), None)
        if other is not None:
            code, refused = admin.call("PATCH", f"/api/users/{victim['id']}/", {"email": other["email"]})
            check(code == 400, f"занятая почта → {code}, ожидали 400")
            check("занята" in str(refused.get("detail", "")), "отказ объясняет причину словами")

        # чужим ролям правка закрыта
        for role in ("director_exam", "curator", "student"):
            if role in sessions:
                code, _ = sessions[role].call("PATCH", f"/api/users/{victim['id']}/", {"full_name": "Чужая"})
                check(code == 403, f"{role} правит чужую запись → {code}, ожидали 403")

    # предпросмотр удаления: числа есть, содержимого нет
    code, archive67 = admin.call("GET", "/api/archive/?restored=false")
    entries = archive67 if isinstance(archive67, list) else archive67.get("results", [])
    entry = entries[0] if entries else None
    if entry is not None:
        code, shown = admin.call("GET", f"/api/archive/{entry['id']}/purge/")
        check(code == 200, f"предпросмотр удаления открывается → {code}")
        body = json.dumps(shown, ensure_ascii=False)
        check("confirm" in shown, "предпросмотр говорит, чем подтверждать")
        check("ciphertext" not in body, "шифртекст пароля в предпросмотре не появляется")
        # у строк предпросмотра только название вида, число и размер: содержимого
        # записей там нет. «Заметки куратора» — это имя вида, а не текст заметки
        allowed = {"title", "count", "note"}
        leaked = [key for row in shown.get("erased", []) for key in row if key not in allowed]
        check(not leaked, f"в предпросмотре только числа, а не содержимое: лишние поля {leaked}")
        for row in shown.get("erased", []):
            check(isinstance(row.get("count"), int), f"«{row.get('title')}» — число, а не текст")

        # удаление закрыто всем, кроме администратора
        for role in ("director_behavior", "curator", "student"):
            if role in sessions:
                code, _ = sessions[role].call("POST", f"/api/archive/{entry['id']}/purge/", {"confirm": "УДАЛИТЬ"})
                check(code == 403, f"{role} удаляет навсегда → {code}, ожидали 403")

        # одной кнопки мало: без осмысленного ввода отказ
        code, _ = admin.call("POST", f"/api/archive/{entry['id']}/purge/", {"confirm": "да"})
        check(code == 400, f"удаление без подтверждения → {code}, ожидали 400")

    print("\n== Администратор во всех доменах, блок по таблице (фаза 68) ==")
    code, some = admin.call("GET", "/api/students/?page_size=1")
    first = (some.get("results") or [None])[0] if isinstance(some, dict) else None
    if first is not None:
        sid = first["id"]
        # правка в чужом домене проходит и помечена в журнале
        code, _ = admin.call("PATCH", f"/api/profiles/exam/{sid}/", {"ielts_target": "7.0"})
        check(code == 200, f"администратор правит домен экзаменов → {code}")
        code, _ = admin.call("PATCH", f"/api/profiles/sport/{sid}/", {"rank": "проба"})
        check(code == 200, f"администратор правит домен спорта → {code}")
        code, history = admin.call("GET", f"/api/students/{sid}/history/")
        rows_h = history if isinstance(history, list) else history.get("results", [])
        check(
            any("правил администратор" in str(r.get("acting_for_title", "")) for r in rows_h),
            "в журнале стоит «правил администратор»",
        )
        # реестр отдаёт администратору все домены как свои
        code, meta = admin.call("GET", "/api/meta/domains/")
        check(all(d.get("is_mine") for d in meta.get("domains", [])), "все домены помечены «мои» у администратора")
        # блок «Поступление» — ровно таблица: целей и служебных признаков в нём нет
        admission_meta = next((d for d in meta.get("domains", []) if d["code"] == "admission"), {})
        fields = [f for m in admission_meta.get("models", []) if m.get("is_profile") for f in m["fields"]]
        main = {f["name"] for f in fields if f.get("card") == "main"}
        # состав блока равен колонкам таблицы Асем: с фазы 70 в нём личная
        # почта, с 71-й — срок паспорта (проверка обновлена в 77-й)
        check(
            main == {"student_phone", "personal_email", "common_app_email", "drive_folder_url", "passport_expires_at"},
            f"поля блока: {sorted(main)}",
        )
        check(
            all(f["name"] not in main for f in fields if f["name"] in ("target_country", "status", "has_common_app")),
            "цели и служебные признаки из блока ушли",
        )
        # первичные данные за ученика — нет
        code, refused = admin.call(
            "POST",
            "/api/suggestions/propose/",
            {"rows": [{"model": "students.ExamProfile", "field": "ielts_current", "value": "7.0"}]},
        )
        check(code == 403, f"администратор предлагает за ученика → {code}, ожидали 403")
        check("вносит ученик" in str(refused.get("detail", "")), "отказ объясняет границу словами")
        code, _ = admin.call("GET", "/api/notes/")
        check(code == 200, f"администратор читает заметки → {code}")
        # права остальных не изменились
        code, _ = sessions["director_exam"].call("PATCH", f"/api/profiles/admission/{sid}/", {"target_country": "x"})
        check(code == 403, f"директор экзаменов правит поступление → {code}, ожидали 403")
        code, _ = student.call("PATCH", f"/api/profiles/exam/{sid}/", {"ielts_target": "8.0"})
        check(code in (403, 404), f"ученик правит домен → {code}")

    print("\n== Экран «Пользователи»: фильтры и раздача паролей (фаза 69) ==")
    code, page69 = admin.call("GET", "/api/users/")
    rows69 = page69.get("results", []) if isinstance(page69, dict) else []
    check(code == 200 and isinstance(page69, dict), f"список отдаёт строки и счётчики → {code}")
    check("counts" in page69 and "states" in page69, "в ответе есть счётчики и набор чипов")
    chips = [c["code"] for c in page69.get("states", [])]
    check(chips == ["no_password", "waiting", "expired", "ready"], f"чипы по состоянию пароля: {chips}")
    check(all("password_state" in r for r in rows69), "у каждой строки есть состояние пароля")

    # счётчик чипа сходится с числом строк под ним
    for chip in chips:
        code, filtered = admin.call("GET", f"/api/users/?state={chip}")
        got = len(filtered.get("results", [])) if isinstance(filtered, dict) else -1
        check(got == page69["counts"].get(chip), f"чип «{chip}»: строк {got}, счётчик {page69['counts'].get(chip)}")

    # предпросмотр раздачи: числа есть, пароли — нет
    code, plan69 = admin.call("POST", "/api/users/handout/", {})
    check(code == 200, f"предпросмотр раздачи открывается → {code}")
    check(isinstance(plan69.get("total"), int), "предпросмотр говорит, скольких затронет")
    check(plan69.get("confirm") == str(plan69.get("total")), "подтверждение — набранное число затронутых")
    ready69 = next((r for r in plan69.get("breakdown", []) if r["code"] == "ready"), {})
    check(plan69.get("protected") == ready69.get("count", 0), "те, у кого пароль задан, по умолчанию исключены")
    # предпросмотр ничего не выпускает: строк с паролями в нём нет вовсе.
    # Ищем именно поле, а не подстроку: коды состояний сами зовутся
    # «no_password», и поиск по тексту всегда находил бы их
    def _carries_password(payload) -> bool:
        if isinstance(payload, dict):
            return "password" in payload or any(_carries_password(value) for value in payload.values())
        if isinstance(payload, list):
            return any(_carries_password(value) for value in payload)
        return False

    check(not _carries_password(plan69), "паролей в предпросмотре нет")
    check(not plan69.get("rows") and not plan69.get("issued"), "предпросмотр ничего не выдал")

    # без набранного числа выдача не проходит
    code, refused69 = admin.call("POST", "/api/users/handout/", {"confirm": "да"})
    check(code == 400, f"раздача без подтверждения → {code}, ожидали 400")
    check("Наберите число" in str(refused69.get("detail", "")), "отказ называет, что набрать")

    # раздача закрыта всем, кроме администратора
    for role in ("director_behavior", "curator", "student"):
        if role in sessions:
            code, _ = sessions[role].call("POST", "/api/users/handout/", {})
            check(code == 403, f"{role} раздаёт пароли → {code}, ожидали 403")

    print("\n== Карточка по таблице, вузы и контакты (фаза 70) ==")
    # берём ученика куратора: блок сверяется у трёх ролей, а контакт
    # заводит куратор — чужого ученика он не видит вовсе
    target70 = my_ids[0] if my_ids else contact_target
    code, card70 = admin.call("GET", f"/api/students/{target70}/")
    block70 = card70.get("admission_block") if isinstance(card70, dict) else None
    check(code == 200 and isinstance(block70, dict), f"блок «Поступление» приходит в карточке → {code}")
    if isinstance(block70, dict):
        need = {"student_phone", "email", "common_app_email", "drive_folder_url", "gpa", "credentials", "attempts", "documents"}
        check(need <= set(block70), f"состав блока: не хватает {sorted(need - set(block70))}")
        check([s["exam"] for s in block70.get("attempts", [])] == ["IELTS", "SAT"], "попытки разложены по экзаменам")
        check(all(s["slots"] == 3 for s in block70.get("attempts", [])), "по три слота на экзамен, как колонок в таблице")
        check("password" not in json.dumps(block70, ensure_ascii=False), "паролей в блоке нет — только «есть / нет»")

    # тот же блок у куратора: один состав на все роли
    if "curator" in sessions:
        code, mine70 = sessions["curator"].call("GET", f"/api/curator/students/{target70}/")
        if code == 200 and isinstance(block70, dict):
            check(set(mine70.get("admission", {})) == set(block70), "блок у куратора и у администратора одного состава")

    # целей в карточке нет ни у кого: их нет в таблице
    code, meta70 = admin.call("GET", "/api/meta/domains/")
    cards70 = set()
    if isinstance(meta70, dict):
        for domain in meta70.get("domains", []):
            for model in domain.get("models", []):
                cards70 |= {f.get("card") for f in model.get("fields", [])}
    check(cards70 <= {"main", "none"}, f"раскладка карточки знает два значения: {sorted(cards70)}")

    # контакты заводит куратор своей группы
    if "curator" in sessions:
        code, made70 = sessions["curator"].call(
            "POST",
            "/api/contacts/",
            {
                "student": target70,
                "full_name": "Прогон Родителев",
                "relation": "mother",
                "phone": "+77070000070",
                "email": "",
                "preferred_channel": "",
                "note": "",
                "is_primary": False,
            },
        )
        check(code == 201, f"куратор заводит контакт → {code}")
        if code == 201 and isinstance(made70, dict):
            code, _ = sessions["curator"].call("DELETE", f"/api/contacts/{made70['id']}/")
            check(code in (200, 204), f"и убирает его → {code}")

    print("\n== Ученик 8–10 без почты: вход логином, поступления нет ==")
    # карточку 8–10 заводит посев прогона; запись probe_junior живёт от прогона
    # до прогона, поэтому связываем их здесь, по логину — как это делает посев
    from urllib.parse import quote

    code, found = sessions["admin"].call("GET", f"/api/students/?search={quote('Ерлан')}&parallel=9")
    card_row = next(
        (row for row in (found.get("results", []) if isinstance(found, dict) else []) if row["full_name"] == "Прогон Ерлан"),
        None,
    )
    check(card_row is not None, "карточка ученика 8–10 посева на месте")
    if card_row is not None:
        code, _ = sessions["admin"].call("PATCH", f"/api/students/{card_row['id']}/", {"login": "probe_junior"})
        check(code == 200, f"карточка связывается с логином → {code}")
    junior = login_as("probe_junior", _password(ACCOUNTS["student"][1]))
    check(junior is not None, "ученик 8–10 входит логином probe_junior")
    if junior is not None:
        code, me = junior.call("GET", "/api/auth/me/")
        check(code == 200 and isinstance(me, dict) and me.get("has_admission") is False, "у 8–10 поступления нет")
        for path in ("/api/catalog/", "/api/student-universities/", "/api/portfolio/", "/api/tasks/", "/api/career/"):
            code, body = junior.call("GET", path)
            check(
                code == 403 and isinstance(body, dict) and body.get("code") == "parallel_closed",
                f"8–10: {path} → {code}, ожидали 403 parallel_closed",
            )
        code, card = junior.call("GET", "/api/students/me/")
        check(
            code == 200 and isinstance(card, dict) and "admission" not in card and "exam" not in card,
            "8–10: в своей карточке нет поступления и экзаменов",
        )
        code, _ = junior.call("GET", "/api/acad/me/home/")
        check(code == 200, f"8–10: главная про учёбу → {code}")
        check(not find_internal(card), "8–10: внутренних ярлыков в своей карточке нет")

    print(f"\nИтог: дефектов {len(FAILS)}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
