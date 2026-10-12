/**
 * Подбор вузов: результат-снимок, объяснение процентов, избранное и история запусков.
 *
 * Ученик запускает подбор и получает результат-снимок: сводка профиля,
 * три карточки стратегии, воронка числами, объяснение процентов,
 * категории и секции, карточка вуза с двумя числами соответствия.
 * Повторный подбор с фильтром стран даёт другой результат, оба в истории.
 * Экрана «Избранное» с 07.10.2026 нет, его API проверяет `api_probe.py`.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";

test.describe.configure({ mode: "serial", timeout: 240_000 });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

async function waitForResult(page: Page) {
  // маленький справочник считается быстро: ждём либо этапы, либо готовый результат
  await expect(page.getByText(/Идёт расчёт|Подбор от/).first()).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText("Подбор от").first()).toBeVisible({
    timeout: 60_000,
  });
}

test("ученик запускает подбор и получает результат со всеми блоками", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  await page.goto("/selection");

  const running = await page.getByText("Идёт расчёт").count();
  if (running === 0) {
    await page.getByRole("button", { name: "Запустить подбор" }).click();
  }
  await waitForResult(page);

  // сводка профиля, из которого считалось
  // три карточки стратегии
  for (const title of [
    "Текущая позиция",
    "Что важно усилить",
    "Следующий шаг",
  ]) {
    await expect(page.getByText(title, { exact: true }).first()).toBeVisible();
  }
  // воронка числами
  await expect(page.getByText("Как построена подборка")).toBeVisible();
  // воронка — четыре числа через стрелки под заголовком карточки
  await expect(page.getByText(/\d+ → \d+ → \d+ → \d+/).first()).toBeVisible();
  // раскрывающееся объяснение
  await page
    .getByRole("button", { name: "Как считаются проценты и категории" })
    .click();
  await expect(
    page.getByText("не шанс поступления", { exact: false }).first(),
  ).toBeVisible();
  // «что дальше»
  await expect(page.getByText("Следующий шаг").first()).toBeVisible();
});

test("карточка вуза: два числа соответствия и разбор процента", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  await page.goto("/selection");
  // история подборов — строки-ссылки
  await page.locator(".datacard", { hasText: "История подборов" }).locator(".rowline--link").first().click();
  await waitForResult(page);

  const card = page.locator(".sel__result").first();
  // два числа соответствия одной пометкой: «сейчас → если закрыть разрывы»
  await expect(card.getByText(/\d+% → \d+%/)).toBeVisible();

  await card.getByRole("button", { name: "Почему такой процент" }).click();
  await expect(card.locator(".sel__explain")).toBeVisible();
  await expect(card.getByText("вес", { exact: false }).first()).toBeVisible();
});

test("повторный подбор с фильтром стран — другой результат, оба в истории", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  await page.goto("/selection");

  const facets = (await (
    await page.request.get("/api/catalog/facets/")
  ).json()) as { countries: string[] };
  const country = facets.countries[0];
  await page
    .getByRole("button", { name: country, exact: true })
    .first()
    .click();
  await page.getByRole("button", { name: "Запустить подбор" }).click();
  await waitForResult(page);
  await expect(page.locator(".rowline", { hasText: "Страны" }).first()).toContainText(country);

  await page.goto("/selection");
  const history = (await (
    await page.request.get("/api/selection/runs/")
  ).json()) as {
    results: { countries: string[]; funnel: { filtered: number } }[];
  };
  expect(history.results.length).toBeGreaterThanOrEqual(2);
  const withFilter = history.results.find((r) => r.countries.length > 0);
  const without = history.results.find((r) => r.countries.length === 0);
  expect(withFilter).toBeTruthy();
  expect(without).toBeTruthy();
  expect(withFilter!.funnel.filtered).toBeLessThanOrEqual(
    without!.funnel.filtered,
  );
  await expect(
    page.locator(".datacard", { hasText: "История подборов" }).locator(".rowline--link").first(),
  ).toBeVisible();
});
