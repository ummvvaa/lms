/**
 * «Учителя» с вкладками и предметы «ведётся в LMS / только расписание»
 * (07–09.10.2026), SAT одним предметом по умолчанию.
 *
 * Посев прогона даёт физкультуру «только расписание» у четвёртого учителя
 * (`schedule@probe.local`) и профориентацию у третьего. Здесь:
 *
 * 1. «Учителя»: две вкладки; физрук — во вкладке «Только расписание» без
 *    карточки; «Закрыть вход» с набором числа выключает учётку, уроки остаются.
 * 2. «Учебный год» → «Предметы»: признаки предметов, режим SAT, переключатель
 *    пишет на сервер и возвращается.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { apiPatch, watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

const SCHEDULE_TEACHER = "Прогон Физрук";

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  return page;
}

async function userOf(page: Page, email: string): Promise<{ id: number; is_active: boolean }> {
  const users = (await (await page.request.get(`/api/users/?search=${encodeURIComponent(email)}&show=all`)).json()) as {
    results: { id: number; email: string; is_active: boolean }[];
  };
  const row = users.results.find((u) => u.email === email);
  expect(row, `учётная запись ${email}`).toBeTruthy();
  return row!;
}

test("«Учителя»: физрук во вкладке «Только расписание», «Закрыть вход» выключает учётку, уроки остаются", async ({
  browser,
}) => {
  const admin = await as(browser, "admin");
  const diag = watch(admin);
  await admin.goto("/teachers");
  await expect(admin.getByRole("tab", { name: /Ведут в LMS/ })).toBeVisible();
  // учителя предметов LMS — в первой вкладке, физрука среди них нет
  await expect(admin.locator("body")).toContainText("Прогон Профориентатор");
  await expect(admin.locator("main")).not.toContainText(SCHEDULE_TEACHER);

  await admin.getByRole("tab", { name: /Только расписание/ }).click();
  await expect(admin).toHaveURL(/tab=schedule/);
  const row = admin.locator("tbody tr, .rows__item").filter({ hasText: SCHEDULE_TEACHER }).first();
  await expect(row).toBeVisible();
  await expect(row).toContainText("Физкультура");
  await expect(row).toContainText("вход открыт");
  // карточки и действий у него нет: строка — не ссылка
  await expect(row.getByRole("button", { name: "Открыть" })).toHaveCount(0);

  const closeAll = admin.getByRole("button", { name: /Закрыть вход всем в списке/ });
  await expect(closeAll).toBeVisible();
  const open = Number((await closeAll.innerText()).replace(/\D/g, ""));
  expect(open, "открытых входов в списке").toBeGreaterThan(0);
  await closeAll.click();
  const confirm = admin.getByRole("alertdialog").or(admin.getByRole("dialog")).first();
  await expect(confirm).toContainText("Закрыть вход учителям только расписания?");
  const button = confirm.getByRole("button", { name: "Закрыть вход", exact: true });
  await expect(button).toBeDisabled();
  await confirm.getByLabel(`Наберите ${open}, чтобы подтвердить`).fill(String(open));
  const [closed] = await Promise.all([
    admin.waitForResponse((r) => r.url().includes("/api/acad/teachers/close-schedule-only/")),
    button.click(),
  ]);
  expect(closed.status(), await closed.text()).toBe(200);
  await expect(row).toContainText("вход закрыт");
  // учётка выключена, фамилия и уроки в расписании остались
  const user = await userOf(admin, probeEmail("schedule"));
  expect(user.is_active, "учётная запись выключена").toBe(false);
  await expect(row).toContainText(/\d+ ч в неделю|\d+/);
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);

  // возвращаем вход — как администратор на «Пользователях»
  await apiPatch(admin, `/api/users/${user.id}/`, { is_active: true });
  await admin.context().close();
});

test("«Учебный год» → «Предметы»: признаки, режим SAT, переключатель пишет на сервер", async ({ browser }) => {
  const kymbat = await as(browser, "director_exam");
  const diag = watch(kymbat);
  await kymbat.goto("/academic-year");
  const card = kymbat.locator(".datacard", { hasText: "Предметы" }).first();
  await expect(card).toBeVisible();
  await expect(card).toContainText(/ведутся в LMS: \d+ из \d+/);
  await expect(card).toContainText("SAT — один предмет");

  const pe = card.getByLabel("Физкультура: ведётся в LMS или только расписание");
  await expect(pe).toHaveValue("no");
  const career = card.getByLabel("Профориентация: предмет профориентации или нет");
  await expect(career).toHaveValue("yes");

  // переключение уходит запросом и возвращается тем же путём
  const [on] = await Promise.all([
    kymbat.waitForResponse((r) => /\/api\/acad\/subjects\/\d+\//.test(r.url()) && r.request().method() === "PATCH"),
    pe.selectOption("yes"),
  ]);
  expect(on.status(), await on.text()).toBe(200);
  await expect(card.getByLabel("Физкультура: ведётся в LMS или только расписание")).toHaveValue("yes");
  const [off] = await Promise.all([
    kymbat.waitForResponse((r) => /\/api\/acad\/subjects\/\d+\//.test(r.url()) && r.request().method() === "PATCH"),
    card.getByLabel("Физкультура: ведётся в LMS или только расписание").selectOption("no"),
  ]);
  expect(off.status()).toBe(200);
  await kymbat.reload();
  await expect(
    kymbat.locator(".datacard", { hasText: "Предметы" }).first().getByLabel("Физкультура: ведётся в LMS или только расписание"),
  ).toHaveValue("no");
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  await kymbat.context().close();
});
