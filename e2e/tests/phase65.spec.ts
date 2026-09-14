/**
 * Фаза 65 — данные поступления и импорт таблицы Асем в живом браузере.
 *
 * Два сценария, оба точечные: полного прогона в этой фазе нет.
 *
 * 1. Карточка ученика: блок «Поступление» с телефоном, почтой Common App,
 *    папкой и GPA, и пароль под маской — «Показать» шлёт свой запрос,
 *    открывает пароль и оставляет запись в журнале. Пароля до нажатия
 *    в ответах экрана нет: это проверяется по самим сетевым ответам,
 *    а не по тому, что нарисовано.
 * 2. Мастер импорта у Асем: обезличенная копия таблицы с бедами —
 *    ненайденная фамилия, неразобранный телефон, текст в ячейке балла
 *    и лист без группы. Строки правятся или пропускаются, применение
 *    даёт отчёт с числами и причинами.
 *
 * Кнопка считается рабочей, только если по клику ушёл запрос, ответ 2xx
 * и в консоли пусто — за этим следит `watch()`.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

/** Обезличенная копия структуры таблицы: 3 листа, 18 и 19 колонок. */
const TABLE = readFileSync(
  path.join(__dirname, "..", "fixtures", "admission-table.xlsx"),
);

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

async function studentId(page: Page, email: string): Promise<number> {
  const list = (await (
    await page.request.get("/api/students/?page_size=500")
  ).json()) as { results: { id: number; email: string }[] };
  const row = list.results.find((r) => r.email === email);
  expect(row, `карточка ${email}`).toBeTruthy();
  return row!.id;
}

test("карточка: блок «Поступление» и показ пароля с записью в журнал", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  const id = await studentId(page, probeEmail("pupil01"));

  await page.goto(`/students/${id}`);
  const block = page
    .locator(".card")
    .filter({ hasText: "Поступление" })
    .first();
  await expect(block).toContainText("Телефон ученика");
  await expect(block).toContainText("+77753730924");
  await expect(block).toContainText("Почта Common App");
  await expect(block).toContainText("GPA");
  await expect(block).toContainText("Ведёт директор по поступлению");

  // до нажатия пароль скрыт — и на экране, и в том, что пришло с сервера
  await expect(block).toContainText("••••••");
  const beforeReveal = await (
    await page.request.get(`/api/curator/students/${id}/`)
  ).text();
  expect(beforeReveal, "пароль в карточке до показа").not.toContain(
    "Seed-email-",
  );

  const journalBefore = (await (
    await page.request.get(`/api/students/${id}/history/`)
  ).json()) as { field_title?: string }[];
  const revealsBefore = journalBefore.filter((row) =>
    (row.field_title ?? "").includes("Показан пароль"),
  ).length;

  const mark = diag.mark();
  await block.getByRole("button", { name: "Показать" }).first().click();
  await expect(block).toContainText(`Seed-email-${id}`);
  expect(
    diag
      .since(mark)
      .some(
        (call) =>
          call.url.includes("/credentials/reveal/") && call.status === 200,
      ),
    "показ идёт отдельным запросом",
  ).toBeTruthy();

  // показ оставил след в журнале ученика
  const journalAfter = (await (
    await page.request.get(`/api/students/${id}/history/`)
  ).json()) as { field_title?: string }[];
  const revealsAfter = journalAfter.filter((row) =>
    (row.field_title ?? "").includes("Показан пароль"),
  ).length;
  expect(revealsAfter, "показ записан в журнал").toBe(revealsBefore + 1);

  await block.getByRole("button", { name: "Скрыть" }).first().click();
  await expect(block).toContainText("••••••");

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("мастер импорта: беды в строках, правка, пропуск и отчёт", async ({
  browser,
}) => {
  const page = await as(browser, "director_admission");
  const diag = watch(page);

  // с фазы 72 мастер один на все домены: без отдельной вкладки Асем
  await page.goto("/import");
  await expect(page.locator(".wizard__steps")).toBeVisible();
  const responded = page.waitForResponse(
    (r) =>
      r.url().includes("/admission-imports/preview/") && r.status() === 200,
  );
  await page.locator('input[type="file"]').first().setInputFiles({
    name: "admission-table.xlsx",
    mimeType:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: TABLE,
  });
  await responded;
  await page.getByRole("button", { name: "Дальше" }).click();
  await page.getByRole("button", { name: "Дальше" }).click();

  const preview = page
    .locator(".card")
    .filter({ hasText: "Проверка строк" })
    .first();
  await expect(preview).toBeVisible();

  // беды из файла названы словами
  await expect(preview).toContainText("Строк с ошибкой:");
  await expect(preview).toContainText("ученик не найден в этой группе");
  await expect(preview).toContainText("не разбирается");
  await expect(preview).toContainText("не балл, а текст");
  // формулировка из реестра (фаза 71): колонка названа словами реестра
  await expect(preview).toContainText("записано словами");
  // пароли на этом шаге — только признаком
  await expect(preview).toContainText("пароли есть");
  const previewText = await preview.innerText();
  expect(previewText, "пароль на шаге проверки").not.toContain("Almaty-2010");

  // строки с бедой пропускаем осознанно — они попадут в отчёт с причиной;
  // пропущенная остаётся помеченной, но кнопки у неё уже нет
  const pending = preview.locator("tr.aimp__row--bad:has(button)");
  await expect(pending.first()).toBeVisible();
  while ((await pending.count()) > 0) {
    const again = page.waitForResponse((r) =>
      r.url().includes("/admission-imports/preview/"),
    );
    await pending.first().getByRole("button", { name: "Пропустить" }).click();
    await again;
  }
  await expect(preview).toContainText("пропущена");

  const applied = page.waitForResponse(
    (r) =>
      r.url().includes("/admission-imports/apply/") &&
      r.request().method() === "POST",
  );
  await preview.getByRole("button", { name: "Применить" }).click();
  expect((await applied).status(), "применение уходит запросом").toBe(201);

  const report = page.locator(".card").filter({ hasText: "Готово" }).first();
  await expect(report).toBeVisible();
  await expect(report).toContainText("Учеников обновлено:");
  await expect(report).toContainText("Паролей записано:");
  // лист без группы — в пропусках по видам
  await expect(report).toContainText("Листы без группы");

  const download = page.waitForEvent("download");
  await report.getByRole("button", { name: "Скачать отчёт" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});
