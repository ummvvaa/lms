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
                return response.status, (json.loads(raw) if raw else None)
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

    print(f"\nИтог: дефектов {len(FAILS)}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
