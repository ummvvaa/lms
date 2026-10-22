/**
 * Дисциплина у куратора в живом браузере.
 *
 * Два сценария:
 *
 * 1. Посещаемость: утренняя отметка своих групп строками «в школе / нет /
 *    опоздал», аналитика за период с процентом по ученикам, а дни без
 *    причины — в карточке ученика с «Оформить».
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

test("посещаемость: утренняя отметка строками, аналитика за период, дни без причины в карточке", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);

  // 1. Отметка: строка на ученика — ФИО и три кнопки рядом
  await page.goto("/attendance");
  await expect(page.locator("h1")).toContainText("Посещаемость");
  const rows = page.locator(".cmark__row");
  await expect(rows.first()).toBeVisible();
  expect(await rows.count(), "в группах куратора есть ученики").toBeGreaterThan(0);
  const name = (await rows.first().locator(".cmark__name").innerText()).trim();
  const marks = rows.first().getByRole("group", { name: `${name}: отметка` });
  await expect(marks).toBeVisible();
  for (const word of ["в школе", "нет", "опоздал"])
    await expect(marks.getByRole("button", { name: word, exact: true }), `кнопка «${word}»`).toBeVisible();

  // 2. Аналитика: период переключается, процент по ученикам и средний
  await page
    .getByRole("group", { name: "Раздел" })
    .getByRole("button", { name: "Аналитика", exact: true })
    .click();
  await expect(page).toHaveURL(/tab=stats/);
  const week = (await (await page.request.get("/api/attendance/stats/?group=all&period=week")).json()) as {
    periods: { code: string; title: string }[];
  };
  // текущий месяц — второй период после недели
  const month = week.periods.find((row) => /^\d{4}-\d{2}$/.test(row.code));
  expect(month, "месяц среди периодов аналитики").toBeTruthy();
  const loaded = page.waitForResponse(
    (r) => r.url().includes("/api/attendance/stats/") && r.url().includes(`period=${month!.code}`),
  );
  await page
    .getByRole("group", { name: "Период" })
    .getByRole("button", { name: month!.title, exact: true })
    .click();
  expect((await loaded).status(), "аналитика за месяц").toBe(200);
  const stats = (await (
    await page.request.get(`/api/attendance/stats/?group=all&period=${month!.code}`)
  ).json()) as { totals: { percent: number | null } };
  await expect(page.locator(".datacard", { hasText: "По ученикам" }).first()).toBeVisible();
  // средний процент — плиткой, только когда он посчитан: плитка «нет» ничего не говорит
  const average = page.locator(".stat", { hasText: "Средний процент" });
  if (stats.totals.percent !== null) await expect(average).toBeVisible();
  else await expect(average).toHaveCount(0);
  const mark = diag.mark();
  await page.reload();
  await expect(page.locator(".datacard", { hasText: "По ученикам" }).first()).toBeVisible();
  expect(diag.since(mark).filter((c) => c.status >= 400), "отказы API после перезагрузки").toEqual([]);

  // 3. Дни без причины — в карточке ученика: «Дни с пропусками» и «Оформить»
  const pupils = (await (
    await page.request.get("/api/students/?page_size=500")
  ).json()) as { results: { id: number }[] };
  let absent = 0;
  for (const pupil of pupils.results.slice(0, 60)) {
    const grades = (await (
      await page.request.get(`/api/acad/students/${pupil.id}/grades/`)
    ).json()) as { days?: { has_absent: boolean }[] };
    if (grades.days?.some((day) => day.has_absent)) {
      absent = pupil.id;
      break;
    }
  }
  expect(absent, "у учеников куратора есть пропуски без причины (посев)").toBeGreaterThan(0);
  await page.goto(`/students/${absent}?tab=grades`);
  const days = page.locator(".datacard").filter({
    has: page.locator(".datacard__title", { hasText: /^Дни с пропусками$/ }),
  });
  await expect(days).toBeVisible();
  const excuse = days.getByRole("button", { name: "Оформить", exact: true }).first();
  await expect(excuse).toBeVisible();
  // кнопка открывает окно причины за этот день; закрываем, ничего не оформляя
  await excuse.click();
  const dialog = page.getByRole("dialog", { name: "Уважительная причина" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Отмена", exact: true }).click();
  await expect(dialog).toBeHidden();

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

  await expect(discipline).toBeVisible();
  // у ученика без отметок и замечаний блок свёрнут в строку: форма — по кнопке
  const open = discipline.getByRole("button", { name: "Записать замечание" });
  if (await open.count()) await open.click();

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
  // «Изменить» и «Убрать» — в меню «…» строки: колонка узкая, на виду одно действие
  await contacts.getByRole("button", { name: "Ещё действия" }).first().click();
  await page.getByRole("menuitem", { name: "Изменить" }).click();
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
