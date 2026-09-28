/**
 * Пользователи с панелями и ролью «Учитель»; архив с удалённым уроком
 * и «Вернуть». Заведённое сценарием убирается им же.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { daysAgo, lessonsBetween } from "../helpers/academics";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { apiPost, watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  return page;
}

const TEACHER = probeEmail("teacher-panel");

test("пользователи: учитель заводится в панели, фильтр по роли, пароль выдаётся", async ({ browser }) => {
  const admin = await as(browser, "admin");
  const diag = watch(admin);
  await admin.goto("/users");
  await expect(admin.locator("h1")).toContainText("Пользователи");
  // блокировки — под таблицей; учебные группы — своей вкладкой (27.09.2026)
  await expect(admin.locator(".datacard", { hasText: "Блокировки" }).first()).toBeVisible();
  await admin.getByRole("tab", { name: "Учебные группы" }).click();
  await expect(admin.locator(".datacard", { hasText: "Учебные группы" }).first()).toBeVisible();
  await admin.getByRole("tab", { name: "Учётные записи" }).click();

  await admin.getByRole("button", { name: "Завести пользователя" }).click();
  const panel = admin.locator(".drawer");
  await expect(panel).toContainText("Новая учётная запись");
  await panel.getByLabel("Почта").fill(TEACHER);
  await panel.getByLabel("ФИО").fill("Прогон Учитель Панельный");
  await panel.getByLabel("Роль").selectOption("teacher");
  const created = admin.waitForResponse(
    (r) => r.url().endsWith("/api/users/") && r.request().method() === "POST",
  );
  await panel.getByRole("button", { name: "Завести и пригласить" }).click();
  expect((await created).status()).toBe(201);
  await expect(admin.locator("body")).toContainText("Ссылка на установку пароля");
  // окно со ссылкой закрывается клавишей: кнопки «Закрыть» у него нет
  await admin.keyboard.press("Escape");
  await expect(admin.getByText("Ссылка на установку пароля")).toHaveCount(0);

  // фильтр по роли сужает таблицу до учителей
  await admin.locator(".acad__toolbar").getByLabel("Роль", { exact: true }).selectOption("teacher");
  await expect(admin).toHaveURL(/role=teacher/);
  const rows = admin.locator("table.tbl tbody tr");
  await expect(rows.filter({ hasText: TEACHER })).toHaveCount(1);
  for (const cell of await rows.locator("select").allTextContents())
    expect(cell).toContain("Учитель");

  // пароль выдаётся из строки и показывается один раз
  const issued = admin.waitForResponse(
    (r) => r.url().includes("/temp-password/") && r.request().method() === "POST",
  );
  await rows.filter({ hasText: TEACHER }).getByRole("button", { name: "Выдать пароль" }).click();
  expect((await issued).status()).toBe(200);
  await expect(admin.getByRole("dialog")).toContainText("Временный пароль");
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  await admin.context().close();
});

test("архив: удалённый урок лежит строкой типа «урок» и возвращается", async ({ browser }) => {
  const kymbat = await as(browser, "director_exam");
  // прошедший урок не удаляется — это история журнала; в архив уходит будущий
  const marked = (await lessonsBetween(kymbat, daysAgo(0), daysAgo(-14))).filter(
    (row) => row.date > daysAgo(0) && row.actual_teacher?.short?.includes("Прогон"),
  );
  expect(marked.length, "есть отмеченный урок учителя прогона").toBeGreaterThan(0);
  const lesson = marked[0];
  const deleted = await apiPost<{ archived?: boolean; deleted?: number }>(
    kymbat,
    `/api/acad/lessons/${lesson.id}/delete/`,
    { scope: "this" },
  );
  expect(deleted).toBeTruthy();
  await kymbat.context().close();

  const admin = await as(browser, "admin");
  const diag = watch(admin);
  await admin.goto("/archive");
  await expect(admin.locator("h1")).toContainText("Архив");
  await admin.getByRole("button", { name: /^урок/i }).first().click().catch(() => undefined);
  const row = admin.locator("table.tbl tbody tr", { hasText: lesson.subject.title }).first();
  await expect(row).toBeVisible();
  await expect(row).toContainText("в архиве");
  const restored = admin.waitForResponse(
    (r) => r.url().includes("/api/archive/") && r.url().includes("/restore/") && r.request().method() === "POST",
  );
  await row.getByRole("button", { name: "Вернуть" }).click();
  expect((await restored).status()).toBe(200);
  await expect(admin.locator("body")).toContainText("Восстановлено");
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);

  // урок снова в расписании учителя
  const back = await lessonsBetween(admin, lesson.date, lesson.date);
  expect(back.some((row) => row.id === lesson.id), "урок вернулся").toBeTruthy();
  await admin.context().close();
});

test("уборка: учётная запись учителя из панели убрана", async ({ browser }) => {
  const admin = await as(browser, "admin");
  const users = (await (await admin.request.get(`/api/users/?search=${TEACHER}`)).json()) as {
    results: { id: number; email: string }[];
  };
  const who = users.results.find((row) => row.email === TEACHER);
  if (who) {
    const csrf = (await admin.context().cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
    await admin.request.delete(`/api/users/${who.id}/`, { headers: { "X-CSRFToken": csrf } });
  }
  await admin.context().close();
});
