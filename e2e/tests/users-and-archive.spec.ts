/**
 * Пользователи: учитель заводится окном человека по роли (11.10.2026);
 * архив с удалённым уроком и «Вернуть». Заведённое сценарием убирается им же.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { daysAgo, lessonsBetween, markLesson } from "../helpers/academics";
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

test("пользователи: учитель заводится в окне, фильтр по роли, пароль выдаётся", async ({ browser }) => {
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
  const panel = admin.getByRole("dialog");
  await expect(panel).toContainText("Завести пользователя");
  await panel.getByLabel("Роль", { exact: true }).selectOption("teacher");
  await panel.getByLabel("Фамилия и имя").fill("Прогон Учитель Панельный");
  await panel.getByLabel("Почта или логин").fill(TEACHER);
  const created = admin.waitForResponse(
    (r) => r.url().endsWith("/api/users/") && r.request().method() === "POST",
  );
  await panel.getByRole("button", { name: "Завести", exact: true }).click();
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
  // роль с 11.10.2026 — подписью под именем, а не выпадающим списком
  await expect(rows.filter({ hasText: "@" }).filter({ hasNotText: "Учитель" })).toHaveCount(0);

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
  // в архив уходит только урок с отметками, без отметок удаляется насовсем,
  // а прошедший не меняется вовсе — значит, нужен сегодняшний начавшийся урок
  // учителя прогона, который он сам и отмечает
  const teacher = await as(browser, "teacher");
  const now = new Date();
  const clock = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  const started = (await lessonsBetween(teacher, daysAgo(0), daysAgo(0))).filter(
    (row) => row.is_live !== false && Boolean(row.bell) && (row.bell ?? "") <= clock,
  );
  test.skip(started.length === 0, "сегодня у учителя прогона ещё нет начавшегося урока");
  const lesson = started[0];
  await markLesson(teacher, lesson.id, "all");
  await teacher.context().close();
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
  // запись архива называется «предмет · состав · дата, N урок»
  const row = admin.locator("table.tbl tbody tr", { hasText: lesson.subject.title }).filter({ hasText: "в архиве" }).first();
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
