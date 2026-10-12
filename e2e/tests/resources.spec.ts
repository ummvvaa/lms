/**
 * Ресурсы школы у директора в живом браузере: памятка заводится с экрана
 * и показывается в списке; сценарий убирает её за собой.
 *
 * Раздел «Ресурсы» у ученика убран из кабинета 07.10.2026, прежняя анкета
 * профтеста убрана 08.10.2026 — их проверки отсюда ушли; профтест —
 * `career-tests.spec.ts`.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 120_000 });

const TITLE = "Probe Browser Guide";

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

function csrf(page: Page): Promise<string> {
  return page
    .context()
    .cookies()
    .then((c) => c.find((x) => x.name === "csrftoken")?.value ?? "");
}

test("директор пишет памятку с экрана", async ({ browser }) => {
  const director = await as(browser, "director_exam");
  const diag = watch(director);
  await director.goto("/resources");
  await expect(director.getByRole("heading", { name: /Ресурсы/ })).toBeVisible();

  await director.getByRole("button", { name: "Добавить материал" }).first().click();
  await director.getByLabel("Заголовок", { exact: true }).fill(TITLE);
  await director.getByLabel("Категория").selectOption({ label: "Подготовка" });
  await director.getByLabel("Короткое описание").fill("Как готовиться к пробному экзамену");
  await director.getByLabel("Текст материала").fill("Первый абзац памятки.\nВторой абзац памятки.");
  await director.getByLabel("Метки через запятую").fill("пробник, подготовка");
  const [created] = await Promise.all([
    director.waitForResponse((r) => r.url().includes("/api/resources/") && r.request().method() === "POST"),
    director.getByRole("button", { name: "Опубликовать" }).click(),
  ]);
  expect(created.status(), await created.text()).toBe(201);
  await expect(director.getByText(TITLE).first()).toBeVisible();
  await director.reload();
  await expect(director.getByText(TITLE).first()).toBeVisible();
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  await director.context().close();
});

test("уборка: памятка прогона удалена", async ({ browser }) => {
  const director = await as(browser, "director_exam");
  const token = await csrf(director);
  const listing = (await (await director.request.get("/api/resources/?page_size=200")).json()) as {
    results: { id: number; title: string }[];
  };
  for (const row of listing.results.filter((item) => item.title === TITLE)) {
    const gone = await director.request.delete(`/api/resources/${row.id}/`, {
      headers: { "X-CSRFToken": token },
    });
    expect(gone.ok()).toBeTruthy();
  }
  await director.context().close();
});
