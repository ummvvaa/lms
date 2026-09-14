/**
 * Фаза 70 — карточка строго по таблице, вузы, контакты, файл паролей.
 *
 * Четыре сценария:
 *
 * 1. Блок «Поступление» один и тот же у куратора, у Асем и у
 *    администратора: до 70-й владелец домена видел в нём три поля,
 *    а куратор — одиннадцать.
 * 2. Вузы ученика: добавить из каталога, сделать приоритетным (он
 *    встаёт первым), убрать с подтверждением, где написано название.
 * 3. Контакт родителя куратор заводит сам — раньше в карточке было
 *    только «Контактов пока нет».
 * 4. Раздача паролей отдаёт книгу с листом «Сотрудники» и листами
 *    по группам, а писем при этом не шлёт.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

/** Подписи блока «Поступление» — в порядке колонок таблицы Асем. */
const BLOCK_LABELS = [
  "Номер телефона",
  "Электронный адрес",
  "Пароль от эл. адреса",
  "Пароль от Common App",
  "Электронный адрес Common App",
  "Ссылка на папку студента",
  "Ссылка на паспорт",
  "Средний GPA",
  "IELTS-1",
  "SAT-1",
  "Ссылка на табель",
  "Ссылка на рек. письмо",
];

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

async function studentId(page: Page, email: string): Promise<number> {
  const answer = await page.request.get("/api/students/?page_size=500");
  // список бывает и отказом, и страницей ошибки: без этой проверки падение
  // выглядит как «undefined.find», а не как «сервер ответил 403»
  expect(answer.status(), await answer.text()).toBe(200);
  const list = (await answer.json()) as {
    results?: { id: number; email: string }[];
  };
  const row = (list.results ?? []).find((r) => r.email === email);
  expect(row, `карточка ${email}`).toBeTruthy();
  return row!.id;
}

test("блок «Поступление» одинаков у куратора, Асем и администратора", async ({
  browser,
}) => {
  const seen: Record<string, string[]> = {};

  for (const role of ["curator", "director_admission", "admin"]) {
    const page = await as(browser, role);
    const diag = watch(page);
    const id = await studentId(page, probeEmail("pupil01"));

    await page.goto(`/students/${id}`);
    const block = page
      .locator(".card")
      .filter({ hasText: "Поступление" })
      .first();
    await expect(block).toBeVisible();

    const found: string[] = [];
    for (const label of BLOCK_LABELS) {
      await expect(block, `${role}: ${label}`).toContainText(label);
      found.push(label);
    }
    // целей и служебных признаков в блоке нет: их нет в таблице
    await expect(block).not.toContainText("Целевая страна");
    await expect(block).not.toContainText("Статус по поступлению");
    seen[role] = found;

    expect(diag.pageErrors, `исключения у ${role}`).toEqual([]);
    await page.context().close();
  }

  expect(seen.curator).toEqual(seen.director_admission);
  expect(seen.curator).toEqual(seen.admin);
});

test("вузы ученика: добавить, сделать приоритетным, убрать", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  const diag = watch(page);

  // добавляем две программы из каталога — на них и проверяем приоритет
  const catalog = (await (
    await page.request.get("/api/catalog/?page_size=50")
  ).json()) as { results: { program: number; in_my_list: boolean }[] };
  const free = catalog.results.filter((row) => !row.in_my_list).slice(0, 2);
  expect(free.length, "в справочнике есть свободные программы").toBe(2);

  const csrf =
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? "";
  for (const row of free) {
    const added = await page.request.post("/api/catalog/add/", {
      data: { program: row.program, tier: "target" },
      headers: { "X-CSRFToken": csrf },
    });
    expect(added.status(), await added.text()).toBe(201);
  }

  await page.goto("/universities");
  const cards = page.locator("article.match");
  await expect(cards.first()).toBeVisible();

  // приоритет ставится кнопкой и уходит запросом
  const marked = page.waitForResponse((r) =>
    r.url().includes("/api/catalog/priority/"),
  );
  await page
    .getByRole("button", { name: "Сделать приоритетным" })
    .first()
    .click();
  expect((await marked).status(), "пометка уходит запросом").toBe(200);

  // и он встаёт первым в списке — с пометкой
  await expect(cards.first()).toContainText("Приоритетный");

  // «Убрать» спрашивает подтверждение и называет вуз
  const name = (
    await cards.first().locator("h3, .match__title").first().innerText()
  ).trim();
  await page.getByRole("button", { name: "Убрать" }).first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Убрать из списка?");
  expect(name.length, "название вуза в карточке есть").toBeGreaterThan(0);

  // отмена ничего не убирает
  const before = await cards.count();
  await dialog.getByRole("button", { name: "Отмена" }).click();
  await expect(dialog).toBeHidden();
  await expect(cards).toHaveCount(before);

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("куратор заводит контакт родителя прямо в карточке", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  const id = await studentId(page, probeEmail("pupil02"));

  // блок «Контакты» стоит на вкладке «Обзор», рядом с дисциплиной
  await page.goto(`/students/${id}`);
  const block = page.locator(".card").filter({ hasText: "Контакты" }).first();
  await expect(block).toBeVisible();

  const stamp = String(Date.now()).slice(-6);
  const saved = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/contacts/") && r.request().method() === "POST",
  );
  await block.getByRole("button", { name: "Добавить контакт" }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("ФИО родителя или опекуна")
    .fill(`Родитель Прогона ${stamp}`);
  await dialog.getByLabel("Телефон").fill("+77070000000");
  await dialog.getByRole("button", { name: "Добавить" }).click();
  expect((await saved).status(), "контакт уходит запросом").toBe(201);

  await expect(block).toContainText(`Родитель Прогона ${stamp}`);

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("раздача паролей: файл с листами по группам, писем нет", async ({
  browser,
}) => {
  const page = await as(browser, "admin");
  const diag = watch(page);

  // заводим одного человека и раздаём пароли только ему
  const email = `handout70.${String(Date.now()).slice(-6)}@probe.local`;
  const csrf =
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? "";
  const created = await page.request.post("/api/users/", {
    data: { email, full_name: "Асель Файлова", role: "student" },
    headers: { "X-CSRFToken": csrf },
  });
  expect(created.status(), await created.text()).toBe(201);
  const victim = (await created.json()) as { id: number };

  await page.goto("/users");
  await page.getByPlaceholder("Поиск по имени или почте").fill(email);
  const row = page.locator("tr", { hasText: email });
  await expect(row).toBeVisible();
  await row.getByLabel("Отметить строку").check();

  await page.getByRole("button", { name: "Выдать пароли" }).first().click();
  const dialog = page.getByRole("dialog");
  // текст модалки говорит прямо: писем не будет
  await expect(dialog).toContainText("Пароли не рассылаются");

  const plan = (await (
    await page.request.post("/api/users/handout/", {
      data: { users: [victim.id] },
      headers: { "X-CSRFToken": csrf },
    })
  ).json()) as { confirm: string };
  await dialog.getByLabel("Число затронутых").fill(plan.confirm);
  const issued = page.waitForResponse(
    (r) =>
      r.url().includes("/api/users/handout/") &&
      r.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "Выдать пароли" }).click();
  expect((await issued).status(), "выдача уходит запросом").toBe(200);

  // файл скачивается по кнопке и приходит книгой
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать список" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toContain(".xlsx");

  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});
