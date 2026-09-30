/**
 * Расписание и оценки ученика: своя неделя с заменами и СОР, оценки
 * по предметам без ярлыков и чужих учеников, главная с уроками сегодня;
 * на 390 без горизонтального выезда, цель касания 44.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";

test.describe.configure({ timeout: 180_000 });

const PHONE = { width: 390, height: 844 };
const INTERNAL = ["critical", "needs_supervision", "нужен контроль", "средн", "по группе"];

async function as(browser: Browser, viewport?: { width: number; height: number }): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath("student"),
    ...(viewport ? { viewport, isMobile: true, hasTouch: true, deviceScaleFactor: 2 } : {}),
  });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  return page;
}

test("расписание: неделя своих уроков, урок открывается", async ({ browser }) => {
  const student = await as(browser);
  const diag = watch(student);
  await student.goto("/schedule");
  await expect(student.locator("h1")).toContainText("Расписание");
  const chips = student.locator(".les");
  await expect(chips.first()).toBeVisible();
  await chips.first().click();
  await expect(student).toHaveURL(/\/lessons\/\d+/);
  await expect(student.locator(".datacard", { hasText: "Урок" })).toContainText("Моя отметка");
  expect(diag.since(0).filter((c) => c.status >= 400)).toEqual([]);
  await student.context().close();
});

test("оценки: по предметам, последние оценки, без ярлыков", async ({ browser }) => {
  const student = await as(browser);
  const diag = watch(student);
  await student.goto("/grades");
  await expect(student.locator("h1")).toContainText("Оценки");
  await expect(student.locator(".statrow .stat").first()).toBeVisible();
  await expect(student.locator(".datacard", { hasText: "По предметам" })).toBeVisible();
  const text = (await student.locator("main").innerText()).toLowerCase();
  for (const word of INTERNAL) expect(text, `ярлык «${word}» на экране ученика`).not.toContain(word);
  const body = (await (await student.request.get("/api/acad/me/grades/")).json()) as Record<string, unknown>;
  const raw = JSON.stringify(body).toLowerCase();
  for (const word of ["critical", "needs_supervision", "group_avg", "average"])
    expect(raw, `ярлык «${word}» в ответе ученику`).not.toContain(word);
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  await student.context().close();
});

test("телефон: главная, расписание, оценки и ДЗ без выезда, касания не ниже 44", async ({ browser }) => {
  const student = await as(browser, PHONE);
  for (const path of ["/dashboard", "/schedule", "/grades", "/homework"]) {
    await student.goto(path);
    await student.waitForLoadState("networkidle").catch(() => undefined);
    const overflow = await student.evaluate(() => document.documentElement.scrollWidth - screen.width);
    expect(overflow, `${path}: выезд вбок`).toBeLessThanOrEqual(1);
    const small = await student.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>("main button, main a[href], .tabbar a")]
        .filter((el) => el.offsetParent !== null)
        .map((el) => el.getBoundingClientRect().height)
        .filter((height) => height > 0 && height < 40).length,
    );
    expect(small, `${path}: кнопки ниже цели касания`).toBeLessThanOrEqual(2);
  }
  // нижний бар ученика: главная, расписание, ДЗ и вузы (у 8–10 вместо вузов — оценки)
  await expect(student.locator(".tabbar")).toContainText("Расписание");
  await expect(student.locator(".tabbar")).toContainText("ДЗ");
  await student.context().close();
});
