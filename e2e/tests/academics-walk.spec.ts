/**
 * Обход адресов всех девяти ролей на наполненной школе: каждый адрес
 * из `routes.ts` открывается на 1440 и 390 без ошибок в консоли, без
 * ответов 4xx/5xx и без горизонтального выезда на телефоне; на экране
 * есть заголовок. Адреса с `{lesson}` и `{course}` берут уроки учителя
 * прогона, которые завёл посев.
 */
import { expect, test, type Browser } from "@playwright/test";
import { routeIds, substitute } from "../helpers/academics";
import { ROUTES, clickTab } from "../helpers/routes";
import { watch } from "../helpers/session";
import { LAPTOP, PHONE, findPupil, openAs, settle } from "../helpers/walk";

test.describe.configure({ timeout: 900_000 });

async function walkRole(
  browser: Browser,
  role: string,
  routes: string[],
  viewport: { width: number; height: number },
): Promise<string[]> {
  const page = await openAs(browser, role, viewport);
  const diag = watch(page);
  const problems: string[] = [];
  const ids = await routeIds(page, role, routes, () => findPupil(page, role));
  for (const route of routes) {
    const url = substitute(route, ids);
    if (url === null) {
      problems.push(`${role} ${route}: нет записи под адрес`);
      continue;
    }
    const mark = diag.mark();
    await page.goto(url.split("#")[0]);
    await settle(page);
    const tab = clickTab(route);
    if (tab)
      await page
        .getByRole("tab", { name: tab })
        .first()
        .click({ timeout: 5000 })
        .catch(() => undefined);
    await settle(page);
    // экран не увёл на главную: адрес роли открыт ей самой
    if (!url.startsWith("/dashboard") && page.url().endsWith("/dashboard"))
      problems.push(`${role} ${route}: увело на главную`);
    if ((await page.locator("h1").count()) === 0)
      problems.push(`${role} ${route}: нет заголовка`);
    const bad = diag.since(mark).filter((call) => call.status >= 400);
    if (bad.length > 0)
      problems.push(
        `${role} ${route}: ${bad.map((c) => `${c.method} ${c.url} → ${c.status}`).join(", ")}`,
      );
    if (viewport.width <= 640) {
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - screen.width,
      );
      if (overflow > 1) problems.push(`${role} ${route}: выезд вбок на ${overflow}px`);
    }
  }
  if (diag.consoleErrors.length > 0)
    problems.push(`${role}: ошибки в консоли: ${diag.consoleErrors.slice(0, 3).join(" | ")}`);
  if (diag.pageErrors.length > 0)
    problems.push(`${role}: исключения: ${diag.pageErrors.slice(0, 3).join(" | ")}`);
  await page.context().close();
  return problems;
}

for (const [role, routes] of Object.entries(ROUTES)) {
  test(`обход: ${role} на ноутбуке и телефоне`, async ({ browser }) => {
    const problems = [
      ...(await walkRole(browser, role, routes, LAPTOP)),
      ...(await walkRole(browser, role, routes, PHONE)),
    ];
    expect(problems, problems.join("\n")).toEqual([]);
  });
}
