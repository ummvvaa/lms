/**
 * Файлы грузит только администратор: импорт, история загрузок, вставка текста и таблица быстрого ввода после переноса загрузок администратору.
 *
 * Узкая проверка по заданию: экраны, которых касается фаза, под
 * администратором и двумя директорами. Академический директор: «Импорт»
 * с мастером (он оставлен администратору и ей), кнопки в таблице нет, отказ
 * по старому пути API, история загрузок своего домена и отмена загрузки
 * администратора. Директор спорта: ни пункта «Импорт», ни экрана, ни кнопки
 * «История загрузок». Администратор: выбор
 * домена → файл → предпросмотр → применение, запись в журнале помечена
 * доменом. Вставка текста: у администратора с выбором домена, у директора
 * без. Таблица быстрого ввода: Tab, вставка прямоугольником, растягивание,
 * отмена, отказ по ячейке без потери остального.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { apiPost, watch, unlockTable } from "../helpers/session";
import { sidebar } from "../helpers/shell";
import { wizardApply, wizardFile, wizardToColumns, wizardToRows } from "../helpers/wizard";

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
let previous: string | null = null;
let batchId = 0;

test("директор: «Импорт» с мастером, в таблице кнопки нет, старый путь по API — отказ", async ({
  browser,
}) => {
  const page = await as(browser, "director_exam");
  const diag = watch(page);

  // меню: пункт «Импорт» с мастером — у администратора и у Кымбат (у остальных
  // директоров его нет, см. ниже); отдельной «Истории загрузок» в меню нет
  const nav = sidebar(page);
  await expect(
    nav.getByRole("link", { name: "Импорт", exact: true }),
  ).toBeVisible();
  await expect(nav.getByRole("link", { name: "История загрузок" })).toHaveCount(
    0,
  );

  // таблица: кнопки импорта нет, подсказка есть
  await page.goto("/table");
  await expect(page.locator("h1")).toContainText("Таблица");
  await expect(
    page.getByRole("button", { name: "Импорт из файла" }),
  ).toHaveCount(0);
  await expect(page.locator(".manual-note")).toContainText(
    "файлы загружает администратор",
  );
  // «История загрузок» в подсказке — только у тех, у кого есть экран «Импорт»
  await expect(
    page
      .locator(".manual-note")
      .getByRole("button", { name: "История загрузок" }),
  ).toBeVisible();

  // экран /import — мастер с файлом и история под ним (фаза 72)
  await page.goto("/import");
  await expect(page.locator("h1")).toContainText("Импорт");
  await expect(page.locator("input[type=file]")).toHaveCount(1);
  await expect(page.locator(".manual-note")).toBeVisible();

  // прежнего пути с ручным сопоставлением колонок больше нет: поля грузит мастер
  const csrf = await csrfOf(page);
  const gone = await page.request.post("/api/import/preview/", {
    multipart: {
      domain: "exam",
      file: {
        name: "x.csv",
        mimeType: "text/csv",
        buffer: Buffer.from("email,ielts\n"),
      },
    },
    headers: { "X-CSRFToken": csrf },
  });
  expect(gone.status()).toBe(404);

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
  await expect(
    page.getByRole("button", { name: "Загрузить файлом" }),
  ).toHaveCount(0);
  await expect(page.locator(".manual-note")).toBeVisible();
  // экрана «Импорт» у директора спорта нет — и кнопки «История загрузок»
  // в подсказке нет: она вела бы в никуда; пункта меню тоже нет
  await expect(
    page
      .locator(".manual-note")
      .getByRole("button", { name: "История загрузок" }),
  ).toHaveCount(0);
  await expect(
    sidebar(page).getByRole("link", { name: "Импорт", exact: true }),
  ).toHaveCount(0);
  await page.goto("/import");
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 });

  const csrf = await csrfOf(page);
  const refused = await page.request.post("/api/competitions/import/preview/", {
    multipart: {
      file: {
        name: "x.csv",
        mimeType: "text/csv",
        buffer: Buffer.from("email\n"),
      },
    },
    headers: { "X-CSRFToken": csrf },
  });
  expect(refused.status()).toBe(403);
  await page.context().close();
});

test("администратор: файл → что заполняем → проверка → применение, журнал помечен доменом", async ({
  browser,
}) => {
  const page = await as(browser, "admin");
  const diag = watch(page);
  const list = await students(page);
  expect(list.length, "для проверки нужны ученики из посева").toBeGreaterThan(
    2,
  );
  uploadedFor = list[0];
  // «Применить» неактивна, когда файл ничего не меняет: значение берём
  // отличным от текущего балла ученика — под нагрузкой полного прогона
  // он уже мог быть 7.5 от соседних сценариев (D40)
  const current = (await (
    await page.request.get(`/api/profiles/exam/${uploadedFor.id}/`)
  ).json()) as { ielts_current: string | null };
  previous = current.ielts_current;
  const value = Number(current.ielts_current ?? 0) === 7.5 ? "7.0" : "7.5";

  await page.goto("/import");
  await expect(page.locator("h1")).toContainText("Импорт");
  // вкладки «Поля по CSV» больше нет: поля профилей грузит мастер
  await expect(page.getByRole("tab", { name: "Поля по CSV" })).toHaveCount(0);

  await wizardFile(page, FILE_NAME, `email,ielts\n${uploadedFor.email},${value}\n`);
  await wizardToColumns(page);
  // колонку мастер узнал по реестру и положил в её домен
  const column = page.locator("table.tbl tbody tr").filter({ hasText: "Текущий балл IELTS" }).first();
  await expect(column).toContainText("Экзамены");
  await wizardToRows(page);
  await expect(page.locator(".toolbar").filter({ hasText: "Строк готово:" }).first()).toContainText("Строк готово: 1");

  const mark = diag.mark();
  await wizardApply(page);
  await expect
    .poll(() =>
      diag
        .since(mark)
        .filter((c) => c.url.includes("/admission-imports/apply/"))
        .map((c) => c.status),
    )
    .toEqual([201]);

  // значение в базе
  const profile = await (
    await page.request.get(`/api/profiles/exam/${uploadedFor.id}/`)
  ).json();
  expect(profile.ielts_current).toBe(value);

  // история: загрузка помечена доменом и тем, что её делал администратор
  await page.reload();
  // у загрузки мастера две строки истории: отчёт и пачка домена — помечена пачка
  const row = page
    .locator("table.tbl tbody tr")
    .filter({ hasText: FILE_NAME })
    .filter({ has: page.getByRole("button", { name: "Отменить", exact: true }) })
    .first();
  await expect(row).toBeVisible();
  await expect(row).toContainText("администратор за домен «Экзамены»");
  const history = await (await page.request.get("/api/imports/")).json();
  batchId = history.find(
    (b: { file_name: string }) => b.file_name === FILE_NAME,
  ).id;

  // карточка ученика: строка истории говорит «за домен «Экзамены»»
  await page.goto(`/students/${uploadedFor.id}`);
  await page.getByRole("tab", { name: "История изменений" }).click();
  const entry = page
    .locator("table.tbl tr")
    .filter({ hasText: "Текущий балл IELTS" })
    .first();
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
  const row = page
    .locator("table.tbl tbody tr")
    .filter({ hasText: FILE_NAME })
    .filter({ has: page.getByRole("button", { name: "Отменить", exact: true }) })
    .first();
  await expect(row).toBeVisible();
  await expect(row).toContainText("администратор за домен «Экзамены»");
  await row.getByRole("button", { name: "Отменить", exact: true }).click();
  await page
    .locator(".confirm")
    .getByRole("button", { name: "Отменить импорт" })
    .click();
  await expect(page.locator(".rowline", { hasText: "Возвращено прежних значений" }).first()).toContainText(
    "Возвращено прежних значений",
  );

  const profile = await (
    await page.request.get(`/api/profiles/exam/${uploadedFor.id}/`)
  ).json();
  // отмена возвращает прежнее значение — каким бы оно ни было (D40)
  expect(profile.ielts_current).toBe(previous);
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
    admin.waitForResponse(
      (r) => r.url().includes("/api/commands/paste/") && r.status() === 202,
    ),
    admin.getByRole("button", { name: "Разобрать" }).click(),
  ]);
  await expect(admin.getByText(/Разобрано строк/)).toBeVisible({
    timeout: 30_000,
  });
  const latest = await (
    await admin.request.get("/api/suggestions/?ordering=-id")
  ).json();
  const rows = latest.results ?? latest;
  const mine = rows.find((s: { role: string }) => s.role === "admin");
  expect(mine.domain_code).toBe("exam");
  await admin.context().close();

  const director = await as(browser, "director_exam");
  await director.goto("/assistant?panel=paste_as_is");
  await expect(director.getByLabel("Домен", { exact: true })).toHaveCount(0);
  await director.locator("textarea").fill(text);
  await Promise.all([
    director.waitForResponse(
      (r) => r.url().includes("/api/commands/paste/") && r.status() === 202,
    ),
    director.getByRole("button", { name: "Разобрать" }).click(),
  ]);
  await expect(director.getByText(/Разобрано строк/)).toBeVisible({
    timeout: 30_000,
  });
  await director.context().close();
});

test("таблица: Tab, вставка прямоугольником, растягивание, отмена, отказ по ячейке", async ({
  browser,
}) => {
  const page = await as(browser, "director_exam");
  const diag = watch(page);
  const list = await students(page);
  const before = await Promise.all(
    list
      .slice(0, 3)
      .map(async (row) =>
        (await page.request.get(`/api/profiles/exam/${row.id}/`)).json(),
      ),
  );

  await page.goto("/table");
  // с фазы 49 таблица открывается на чтение: быстрый ввод включается кнопкой
  await unlockTable(page);
  const cell = (r: number, c: number) =>
    page.locator(`.cell[data-row="${r}"][data-col="${c}"]`);
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
    el.dispatchEvent(
      new ClipboardEvent("paste", {
        clipboardData: data,
        bubbles: true,
        cancelable: true,
      }),
    );
  }, "7.0\t7.5\n6.5\t7.0");
  await expect(cell(0, 0)).toHaveValue("7.0");
  await expect(cell(0, 1)).toHaveValue("7.5");
  await expect(cell(1, 0)).toHaveValue("6.5");
  await expect(cell(1, 1)).toHaveValue("7.0");
  await expect(page.locator("[data-sync]")).toHaveAttribute(
    "data-sync",
    "dirty",
  );

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
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  // ведём курсор по каждой строке отдельно: диапазон расширяется по
  // `mouseenter` ячейки, и один длинный отрезок иногда проскакивает
  // последнюю — человек ведёт мышь через все строки подряд
  for (const row of [1, 2]) {
    await cell(row, 2).hover();
    // подсветка диапазона — признак, что ячейка приняла курсор
    await expect(
      page.locator(`td:has(.cell[data-row="${row}"][data-col="2"])`),
    ).toHaveClass(/cell-fillrange/);
  }
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
    .poll(
      () =>
        diag.since(mark).filter((c) => c.url.includes("/batch/save/")).length,
    )
    .toBeGreaterThan(0);
  await expect(cell(0, 0)).toHaveClass(/cell-error/);
  await expect(cell(0, 0)).toHaveAttribute(
    "title",
    /не подходит|Текущий балл IELTS/,
  );
  await expect(cell(0, 4)).not.toHaveClass(/cell-error/);
  await expect(page.locator("[data-sync]")).toHaveAttribute(
    "data-sync",
    "rejected",
  );
  const saved = await (
    await page.request.get(`/api/profiles/exam/${list[0].id}/`)
  ).json();
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
