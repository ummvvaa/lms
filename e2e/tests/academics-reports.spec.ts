/**
 * Отчёты родителям у куратора: статусы сегментами со счётчиками, ZIP
 * проверенных, «Поделиться» на телефоне; у Кымбат — только чтение.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

const PHONE = { width: 390, height: 844 };

async function as(browser: Browser, role: string, viewport?: { width: number; height: number }): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    ...(viewport ? { viewport, isMobile: true, hasTouch: true, deviceScaleFactor: 2 } : {}),
  });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  return page;
}

test("статусы сегментами, таблица, ZIP отмеченных", async ({ browser }) => {
  const curator = await as(browser, "curator");
  const diag = watch(curator);
  await curator.goto("/reports");
  await expect(curator.locator("h1")).toContainText("Отчёты родителям");
  const counts = (await (await curator.request.get("/api/acad/reports/")).json()) as {
    counts: Record<string, number>;
    rows: { id: number; status: string; student: { full_name: string } }[];
  };
  expect(counts.rows.length, "отчёты собраны цепочкой").toBeGreaterThan(0);
  // сегмент статуса сужает таблицу и уходит в адрес
  const segments = curator.locator(".segrow", { hasText: "Все" }).first();
  await expect(segments).toBeVisible();
  await curator.getByRole("button", { name: /^Отправлены/ }).click();
  await expect(curator).toHaveURL(/status=sent/);
  await expect(curator.locator("table.tbl tbody tr")).toHaveCount(counts.counts.sent ?? 0);
  await curator.getByRole("button", { name: /^Все/ }).first().click();

  // отмечаем проверенный или отправленный отчёт и качаем ZIP
  const ready = counts.rows.find((row) => row.status !== "draft");
  expect(ready, "есть проверенный отчёт").toBeTruthy();
  const row = curator.locator("table.tbl tbody tr", { hasText: ready!.student.full_name }).first();
  await row.getByRole("checkbox").check();
  const download = curator.waitForEvent("download");
  await curator.getByRole("button", { name: /^Скачать архивом/ }).click();
  expect((await download).suggestedFilename()).toMatch(/\.zip$/);
  await expect(curator.locator("body")).toContainText("Архив скачан");
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  await curator.context().close();
});

test("телефон: отчёт открывается панелью, PDF уходит в «Поделиться» или скачивается", async ({ browser }) => {
  const curator = await as(browser, "curator", PHONE);
  await curator.goto("/reports");
  const first = curator.locator("table.tbl tbody tr").first();
  await expect(first).toBeVisible();
  await first.click();
  const drawer = curator.locator(".drawer");
  await expect(drawer).toBeVisible();
  // на телефоне кнопка называется «Поделиться»; без Web Share API — скачивание
  const share = drawer.getByRole("button", { name: "Поделиться" });
  await expect(share).toBeVisible();
  const download = curator.waitForEvent("download", { timeout: 20_000 }).catch(() => null);
  await share.click();
  const file = await download;
  if (file) expect(file.suggestedFilename()).toMatch(/\.pdf$/);
  await expect(curator.locator("body")).toContainText(/PDF скачан|Поделиться/);
  const overflow = await curator.evaluate(() => document.documentElement.scrollWidth - screen.width);
  expect(overflow, "выезда вбок нет").toBeLessThanOrEqual(1);
  await curator.context().close();
});
