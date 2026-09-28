/**
 * Журнал учителя с клавиатуры: клетка выбирается мышью, цифра ставит
 * оценку ФО, буква «н» — отметку, Backspace снимает; каждое нажатие —
 * запрос на сервер и результат виден после перезагрузки.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { daysAgo, lessonsBetween } from "../helpers/academics";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  return page;
}

test("журнал: оценка и отметка с клавиатуры, снятие Backspace", async ({ browser }) => {
  const teacher = await as(browser, "teacher");
  const diag = watch(teacher);
  const mine = (await lessonsBetween(teacher, daysAgo(6), daysAgo(1))).filter(
    (row) => row.date < daysAgo(0),
  );
  expect(mine.length, "есть урок внутри окна правки").toBeGreaterThan(0);
  const lesson = mine[mine.length - 1];
  await teacher.goto(`/journals/${lesson.course}?period=${lesson.date.slice(0, 7)}`);
  await expect(teacher.locator("h1")).toContainText(lesson.subject.title);
  const grid = teacher.locator(".matrix").first();
  await expect(grid).toBeVisible();

  // колонка этого урока: по дате в подписи столбца
  const journal = (await (
    await teacher.request.get(`/api/acad/journals/${lesson.course}/?period=${lesson.date.slice(0, 7)}`)
  ).json()) as { columns: { lesson: number }[]; rows: { id: number; full_name: string }[] };
  const col = journal.columns.findIndex((column) => column.lesson === lesson.id);
  expect(col, "урок в колонках недели").toBeGreaterThanOrEqual(0);
  const cell = grid.locator(`[data-row="0"][data-col="${col}"]`);
  await cell.click();
  await expect(cell).toHaveAttribute("aria-selected", "true");

  const graded = teacher.waitForResponse(
    (r) => r.url().includes(`/acad/lessons/${lesson.id}/grade/`) && r.request().method() === "POST",
  );
  await grid.focus();
  await teacher.keyboard.press("8");
  expect((await graded).status()).toBe(200);
  await expect(cell).toContainText("8");

  const marked = teacher.waitForResponse(
    (r) => r.url().includes(`/acad/lessons/${lesson.id}/attendance/`) && r.request().method() === "POST",
  );
  await teacher.keyboard.type("н");
  expect((await marked).status()).toBe(200);
  await expect(cell).toContainText("н");

  await teacher.reload();
  const again = teacher.locator(".matrix").first().locator(`[data-row="0"][data-col="${col}"]`);
  await expect(again).toContainText("8");
  await expect(again).toContainText("н");

  // Backspace снимает оценку, второй — возвращает «был»
  await again.click();
  await teacher.locator(".matrix").first().focus();
  const cleared = teacher.waitForResponse(
    (r) => r.url().includes(`/acad/lessons/${lesson.id}/grade/`) && r.request().method() === "POST",
  );
  await teacher.keyboard.press("Backspace");
  expect((await cleared).status()).toBe(200);
  const present = teacher.waitForResponse(
    (r) => r.url().includes(`/acad/lessons/${lesson.id}/attendance/`) && r.request().method() === "POST",
  );
  await teacher.keyboard.press("Backspace");
  expect((await present).status()).toBe(200);
  await teacher.reload();
  await expect(teacher.locator(".matrix").first().locator(`[data-row="0"][data-col="${col}"]`)).not.toContainText("8");

  // стрелка вправо двигает выбор, Esc снимает
  const origin = teacher.locator(".matrix").first().locator(`[data-row="0"][data-col="0"]`);
  await origin.click();
  await teacher.keyboard.press("ArrowRight");
  await expect(teacher.locator(".matrix").first().locator(`[data-row="0"][data-col="1"]`)).toHaveAttribute("aria-selected", "true");
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await teacher.context().close();
});
