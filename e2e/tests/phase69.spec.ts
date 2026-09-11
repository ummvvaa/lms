/**
 * Фаза 69 — экран «Пользователи» в день раздачи паролей.
 *
 * Четыре сценария:
 *
 * 1. Чипы фильтруют список, счётчик чипа сходится с числом строк,
 *    выбранный фильтр остаётся в адресе после перезагрузки.
 * 2. Выдача паролей: модалка показывает разбивку, кнопка не работает
 *    без набранного числа, отмена ничего не меняет.
 * 3. Тост виден внизу и исчезает; в ячейке действий после него ничего
 *    не остаётся, и строка не меняет высоту.
 * 4. Меню последней строки открывается вверх и не обрезается краем.
 *
 * Пароли никому не сбрасываем: выдача гоняется по одной отмеченной
 * строке, заведённой здесь же.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

const STAMP = String(Date.now()).slice(-6);
const VICTIM = `handout${STAMP}@probe.local`;

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

async function csrf(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  return cookies.find((c) => c.name === "csrftoken")?.value ?? "";
}

test("чипы фильтруют список и остаются в адресе", async ({ browser }) => {
  const page = await as(browser, "admin");
  const diag = watch(page);

  await page.goto("/users");
  const chips = page.locator(".users__chips .cchip");
  await expect(chips.first()).toBeVisible();
  // чипов пять: «Все» и четыре состояния пароля
  await expect(chips).toHaveCount(5);

  const waiting = chips.filter({ hasText: "Ждёт смены пароля" });
  const counter = Number((await waiting.locator("b").innerText()).trim());

  const filtered = page.waitForResponse(
    (response) =>
      response.url().includes("/api/users/") &&
      response.url().includes("state="),
  );
  await waiting.click();
  expect((await filtered).status(), "фильтр уходит запросом").toBe(200);

  await expect(waiting).toHaveClass(/cchip--on/);
  await expect(page.locator("tbody tr")).toHaveCount(counter);
  // фильтр в адресе: к набору можно вернуться
  expect(page.url()).toContain("state=waiting");

  await page.reload();
  await expect(
    page.locator(".users__chips .cchip", { hasText: "Ждёт смены пароля" }),
  ).toHaveClass(/cchip--on/);

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("выдача паролей: разбивка, защита и отмена", async ({ browser }) => {
  const page = await as(browser, "admin");
  const diag = watch(page);

  // заводим одного человека — на нём и проверяем выдачу
  const created = await page.request.post("/api/users/", {
    data: { email: VICTIM, full_name: "Асель Раздача", role: "student" },
    headers: { "X-CSRFToken": await csrf(page) },
  });
  expect(created.status(), await created.text()).toBe(201);

  await page.goto("/users");
  await page.getByPlaceholder("Поиск по имени или почте").fill(VICTIM);
  const row = page.locator("tr", { hasText: VICTIM });
  await expect(row).toBeVisible();
  await row.getByLabel("Отметить строку").check();

  const planned = page.waitForResponse((r) =>
    r.url().includes("/api/users/handout/"),
  );
  await page.getByRole("button", { name: "Выдать пароли" }).first().click();
  expect((await planned).status(), "предпросмотр приходит с сервера").toBe(200);

  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Действие по отмеченным строкам");
  await expect(dialog).toContainText("Кого затронет");
  await expect(dialog).toContainText("Пароль не задан");

  // пока число не набрано, кнопка не работает
  const confirm = dialog.getByRole("button", { name: "Выдать пароли" });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel("Число затронутых").fill("99");
  await expect(confirm).toBeDisabled();

  // отмена ничего не меняет
  await dialog.getByRole("button", { name: "Отмена" }).click();
  await expect(dialog).toBeHidden();
  const after = (await (
    await page.request.get(`/api/users/?search=${VICTIM}`)
  ).json()) as { results: { password_state: string }[] };
  expect(after.results[0].password_state, "пароль не выдан").toBe(
    "no_password",
  );

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("тост виден внизу, а в ячейке действий ничего не остаётся", async ({
  browser,
}) => {
  const page = await as(browser, "admin");
  const diag = watch(page);

  await page.goto("/users");
  await page.getByPlaceholder("Поиск по имени или почте").fill(VICTIM);
  const row = page.locator("tr", { hasText: VICTIM });
  await expect(row).toBeVisible();
  const before = (await row.boundingBox())!.height;

  await row.getByRole("button", { name: "Ещё действия" }).click();
  await page.getByRole("menuitem", { name: "Выслать письмо заново" }).click();

  const toast = page.locator("[data-sonner-toast]").first();
  await expect(toast).toBeVisible();
  // тост внизу экрана, а не поверх строк таблицы
  const box = (await toast.boundingBox())!;
  const view = page.viewportSize()!;
  expect(box.y, "тост внизу экрана").toBeGreaterThan(view.height / 2);

  // в ячейке действий плашки не появилось, и строка не подросла.
  // Меню ждём закрытым: пока оно открыто, блокировка прокрутки меняет
  // ширину страницы, и высота строки гуляет на доли пикселя
  await expect(page.getByRole("menu")).toBeHidden();
  await expect(row).not.toContainText("Ссылка отправлена");
  const after = (await row.boundingBox())!.height;
  expect(Math.abs(after - before), "высота строки не изменилась").toBeLessThan(
    1,
  );

  // и он уходит сам
  await expect(toast).toBeHidden({ timeout: 15_000 });

  // пароль и ссылку скопировать надо — они открываются окном поверх
  // таблицы, а не карточкой внутри ячейки, которая растила строку
  await row.getByRole("button", { name: "Выдать пароль" }).click();
  const shown = page.getByRole("dialog");
  await expect(shown).toContainText("Временный пароль");
  await expect(row).not.toContainText("Временный пароль");
  expect(
    Math.abs((await row.boundingBox())!.height - before),
    "окно не двигает строку",
  ).toBeLessThan(1);

  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("меню последней строки открывается вверх и не обрезается", async ({
  browser,
}) => {
  const page = await as(browser, "admin");
  const diag = watch(page);

  await page.goto("/users");
  const rows = page.locator("tbody tr");
  await expect(rows.first()).toBeVisible();
  const last = rows.last();
  await last.scrollIntoViewIfNeeded();

  await last.getByRole("button", { name: "Ещё действия" }).click();
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();

  // меню целиком помещается в окно: ни верх, ни низ не срезаны
  const box = (await menu.boundingBox())!;
  const view = page.viewportSize()!;
  expect(box.y, "верх меню виден").toBeGreaterThanOrEqual(0);
  expect(box.y + box.height, "низ меню виден").toBeLessThanOrEqual(view.height);

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});
