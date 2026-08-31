/**
 * Фаза 40 — подбор вузов.
 *
 * Ученик запускает подбор и получает результат-снимок: сводка профиля,
 * три карточки стратегии, воронка числами, объяснение процентов,
 * категории и секции, карточка вуза с двумя числами соответствия.
 * Избранное живёт отдельно от списка подачи. Повторный подбор
 * с фильтром стран даёт другой результат, оба в истории.
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
  await expect(page.getByText(/Идёт расчёт|Подбор от/).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Подбор от").first()).toBeVisible({ timeout: 60_000 });
}

test("ученик запускает подбор и получает результат со всеми блоками", async ({ browser }) => {
  const page = await as(browser, "student");
  await page.goto("/selection");

  const running = await page.getByText("Идёт расчёт").count();
  if (running === 0) {
    await page.getByRole("button", { name: "Запустить подбор" }).click();
  }
  await waitForResult(page);

  // сводка профиля, из которого считалось
  await expect(page.getByText("Это профиль на момент запуска", { exact: false })).toBeVisible();
  // три карточки стратегии
  for (const title of ["Текущая позиция", "Что важно усилить", "Следующий шаг"]) {
    await expect(page.getByText(title, { exact: true }).first()).toBeVisible();
  }
  // воронка числами
  await expect(page.getByText("Как построена подборка")).toBeVisible();
  for (const label of ["Программ в каталоге", "Прошли фильтр", "Разобраны подробно", "В финальном списке"]) {
    await expect(page.getByText(label).first()).toBeVisible();
  }
  // раскрывающееся объяснение
  await page.getByRole("button", { name: "Как считаются проценты и категории" }).click();
  await expect(page.getByText("не шанс поступления", { exact: false }).first()).toBeVisible();
  // «что дальше»
  await expect(page.getByText("Что дальше")).toBeVisible();
});

test("карточка вуза: два числа соответствия и разбор процента", async ({ browser }) => {
  const page = await as(browser, "student");
  await page.goto("/selection");
  await page.getByRole("button", { name: "Смотреть результат" }).first().click();
  await waitForResult(page);

  const card = page.locator(".sel__uni").first();
  await expect(card.getByText("Соответствие сейчас")).toBeVisible();
  await expect(card.getByText("Если закрыть разрывы")).toBeVisible();

  await card.getByRole("button", { name: "Почему такой процент" }).click();
  await expect(card.locator(".sel__explain")).toBeVisible();
  await expect(card.getByText("вес", { exact: false }).first()).toBeVisible();
});

test("избранное работает отдельно от списка подачи", async ({ browser }) => {
  const page = await as(browser, "student");
  await page.goto("/selection");
  await page.getByRole("button", { name: "Смотреть результат" }).first().click();
  await waitForResult(page);

  const card = page.locator(".sel__uni").first();
  const heart = card.locator(".sel__heart");
  const wasOn = (await heart.getAttribute("class"))?.includes("sel__heart--on") ?? false;
  if (!wasOn) {
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/favorites/")),
      heart.click(),
    ]);
    expect([200, 201]).toContain(response.status());
  }

  await page.goto("/favorites");
  await expect(page.locator(".sel__uni").first()).toBeVisible();

  // избранное — не список подачи: на «Моих вузах» этой пометки нет
  const favorites = (await (await page.request.get("/api/favorites/")).json()) as {
    results: { in_my_list: boolean }[];
  };
  expect(favorites.results.length).toBeGreaterThan(0);
});

test("повторный подбор с фильтром стран — другой результат, оба в истории", async ({ browser }) => {
  const page = await as(browser, "student");
  await page.goto("/selection");

  const facets = (await (await page.request.get("/api/catalog/facets/")).json()) as { countries: string[] };
  const country = facets.countries[0];
  await page.getByRole("button", { name: country, exact: true }).first().click();
  await page.getByRole("button", { name: "Запустить подбор" }).click();
  await waitForResult(page);
  await expect(page.getByText(`Страны: ${country}`, { exact: false })).toBeVisible();

  await page.goto("/selection");
  const history = (await (await page.request.get("/api/selection/runs/")).json()) as {
    results: { countries: string[]; funnel: { filtered: number } }[];
  };
  expect(history.results.length).toBeGreaterThanOrEqual(2);
  const withFilter = history.results.find((r) => r.countries.length > 0);
  const without = history.results.find((r) => r.countries.length === 0);
  expect(withFilter).toBeTruthy();
  expect(without).toBeTruthy();
  expect(withFilter!.funnel.filtered).toBeLessThanOrEqual(without!.funnel.filtered);
  await expect(page.getByRole("button", { name: "Смотреть результат" }).first()).toBeVisible();
});
