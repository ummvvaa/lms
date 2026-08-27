/**
 * Фаза 35 — файлы грузит только администратор.
 *
 * Узкая проверка по заданию: экраны, которых касается фаза, под
 * администратором и двумя директорами. Директор: ни пункта «Импорт»,
 * ни кнопки, ни поля файла, отказ по прямому запросу к API, история
 * загрузок своего домена и отмена чужой загрузки. Администратор: выбор
 * домена → файл → предпросмотр → применение, запись в журнале помечена
 * доменом. Вставка текста: у администратора с выбором домена, у директора
 * без. Таблица быстрого ввода: Tab, вставка прямоугольником, растягивание,
 * отмена, отказ по ячейке без потери остального.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { apiPost, watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 120_000 });

interface Row {
  id: number;
  email: string;
  full_name: string;
  exam: Record<string, unknown>;
}

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  await page.goto("/dashboard");
  return page;
}

async function csrfOf(page: Page): Promise<string> {
  return (
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? ""
  );
}

async function students(page: Page): Promise<Row[]> {
  const list = await (
    await page.request.get("/api/students/?page_size=10&ordering=id")
  ).json();
  return list.results as Row[];
}

const FILE_NAME = "фаза35-баллы.csv";
let uploadedFor: Row;
let batchId = 0;

test("директор: ни меню, ни кнопки, ни файла — и отказ по API", async ({
  browser,
}) => {
  const page = await as(browser, "director_exam");
  const diag = watch(page);

  // меню: «История загрузок» есть, «Импорт» нет
  const nav = page.locator("nav");
  await expect(nav.getByRole("link", { name: "История загрузок" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Импорт", exact: true })).toHaveCount(0);

  // таблица: кнопки импорта нет, подсказка есть
  await page.goto("/table");
  await expect(page.locator("h1")).toContainText("Быстрый ввод");
  await expect(page.getByRole("button", { name: "Импорт из файла" })).toHaveCount(0);
  await expect(page.locator(".manual-note")).toContainText("файлы загружает администратор");

  // экран /import — история, а не загрузка
  await page.goto("/import");
  await expect(page.locator("h1")).toContainText("История загрузок");
  await expect(page.locator("input[type=file]")).toHaveCount(0);
  await expect(page.locator(".manual-note")).toBeVisible();

  // прямой запрос к API — отказ с объяснением, куда идти
  const csrf = await csrfOf(page);
  const refused = await page.request.post("/api/import/preview/", {
    multipart: {
      domain: "exam",
      file: { name: "x.csv", mimeType: "text/csv", buffer: Buffer.from("email,ielts\n") },
    },
    headers: { "X-CSRFToken": csrf },
  });
  expect(refused.status()).toBe(403);
  expect((await refused.json()).detail).toContain("администратор");

  expect(diag.consoleErrors).toEqual([]);
  expect(diag.pageErrors).toEqual([]);
  await page.context().close();
});

test("директор спорта: соревнования без «Загрузить файлом», отказ на файл выступлений", async ({
  browser,
}) => {
  const page = await as(browser, "director_sport");
  await page.goto("/competitions");
  await expect(page.locator("h1")).toContainText("Соревнования");
  await expect(page.getByRole("button", { name: "Загрузить файлом" })).toHaveCount(0);
  await expect(page.locator(".manual-note")).toBeVisible();

  const csrf = await csrfOf(page);
  const refused = await page.request.post("/api/competitions/import/preview/", {
    multipart: {
      file: { name: "x.csv", mimeType: "text/csv", buffer: Buffer.from("email\n") },
    },
    headers: { "X-CSRFToken": csrf },
  });
  expect(refused.status()).toBe(403);
  await page.context().close();
});

test("администратор: домен → файл → предпросмотр → применение, журнал помечен доменом", async ({
  browser,
}) => {
  const page = await as(browser, "admin");
  const diag = watch(page);
  const list = await students(page);
  expect(list.length, "для проверки нужны ученики из посева").toBeGreaterThan(2);
  uploadedFor = list[0];

  await page.goto("/import");
  await expect(page.locator("h1")).toContainText("Импорт из файла");
  // без домена файл выбрать негде
  await expect(page.locator("input[type=file]")).toHaveCount(0);
  await page.getByLabel("Домен", { exact: true }).selectOption("exam");
  await expect(page.getByText("администратор за домен «Экзамены»")).toBeVisible();

  await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/import/preview/")),
    page.setInputFiles("input[type=file]", {
      name: FILE_NAME,
      mimeType: "text/csv",
      buffer: Buffer.from(`email,ielts\n${uploadedFor.email},7.5\n`, "utf8"),
    }),
  ]);
  const mapping = page.locator("table.history tbody tr");
  await expect(mapping.first()).toBeVisible();
  // в списке полей — только выбранный домен: поля поступления не предлагаются
  const options = await mapping.nth(1).locator("select option").allTextContents();
  expect(options).toContain("Текущий балл IELTS");
  expect(options).not.toContain("Целевая страна");

  await mapping.nth(0).locator("select").selectOption("student");
  await mapping.nth(1).locator("select").selectOption("students.ExamProfile.ielts_current");
  await page.getByRole("button", { name: "Показать предпросмотр" }).click();
  await expect(page.getByText("Нашлось: 1")).toBeVisible();

  const mark = diag.mark();
  await page.getByRole("button", { name: "Применить", exact: true }).click();
  await expect
    .poll(() => diag.since(mark).filter((c) => c.url.includes("/import/apply/")).map((c) => c.status))
    .toEqual([200]);

  // значение в базе
  const profile = await (
    await page.request.get(`/api/profiles/exam/${uploadedFor.id}/`)
  ).json();
  expect(profile.ielts_current).toBe("7.5");

  // история: загрузка помечена доменом и тем, что её делал администратор
  await page.reload();
  await page.getByLabel("Домен", { exact: true }).selectOption("exam");
  const row = page.locator(".imp__row").filter({ hasText: FILE_NAME }).first();
  await expect(row).toBeVisible();
  await expect(row).toContainText("администратор за домен «Экзамены»");
  const history = await (await page.request.get("/api/imports/")).json();
  batchId = history.find((b: { file_name: string }) => b.file_name === FILE_NAME).id;

  // карточка ученика: строка истории говорит «за домен «Экзамены»»
  await page.goto(`/students/${uploadedFor.id}`);
  await page.getByRole("tab", { name: "История изменений" }).click();
  const entry = page.locator("table.history tr").filter({ hasText: "Текущий балл IELTS" }).first();
  await expect(entry).toContainText("за домен «Экзамены»");

  expect(diag.consoleErrors).toEqual([]);
  expect(diag.pageErrors).toEqual([]);
  await page.context().close();
});

test("директор видит загрузку администратора по своему домену и отменяет её", async ({
  browser,
}) => {
  // чужому домену загрузка не показывается
  const talent = await as(browser, "director_talent");
  const foreign = await (await talent.request.get("/api/imports/")).json();
  expect(foreign.map((b: { id: number }) => b.id)).not.toContain(batchId);
  await talent.context().close();

  const page = await as(browser, "director_exam");
  await page.goto("/import");
  const row = page.locator(".imp__row").filter({ hasText: FILE_NAME }).first();
  await expect(row).toBeVisible();
  await expect(row).toContainText("администратор за домен «Экзамены»");
  await row.getByRole("button", { name: "Отменить импорт" }).click();
  await page.locator(".confirm").getByRole("button", { name: "Отменить импорт" }).click();
  await expect(page.locator(".imp__report")).toContainText("Возвращено прежних значений");

  const profile = await (
    await page.request.get(`/api/profiles/exam/${uploadedFor.id}/`)
  ).json();
  expect(profile.ielts_current).not.toBe("7.5");
  await page.context().close();
});

test("вставка текста: администратор выбирает домен, директору выбирать нечего", async ({
  browser,
}) => {
  const admin = await as(browser, "admin");
  const list = await students(admin);
  const person = list[1];
  const text = `${person.full_name} — 6.5`;

  await admin.goto("/assistant?panel=paste_as_is");
  await expect(admin.getByLabel("Домен", { exact: true })).toBeVisible();
  await admin.locator("textarea").fill(text);
  // без домена разбор не уходит
  await admin.getByRole("button", { name: "Разобрать" }).click();
  await expect(admin.getByText("Сначала выберите домен")).toBeVisible();
  await admin.getByLabel("Домен", { exact: true }).selectOption("exam");
  await Promise.all([
    admin.waitForResponse((r) => r.url().includes("/api/commands/paste/") && r.status() === 202),
    admin.getByRole("button", { name: "Разобрать" }).click(),
  ]);
  await expect(admin.getByText(/Разобрано строк/)).toBeVisible({ timeout: 30_000 });
  const latest = (await (await admin.request.get("/api/suggestions/?ordering=-id")).json());
  const rows = latest.results ?? latest;
  const mine = rows.find((s: { role: string }) => s.role === "admin");
  expect(mine.domain_code).toBe("exam");
  await admin.context().close();

  const director = await as(browser, "director_exam");
  await director.goto("/assistant?panel=paste_as_is");
  await expect(director.getByLabel("Домен", { exact: true })).toHaveCount(0);
  await director.locator("textarea").fill(text);
  await Promise.all([
    director.waitForResponse((r) => r.url().includes("/api/commands/paste/") && r.status() === 202),
    director.getByRole("button", { name: "Разобрать" }).click(),
  ]);
  await expect(director.getByText(/Разобрано строк/)).toBeVisible({ timeout: 30_000 });
  await director.context().close();
});

test("таблица: Tab, вставка прямоугольником, растягивание, отмена, отказ по ячейке", async ({
  browser,
}) => {
  const page = await as(browser, "director_exam");
  const diag = watch(page);
  const list = await students(page);
  const before = await Promise.all(
    list.slice(0, 3).map(async (row) => (await page.request.get(`/api/profiles/exam/${row.id}/`)).json()),
  );

  await page.goto("/table");
  const cell = (r: number, c: number) => page.locator(`.cell[data-row="${r}"][data-col="${c}"]`);
  await expect(cell(0, 0)).toBeVisible();

  // Tab — следующая ячейка; Shift+Tab — назад
  await cell(0, 0).focus();
  await page.keyboard.press("Tab");
  await expect(cell(0, 1)).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(cell(0, 0)).toBeFocused();
  // стрелка вниз — по колонке
  await page.keyboard.press("ArrowDown");
  await expect(cell(1, 0)).toBeFocused();

  // вставка прямоугольником 2×2 из буфера
  await cell(0, 0).evaluate((el, text) => {
    const data = new DataTransfer();
    data.setData("text/plain", text);
    el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }));
  }, "7.0\t7.5\n6.5\t7.0");
  await expect(cell(0, 0)).toHaveValue("7.0");
  await expect(cell(0, 1)).toHaveValue("7.5");
  await expect(cell(1, 0)).toHaveValue("6.5");
  await expect(cell(1, 1)).toHaveValue("7.0");
  await expect(page.locator("[data-sync]")).toHaveAttribute("data-sync", "dirty");

  // Ctrl+Z — вставка отменяется целиком, одним действием
  await cell(0, 0).focus();
  await page.keyboard.press("Control+z");
  await expect(cell(0, 0)).toHaveValue(String(before[0].ielts_current ?? ""));
  await expect(cell(1, 1)).toHaveValue(String(before[1].ielts_target ?? ""));

  // растягивание вниз: маркер в углу активной ячейки тянем на две строки
  await cell(0, 2).fill("1300");
  const handle = page.locator(".cell-fill");
  await expect(handle).toBeVisible();
  const from = (await handle.boundingBox())!;
  const to = (await cell(2, 2).boundingBox())!;
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 6 });
  await page.mouse.up();
  await expect(cell(1, 2)).toHaveValue("1300");
  await expect(cell(2, 2)).toHaveValue("1300");

  // всё, что набрано, сбрасывается, чтобы не трогать посев
  await page.getByRole("button", { name: "Отменить правки" }).click();
  await expect(cell(1, 2)).toHaveValue(String(before[1].sat_current ?? ""));

  // отказ по ячейке: кривое значение подсвечено с причиной, соседнее сохранилось
  await cell(0, 0).fill("не число");
  await cell(0, 4).fill("5");
  const mark = diag.mark();
  await page.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect
    .poll(() => diag.since(mark).filter((c) => c.url.includes("/batch/save/")).length)
    .toBeGreaterThan(0);
  await expect(cell(0, 0)).toHaveClass(/cell-error/);
  await expect(cell(0, 0)).toHaveAttribute("title", /не подходит|Текущий балл IELTS/);
  await expect(cell(0, 4)).not.toHaveClass(/cell-error/);
  await expect(page.locator("[data-sync]")).toHaveAttribute("data-sync", "rejected");
  const saved = await (await page.request.get(`/api/profiles/exam/${list[0].id}/`)).json();
  expect(saved.hours_per_week).toBe(5);

  // возвращаем посев в прежнее состояние тем же API, что и таблица
  await page.getByRole("button", { name: "Отменить правки" }).click();
  await apiPost(page, "/api/batch/save/", {
    changes: [
      {
        student: list[0].id,
        model: "students.ExamProfile",
        field: "hours_per_week",
        value: before[0].hours_per_week,
        expected: "5",
      },
    ],
  });

  expect(diag.pageErrors).toEqual([]);
  expect(diag.consoleErrors).toEqual([]);
  await page.context().close();
});
