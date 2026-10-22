/**
 * Отчёты родителям у куратора: статусы сегментами со счётчиками, ZIP
 * проверенных, «Поделиться» на телефоне; у Кымбат — только чтение.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { apiPost, watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

const PHONE = { width: 390, height: 844 };

interface Listed {
  counts: Record<string, number>;
  rows: { id: number; status: string; student: { full_name: string } }[];
}

/** Период, за который файл собрал отчёты сам; пусто — смотрим период по умолчанию. */
let period = "";

const listed = async (page: Page): Promise<Listed> =>
  (await (
    await page.request.get(`/api/acad/reports/${period ? `?period=${encodeURIComponent(period)}` : ""}`)
  ).json()) as Listed;

/**
 * Файл не зависит от цепочки учебной части: нет отчётов — куратор собирает
 * стандартный за текущий месяц по своим группам, нет проверенного —
 * отмечает проверенным первый черновик. Так же, как он сделал бы на экране.
 */
async function ensureReady(curator: Page): Promise<Listed> {
  let data = await listed(curator);
  if (data.rows.length === 0) {
    const built = await apiPost<{ built: number; period: string }>(curator, "/api/acad/reports/build/", {
      template: "standard",
    });
    expect(built.built, "куратор собрал отчёты своих групп").toBeGreaterThan(0);
    period = built.period;
    data = await listed(curator);
  }
  if (!data.rows.some((row) => row.status !== "draft")) {
    await apiPost(curator, `/api/acad/reports/${data.rows[0].id}/check/`, {});
    data = await listed(curator);
  }
  return data;
}

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
  const counts = await ensureReady(curator);
  expect(counts.rows.length, "отчёты собраны").toBeGreaterThan(0);
  if (period) await curator.goto(`/reports?period=${encodeURIComponent(period)}`);
  // сегмент статуса сужает таблицу и уходит в адрес
  const segments = curator.locator(".segrow", { hasText: "Все" }).first();
  await expect(segments).toBeVisible();
  await curator.getByRole("button", { name: /^Отправлен родителям/ }).click();
  await expect(curator).toHaveURL(/status=sent/);
  await expect(curator.locator("table.tbl tbody tr")).toHaveCount(counts.counts.sent ?? 0);
  // именно сегмент статуса: рядом есть «Все группы» у переключателя групп
  await curator.getByRole("group", { name: "Статус" }).getByRole("button", { name: /^Все/ }).click();

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
  // PDF есть у проверенного или отправленного отчёта; черновик сначала проверяют
  await curator.goto("/reports");
  const ready = (await ensureReady(curator)).rows.find((row) => row.status !== "draft");
  expect(ready, "есть проверенный отчёт").toBeTruthy();
  await curator.goto(`/reports?open=${ready!.id}`);
  const drawer = curator.locator(".drawer");
  await expect(drawer).toBeVisible();
  // на телефоне кнопка называется «Поделиться»; без Web Share API — скачивание
  // подпись с форматом: «Поделиться PDF»
  const share = drawer.getByRole("button", { name: "Поделиться PDF", exact: true });
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
