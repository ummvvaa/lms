/**
 * Раскладка дашбордов Кымбат и Асем: длинные списки и герой (фаза 80).
 *
 * Правила одни на три дашборда: список длиннее пяти строк показывает пять
 * и «Показать все N» и раскрывается на месте; герой Асем стоит, только пока
 * в ближайшие 30 дней есть дедлайн с подающими. Пустые карточки и ровные
 * колонки проверяют эталоны (`seed-baseline.spec.ts`, `baseline.spec.ts`).
 *
 * Ответ кабинета здесь дополняется на лету: семь групп без целей и дедлайн
 * через двенадцать дней посевом не завести так, чтобы они не уехали к завтра.
 * Остальное в ответе — настоящее.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";

test.describe.configure({ timeout: 120_000 });

async function dashboard(
  browser: Browser,
  role: string,
  patch: (cabinet: Record<string, unknown>) => void,
): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  await page.route("**/api/cabinet/", async (route) => {
    const response = await route.fetch();
    const cabinet = (await response.json()) as Record<string, unknown>;
    patch(cabinet);
    await route.fulfill({ response, json: cabinet });
  });
  await page.goto("/dashboard");
  return page;
}

test("Кымбат: список длиннее пяти строк раскрывается на месте", async ({ browser }) => {
  const groups = ["G1", "G2", "G3", "G4", "G5", "G6", "G7"];
  const page = await dashboard(browser, "director_exam", (cabinet) => {
    cabinet.without_goals = groups.map((code) => ({ code, students: 3 }));
  });

  const card = page.locator(".datacard", { hasText: "Без целей по экзаменам" });
  await expect(card.locator(".rowline")).toHaveCount(5);
  const more = card.getByRole("button", { name: "Показать все 7" });
  await expect(more).toHaveAttribute("aria-expanded", "false");

  await more.click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(card.getByText("G7", { exact: true })).toBeVisible();
  await expect(card.getByRole("button", { name: "Свернуть" })).toHaveAttribute("aria-expanded", "true");

  // «мок просел» — один раз: списком, где по ученику есть действие
  await expect(page.getByText("Мок просел", { exact: true })).toHaveCount(1);
  await page.context().close();
});

test("Асем: герой стоит только при дедлайнах в ближайшие 30 дней", async ({ browser }) => {
  const none = await dashboard(browser, "director_admission", (cabinet) => {
    Object.assign(cabinet.urgent as object, { applying: 0, rounds: 0, applicants: 0, nearest: null, first: null });
  });
  await expect(none.locator(".statrow").first()).toBeVisible();
  await expect(none.locator(".hero")).toHaveCount(0);
  await expect(none.getByText("дедлайнов нет")).toHaveCount(0);
  await none.context().close();

  const soon = await dashboard(browser, "director_admission", (cabinet) => {
    Object.assign(cabinet.urgent as object, {
      applying: 0,
      rounds: 2,
      applicants: 3,
      first: null,
      nearest: { university: "Probe University", deadline: "2030-01-01", days: 12 },
    });
  });
  const hero = soon.locator(".hero");
  await expect(hero).toContainText("Дедлайны в ближайшие 30 дней");
  await expect(hero).toContainText("Ближайший дедлайн — Probe University, через 12 дн.");
  await hero.getByRole("button", { name: "Открыть список" }).click();
  await expect(soon).toHaveURL(/\/deadlines/);
  await soon.context().close();
});
