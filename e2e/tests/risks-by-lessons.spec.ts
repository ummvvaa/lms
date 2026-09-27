/**
 * «Риски» у Салтанат считаются по урокам: показатели сверху, таблица
 * с «н»/«у» и днями без причины, переход в посещаемость на нужный день;
 * у дашборда худшая посещаемость тоже по урокам.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";

test.describe.configure({ timeout: 120_000 });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  return page;
}

test("риски: показатели, таблица по урокам, переход в посещаемость", async ({ browser }) => {
  const page = await as(browser, "director_behavior");
  const diag = watch(page);
  await page.goto("/risks");
  await expect(page.locator("h1")).toContainText("Риски");
  await expect(page.locator(".statrow .stat")).toHaveCount(4);
  await expect(page.locator(".statrow")).toContainText("Ниже порога посещаемости");
  const risks = (await (await page.request.get("/api/acad/risks/")).json()) as {
    threshold: number;
    rows: { id: number; full_name: string; group: string; unexcused_days: string[] }[];
  };
  expect(risks.rows.length, "посев дал пропуски по урокам").toBeGreaterThan(0);
  const table = page.locator(".datacard", { hasText: "Посещаемость по урокам" });
  await expect(table.locator("table.tbl tbody tr").first()).toBeVisible();
  await expect(table).toContainText(`${risks.rows[0].full_name}`);
  await expect(page.locator(".datacard", { hasText: "Что делать" })).toContainText("только «н»");

  const row = table.locator("table.tbl tbody tr", { hasText: risks.rows[0].full_name }).first();
  await row.getByRole("button", { name: "Посещаемость" }).click();
  await expect(page).toHaveURL(new RegExp(`/attendance\\?group=${encodeURIComponent(risks.rows[0].group)}`));
  await expect(page.locator("h1")).toContainText("Посещаемость");
  // Салтанат читает: оформить причину и сохранить ей нечем
  await expect(page.getByRole("button", { name: "Оформить" })).toHaveCount(0);
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  await page.context().close();
});

test("дашборд: худшая посещаемость по урокам с процентом", async ({ browser }) => {
  const page = await as(browser, "director_behavior");
  await page.goto("/dashboard");
  const body = (await (await page.request.get("/api/dashboards/behavior/")).json()) as {
    worst_attendance: { attendance_percent: number; lessons: number }[];
  };
  expect(body.worst_attendance.length).toBeGreaterThan(0);
  for (const row of body.worst_attendance) expect(row.lessons).toBeGreaterThan(0);
  await page.context().close();
});
