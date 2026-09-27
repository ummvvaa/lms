/**
 * Мастер импорта: видно, что куда ложится.
 *
 * Три сценария:
 *
 * 1. Полный проход: файл → шаг «Что заполняем» с таблицей колонок, чипами
 *    доменов и счётом → проверка строк с пропуском беды → отчёт по доменам.
 * 2. Снятие домена: «Экзамены» сняты — в отчёте их нет, GPA не записан.
 * 3. CSV с нераспознанной колонкой: группа выбирается на первом шаге,
 *    колонка перечислена поимённо «будут пропущены». Идёт под Кымбат:
 *    мастер открыт только администратору и ей, и она — единственный
 *    владелец домена, который видит чужие колонки «домен не ваш».
 * 4. Остальным директорам мастер закрыт: пункта меню нет, `/import` уводит
 *    на главную, API отвечает 403 с объяснением.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";
import { sidebar } from "../helpers/shell";

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

/** Дойти до шага «Что заполняем» с книгой таблицы поступления. */
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
  const chips = page.locator(".wizard__chips [data-slot='button']");
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
  const exams = page.locator(".wizard__chips [data-slot='button']", { hasText: "Экзамены" });
  await exams.click();
  await expect(exams).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator("table.tbl tbody tr", { hasText: "не будет записано" }).first()).toBeVisible();

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
  // раньше сценарий шёл под Асем; мастер у неё закрыт, из владельцев доменов
  // он остался у Кымбат — её домен «Экзамены», остальное в файле чужое
  const page = await as(browser, "director_exam");
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
  const preview = (await (await responded).json()) as {
    domains: string[];
    writable_domains: string[];
  };
  // в файле найдены поступление и экзамены, писать Кымбат вправе только своё
  expect(preview.domains).toEqual(["admission", "exam"]);
  expect(preview.writable_domains).toEqual(["exam"]);
  // группа распознана: плашка «Группы:» на первом шаге
  await expect(page.getByText(/Группы:/)).toContainText("CHICAGO");

  await page.getByRole("button", { name: "Дальше" }).click();
  await expect(page.locator(".wizard__unknown")).toContainText(
    "«Любимый цвет»",
  );
  // GPA — её домен: чип доступен; «Поступление» — чужой: чип закрыт,
  // а строка телефона подписана «домен не ваш, будет пропущен»
  const chips = page.locator(".wizard__chips [data-slot='button']");
  await expect(chips.filter({ hasText: "Экзамены" })).toBeEnabled();
  await expect(chips.filter({ hasText: "Поступление" })).toBeDisabled();
  const phone = page
    .locator(".wizard__map tbody tr")
    .filter({ hasText: "Номер телефона" })
    .first();
  await expect(phone).toHaveClass(/wizard__off/);
  await expect(phone).toContainText("домен не ваш, будет пропущен");
  const gpa = page
    .locator(".wizard__map tbody tr")
    .filter({ hasText: "Средний GPA" })
    .first();
  await expect(gpa).not.toContainText("домен не ваш");

  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("остальным директорам мастер закрыт: ни меню, ни экрана, API — 403 словами", async ({
  browser,
}) => {
  // файлы грузят администратор и академический директор; Асем, хоть таблица
  // поступления и её, вносит руками — как и три других директора
  for (const role of [
    "director_admission",
    "director_behavior",
    "director_talent",
    "director_sport",
  ]) {
    const page = await as(browser, role);
    await page.goto("/dashboard");
    const nav = sidebar(page);
    await expect(
      nav.getByRole("link", { name: "Дашборд", exact: true }),
      role,
    ).toBeVisible();
    await expect(
      nav.getByRole("link", { name: "Импорт", exact: true }),
      role,
    ).toHaveCount(0);

    await page.goto("/import");
    await page.waitForURL(/\/dashboard/, { timeout: 15_000 });

    const history = await page.request.get("/api/admission-imports/");
    expect(history.status(), `${role}: история`).toBe(403);
    const csrf =
      (await page.context().cookies()).find((c) => c.name === "csrftoken")
        ?.value ?? "";
    const refused = await page.request.post("/api/admission-imports/preview/", {
      multipart: {
        file: { name: "admission-table.xlsx", mimeType: XLSX, buffer: TABLE },
      },
      headers: { "X-CSRFToken": csrf },
    });
    expect(refused.status(), `${role}: разбор файла`).toBe(403);
    expect((await refused.json()).detail).toContain(
      "Файлы загружают администратор и академический директор",
    );
    await page.context().close();
  }
});
