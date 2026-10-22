/**
 * Экран входа по макету владельца (11.10.2026) на 1440 и 390.
 *
 * Логотип и название над карточкой на полотне, в карточке только форма:
 * «Почта или логин», «Пароль» с глазком, одна кнопка «Войти», под ней тихая
 * ссылка «Забыли пароль?» и мелкая «Я выпускник, у меня нет пароля». Справа
 * вверху переключатель «Рус · Қаз · Eng», выбор помнится на устройстве;
 * слева внизу адрес сайта. Вход под учеником прогона проходит.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { byKey } from "../helpers/roles";
import { watch } from "../helpers/session";

test.describe.configure({ timeout: 120_000 });

const SIZES: { name: string; width: number; height: number }[] = [
  { name: "1440", width: 1440, height: 900 },
  { name: "390", width: 390, height: 844 },
];

async function open(browser: Browser, size: (typeof SIZES)[number]): Promise<Page> {
  const phone = size.width <= 640;
  const context = await browser.newContext({
    viewport: { width: size.width, height: size.height },
    ...(phone ? { isMobile: true, hasTouch: true, deviceScaleFactor: 2 } : {}),
  });
  const page = await context.newPage();
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Войти", exact: true })).toBeVisible();
  return page;
}

for (const size of SIZES) {
  test(`вход на ${size.name}: логотип над карточкой, одна кнопка, тихие ссылки`, async ({ browser }) => {
    const page = await open(browser, size);
    const diag = watch(page);

    const logo = page.locator(".login__logo");
    const card = page.locator(".login__card");
    await expect(logo).toBeVisible();
    await expect(page.locator(".login__title")).toBeVisible();
    const [logoBox, cardBox] = await Promise.all([logo.boundingBox(), card.boundingBox()]);
    expect((logoBox?.y ?? 0) + (logoBox?.height ?? 0), "логотип стоит над карточкой").toBeLessThanOrEqual(
      (cardBox?.y ?? 0) + 1,
    );

    // карточка — только форма: два поля, глазок у пароля, одна кнопка
    await expect(card.getByLabel("Почта или логин", { exact: true })).toBeVisible();
    await expect(card.getByLabel("Пароль", { exact: true })).toBeVisible();
    await expect(card.getByRole("button", { name: "Показать пароль" })).toBeVisible();
    await expect(card.locator("button[type='submit']")).toHaveCount(1);
    await expect(page.getByText("Учётные записи заводит администратор")).toHaveCount(0);

    // тихие ссылки под кнопкой: «Забыли пароль?» в карточке, «Я выпускник» — под ней (22.10.2026)
    const forgot = card.getByRole("button", { name: "Забыли пароль?" });
    const alumni = page.getByRole("button", { name: "Я выпускник, у меня нет пароля" });
    await expect(forgot).toBeVisible();
    await expect(alumni).toBeVisible();
    const [forgotBox, alumniBox, submitBox] = await Promise.all([
      forgot.boundingBox(),
      alumni.boundingBox(),
      card.locator("button[type='submit']").boundingBox(),
    ]);
    expect(forgotBox?.y ?? 0, "ссылки ниже кнопки").toBeGreaterThan(submitBox?.y ?? 0);
    const alumniSize = await alumni.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    const forgotSize = await forgot.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    expect(alumniSize, "«Я выпускник» мельче").toBeLessThanOrEqual(forgotSize);
    expect(alumniBox?.y ?? 0).toBeGreaterThan(forgotBox?.y ?? 0);

    // «Забыли пароль?» — режим на той же карточке, «Назад ко входу» возвращает
    await forgot.click();
    await expect(card.getByRole("button", { name: "Прислать ссылку" })).toBeVisible();
    await expect(card.getByLabel("Пароль", { exact: true })).toHaveCount(0);
    await card.getByRole("button", { name: "Назад ко входу" }).click();
    await expect(card.getByRole("button", { name: "Войти", exact: true })).toBeVisible();
    await alumni.click();
    await expect(card.getByText("Для выпускников: вход по ссылке на личную почту.")).toBeVisible();
    await card.getByRole("button", { name: "Назад ко входу" }).click();

    // адрес сайта на полотне — текущий хост, не строка
    await expect(page.locator(".login__host")).toHaveText(new URL(page.url()).host);

    if (size.width <= 640) {
      const overflow = await page.evaluate((limit) => document.documentElement.scrollWidth - limit, size.width);
      expect(overflow, "страница не шире экрана").toBeLessThanOrEqual(0);
    }
    // до входа оболочка спрашивает «кто я» и получает отказ — это не ошибка экрана
    expect(diag.consoleErrors.filter((text) => !/40[13]/.test(text)), "ошибки в консоли").toEqual([]);
    expect(diag.pageErrors, "исключения").toEqual([]);
    await page.context().close();
  });
}

// Выбор до входа живёт только в памяти устройства (`localStorage`), на сервер
// не пишется: свой контекст теста — своя память, общий вход не задевается.
// И всё же в конце — русский, даже после падения: ни один шаг не оставляет
// экран входа на другом языке
test("переключатель языка меняет подписи и помнится на устройстве", async ({ browser }) => {
  const page = await open(browser, SIZES[0]);
  // подпись группы переводится вместе с экраном — берём её по классу
  const langs = page.locator(".login__langs");
  try {
    await expect(langs.getByRole("button", { name: "Рус" })).toBeVisible();
    await langs.getByRole("button", { name: "Қаз" }).click();
    await expect(page.getByLabel("Пошта немесе логин", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Кіру", exact: true })).toBeVisible();
    await expect(langs.getByRole("button", { name: "Қаз" })).toHaveAttribute("aria-pressed", "true");

    await page.reload();
    await expect(page.getByLabel("Пошта немесе логин", { exact: true })).toBeVisible();

    await langs.getByRole("button", { name: "Eng" }).click();
    await expect(page.getByLabel("Email or login", { exact: true })).toBeVisible();
  } finally {
    // подписи языков не переводятся — «Рус» есть на любом языке экрана
    await langs.getByRole("button", { name: "Рус" }).click();
    await expect(page.getByLabel("Почта или логин", { exact: true })).toBeVisible();
    await page.context().close();
  }
});

test("вход учеником с нового экрана проходит", async ({ browser }) => {
  const page = await open(browser, SIZES[1]);
  const account = byKey("student");
  await page.getByLabel("Почта или логин", { exact: true }).fill(account.email);
  await page.getByLabel("Пароль", { exact: true }).fill(account.password);
  const [entered] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/auth/login/") && r.request().method() === "POST"),
    page.getByRole("button", { name: "Войти", exact: true }).click(),
  ]);
  expect(entered.status()).toBe(200);
  await page.waitForURL(/\/(dashboard|onboarding)/, { timeout: 15_000 });
  await page.context().close();
});
