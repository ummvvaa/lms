/**
 * Фаза 53 — D27 в живом браузере.
 *
 * Справочник правил обзвона закрыт всем, кроме владельца домена
 * «Профиль и дисциплина». В pytest это проверено по статусам, здесь —
 * то, чего оттуда не видно: экран Салтанат работает как работал, а
 * ученик не получает формулировок ни через адрес, ни через сырой ответ
 * API из своей же сессии (инвариант №7 один раз уже ломался именно так —
 * в ответе API, оставаясь исправным на вид).
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { apiPost } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 120_000 });

/** Фраза, которой школа описывает ученика: её он видеть не должен. */
const REASON = "проба 53: просел по пробным экзаменам";

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

/** CSRF-заголовок сессии: без него отказ пришёл бы не от прав, а от Django. */
async function csrf(page: Page): Promise<Record<string, string>> {
  const cookie = (await page.context().cookies()).find(
    (c) => c.name === "csrftoken",
  );
  return { "X-CSRFToken": cookie?.value ?? "" };
}

test("правила обзвона: экран владельца работает, ученику закрыт", async ({
  browser,
}) => {
  const owner = await as(browser, "director_behavior");
  await owner.goto("/dashboard");

  // условия ставит сам сценарий: полагаться на то, что оставили соседние,
  // нельзя — правило могло не дожить до этой проверки
  const rule = await apiPost<{ id: number }>(owner, "/api/call-rules/", {
    code: `probe53_${Date.now()}`,
    condition: "inactive",
    reason: REASON,
    urgency: "today",
    threshold: 21,
  });

  // экран владельца: строка на месте, ничего не изменилось
  await owner.goto("/call-rules");
  await expect(owner.locator("h1")).toContainText("Правила обзвона");
  await expect(owner.locator("table.tbl")).toContainText(REASON);

  const student = await as(browser, "student");

  // прямой адрес уводит на свою главную — раздел чужого домена
  await student.goto("/call-rules");
  await expect(student).toHaveURL(/\/dashboard$/);
  await expect(student.locator("body")).not.toContainText(REASON);

  // сырой ответ из сессии ученика: отказ, а не пустой список
  for (const path of ["/api/call-rules/", `/api/call-rules/${rule.id}/`]) {
    const response = await student.request.get(path);
    expect(response.status(), `${path} у ученика`).toBe(403);
    expect(
      await response.text(),
      `${path}: формулировка правила`,
    ).not.toContain(REASON);
  }

  // и запись, и удаление — тот же отказ
  const headers = await csrf(student);
  const patched = await student.request.patch(`/api/call-rules/${rule.id}/`, {
    data: { threshold: 1 },
    headers,
  });
  expect(patched.status(), "ученик правит правило").toBe(403);
  const removed = await student.request.delete(`/api/call-rules/${rule.id}/`, {
    headers,
  });
  expect(removed.status(), "ученик удаляет правило").toBe(403);

  // карусель главной ученику по-прежнему открыта: правка не про неё
  const cues = await student.request.get("/api/home/cues/");
  expect(cues.status(), "сюжеты карусели у ученика").toBe(200);

  // уборка: правило прогона снимает тот, кто его завёл
  const cleaned = await owner.request.delete(`/api/call-rules/${rule.id}/`, {
    headers: await csrf(owner),
  });
  expect(cleaned.status(), "правило прогона удалено").toBe(204);
  await owner.context().close();
  await student.context().close();
});
