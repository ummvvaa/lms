/**
 * Раскладка дашбордов Кымбат и Асем: длинные списки и герой (фаза 80).
 *
 * Правила одни на три дашборда: список длиннее пяти строк показывает пять
 * и «Показать все N» и раскрывается на месте; герой Асем стоит, только пока
 * в ближайшие 30 дней есть дедлайн с подающими. Пустые карточки и ровные
 * колонки проверяют эталоны (`seed-baseline.spec.ts`, `baseline.spec.ts`).
 *
 * Ответ ручки здесь дополняется на лету: семь просроченных задач и дедлайн
 * через двенадцать дней посевом не завести так, чтобы они не уехали к завтра.
 * Остальное в ответе — настоящее.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";

test.describe.configure({ timeout: 120_000 });

async function dashboard(
  browser: Browser,
  role: string,
  url: string,
  patch: (payload: Record<string, unknown>) => void,
): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  await page.route(url, async (route) => {
    const response = await route.fetch();
    const payload = (await response.json()) as Record<string, unknown>;
    patch(payload);
    await route.fulfill({ response, json: payload });
  });
  await page.goto("/dashboard");
  return page;
}

/** Дата «через N дней» по Алматы — дедлайн и срок задачи. */
const inDays = (n: number): string =>
  new Date(Date.now() + n * 86_400_000).toLocaleDateString("sv-SE", { timeZone: "Asia/Almaty" });

test("Кымбат: список длиннее пяти строк раскрывается на месте", async ({ browser }) => {
  // главная по макету кабинетов (24.10.2026): «Задачи сотрудникам: просрочено»
  const page = await dashboard(browser, "director_exam", "**/api/directors/staff-tasks/", (payload) => {
    payload.rows = [1, 2, 3, 4, 5, 6, 7].map((n) => ({
      id: 9000 + n,
      title: `Задача прогона ${n}`,
      due: inDays(-n),
      status: "open",
      status_title: "Открыта",
      late: true,
      days_late: n,
      assignee: { id: 1, name: `Учитель ${n}`, role: "teacher", role_title: "Учитель" },
      author: "",
      return_note: "",
      done_at: null,
      reminded_at: null,
      created_at: inDays(-10),
    }));
  });

  const card = page.locator(".datacard", { hasText: "Задачи сотрудникам: просрочено" });
  await expect(card.locator(".dir__row")).toHaveCount(5);
  const more = card.getByRole("button", { name: "Показать все 7" });
  await expect(more).toHaveAttribute("aria-expanded", "false");

  await more.click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(card.getByText("Задача прогона 7", { exact: true })).toBeVisible();
  await expect(card.getByRole("button", { name: "Свернуть" })).toHaveAttribute("aria-expanded", "true");
  await page.context().close();
});

test("Асем: карточка дедлайнов стоит только при дедлайнах в ближайшие 30 дней", async ({ browser }) => {
  // пустой карточки нет вовсе (24.10.2026): без дедлайнов с подающими её не рисуют
  const none = await dashboard(browser, "director_admission", "**/api/dashboards/admission/", (payload) => {
    payload.deadlines = [];
  });
  await expect(none.locator("h1")).toContainText("Добрый день");
  await expect(none.getByText("Ближайшие дедлайны")).toHaveCount(0);
  await none.context().close();

  const soon = await dashboard(browser, "director_admission", "**/api/dashboards/admission/", (payload) => {
    payload.deadlines = [
      { id: 1, deadline: inDays(12), round_type: "EA", applicants_count: 3, university: "Probe University", country: "", program_name: "", tone: "warn" },
      { id: 2, deadline: inDays(60), round_type: "RD", applicants_count: 2, university: "Far University", country: "", program_name: "", tone: "neutral" },
    ];
  });
  const card = soon.locator(".datacard", { hasText: "Ближайшие дедлайны" }).first();
  await expect(card).toContainText("Probe University");
  await expect(card).not.toContainText("Far University");
  await card.getByRole("button", { name: "Все", exact: true }).click();
  await expect(soon).toHaveURL(/\/deadlines/);
  await soon.context().close();
});
