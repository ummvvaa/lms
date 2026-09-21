/**
 * Эталоны трёх дашбордов — Кымбат, Асем и куратора — в двух состояниях (фаза 80).
 *
 * Наполненное снимается после посева эталонов (`baseline.spec.ts`), пустое —
 * посреди него, сразу после того как заведены группы и ученики
 * (`seed-baseline.spec.ts`): пробников, дедлайнов, очереди и задач ещё нет.
 *
 * Окно выше обычных 900: каркас прокручивает экран внутри себя, и снимок
 * «всей страницы» иначе обрезается по первому экрану — а проверяется здесь
 * как раз то, что ниже: ровные колонки и пустые карточки в одну строку.
 */
import { expect, type Browser, type Page } from "@playwright/test";
import { statePath } from "./auth-state";

export const DASHBOARD_ROLES = ["director_exam", "director_admission", "curator"] as const;

export const TALL_LAPTOP = { width: 1440, height: 1800 };
export const TALL_PHONE = { width: 390, height: 3200 };

/** Настоящее время в строках очереди и журнала — маскируется только оно. */
const MASKS = [".squeue__when"];

async function serverToday(browser: Browser): Promise<string> {
  const context = await browser.newContext({ storageState: statePath("admin") });
  const state = await (await context.request.get("/api/calendar/")).json();
  await context.close();
  return String(state.today ?? new Date().toISOString().slice(0, 10));
}

export async function openDashboard(
  browser: Browser,
  role: string,
  viewport: { width: number; height: number },
  today: string,
): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role), viewport });
  const page = await context.newPage();
  await page.addInitScript(() => {
    window.localStorage.setItem("first-run-seen", "1");
    // панель «Начало работы» — не про раскладку дашборда: свёрнута
    window.localStorage.setItem("getting-started-folded", "1");
  });
  await page.clock.setFixedTime(new Date(`${today}T09:30:00Z`));
  const csrf = (await context.cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
  await page.request
    .patch("/api/auth/me/preferences/", {
      data: { theme: "light", sidebar_collapsed: false },
      headers: { "X-CSRFToken": csrf },
    })
    .catch(() => undefined);
  await page.goto("/dashboard");
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(600);
  return page;
}

/** Снять шесть эталонов состояния: три дашборда на 1440 и на 390. */
export async function shootDashboards(
  browser: Browser,
  state: "filled" | "empty",
  check?: (page: Page, role: string, phone: boolean) => Promise<void>,
): Promise<void> {
  const today = await serverToday(browser);
  for (const role of DASHBOARD_ROLES) {
    for (const [tag, viewport] of [
      ["", TALL_LAPTOP],
      ["phone-", TALL_PHONE],
    ] as const) {
      const page = await openDashboard(browser, role, viewport, today);
      if (tag) {
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - window.screen.width,
        );
        expect(overflow, `${role}: страница не шире экрана`).toBeLessThanOrEqual(1);
      }
      if (check) await check(page, role, Boolean(tag));
      await expect(page).toHaveScreenshot(`${tag}dashboard-${state}-${role}.png`, {
        fullPage: true,
        animations: "disabled",
        caret: "hide",
        scale: "css",
        mask: MASKS.map((selector) => page.locator(selector)),
        threshold: 0.25,
        maxDiffPixelRatio: 0.02,
      });
      await page.context().close();
    }
  }
}
