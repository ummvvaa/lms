/**
 * Сотрудники и 8–10: параллель у группы, фильтры, ссылка на пароль,
 * перевод на следующий год.
 *
 * Ученик прогона 8–10 — «Прогон Ерлан» в LISBON (9 параллель), его заводит
 * посев. Асем его не видит нигде; Салтанат находит фильтром по параллели;
 * куратор в карточке видит учёбу без вкладок поступления и выдаёт ссылку
 * на пароль на экране; администратор задаёт параллель группе и видит
 * предпросмотр перевода года. Сам перевод здесь не запускается: он
 * переводит всю школу контура, а проверяют его тесты сервера.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";


test.describe.configure({ timeout: 180_000 });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  return page;
}

async function juniorId(page: Page): Promise<number> {
  const list = await (await page.request.get("/api/students/?search=Ерлан&parallel=9")).json();
  const row = (list.results as { id: number; full_name: string }[]).find((r) => r.full_name === "Прогон Ерлан");
  expect(row, "ученик 8–10 посева на месте").toBeTruthy();
  return row!.id;
}

test("Асем не видит 8–10, Салтанат находит их фильтром по параллели", async ({ browser }) => {
  const saltanat = await as(browser, "director_behavior");
  const id = await juniorId(saltanat);
  await saltanat.goto("/table");
  const parallel = saltanat.getByRole("combobox", { name: "Параллель" });
  await expect(parallel).toBeVisible();
  const filtered = saltanat.waitForResponse((r) => r.url().includes("/api/students/") && r.url().includes("parallel=9"));
  await parallel.selectOption("9");
  expect((await filtered).status()).toBe(200);
  await expect(saltanat.locator("main")).toContainText("Прогон Ерлан");
  await saltanat.context().close();

  const asem = await as(browser, "director_admission");
  expect((await asem.request.get(`/api/students/${id}/`)).status(), "карточка 8–10 у Асем").toBe(404);
  const list = await (await asem.request.get("/api/students/?page_size=500")).json();
  expect((list.results as { full_name: string }[]).map((r) => r.full_name)).not.toContain("Прогон Ерлан");
  await asem.goto("/table");
  await expect(asem.getByRole("combobox", { name: "Параллель" }), "у Асем выбирать нечего").toHaveCount(0);
  await asem.context().close();
});

test("куратор: карточка 8–10 без поступления, ссылка на пароль на экране", async ({ browser }) => {
  const curator = await as(browser, "curator");
  const id = await juniorId(curator);
  await curator.goto(`/students/${id}`);
  await expect(curator.locator("h1")).toContainText("Прогон Ерлан");
  const tabs = curator.locator(".screentabs, [role=tablist]").first();
  await expect(tabs).toContainText("Успеваемость");
  for (const tab of ["Экзамены", "Документы", "Вузы", "Задачи"]) await expect(tabs, tab).not.toContainText(tab);

  const issued = curator.waitForResponse((r) => r.url().includes(`/api/students/${id}/password-link/`));
  await curator.getByRole("button", { name: "Ссылка на пароль" }).click();
  expect((await issued).status()).toBe(200);
  const dialog = curator.getByRole("dialog");
  await expect(dialog).toContainText("probe_junior");
  await expect(dialog).toContainText("Письма не было");
  await expect(dialog.locator("input")).toHaveValue(/\/set-password\?token=/);
  await curator.context().close();
});

test("администратор: параллель при заведении группы и предпросмотр перевода года", async ({ browser }) => {
  const admin = await as(browser, "admin");
  const code = `P8${Date.now() % 100000}`;
  await admin.goto("/users?tab=groups");
  await admin.getByRole("button", { name: "Завести группу" }).click();
  await admin.getByLabel("Код группы").fill(code);
  await admin.getByLabel("Параллель").first().selectOption("8");
  const made = admin.waitForResponse((r) => r.url().endsWith("/api/groups/") && r.request().method() === "POST");
  await admin.getByRole("button", { name: "Завести", exact: true }).click();
  expect((await made).status()).toBe(201);
  await admin.reload();
  await expect(admin.locator(".rows__item", { hasText: code })).toContainText("8 параллель");

  const plan = admin.waitForResponse((r) => r.url().includes("/api/year-transfer/"));
  await admin.getByRole("button", { name: "Перевести на следующий год" }).click();
  expect((await plan).status()).toBe(200);
  const dialog = admin.getByRole("dialog");
  await expect(dialog).toContainText("Перевод за");
  await expect(dialog).toContainText(`${code}`);
  const run = dialog.getByRole("button", { name: "Перевести", exact: true });
  if (await run.count()) {
    await dialog.getByLabel("Число учеников").fill("0");
    await expect(run, "без верного числа перевод не запускается").toBeDisabled();
  }
  await admin.keyboard.press("Escape");

  // уборка: группа без учеников уходит в архив
  const groups = await (await admin.request.get("/api/groups/?page_size=200")).json();
  const mine = (groups.results as { id: number; code: string }[]).find((g) => g.code === code);
  if (mine) {
    const csrf = (await admin.context().cookies()).find((c) => c.name === "csrftoken")!.value;
    await admin.request.delete(`/api/groups/${mine.id}/`, { headers: { "X-CSRFToken": csrf } });
  }
  await admin.context().close();
});

test("администратор: фильтр по параллели в «Пользователях»", async ({ browser }) => {
  const admin = await as(browser, "admin");
  await admin.goto("/users");
  const filtered = admin.waitForResponse((r) => r.url().includes("/api/users/") && r.url().includes("parallel=9"));
  await admin.getByLabel("Параллель").selectOption("9");
  expect((await filtered).status()).toBe(200);
  await expect(admin.locator("main")).toContainText("probe_junior");
  await admin.context().close();
});
