/**
 * Фаза 73 — блок «Поступление»: значение одной строкой.
 *
 * Два сценария:
 *
 * 1. Длинная почта и длинный пароль не переносятся — строка блока остаётся
 *    высотой в одну строку и на 1440, и на 390; пароль при показе читается
 *    целиком одной строкой.
 * 2. Срок паспорта виден отдельной строкой без ссылки на паспорт, а строк
 *    в блоке ровно столько, сколько колонок в таблице.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

const LONG_EMAIL =
  "ochen.dlinnaya.pochta.uchenika.dlya.proverki.perenosa@example-university.edu";
const LONG_PASSWORD = "Xk9!vP2mQ7rT4wZ1nB6cL8dF3gH5jK0s";

async function as(
  browser: Browser,
  role: string,
  viewport?: { width: number; height: number },
): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    viewport,
  });
  return context.newPage();
}

async function csrf(page: Page): Promise<string> {
  return (
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? ""
  );
}

async function studentId(page: Page, email: string): Promise<number> {
  const answer = await page.request.get("/api/students/?page_size=500");
  expect(answer.status(), await answer.text()).toBe(200);
  const list = (await answer.json()) as {
    results?: { id: number; email: string }[];
  };
  const row = (list.results ?? []).find((r) => r.email === email);
  expect(row, `карточка ${email}`).toBeTruthy();
  return row!.id;
}

/** Строка блока по названию. */
const line = (page: Page, label: string) =>
  page
    .locator(".cadm__pair")
    .filter({ has: page.locator(".cadm__k", { hasText: label }) })
    .first();

test("длинная почта и пароль читаются одной строкой на обеих ширинах", async ({
  browser,
}) => {
  const setup = await as(browser, "admin");
  const id = await studentId(setup, probeEmail("pupil01"));
  const token = await csrf(setup);
  expect(
    (
      await setup.request.patch(`/api/profiles/admission/${id}/`, {
        data: { personal_email: LONG_EMAIL },
        headers: { "X-CSRFToken": token },
      })
    ).status(),
  ).toBe(200);
  expect(
    (
      await setup.request.post(`/api/students/${id}/credentials/set/`, {
        data: { kind: "email", password: LONG_PASSWORD },
        headers: { "X-CSRFToken": token },
      })
    ).status(),
  ).toBe(200);
  await setup.context().close();

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
  ]) {
    const page = await as(browser, "director_admission", viewport);
    const diag = watch(page);
    await page.goto(`/students/${id}`);

    const email = line(page, "Электронный адрес");
    await expect(email).toBeVisible();
    const text = email.locator(".cadm__text").first();
    await expect(text).toHaveAttribute("title", LONG_EMAIL);
    // одна строка: высота значения не больше полутора строк текста
    const box = (await text.boundingBox())!;
    expect(box.height, `почта в одну строку на ${viewport.width}`).toBeLessThan(
      32,
    );
    // и оно не вылезает за свою ячейку — обрезано многоточием, а не перенесено
    const overflow = await text.evaluate(
      (el) => el.scrollWidth > el.clientWidth,
    );
    if (viewport.width === 390)
      expect(overflow, "длинная почта обрезана, не перенесена").toBe(true);

    const password = line(page, "Пароль от эл. адреса");
    await password.getByRole("button", { name: "Показать" }).click();
    const shown = password.locator(".cadm__text");
    await expect(shown).toHaveText(LONG_PASSWORD);
    const pbox = (await shown.boundingBox())!;
    expect(
      pbox.height,
      `пароль в одну строку на ${viewport.width}`,
    ).toBeLessThan(32);

    expect(diag.pageErrors, "исключения").toEqual([]);
    await page.context().close();
  }
});

test("срок паспорта виден без ссылки, строк ровно как колонок в таблице", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  const id = await studentId(page, probeEmail("pupil02"));
  const token = await csrf(page);
  await page.request.patch(`/api/profiles/admission/${id}/`, {
    data: { passport_expires_at: "2030-01-16" },
    headers: { "X-CSRFToken": token },
  });

  await page.goto(`/students/${id}`);
  const expiry = line(page, "Срок годности паспорта");
  await expect(expiry).toContainText("16.01.2030");
  await expect(line(page, "Ссылка на паспорт")).toContainText("—");
  await expect(page.locator(".cadm")).not.toContainText("срок не указан");

  // строки блока: 8 полей + GPA + 6 попыток + 2 документа = 17
  await expect(page.locator(".cadm .cadm__pair")).toHaveCount(17);

  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});
