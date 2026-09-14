/**
 * Фаза 72 — мастер импорта: видно, что куда ложится.
 *
 * Три сценария:
 *
 * 1. Полный проход: файл → шаг «Что заполняем» с таблицей колонок, чипами
 *    доменов и счётом → проверка строк с пропуском беды → отчёт по доменам.
 * 2. Снятие домена: «Экзамены» сняты — в отчёте их нет, GPA не записан.
 * 3. CSV с нераспознанной колонкой: группа выбирается на первом шаге,
 *    колонка перечислена поимённо «будут пропущены».
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

const TABLE = readFileSync(
  path.join(__dirname, "..", "fixtures", "admission-table.xlsx"),
);
const XLSX =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

/** Дойти до шага «Что заполняем» с книгой Асем. */
async function toStepTwo(page: Page): Promise<void> {
  await page.goto("/import");
  const responded = page.waitForResponse(
    (r) =>
      r.url().includes("/admission-imports/preview/") && r.status() === 200,
  );
  await page.locator('input[type="file"]').first().setInputFiles({
    name: "admission-table.xlsx",
    mimeType: XLSX,
    buffer: TABLE,
  });
  await responded;
  await page.getByRole("button", { name: "Дальше" }).click();
  await expect(page.locator(".wizard__map")).toBeVisible();
}

test("полный проход мастера: колонки, домены, проверка, отчёт", async ({
  browser,
}) => {
  const page = await as(browser, "admin");
  const diag = watch(page);
  await toStepTwo(page);

  // шаг 2: таблица соответствий из реестра — колонка, поле, домен, владелец, строки
  const map = page.locator(".wizard__map");
  for (const text of [
    "Номер телефона",
    "Телефон ученика",
    "Поступление",
    "Асем",
  ]) {
    await expect(map).toContainText(text);
  }
  await expect(map).toContainText("Средний GPA");
  await expect(map).toContainText("Кымбат");
  // чипы доменов с числом колонок и счёт внизу
  const chips = page.locator(".wizard__chips .cchip");
  await expect(chips).toHaveCount(3);
  await expect(page.locator(".wizard__sum")).toContainText("Будет записано:");

  await page.getByRole("button", { name: "Дальше" }).click();
  // шаг 3: беда в строке — пропускаем осознанно, иначе «Применить» закрыта
  await expect(page.getByRole("button", { name: "Применить" })).toBeDisabled();
  // пропущенная строка остаётся помеченной, но кнопки у неё уже нет
  const pending = page.locator("tr.aimp__row--bad:has(button)");
  while ((await pending.count()) > 0) {
    const responded = page.waitForResponse((r) =>
      r.url().includes("/admission-imports/preview/"),
    );
    await pending.first().getByRole("button", { name: "Пропустить" }).click();
    await responded;
  }
  await expect(page.getByRole("button", { name: "Применить" })).toBeEnabled();

  const applied = page.waitForResponse(
    (r) =>
      r.url().includes("/admission-imports/apply/") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Применить" }).click();
  expect((await applied).status(), "применение уходит запросом").toBe(201);

  // шаг 4: отчёт по доменам числами
  const done = page.locator(".card").filter({ hasText: "Готово" }).first();
  await expect(done).toContainText("Учеников обновлено:");
  await expect(done.locator(".wizard__domains").first()).toContainText(
    "записано значений",
  );
  await expect(done).toContainText("Поступление");

  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("снятый домен не пишется и не попадает в отчёт", async ({ browser }) => {
  const page = await as(browser, "admin");
  const diag = watch(page);
  await toStepTwo(page);

  // снимаем «Экзамены»: строки красятся серым и подписаны
  const exams = page.locator(".wizard__chips .cchip", { hasText: "Экзамены" });
  await exams.click();
  await expect(exams).not.toHaveClass(/cchip--on/);
  await expect(page.locator("tr.wizard__off").first()).toContainText(
    "не будет записано",
  );

  await page.getByRole("button", { name: "Дальше" }).click();
  const bad = page.locator("tr.aimp__row--bad:has(button)");
  while ((await bad.count()) > 0) {
    const responded = page.waitForResponse((r) =>
      r.url().includes("/admission-imports/preview/"),
    );
    await bad.first().getByRole("button", { name: "Пропустить" }).click();
    await responded;
  }
  const applied = page.waitForResponse(
    (r) =>
      r.url().includes("/admission-imports/apply/") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Применить" }).click();
  const body = (await (await applied).json()) as { domains: string[] };
  expect(body.domains, "экзамены не выбраны").not.toContain("exam");

  const done = page.locator(".card").filter({ hasText: "Готово" }).first();
  await expect(done.locator(".wizard__domains").first()).not.toContainText(
    "Экзамены",
  );
  await expect(done).toContainText("Колонки вне выбранных доменов");

  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("CSV с нераспознанной колонкой: группа на первом шаге, колонка названа", async ({
  browser,
}) => {
  const page = await as(browser, "director_admission");
  const diag = watch(page);
  await page.goto("/import");

  // владельцу домена — тот же мастер, без отдельной вкладки
  await expect(page.locator(".wizard__steps")).toBeVisible();
  await page.getByLabel("Группа для CSV").selectOption("CHICAGO");

  const csv = [
    "ФИО,Номер телефона,Любимый цвет,Средний GPA",
    "Нет Такого,8 707 000 00 00,синий,4.5",
  ].join("\n");
  const responded = page.waitForResponse(
    (r) =>
      r.url().includes("/admission-imports/preview/") && r.status() === 200,
  );
  await page
    .locator('input[type="file"]')
    .first()
    .setInputFiles({
      name: "chicago.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(csv, "utf8"),
    });
  await responded;
  // группа распознана: плашка «Группы:» на первом шаге
  await expect(page.getByText(/Группы:/)).toContainText("CHICAGO");

  await page.getByRole("button", { name: "Дальше" }).click();
  await expect(page.locator(".wizard__unknown")).toContainText(
    "«Любимый цвет»",
  );
  // GPA — домен экзаменов: Асем пишет его по исключению реестра, чип доступен
  const exams = page.locator(".wizard__chips .cchip", { hasText: "Экзамены" });
  await expect(exams).toBeEnabled();

  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});
