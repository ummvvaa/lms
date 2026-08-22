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
        raise SystemExit(f"Не задана переменная {name}. Возьмите её из deploy/.env")
    return value


ACCOUNTS = {
    "student": ("test.student@lms.local", "DEV_STUDENT_PASSWORD"),
    "director_behavior": ("test.behavior@lms.local", "DEV_BEHAVIOR_PASSWORD"),
    "director_admission": ("test.admission@lms.local", "DEV_ADMISSION_PASSWORD"),
    "director_exam": ("test.exam@lms.local", "DEV_EXAM_PASSWORD"),
    "director_talent": ("test.talent@lms.local", "DEV_TALENT_PASSWORD"),
    "director_sport": ("test.sport@lms.local", "DEV_SPORT_PASSWORD"),
    "admin": ("test.admin@lms.local", "DEV_ADMIN_PASSWORD"),
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
    for path in ("/api/students/me/", "/api/meta/domains/", "/api/match/my-universities/", "/api/tasks/my/"):
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

    print("\n== Директора: чужой домен ==")
    code, payload = sessions["director_exam"].call("GET", "/api/students/?page_size=1")
    target = payload["results"][0]["id"] if isinstance(payload, dict) and payload.get("results") else None
    if target:
        cases = [
            ("director_exam", "behavior", {"attendance_percent": 50}),
            ("director_behavior", "exam", {"ielts_current": "8.0"}),
            ("director_sport", "talent", {"main_track": "research"}),
            ("director_talent", "sport", {"sport_kind": "Бокс"}),
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

    print(f"\nИтог: дефектов {len(FAILS)}")
    for item in FAILS:
        print(f"  - {item}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
