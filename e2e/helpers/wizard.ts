/**
 * Мастер импорта в сценариях: файл-список с почтой или логином ученика.
 *
 * Поля профилей грузит мастер (вкладки «Поля по CSV» больше нет): файл →
 * что заполняем → проверка строк → «Применить». Здесь шаги, которые
 * сценарии проходят одинаково, и та же загрузка прямым запросом — для
 * подготовки известного состояния.
 */
import { expect, type APIResponse, type Page } from "@playwright/test";

const PREVIEW = "/api/admission-imports/preview/";
const APPLY = "/api/admission-imports/apply/";

/** Выбрать файл на шаге 1 мастера и дождаться разбора. Экран — «Импорт», вкладка мастера. */
export async function wizardFile(page: Page, name: string, csv: string): Promise<void> {
  await Promise.all([
    page.waitForResponse((r) => r.url().includes(PREVIEW) && r.status() === 200),
    page.locator("input[type=file]").first().setInputFiles({
      name,
      mimeType: "text/csv",
      buffer: Buffer.from(csv, "utf8"),
    }),
  ]);
}

/** Шаг 1 → шаг 2 «Что заполняем». */
export async function wizardToColumns(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Дальше", exact: true }).click();
  await expect(page.getByText("Колонка → поле → домен: из реестра соответствий")).toBeVisible();
}

/** Назначить колонке файла место из реестра — по ключу колонки, не по подписи. */
export async function wizardAssign(page: Page, header: string, key: string): Promise<void> {
  await Promise.all([
    page.waitForResponse((r) => r.url().includes(PREVIEW) && r.status() === 200),
    page.locator(`select[aria-label="${header}"]`).selectOption(key),
  ]);
}

/** Шаг 2 → шаг 3 «Проверка строк». */
export async function wizardToRows(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Дальше", exact: true }).click();
  await expect(page.getByRole("button", { name: "Применить", exact: true })).toBeVisible();
}

/** «Применить» на шаге 3: ждём сам ответ применения и шаг «Готово». */
export async function wizardApply(page: Page): Promise<void> {
  await Promise.all([
    page.waitForResponse((r) => r.url().includes(APPLY) && r.status() === 201),
    page.getByRole("button", { name: "Применить", exact: true }).click(),
  ]);
  await expect(page.getByText("Учеников обновлено:")).toBeVisible();
}

/** Весь путь для файла, который мастер узнаёт сам и в котором нет ошибок. */
export async function wizardLoad(page: Page, name: string, csv: string): Promise<void> {
  await wizardFile(page, name, csv);
  await wizardToColumns(page);
  await wizardToRows(page);
  await wizardApply(page);
}

/** Та же загрузка прямым запросом: файл-список за выбранные домены. */
export async function wizardApplyByApi(
  page: Page,
  name: string,
  csv: string,
  domains: string[],
): Promise<APIResponse> {
  const csrf = (await page.context().cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
  return page.request.post(APPLY, {
    multipart: {
      file: { name, mimeType: "text/csv", buffer: Buffer.from(csv, "utf8") },
      domains: JSON.stringify(domains),
    },
    headers: { "X-CSRFToken": csrf },
  });
}
