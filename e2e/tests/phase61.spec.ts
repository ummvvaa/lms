/**
 * Фаза 61 — кабинет куратора в живом браузере.
 *
 * Здесь то, чего не видно из pytest: главная с числами-кнопками, очередь
 * с массовым подтверждением и отклонением с причиной, таблица с сортировкой
 * и корзинами, карточка со всеми пятью вкладками, задача группе и телефон.
 *
 * Кнопка считается рабочей, только если по клику ушёл запрос, ответ 2xx
 * и в консоли пусто — за этим следит `watch()`.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { apiPost, watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

const PHONE = { width: 390, height: 844 };

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

/**
 * Строка очереди, которую можно решить, не ломая соседние проверки.
 *
 * Значение считается от текущего балла ученика, а не задаётся числом:
 * соседние сценарии подтверждают свои предложения, и «8.5» после
 * подтверждённых 7.5 уже не скачок. Порог школы — 1.5 балла в любую
 * сторону, поэтому «скачок» — на два балла вверх или вниз, «правка» —
 * на полбалла.
 */
async function proposeScore(
  browser: Browser,
  kind: "jump" | "small",
): Promise<number> {
  const student = await as(browser, "student");
  const me = await (await student.request.get("/api/students/me/")).json();
  const current = Number(me.exam?.ielts_current ?? 6);
  const delta = kind === "jump" ? 2 : 0.5;
  const value = current + delta <= 9 ? current + delta : current - delta;
  const made = await apiPost<{ suggestions: number[] }>(
    student,
    "/api/suggestions/propose/",
    {
      rows: [
        {
          model: "students.ExamProfile",
          field: "ielts_current",
          value: String(value),
        },
      ],
    },
  );
  await student.context().close();
  return made.suggestions[0];
}

test("главная: числа-кнопки, очередь, корзины, последние действия", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/dashboard");

  await expect(page.locator("h1")).toContainText("Кабинет куратора");
  // четыре числа-кнопки: очередь, две корзины и просроченные задачи
  const numbers = page.locator(".statrow .stat");
  await expect(numbers).toHaveCount(4);
  await expect(page.locator("body")).toContainText("ждут подтверждения");
  await expect(page.locator("body")).toContainText("без цели по экзаменам");
  await expect(page.locator("body")).toContainText(
    "пробника не было больше месяца",
  );
  await expect(page.locator("body")).toContainText("просроченные задачи");

  // документов и срока действия в этой фазе нет — они появятся в 62
  await expect(page.locator("body")).not.toContainText("документы не собраны");

  await expect(page.locator("body")).toContainText("Кого дёргать");
  await expect(page.locator("body")).toContainText("Последние действия");

  // число ведёт в очередь, а не просто светится
  const mark = diag.mark();
  await numbers.first().click();
  await expect(page).toHaveURL(/\/queue/);
  await expect(page.locator("h1")).toContainText("Очередь подтверждений");
  expect(diag.since(mark).filter((c) => c.status >= 400)).toEqual([]);

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("переключатель групп фильтрует всё", async ({ browser }) => {
  const page = await as(browser, "curator");
  await page.goto("/students");

  const chips = page.locator(".gswitch__chip");
  await expect(chips.first()).toContainText("Все мои группы");
  const groups = await chips.count();
  expect(groups).toBeGreaterThan(2);

  await expect(page.locator("table.tbl tbody tr").first()).toBeVisible();
  const all = await page.locator("table.tbl tbody tr").count();
  const code = (await chips.nth(1).innerText()).trim().split(/\s+/)[0];
  await chips.nth(1).click();
  await expect(page).toHaveURL(/group=/);
  // ждём именно перерисованных строк: пока ответ не пришёл, на экране
  // остаётся прежний список (`placeholderData`), и счёт соврал бы
  const cells = page.locator('table.tbl tbody tr td[data-label="Группа"]');
  await expect(cells.first()).toHaveText(code);
  await expect(cells.last()).toHaveText(code);
  const some = await page.locator("table.tbl tbody tr").count();
  expect(some).toBeLessThan(all);
  expect(some).toBeGreaterThan(0);

  // выбор переживает переход в другой раздел: он живёт в сессии
  await page.goto("/tasks");
  await expect(page.locator(".gswitch__chip--on")).not.toContainText(
    "Все мои группы",
  );
  await page.context().close();
});

test("очередь: резкий скачок, массовое подтверждение, отклонение с причиной", async ({
  browser,
}) => {
  const first = await proposeScore(browser, "jump");
  const second = await proposeScore(browser, "small");

  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/queue?group=all");

  await expect(page.locator("body")).toContainText(
    "Ученик внёс, вы подтверждаете",
  );
  // резкий скачок считает сервер — на экране он чипом у строки
  await expect(page.locator(`[data-suggestion="${first}"]`)).toContainText(
    "резкий скачок",
  );

  // вкладки и порядок
  await page.getByRole("button", { name: /^Экзамены/ }).click();
  await expect(page.locator(`[data-suggestion="${first}"]`)).toBeVisible();
  await page.getByRole("button", { name: "по времени" }).click();

  // отклонение без причины не проходит
  const row = page.locator(`[data-suggestion="${second}"]`);
  await row.getByRole("button", { name: "Отклонить" }).click();
  await expect(
    row.getByRole("button", { name: "Отклонить с причиной" }),
  ).toBeDisabled();

  // подсказка причины подставляет текст, и отказ уходит
  const mark = diag.mark();
  await row.getByRole("button", { name: "Скан нечёткий" }).click();
  await expect(row.getByLabel("Причина отклонения")).toHaveValue("Скан нечёткий");
  await row.getByRole("button", { name: "Отклонить с причиной" }).click();
  // строка ушла из очереди — это и есть видимый след решения
  await expect(page.locator(`[data-suggestion="${second}"]`)).toHaveCount(0);
  const calls = diag.since(mark);
  expect(
    calls.some((c) => c.url.includes("/review/") && c.status === 200),
    `запросы после отклонения: ${JSON.stringify(calls)}`,
  ).toBeTruthy();

  // массовое подтверждение отмеченных
  await page.reload();
  // чекбокс строки подписан именем ученика — по подписи и находим
  const checkbox = page
    .locator(`[data-suggestion="${first}"]`)
    .getByRole("checkbox")
    .first();
  await checkbox.click();
  const bulk = page.getByRole("button", { name: /Подтвердить отмеченные/ });
  await expect(bulk).toBeVisible();
  const second_mark = diag.mark();
  await bulk.click();
  await expect(page.locator(`[data-suggestion="${first}"]`)).toHaveCount(0);
  expect(
    diag.since(second_mark).some((c) => c.url.includes("confirm/") && c.status === 200),
  ).toBeTruthy();

  expect(diag.consoleErrors).toEqual([]);
  expect(diag.pageErrors).toEqual([]);
  await page.context().close();
});

test("ученики: сортировка, корзина, выгрузка и переход в карточку", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/students");

  const rows = page.locator("table.tbl tbody tr");
  await expect(rows.first()).toBeVisible();
  expect(await rows.count()).toBeGreaterThan(0);
  await expect(page.locator("body")).toContainText(
    "Статус — внутренняя метка школы",
  );

  // сортировка по столбцу меняет порядок строк
  const before = await rows.first().innerText();
  await page.getByRole("button", { name: /^IELTS/ }).click();
  const after = await rows.first().innerText();
  expect(after).not.toBe(before);

  // корзина сужает список и попадает в адрес
  const bucket = page.locator(".cfilters .cchip").nth(1);
  const label = await bucket.innerText();
  await bucket.click();
  await expect(page).toHaveURL(/bucket=/);
  const narrowed = await rows.count();
  expect(narrowed, `корзина «${label}» пуста`).toBeGreaterThan(0);

  // выгрузка отдаёт файл, а не открывает пустую вкладку
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Выгрузить" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);

  await rows.first().click();
  await expect(page).toHaveURL(/\/students\/\d+/);
  expect(diag.consoleErrors).toEqual([]);
  await page.context().close();
});

test("карточка ученика: пять вкладок и возврат", async ({ browser }) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/students");
  await expect(page.locator("table.tbl tbody tr").first()).toBeVisible();
  await page.locator("table.tbl tbody tr").first().click();
  await expect(page).toHaveURL(/\/students\/\d+/);

  for (const [tab, marker] of [
    ["Обзор", "Что требует внимания"],
    ["Экзамены", "Официальный балл"],
    ["Вузы", "Список вузов"],
    ["Портфолио", "Заполнено на"],
    ["Задачи", "Задачи ученику"],
  ] as const) {
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.locator("body")).toContainText(marker);
  }
  // вкладка живёт в адресе — ссылку можно отправить
  await expect(page).toHaveURL(/tab=tasks/);

  // вкладок 62 и 63 здесь нет
  await expect(page.getByRole("tab", { name: "Документы" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Заметки" })).toHaveCount(0);

  await page.getByRole("button", { name: "← Назад" }).click();
  await expect(page).toHaveURL(/\/students(\?|$)/);
  expect(diag.consoleErrors).toEqual([]);
  await page.context().close();
});

test("задача группе: по одной на каждого ученика", async ({ browser }) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/students?group=BOSTON");

  await expect(page.locator("table.tbl tbody tr").first()).toBeVisible();
  const students = await page.locator("table.tbl tbody tr").count();
  expect(students).toBeGreaterThan(0);

  const mark = diag.mark();
  await page.getByRole("button", { name: "Задача группе" }).click();
  await page.getByLabel("Что сделать").fill("Проверка из прогона: обновить цель");
  await page.getByRole("button", { name: "Отправить" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(
    diag.since(mark).some((c) => c.url.includes("/curator/tasks/") && c.status === 201),
  ).toBeTruthy();

  await page.goto("/tasks?group=BOSTON&filter=open");
  const made = page.locator(".rowline", {
    hasText: "Проверка из прогона: обновить цель",
  });
  await expect(made).toHaveCount(students);

  // закрытие одной не трогает остальные
  await made.first().getByRole("button", { name: "Сделано" }).click();
  await expect(
    page.locator(".rowline", { hasText: "Проверка из прогона: обновить цель" }),
  ).toHaveCount(students - 1);

  expect(diag.consoleErrors).toEqual([]);
  await page.context().close();
});

test("ученик видит задачу куратора и знает, что она не своя", async ({
  browser,
}) => {
  const curator = await as(browser, "curator");
  const student = await as(browser, "student");
  const mine = await (await student.request.get("/api/students/me/")).json();

  await apiPost(curator, "/api/curator/tasks/", {
    student: mine.id,
    title: "Проверка из прогона: принести аттестат",
  });
  await curator.context().close();

  await student.goto("/roadmap");
  await expect(student.locator("body")).toContainText(
    "Проверка из прогона: принести аттестат",
  );
  // имя куратора ученику не показывается нигде (инвариант фазы 60)
  await expect(student.locator("body")).not.toContainText("Асель");
  await student.context().close();
});

test("телефон: чипы прокруткой, карточки вместо строк", async ({ browser }) => {
  const context = await browser.newContext({
    storageState: statePath("curator"),
    viewport: PHONE,
  });
  const page = await context.newPage();
  await page.goto("/dashboard");

  // нижний бар роли: главная, очередь, ученики, задачи
  await expect(page.locator(".tabbar")).toBeVisible();
  await expect(page.locator("body")).toContainText("Кабинет куратора");

  await page.goto("/students");
  // таблица на телефоне становится карточками: заголовок строки — имя
  const first = page.locator("table.tbl tbody tr").first();
  await expect(first).toBeVisible();
  const width = await first.evaluate((el) => el.getBoundingClientRect().width);
  expect(width).toBeLessThanOrEqual(PHONE.width);

  // чипы групп не переносятся, а прокручиваются
  const scroll = await page
    .locator(".gswitch")
    .evaluate((el) => el.scrollWidth >= el.clientWidth);
  expect(scroll).toBeTruthy();
  await context.close();
});
