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

  // цифра ставит оценку только в колонке ФО: на СОР и СОЧ она открывает
  // ввод баллов, на прошедшем окне правки — отказ. Колонку берём из журнала
  type Column = { lesson: number; kind: string; future: boolean; locked: boolean };
  let course = 0;
  let period = "";
  let col = -1;
  let lessonId = 0;
  for (const row of [...mine].reverse()) {
    const month = row.date.slice(0, 7);
    const journal = (await (
      await teacher.request.get(`/api/acad/journals/${row.course}/?period=${month}`)
    ).json()) as { columns: Column[] };
    const found = journal.columns.findIndex(
      (column) => column.lesson === row.id && column.kind === "fo" && !column.future && !column.locked,
    );
    if (found >= 0) {
      [course, period, col, lessonId] = [row.course, month, found, row.id];
      break;
    }
  }
  expect(col, "есть урок ФО внутри окна правки").toBeGreaterThanOrEqual(0);

  await teacher.goto(`/journals/${course}?period=${period}`);
  const cellAt = () => teacher.locator(".matrix").first().locator(`[data-row="0"][data-col="${col}"]`);
  const post = (path: string) =>
    teacher.waitForResponse(
      (r) => r.url().includes(`/acad/lessons/${lessonId}/${path}/`) && r.request().method() === "POST",
    );
  await expect(cellAt()).toBeVisible();

  // «8» — запрос ушёл, оценка в клетке и после перезагрузки
  await cellAt().click();
  await expect(cellAt()).toHaveAttribute("aria-selected", "true");
  await expect(cellAt()).toBeFocused();
  const graded = post("grade");
  await teacher.keyboard.press("8");
  expect((await graded).status()).toBe(200);
  await expect(cellAt()).toContainText("8");
  await teacher.reload();
  await expect(cellAt()).toContainText("8");

  // Backspace при оценке — оценка снята
  await cellAt().click();
  const cleared = post("grade");
  await teacher.keyboard.press("Backspace");
  expect((await cleared).status()).toBe(200);
  await teacher.reload();
  await expect(cellAt()).not.toContainText("8");

  // «н» — отметка сохранена (оценку отсутствующему не ставят — docs/academics.md).
  // Кириллицу Playwright вводит текстом без keydown, а сетка слушает keydown;
  // сетка принимает и латинские «n» и «y» (на русской раскладке «н» — клавиша Y)
  await cellAt().click();
  const marked = post("attendance");
  await teacher.keyboard.press("n");
  expect((await marked).status()).toBe(200);
  await teacher.reload();
  await expect(cellAt()).toContainText("н");

  // Backspace без оценки — вернуть «был»
  await cellAt().click();
  const present = post("attendance");
  await teacher.keyboard.press("Backspace");
  expect((await present).status()).toBe(200);
  await teacher.reload();
  await expect(cellAt()).not.toContainText("н");

  // стрелка вправо двигает выбор
  const origin = teacher.locator(".matrix").first().locator(`[data-row="0"][data-col="0"]`);
  await origin.click();
  await teacher.keyboard.press("ArrowRight");
  await expect(teacher.locator(".matrix").first().locator(`[data-row="0"][data-col="1"]`)).toHaveAttribute("aria-selected", "true");
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await teacher.context().close();
});
