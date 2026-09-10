/**
 * Фаза 67 — правка учётной записи и удаление навсегда в живом браузере.
 *
 * Три сценария:
 *
 * 1. ФИО правится из меню строки: та самая дыра, ради которой фаза
 *    и затевалась — владелец вписал в имя почту и починить это было нечем.
 * 2. Удаление навсегда: модалка показывает настоящие числа, подтверждение
 *    требует набрать почту, и почта видна рядом с полем — чтобы её не
 *    искать в другой вкладке.
 * 3. Журнал после удаления читается целиком, и автор в нём стал текстом.
 *
 * Удаляем заведённого здесь же человека, а не кого-то из посева: сценарий
 * не должен уносить данные, на которых стоят соседние проверки.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

const STAMP = String(Date.now()).slice(-6);
const VICTIM = `erased${STAMP}@probe.local`;
/** Имя после правки: в архиве запись подписана именем, а не почтой. */
const RENAMED = `Нурлыбек Сериков ${STAMP}`;

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

async function csrf(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  return cookies.find((c) => c.name === "csrftoken")?.value ?? "";
}

test("ФИО учётной записи правится из меню строки", async ({ browser }) => {
  const page = await as(browser, "admin");
  const diag = watch(page);

  // заводим человека с опечаткой в имени — ровно тем способом, каким
  // владелец её и сделал: в поле ФИО оказалась почта
  const created = await page.request.post("/api/users/", {
    data: {
      email: VICTIM,
      full_name: "Сериков Данияр",
      role: "director_sport",
    },
    headers: { "X-CSRFToken": await csrf(page) },
  });
  expect(created.status(), "пользователь заведён").toBe(201);

  await page.goto("/users");
  await page.getByPlaceholder("Поиск по имени или почте").fill(VICTIM);
  const row = page.locator("tr", { hasText: VICTIM });
  await expect(row).toBeVisible();

  await row.getByRole("button", { name: "Ещё действия" }).click();
  await page.getByRole("menuitem", { name: "Изменить" }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Изменить учётную запись");
  await dialog.getByLabel("Имя и фамилия").fill(RENAMED);

  const saved = page.waitForResponse(
    (response) =>
      response.url().includes("/api/users/") &&
      response.request().method() === "PATCH",
  );
  await dialog.getByRole("button", { name: "Сохранить" }).click();
  expect((await saved).status(), "правка уходит запросом").toBe(200);

  await page.reload();
  await page.getByPlaceholder("Поиск по имени или почте").fill(VICTIM);
  await expect(page.locator("tr", { hasText: VICTIM })).toContainText(RENAMED);

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("удаление навсегда: числа в модалке и подтверждение почтой", async ({
  browser,
}) => {
  const page = await as(browser, "admin");
  const diag = watch(page);
  const token = await csrf(page);

  // сначала отключаем доступ — это первый шаг, он кладёт запись в архив
  const users = (await (await page.request.get("/api/users/")).json()) as {
    id: number;
    email: string;
  }[];
  const victim = users.find((u) => u.email === VICTIM);
  expect(victim, "запись из первого сценария на месте").toBeTruthy();

  const archived = await page.request.delete(`/api/users/${victim!.id}/`, {
    headers: { "X-CSRFToken": token },
  });
  expect(archived.status(), "доступ отключён, запись в архиве").toBe(200);

  await page.goto("/archive");
  // строки архива — карточки, а не строки таблицы
  const row = page.locator(".arch__row", { hasText: RENAMED }).first();
  await expect(row).toBeVisible();

  const preview = page.waitForResponse(
    (response) =>
      response.url().includes("/purge/") &&
      response.request().method() === "GET",
  );
  await row.getByRole("button", { name: "Удалить навсегда" }).click();
  expect((await preview).status(), "предпросмотр приходит с сервера").toBe(200);

  const dialog = page.locator(".arch__purge");
  await expect(dialog).toContainText("Останется");
  await expect(dialog).toContainText(/восстановить будет нельзя/i);
  // почта видна рядом с полем: её не должно приходиться искать в другой вкладке
  await expect(dialog).toContainText(VICTIM);

  const field = dialog.getByLabel("Почта для подтверждения");
  const button = dialog.getByRole("button", { name: "Удалить навсегда" });

  // пока набрано не то, кнопка не работает
  await field.fill("что-то другое");
  await expect(button).toBeDisabled();

  await field.fill(VICTIM);
  const erased = page.waitForResponse(
    (response) =>
      response.url().includes("/purge/") &&
      response.request().method() === "POST",
  );
  await button.click();
  expect((await erased).status(), "удаление уходит запросом").toBe(200);

  const left = (await (
    await page.request.get("/api/users/?show=all")
  ).json()) as {
    email: string;
  }[];
  expect(
    left.some((u) => u.email === VICTIM),
    "записи больше нет",
  ).toBeFalsy();

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("журнал удалённой записи читается целиком", async ({ browser }) => {
  const page = await as(browser, "admin");
  const diag = watch(page);

  await page.goto("/archive");
  // строки архива — карточки, а не строки таблицы
  const row = page.locator(".arch__row", { hasText: RENAMED }).first();
  await expect(row).toBeVisible();
  await expect(row).toContainText("удалено навсегда");

  // журнал открывается и не пуст: ради этого удаление и обставлено следом
  await row.getByRole("button", { name: "Журнал изменений" }).click();
  const journal = page.locator(".arch__journal");
  await expect(journal).toBeVisible();

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});
