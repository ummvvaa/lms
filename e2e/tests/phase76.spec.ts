/**
 * Фаза 76 — телефон: остаток после пересъёмки.
 *
 * Всё на 390×844:
 *
 * 1. Вкладки: лента начинается с первой вкладки, активная видна; плашка
 *    не тянет страницу вбок (очередь куратора).
 * 2. Помощник: на телефоне герб в шапке, плавающей кнопки нет; окно
 *    открывается из шапки.
 * 3. «Мои документы» у ученика: названия видны; профтест без дубля;
 *    у Салтанат в таблице подпись статуса, а не код.
 * 4. Очередь на дашборде директора не выше кураторской плотности.
 * 5. Панели фильтров свёрнуты в строку и раскрываются; «Действия» ради
 *    одного пункта нет — вторая кнопка остаётся кнопкой.
 * 6. Цели касания не меньше 44 px: меню строки, малые кнопки, «подробнее».
 * 7. Обрыв связи: экран с сообщением и «Повторить», а не пустота.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 300_000 });

const PHONE = { width: 390, height: 844 };

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    viewport: PHONE,
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  await page.addInitScript(() =>
    window.localStorage.setItem("first-run-seen", "1"),
  );
  return page;
}

async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(300);
}

async function curatorStudentId(page: Page): Promise<number> {
  const list = (await (
    await page.request.get("/api/curator/students/")
  ).json()) as { results?: { id: number }[] };
  return (list.results ?? [])[0]?.id ?? 0;
}

const docWidth = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth);

test("вкладки начинаются с первой, активная видна; плашка не тянет страницу", async ({
  browser,
}) => {
  const student = await as(browser, "student");
  await student.goto("/my-data");
  await settle(student);
  const tabs = await student.locator(".tabs__list").evaluate((el) => {
    const first = el.querySelector(".tabs__tab") as HTMLElement;
    const own = el.getBoundingClientRect();
    return {
      firstLeft: first.getBoundingClientRect().left - own.left,
      justify: getComputedStyle(el).justifyContent,
      scrollLeft: el.scrollLeft,
    };
  });
  expect(tabs.firstLeft, "первая вкладка у левого края").toBeGreaterThanOrEqual(0);
  expect(tabs.justify).toBe("flex-start");
  expect(await docWidth(student)).toBeLessThanOrEqual(PHONE.width);
  await student.context().close();

  const curator = await as(browser, "curator");
  await curator.goto("/queue");
  await settle(curator);
  await expect(curator.locator(".notice--folded").first()).toBeVisible();
  expect(await docWidth(curator), "очередь не шире экрана").toBeLessThanOrEqual(PHONE.width);
  await curator.goto("/journal");
  await settle(curator);
  expect(await docWidth(curator), "журнал не шире экрана").toBeLessThanOrEqual(PHONE.width);
  await curator.context().close();
});

test("помощник на телефоне — в шапке, плавающей кнопки нет", async ({ browser }) => {
  const page = await as(browser, "director_exam");
  const diag = watch(page);
  await page.goto("/dashboard");
  await settle(page);
  await expect(page.locator(".aw__fab")).toHaveCount(0);
  const button = page.locator(".shell__assistbtn");
  await expect(button).toBeVisible();
  const box = await button.boundingBox();
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  await button.click();
  await expect(page.locator(".aw")).toBeVisible();
  await expect(page.locator(".aw__title")).toHaveText("Помощник");
  // запас снизу — только под бар: кнопки больше нет
  const pad = await page
    .locator(".shell__screen")
    .evaluate((el) => parseFloat(getComputedStyle(el).paddingBottom));
  expect(pad).toBeLessThan(120);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("названия документов, профтест без дубля, статус подписью", async ({ browser }) => {
  const student = await as(browser, "student");
  await student.goto("/my-data?tab=documents");
  await settle(student);
  const rows = student.locator(".rows__item");
  if ((await rows.count()) > 0) {
    const label = rows.first().locator(".rows__label");
    await expect(label).toBeVisible();
    // подпись не накрыта липкой панелью: её верх ниже верха строки, а не под кнопками
    const overlap = await rows.first().evaluate((row) => {
      const label = row.querySelector(".rows__label")!.getBoundingClientRect();
      const actions = row.querySelector(".rows__actions")?.getBoundingClientRect();
      return actions ? actions.top < label.bottom && actions.bottom > label.top : false;
    });
    expect(overlap, "кнопки не лежат на названии").toBe(false);
  }
  await student.goto("/career");
  await settle(student);
  const closed = student.locator(".dimmed .hero__note").first();
  if ((await closed.count()) > 0) {
    const text = (await closed.textContent()) ?? "";
    const phrase = "бессмысленный результат";
    expect(text.split(phrase).length - 1, "объяснение один раз").toBeLessThanOrEqual(1);
  }
  await student.context().close();

  const behavior = await as(browser, "director_behavior");
  await behavior.goto("/table");
  await settle(behavior);
  const cards = behavior.locator(".tblcard");
  await expect(cards.first()).toBeVisible();
  const text = await behavior.locator(".tblcards").textContent();
  expect(text).not.toMatch(/can_execute|needs_supervision|critical/);
  await behavior.context().close();
});

test("очередь на дашборде директора — плотность кураторской", async ({ browser }) => {
  const page = await as(browser, "director_exam");
  await page.goto("/dashboard");
  await settle(page);
  const row = page.locator(".pqueue__row").first();
  if ((await row.count()) > 0) {
    const box = await row.boundingBox();
    expect(box?.height ?? 999, "строка очереди не выше 200 px").toBeLessThanOrEqual(200);
    const values = await row.locator(".pqueue__values").evaluate((el) => getComputedStyle(el).flexDirection);
    expect(values).toBe("row");
  }
  await page.context().close();
});

test("панели фильтров свёрнуты и раскрываются; одна кнопка не прячется в меню", async ({
  browser,
}) => {
  const admin = await as(browser, "admin");
  await admin.goto("/users");
  await settle(admin);
  const fold = admin.locator(".fold").first();
  await expect(fold).toBeVisible();
  await expect(admin.getByPlaceholder("Поиск по имени или почте")).toHaveCount(0);
  await fold.getByRole("button", { name: "Развернуть" }).click();
  await expect(admin.getByPlaceholder("Поиск по имени или почте")).toBeVisible();
  // первая строка списка начинается выше, чем до 76-й (было 430 px)
  await fold.getByRole("button", { name: "Свернуть" }).click();
  const top = await admin.locator(".users__table tbody tr").first().evaluate(
    (el) => el.getBoundingClientRect().top + window.scrollY,
  );
  expect(top, "список начинается в первом экране").toBeLessThan(430);
  await admin.context().close();

  const student = await as(browser, "student");
  await student.goto("/universities");
  await settle(student);
  await expect(student.locator(".head__actions").getByRole("button", { name: "Действия" })).toHaveCount(0);
  await expect(student.locator(".head__actions").getByRole("button", { name: /Что откроется/ })).toBeVisible();
  await student.context().close();
});

test("цели касания не меньше 44 px", async ({ browser }) => {
  const page = await as(browser, "admin");
  await page.goto("/users");
  await settle(page);
  for (const selector of [".rowmenu__button", ".notice__more", ".fold__head button", ".shell__searchbtn"]) {
    const box = await page.locator(selector).first().boundingBox();
    expect(box?.height ?? 0, `${selector} по высоте`).toBeGreaterThanOrEqual(44);
  }
  await page.context().close();
});

test("обрыв связи: сообщение и «Повторить», а не пустой экран", async ({ browser }) => {
  const page = await as(browser, "curator");
  await page.goto("/dashboard");
  await settle(page);
  let blocked = true;
  // только запросы к серверу: шаблон `**/api/**` ловил и модули Vite
  // (`/src/api/hooks.ts`), и приложение не загружалось вовсе — так и получался
  // пустой экран на снимках 74-й и 76-й
  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    (route) => (blocked ? route.abort("connectionrefused") : route.continue()),
  );
  await page.goto("/queue").catch(() => undefined);
  const offline = page.locator(".offline");
  await expect(offline).toBeVisible({ timeout: 30_000 });
  await expect(offline).toContainText("Нет связи с сервером");
  const retry = offline.getByRole("button", { name: "Повторить" });
  await expect(retry).toBeVisible();
  // связь вернулась — «Повторить» приводит в кабинет без нового входа
  blocked = false;
  await retry.click();
  await expect(page.locator(".tabbar")).toBeVisible({ timeout: 30_000 });
  await page.context().close();
});
