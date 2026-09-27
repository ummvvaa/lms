/**
 * Выгрузка через предпросмотр: нажали — увидели таблицу — скачали.
 *
 * Файл больше не скачивается сразу: кнопка экрана открывает окно с той же
 * таблицей, что уйдёт в файл, и только «Скачать xlsx» отдаёт книгу. Сценарии
 * проверяют обе половины: предпросмотр пришёл запросом с `preview=1`
 * и показал строки, а файл скачался настоящий.
 */
import { expect, type Locator, type Page } from "@playwright/test";

export async function exportThroughPreview(
  page: Page,
  button: Locator,
  options: { expectRows?: boolean } = {},
): Promise<{ filename: string; columns: string[]; rows: number }> {
  const preview = page.waitForResponse(
    (r) => /[?&]preview=1/.test(r.url()) || r.request().postData()?.includes('"preview":true') === true,
  );
  await button.click();
  const answer = await preview;
  expect(answer.status(), "предпросмотр выгрузки отвечает").toBe(200);

  // окно выгрузки стоит поверх остальных — оно последнее из открытых
  const dialog = page.getByRole("dialog").last();
  const download = dialog.getByRole("button", { name: "Скачать xlsx" });
  await expect(download).toBeVisible();
  // textContent, а не innerText: шапка таблицы рисуется капителью через CSS,
  // а сверяем мы сами подписи колонок, как их отдаёт сервер
  const columns = (await dialog.locator(".xprev__scroll table thead th").allTextContents()).map((s) => s.trim());
  const rows = await dialog.locator(".xprev__scroll table tbody tr").count();
  if (options.expectRows !== false) {
    expect(columns.length, "у предпросмотра есть колонки").toBeGreaterThan(0);
    expect(rows, "у предпросмотра есть строки").toBeGreaterThan(0);
  }

  const file = page.waitForEvent("download");
  await download.click();
  const filename = (await file).suggestedFilename();
  expect(filename).toMatch(/\.xlsx$/);

  await page.keyboard.press("Escape");
  await expect(download).toBeHidden();
  return { filename, columns, rows };
}
