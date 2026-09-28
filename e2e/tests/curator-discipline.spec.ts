/**
 * Дисциплина у куратора в живом браузере.
 *
 * Два сценария:
 *
 * 1. Посещаемость группы за день: лист открывается «все были», снимаем
 *    отметку, пишем причину, сохраняем — и число в карточке ученика
 *    меняется, потому что процент считается из дней.
 * 2. Контакты родителя правятся прямо в карточке, и замечание пишется
 *    словами.
 *
 * Кнопка считается рабочей, только если по клику ушёл запрос, ответ 2xx
 * и в консоли пусто — за этим следит `watch()`.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

/** Вчера — по местным часам: в UTC вечером получился бы позавчерашний день. */
const YESTERDAY = (() => {
  const date = new Date();
  date.setDate(date.getDate() - 1);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
})();

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

async function studentId(page: Page, email: string): Promise<number> {
  const list = (await (
    await page.request.get("/api/students/?page_size=500")
  ).json()) as { results: { id: number; email: string }[] };
  const row = list.results.find((r) => r.email === email);
  expect(row, `карточка ${email}`).toBeTruthy();
  return row!.id;
}

test("посещаемость: день матрицей по урокам, месяц с процентом и днями без причины", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);

  await page.goto("/attendance");
  await expect(page.locator("h1")).toContainText("Посещаемость");

  // день выбираем вчерашний: у посева там отмеченные уроки
  await page.getByLabel("День").fill(YESTERDAY);
  const grid = page.locator(".matrix").first();
  await expect(grid).toBeVisible();
  const rows = grid.locator("tbody tr");
  expect(await rows.count(), "в группе есть ученики").toBeGreaterThan(0);
  await expect(page.locator(".statrow")).toContainText("Не отмечено");
  await expect(page.locator("body")).toContainText("«н» — не был");

  // месяц: процент по урокам и дни без причины с «Оформить»
  await page.getByRole("button", { name: "Месяц", exact: true }).click();
  await expect(page).toHaveURL(/view=month/);
  await expect(page.locator("main")).toContainText("Посещаемость");
  const days = page.locator(".datacard", { hasText: "Дни без причины" }).first();
  await expect(days).toBeVisible();
  const mark = diag.mark();
  await page.reload();
  await expect(page.locator(".matrix").first()).toBeVisible();
  expect(diag.since(mark).filter((c) => c.status >= 400)).toEqual([]);

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("карточка: замечание словами и правка контакта родителя", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  const id = await studentId(page, probeEmail("pupil01"));

  await page.goto(`/students/${id}`);
  const discipline = page
    .locator(".card")
    .filter({ hasText: "Дисциплина" })
    .first();

  // текст свой на каждый прогон: повторный прогон на живой базе не должен
  // проходить за счёт замечания, оставленного прошлым
  const remark = `Опоздал на первый урок ${Date.now()}`;
  await discipline.getByLabel("Замечание").fill(remark);
  const saved = page.waitForResponse(
    (response) =>
      response.url().includes("/remarks/") &&
      response.request().method() === "POST",
  );
  await discipline.getByRole("button", { name: "Записать" }).click();
  expect((await saved).status(), "замечание уходит запросом").toBe(201);
  await expect(discipline).toContainText(remark);

  // контакт родителя правится тут же
  const contacts = page
    .locator(".card")
    .filter({ hasText: "Контакты" })
    .first();
  const phone = `+7701555${String(Date.now()).slice(-4)}`;
  // кнопка называется «Изменить» с фазы 70: рядом с ней появилась «Убрать»
  await contacts.getByRole("button", { name: "Изменить" }).first().click();
  await contacts
    .getByLabel(/Телефон/)
    .first()
    .fill(phone);
  const patched = page.waitForResponse(
    (response) =>
      response.url().includes("/contacts/") &&
      response.request().method() === "PATCH",
  );
  await contacts.getByRole("button", { name: "Сохранить" }).click();
  expect((await patched).status(), "контакт правится запросом").toBe(200);
  await expect(contacts).toContainText(phone);

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});
