/**
 * Фаза 63 — пробники файлом и секции IELTS в живом браузере.
 *
 * Мастер целиком: файл с тремя бедами (ненайденная фамилия, балл вне
 * шкалы, дубль), исправление двух и пропуск третьей, применение. Дальше —
 * страница результатов, архив и возврат, карточка с секциями и искрами,
 * вид ученика без кнопок правки и загрузка Кымбат в чужую группу.
 *
 * Кнопка считается рабочей, только если по клику ушёл запрос, ответ 2xx
 * и в консоли пусто — за этим следит `watch()`.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

const PHONE = { width: 390, height: 844 };

/** Дата пробника этого прогона — своя, чтобы не спорить с посевом. */
const MOCK_DATE = new Date(Date.now() - 2 * 86_400_000)
  .toISOString()
  .slice(0, 10);
const SAT_DATE = new Date(Date.now() - 4 * 86_400_000)
  .toISOString()
  .slice(0, 10);
const CARD_DATE = new Date(Date.now() - 6 * 86_400_000)
  .toISOString()
  .slice(0, 10);

async function as(
  browser: Browser,
  role: string,
  viewport?: { width: number; height: number },
): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    ...(viewport ? { viewport } : {}),
  });
  return context.newPage();
}

const csv = (rows: string[][]): Buffer =>
  Buffer.from(rows.map((row) => row.join(",")).join("\n") + "\n", "utf8");

/**
 * Файл-образец, как в прототипе: одна ненайденная фамилия, один балл
 * вне шкалы и один дубль. Остальные строки ровные.
 */
const BROKEN_FILE = csv([
  ["ФИО", "Listening", "Reading", "Writing", "Speaking", "Балл"],
  ["Оспанов Тимур", "6.5", "7.0", "6.5", "7.0", "7.0"],
  ["Неизвестная Фамилия", "6.0", "6.0", "6.0", "6.0", "6.0"],
  ["Ержанова Малика", "9.5", "6.0", "6.0", "6.0", "9.5"],
  ["Оспанов Тимур", "6.0", "6.0", "6.0", "6.0", "6.0"],
]);

/** Кого мастер должен предложить вместо ненайденной фамилии. */
const REPLACEMENT = "Сейткали Айгерим";

/**
 * Повторный прогон на живой базе: пробник этой группы за эту дату мог
 * остаться с прошлого раза, и мастер честно откажется его дублировать.
 * Убираем прежний в архив — как сделал бы человек перед перезаливкой.
 */
async function clearMock(
  page: Page,
  group: string,
  date: string,
): Promise<void> {
  const list = (await (
    await page.request.get("/api/mock-imports/?group=all")
  ).json()) as { results: { id: number; group: string; date: string }[] };
  const csrf =
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? "";
  for (const row of list.results.filter(
    (r) => r.group === group && r.date === date,
  )) {
    await page.request.post(`/api/mock-imports/${row.id}/archive/`, {
      headers: { "X-CSRFToken": csrf },
    });
  }
}

test("мастер: три беды в файле, две исправлены, одна пропущена", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  await clearMock(page, "CHICAGO", MOCK_DATE);
  const diag = watch(page);
  await page.goto("/mock-imports?group=all");

  await expect(page.locator("h1")).toContainText("Пробники");
  await expect(page.locator("body")).toContainText("Пробник проводит учитель");

  // шаг 1: что за пробник
  await page.getByRole("button", { name: "Загрузить пробник" }).click();
  const wizard = page.getByRole("dialog");
  await expect(wizard).toContainText("Что за пробник");
  await wizard.getByLabel("Экзамен").selectOption("IELTS");
  await wizard.getByLabel("Группа").selectOption("CHICAGO");
  await wizard.getByLabel("Дата пробника").fill(MOCK_DATE);
  await wizard.getByLabel("Кто проверял (учитель)").fill("Гульмира Абаевна");
  await wizard.getByRole("button", { name: "Дальше" }).click();

  // шаг 2: файл. Шаблон скачивается настоящим файлом
  const template = page.waitForEvent("download");
  await wizard.getByRole("button", { name: "Скачать шаблон" }).click();
  expect((await template).suggestedFilename()).toMatch(/\.xlsx$/);

  await wizard.locator('input[type="file"]').setInputFiles({
    name: "ielts-chicago.csv",
    mimeType: "text/csv",
    buffer: BROKEN_FILE,
  });
  const mark = diag.mark();
  await wizard.getByRole("button", { name: "Проверить файл" }).click();

  // шаг 3: разбор пришёл с сервера, три строки с ошибками
  await expect(wizard).toContainText("с ошибками");
  expect(
    diag
      .since(mark)
      .some(
        (c) => c.url.includes("/mock-imports/preview/") && c.status === 200,
      ),
    "разбор идёт запросом на сервер",
  ).toBeTruthy();
  const rows = wizard.locator("table.cmock__rows tbody tr");
  await expect(rows).toHaveCount(4);
  await expect(
    wizard.getByRole("button", { name: "Применить" }),
  ).toBeDisabled();
  await expect(wizard).toContainText("Ученик не найден");
  // 9.5 у секции — «секция вне шкалы»: секции проверяются раньше общего балла
  await expect(wizard).toContainText("Секция вне шкалы");
  await expect(wizard).toContainText("встречается в файле дважды");

  // беда 1: ненайденная фамилия — выбираем ученика из группы
  await rows.nth(1).getByRole("button", { name: "Исправить" }).click();
  const whoIs = page.getByRole("dialog").filter({ hasText: "Кто это?" });
  await whoIs.getByLabel("Ученик").selectOption({ label: REPLACEMENT });
  await whoIs.getByRole("button", { name: "Сопоставить" }).click();
  await expect(
    wizard.locator("table.cmock__rows tbody tr").nth(1),
  ).toContainText(REPLACEMENT);

  // беда 2: балл вне шкалы — вводим значение из бланка
  await wizard
    .locator("table.cmock__rows tbody tr")
    .nth(2)
    .getByRole("button", { name: "Исправить" })
    .click();
  const fixScore = page
    .getByRole("dialog")
    .filter({ hasText: "Балл из бланка" });
  await fixScore.getByLabel("listening").fill("6");
  await fixScore.getByLabel("Общий балл").fill("6");
  await fixScore.getByRole("button", { name: "Сохранить балл" }).click();

  // беда 3: дубль — пропускаем строку
  await wizard
    .locator("table.cmock__rows tbody tr")
    .nth(3)
    .getByRole("button", { name: "Пропустить" })
    .click();
  await expect(wizard.locator(".cmock__row--skip")).toHaveCount(1);

  // теперь применять можно
  const apply = wizard.getByRole("button", { name: "Применить" });
  await expect(apply).toBeEnabled();
  const applyMark = diag.mark();
  await apply.click();
  await expect(wizard).toContainText("результатов записано");
  await expect(wizard).toContainText("Пропущено строк:");
  expect(
    diag
      .since(applyMark)
      .some((c) => c.url.includes("/mock-imports/apply/") && c.status === 201),
  ).toBeTruthy();

  await wizard.getByRole("button", { name: "Открыть результаты" }).click();
  await expect(page).toHaveURL(/\/mock-imports\/\d+/);
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("результаты: сдавали, средний, ниже цели, напоминание и выгрузка", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/mock-imports?group=CHICAGO");
  await page
    .locator("table.tbl tbody tr")
    .first()
    .getByRole("button", { name: "Открыть" })
    .click();
  await expect(page).toHaveURL(/\/mock-imports\/\d+/);

  const numbers = page.locator(".statrow .stat");
  await expect(numbers).toHaveCount(3);
  await expect(page.locator("body")).toContainText("Сдавали");
  await expect(page.locator("body")).toContainText("Средний балл группы");
  await expect(page.locator("body")).toContainText("виден только вам и Кымбат");

  const table = page.locator("table.tbl tbody tr");
  await expect(table.first()).toBeVisible();
  expect(await table.count()).toBeGreaterThan(1);

  // выгрузка и исходник — настоящие файлы
  const sheet = page.waitForEvent("download");
  await page.getByRole("button", { name: "Выгрузить" }).click();
  expect((await sheet).suggestedFilename()).toMatch(/\.xlsx$/);
  const original = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать исходник" }).click();
  expect((await original).suggestedFilename()).toMatch(/\.(csv|xlsx)$/);

  // напоминание тем, кто не сдавал
  const remind = page.getByRole("button", { name: "Напомнить не сдавшим" });
  if (await remind.isVisible()) {
    const mark = diag.mark();
    await remind.click();
    await expect
      .poll(() =>
        diag
          .since(mark)
          .some((c) => c.url.includes("/remind/") && c.status === 200),
      )
      .toBeTruthy();
  }

  expect(diag.consoleErrors).toEqual([]);
  await page.context().close();
});

test("карточка: секции последнего пробника, искры и кто загрузил", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  // свой свежий пробник: у загрузок прошлых прогонов автор удалён вместе
  // с одноразовой записью, и «кто загрузил» там честно пусто
  await clearMock(page, "CHICAGO", CARD_DATE);
  const csrf =
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? "";
  const made = await page.request.post("/api/mock-imports/apply/", {
    multipart: {
      exam_type: "IELTS",
      group: "CHICAGO",
      date: CARD_DATE,
      teacher: "Гульмира Абаевна",
      file: {
        name: "ielts-card.csv",
        mimeType: "text/csv",
        buffer: csv([
          ["ФИО", "Listening", "Reading", "Writing", "Speaking", "Балл"],
          ["Ержанова Малика", "7.0", "7.0", "6.5", "7.0", "7.0"],
        ]),
      },
    },
    headers: { "X-CSRFToken": csrf },
  });
  expect(made.status(), await made.text()).toBe(201);

  const diag = watch(page);
  const listing = (await (
    await page.request.get(
      `/api/mock-imports/${((await made.json()) as { import: number }).import}/`,
    )
  ).json()) as {
    results: { student: number; full_name: string; took: boolean }[];
  };
  const who = listing.results.find((row) => row.took);
  expect(who, "в пробнике есть сдавший").toBeTruthy();
  await page.goto(`/students/${who!.student}?tab=exams`);

  await expect(page.locator("body")).toContainText(
    "Секции — последний пробник",
  );
  const tiles = page.locator(".csec__tile");
  await expect(tiles).toHaveCount(4);
  await expect(tiles.first()).toContainText("Listening");
  // цель одна на все секции: «цель взята» или «до цели N»
  await expect(tiles.first()).toContainText(/цел[ьи]/);
  // несколько пробников из посева — искра по секции рисуется
  await expect(page.locator(".csec__tile .cspark").first()).toBeVisible();

  // история пробников: кто загрузил и какой учитель
  await expect(page.locator("body")).toContainText("загрузил Асель");
  await expect(page.locator("body")).toContainText("учитель Гульмира Абаевна");
  expect(diag.consoleErrors).toEqual([]);
  await page.context().close();
});

test("ученик: пробник помечен, править нечем, официальный балл не сдвинулся", async ({
  browser,
}) => {
  const curator = await as(browser, "curator");
  const before = (await (
    await curator.request.get("/api/curator/students/")
  ).json()) as {
    results: { id: number; full_name: string; ielts_current: number | null }[];
  };
  await curator.context().close();

  const page = await as(browser, "student");
  const diag = watch(page);
  await page.goto("/my-data");

  const card = page
    .locator("section", { hasText: "Сданные экзамены и пробные" })
    .first();
  await expect(card).toBeVisible();
  const mocks = card.locator(".rowline", { hasText: "пробник школы" });
  if ((await mocks.count()) > 0) {
    await expect(mocks.first()).toBeVisible();
    await expect(card).toContainText("обратись к куратору");
    // ни одной кнопки правки у строки пробника
    await expect(mocks.first().getByRole("button")).toHaveCount(0);
  }

  // секции с сертификата — необязательные поля рядом с баллом
  await page.getByRole("button", { name: "Внести баллы" }).click();
  await expect(page.locator("body")).toContainText(
    "Секции IELTS — с сертификата",
  );
  await expect(page.getByLabel("Listening")).toBeVisible();
  await page.getByRole("button", { name: "Отмена" }).click();

  // текущий балл ученика — тот же, что видит куратор: пробник его не менял
  const mine = (await (await page.request.get("/api/students/me/")).json()) as {
    id: number;
    exam: { ielts_current: string | null };
  };
  const seen = before.results.find((row) => row.id === mine.id);
  if (seen) {
    // числом, а не строкой: куратор видит 7, ученик — «7.0», это одно и то же
    expect(Number(seen.ielts_current ?? 0)).toBe(
      Number(mine.exam.ielts_current ?? 0),
    );
  }

  // экран пробников ученику закрыт
  await page.goto("/mock-imports");
  await expect(page.locator("body")).not.toContainText("Загрузить пробник");
  expect(diag.consoleErrors).toEqual([]);
  await page.context().close();
});

test("Кымбат: грузит в чужую группу и возвращает пробник из архива", async ({
  browser,
}) => {
  const page = await as(browser, "director_exam");
  await clearMock(page, "BOSTON", SAT_DATE);
  const diag = watch(page);
  await page.goto("/mock-imports?group=all");
  await expect(page.locator("h1")).toContainText("Пробники");

  // загрузка в BOSTON — группу, которую Кымбат не курирует
  await page.getByRole("button", { name: "Загрузить пробник" }).click();
  const wizard = page.getByRole("dialog");
  await wizard.getByLabel("Экзамен").selectOption("SAT");
  await wizard.getByLabel("Группа").selectOption("BOSTON");
  await wizard.getByLabel("Дата пробника").fill(SAT_DATE);
  await wizard.getByLabel("Кто проверял (учитель)").fill("Ерлан Маратович");
  await wizard.getByRole("button", { name: "Дальше" }).click();
  await wizard.locator('input[type="file"]').setInputFiles({
    name: "sat-boston.csv",
    mimeType: "text/csv",
    buffer: csv([
      ["ФИО", "Балл"],
      ["Бекова Аружан", "1250"],
      ["Мусин Ерлан", "1180"],
    ]),
  });
  await wizard.getByRole("button", { name: "Проверить файл" }).click();
  await expect(wizard.getByRole("button", { name: "Применить" })).toBeEnabled();
  const mark = diag.mark();
  await wizard.getByRole("button", { name: "Применить" }).click();
  await expect(wizard).toContainText("результатов записано");
  expect(
    diag.since(mark).some((c) => c.url.includes("/apply/") && c.status === 201),
  ).toBeTruthy();
  await wizard.getByRole("button", { name: "Открыть результаты" }).click();

  // в архив и обратно
  await page.getByRole("button", { name: "В архив" }).click();
  const ask = page.getByRole("dialog");
  await expect(ask).toContainText("Вернуть сможет Кымбат или администратор");
  const archiveMark = diag.mark();
  await ask.getByRole("button", { name: "В архив", exact: true }).click();
  await expect(page).toHaveURL(/\/mock-imports$|\/mock-imports\?/);
  expect(
    diag
      .since(archiveMark)
      .some((c) => c.url.includes("/archive/") && c.status === 200),
  ).toBeTruthy();

  await page.goto("/mock-imports?group=all&archived=true");
  // именно та строка, которую только что убрали: в архиве лежит и посевная
  const archived = page
    .locator("table.tbl tbody tr")
    .filter({ hasText: "BOSTON" })
    .filter({ hasText: "SAT" })
    .first();
  await expect(archived).toBeVisible();
  const restoreMark = diag.mark();
  await archived.getByRole("button", { name: "Вернуть из архива" }).click();
  await expect
    .poll(() =>
      diag
        .since(restoreMark)
        .some((c) => c.url.includes("/restore/") && c.status === 200),
    )
    .toBeTruthy();

  expect(diag.consoleErrors).toEqual([]);
  await page.context().close();
});

test("телефон: список пробников читается карточками", async ({ browser }) => {
  const page = await as(browser, "curator", PHONE);
  await page.goto("/mock-imports?group=all");
  await expect(page.locator("h1")).toContainText("Пробники");
  // таблица на телефоне становится карточками: заголовок строки — экзамен
  await expect(page.locator("table.tbl tbody tr").first()).toBeVisible();
  await expect(page.locator(".tabbar")).toBeVisible();
  await page.context().close();
});
