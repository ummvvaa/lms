/**
 * Кабинет ученика 8–10: вход логином, меню без поступления, главная
 * про учёбу, олимпиады и спорт, помощник про учёбу, личная почта.
 *
 * Ученик прогона без почты — `probe_junior` (заводит create_probe_users),
 * его карточку в девятой группе LISBON связывает посев (`seed.spec.ts`).
 * Поступление у 8–10 закрыто не только в меню: прямой адрес уводит на
 * главную, а ручка API отвечает 403 с кодом `parallel_closed`.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { probePassword } from "../helpers/roles";
import { watch } from "../helpers/session";

test.describe.configure({ timeout: 180_000 });

const LOGIN = "probe_junior";
const ADMISSION = ["Каталог вузов", "Мои вузы", "Подбор вузов", "План поступления", "Стипендии", "Эссе", "Профтест", "Портфолио", "Мой путь"];

async function asJunior(browser: Browser): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  await page.goto("/login");
  await page.getByLabel("Почта или логин").fill(LOGIN);
  await page.getByLabel("Пароль").fill(probePassword());
  const signed = page.waitForResponse((r) => r.url().includes("/api/auth/login/"));
  await page.getByRole("button", { name: "Войти" }).click();
  expect((await signed).status(), "вход логином").toBe(200);
  await expect(page).toHaveURL(/\/dashboard/);
  return page;
}

test("вход логином: меню 8–10 без поступления, главная про учёбу", async ({ browser }) => {
  const page = await asJunior(browser);
  const diag = watch(page);
  await page.reload();
  const menu = page.locator(".shell__menu");
  for (const item of ["Главная", "Расписание", "Оценки", "Календарь", "Олимпиады", "Спорт"])
    await expect(menu, `пункт «${item}»`).toContainText(item);
  await expect(menu).toContainText("Достижения");
  for (const item of ["Поступление", ...ADMISSION])
    await expect(menu, `пункт поступления «${item}»`).not.toContainText(item);

  await expect(page.locator("h1")).toContainText("Главная");
  for (const title of ["Средний балл", "Посещаемость", "Ближайший СОР", "Достижения"])
    await expect(page.locator("main"), `число «${title}»`).toContainText(title);
  for (const card of ["Уроки сегодня", "Скоро", "Последние оценки"])
    await expect(page.locator(".datacard", { hasText: card }).first()).toBeVisible();
  const text = (await page.locator("main").innerText()).toLowerCase();
  for (const word of ["ielts", "sat", "вуз", "готовность"]) expect(text, `«${word}» на главной 8–10`).not.toContain(word);
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.since(0).filter((c) => c.status >= 400), "отказы API на главной").toEqual([]);
  await page.context().close();
});

test("поступление закрыто и по адресу, и в API", async ({ browser }) => {
  const page = await asJunior(browser);
  for (const path of ["/catalog", "/universities", "/my-data", "/journey", "/prep", "/essays"]) {
    await page.goto(path);
    await expect(page, `${path} уводит на главную`).toHaveURL(/\/dashboard/);
  }
  for (const url of ["/api/catalog/", "/api/student-universities/", "/api/portfolio/", "/api/prep/center/exams/"]) {
    const response = await page.request.get(url);
    expect(response.status(), url).toBe(403);
    expect((await response.json()).code, url).toBe("parallel_closed");
  }
  await page.context().close();
});

test("олимпиады: запись уходит на проверку и видна после перезагрузки", async ({ browser }) => {
  const page = await asJunior(browser);
  const title = `Олимпиада прогона ${Date.now()}`;
  await page.goto("/olympiads");
  await expect(page.locator("h1")).toContainText("Олимпиады");
  await page.getByRole("button", { name: "Добавить олимпиаду" }).click();
  await page.locator(".propose__form").getByLabel("Название").fill(title);
  const sent = page.waitForResponse((r) => r.url().includes("/api/suggestions/propose/"));
  await page.getByRole("button", { name: "Отправить на проверку" }).click();
  expect((await sent).status(), "предложение принято").toBe(201);
  await page.reload();
  await expect(page.locator(".rows__item", { hasText: title })).toContainText("ждёт проверки");

  await page.goto("/sport");
  await expect(page.locator("h1")).toContainText("Спорт");
  await expect(page.locator(".datacard", { hasText: "Соревнования" }).first()).toBeVisible();
  await page.context().close();
});

test("помощник: кнопки про учёбу, ответ без поступления", async ({ browser }) => {
  const page = await asJunior(browser);
  await page.getByRole("button", { name: "Открыть помощника" }).first().click();
  const quick = page.locator(".aw__quick");
  for (const button of ["Что у меня на этой неделе", "Как подтянуть предмет", "Как считается итог четверти", "План подготовки к СОЧ"])
    await expect(quick, `кнопка «${button}»`).toContainText(button);
  await expect(quick).not.toContainText("вуз");
  const answered = page.waitForResponse((r) => r.url().includes("/api/assistant/ask/"));
  await quick.getByRole("button", { name: "Как считается итог четверти" }).click();
  expect((await answered).status()).toBe(200);
  await expect(page.locator(".aw")).toContainText("вес");
  await page.context().close();
});

test("профиль: логин вместо почты и личная почта с подтверждением", async ({ browser }) => {
  const page = await asJunior(browser);
  await page.goto("/profile");
  await expect(page.locator("main")).toContainText(LOGIN);
  const address = `junior.${Date.now()}@example.com`;
  await page.getByRole("button", { name: "Добавить" }).click();
  await page.getByLabel("Личная почта").fill(address);
  const linked = page.waitForResponse((r) => r.url().includes("/api/auth/identities/link/"));
  await page.getByRole("button", { name: "Прислать письмо" }).click();
  expect((await linked).status()).toBe(201);
  await page.reload();
  await expect(page.locator("main")).toContainText(address);
  await expect(page.locator("main")).toContainText("ждёт подтверждения");
  await page.context().close();
});
