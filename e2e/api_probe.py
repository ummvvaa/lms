#!/usr/bin/env python3
"""Прогон API под каждой ролью — сырой JSON ловит то, чего не видно в интерфейсе.

Проверяет:
* чтение и запись чужого домена;
* доступ ученика к дашбордам директоров и чужим профилям;
* наличие внутренних ярлыков в ответах для роли `student` (инвариант №7).

Запуск: python3 e2e/api_probe.py [база]   (по умолчанию http://localhost:8000)
"""

from __future__ import annotations

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

    def upload(self, path: str, filename: str, payload: bytes) -> tuple[int, object]:
        """Настоящая multipart-загрузка: JSON-тело такие ручки не принимают вовсе."""
        boundary = "----probe-boundary"
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: text/csv\r\n\r\n"
        ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
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
    session = Session()
    session.call("GET", "/api/auth/me/")  # получаем csrftoken
    code, _ = session.call("POST", LOGIN_PATH, {"email": email, "password": _password(var)})
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

    code, question = sessions["director_exam"].call(
        "POST",
        "/api/prep/questions/",
        {
            "exam_type": "IELTS",
            "section": "reading",
            "topic": "Проверка",
            "difficulty": "medium",
            "text": "Текст",
            "options": [{"letter": "A", "text": "Да", "is_correct": True}],
        },
    )
    check(code == 201, f"академический директор заводит задание → {code}, ожидали 201")
    if isinstance(question, dict) and question.get("id"):
        code, _ = sessions["director_talent"].call(
            "PATCH", f"/api/prep/questions/{question['id']}/", {"topic": "Чужое"}
        )
        check(code == 403, f"чужой директор правит банк → {code}, ожидали 403")
        code, _ = sessions["director_exam"].call("DELETE", f"/api/prep/questions/{question['id']}/")
        check(code == 200, f"удаление задания владельцем → {code}, ожидали 200")

    print("\n== Реестровая карточка: правит администратор (фаза 30) ==")
    if contact_target:
        code, _ = sessions["admin"].call("PATCH", f"/api/students/{contact_target}/", {"grade": 11})
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
    # сотрудникам его нет вовсе — ни списка, ни очереди проверки
    for role in ("director_behavior", "director_admission", "director_exam", "director_sport", "admin"):
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
        code, _ = sessions["admin"].call("POST", f"/api/suggestions/{proposal}/review/", {"decision": "confirm"})
        check(code == 403, f"администратор подтверждает за владельца → {code}, ожидали 403")

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
    code, kinds = student.call("GET", "/api/exam-kinds/")
    names = {row.get("name") for row in kinds.get("results", [])} if isinstance(kinds, dict) else set()
    check(code == 200 and "ЕНТ" in names, f"справочник экзаменов → {code}, ЕНТ в списке: {'ЕНТ' in names}")

    code, body = student.call("GET", "/api/calendar/")
    check(
        code == 200 and isinstance(body, dict) and "events" in body and "nearest" in body,
        f"календарь ученика → {code}",
    )
    code, _ = sessions["director_exam"].call("GET", "/api/calendar/")
    check(code == 403, f"календарь у директора → {code}, ожидали 403")

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
    seven = isinstance(exams, dict) and len(exams.get("exams", [])) == 7
    check(code == 200 and seven, f"семь плиток экзаменов → {code}")
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
    code, _ = sessions["director_exam"].call("POST", "/api/career-questions/", {"code": "x", "text": "X"})
    check(code == 403, f"чужой директор правит анкету → {code}, ожидали 403")

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

    print(f"\nИтог: дефектов {len(FAILS)}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
