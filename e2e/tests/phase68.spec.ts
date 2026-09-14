/**
 * Фаза 68 — администратор во всех доменах и блок «Поступление» по таблице.
 *
 * Три сценария:
 *
 * 1. Администратор входит в чужой домен: на карточке ученика домен
 *    экзаменов помечен «вы редактируете», правка сохраняется, а в истории
 *    карточки рядом с ней стоит «правил администратор».
 * 2. Карточка куратора показывает полный блок «Поступление»: телефон,
 *    почты, папку, GPA, пароли «есть / нет», документы из таблицы
 *    и попытки IELTS и SAT.
 * 3. У ученика в блоке «Поступление» только колонки таблицы: карточку
 *    «Цели поступления» убрали в фазе 70 — в карточке ровно то, что
 *    есть в таблице Асем.
 *
 * Импорт настоящей структуры файла — три листа, 18 и 19 колонок — гоняет
 * `phase65.spec.ts` тем же мастером; здесь он не дублируется.
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

test("администратор правит чужой домен, и журнал говорит об этом", async ({
  browser,
}) => {
  const page = await as(browser, "admin");
  const diag = watch(page);
  const id = await studentId(page, probeEmail("pupil02"));

  await page.goto(`/students/${id}`);
  const exams = page.locator("section.domain", { hasText: "Экзамены" }).first();
  await expect(exams).toBeVisible();
  // домен чужой, но администратор в нём редактирует
  await expect(exams).toContainText("вы редактируете");

  // значение своё на каждый прогон: иначе «менять нечего»
  const target = (6 + (Date.now() % 3) * 0.5).toFixed(1);
  const input = exams
    .locator("dt", { hasText: "Целевой балл IELTS" })
    .locator("..")
    .locator("input");
  await input.fill(target);

  const saved = page.waitForResponse(
    (response) =>
      response.url().includes("/api/batch/save/") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Сохранить" }).click();
  expect((await saved).status(), "правка уходит запросом").toBe(200);

  await page.getByRole("tab", { name: "История изменений" }).click();
  const history = page.locator("table.history");
  // строка именно этой правки: значение, домен и пометка вместе
  const row = history.locator("tr", { hasText: "Целевой балл IELTS" }).first();
  await expect(row).toContainText(target);
  await expect(row).toContainText("правил администратор");
  await expect(row).toContainText("Экзамены");

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("карточка куратора: блок «Поступление» ровно по таблице", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  const id = await studentId(page, probeEmail("pupil01"));

  await page.goto(`/students/${id}`);
  const block = page
    .locator(".card")
    .filter({ hasText: "Поступление" })
    .first();
  await expect(block).toBeVisible();

  // подписи блока с фазы 70 — в порядке колонок таблицы
  for (const label of [
    "Номер телефона",
    "Электронный адрес",
    "Электронный адрес Common App",
    "Ссылка на папку студента",
    "Средний GPA",
    "Пароль от эл. адреса",
    "Пароль от Common App",
    "Ссылка на паспорт",
    "Ссылка на табель",
    "Ссылка на рек. письмо",
  ]) {
    await expect(block, label).toContainText(label);
  }
  // пароля в блоке нет ни в каком виде — только «есть / нет»
  await expect(block).not.toContainText("ciphertext");
  // целей и статуса в блоке тоже нет: они не из таблицы
  await expect(block).not.toContainText("Целевая страна");
  await expect(block).not.toContainText("Статус по поступлению");

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("у ученика в блоке поступления только колонки таблицы", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  const diag = watch(page);

  await page.goto("/my-data");
  // карточки «Цели поступления» с фазы 70 нет ни у одной роли
  await expect(
    page.locator(".card").filter({ hasText: "Цели поступления" }),
  ).toHaveCount(0);

  const block = page
    .locator(".card")
    .filter({ hasText: "Профиль поступления" })
    .first();
  await expect(block).toBeVisible();
  await expect(block).toContainText("Телефон");
  await expect(block).not.toContainText("Специальность");

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});
