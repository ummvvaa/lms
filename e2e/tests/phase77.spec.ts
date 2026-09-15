/**
 * Фаза 77 — блок «Поступление»: действия значками, карточка в два столбца.
 *
 * 1. На ноутбуке действия строки — значки: у каждого доступное имя и
 *    подпись при наведении, поле касания не меньше 44 px, колонка
 *    действий одной ширины у всех строк. «Скопировать» нет у пустого
 *    значения и у скрытого пароля, «Записать» у отсутствующего пароля —
 *    словом. В режиме правки поле не уже 240 px, кнопки справа от него.
 * 2. На 1280 телефон и показанный пароль читаются целиком под Асем,
 *    куратором и администратором; у куратора блок стоит в широкой колонке.
 * 3. На 1440 у Асем и администратора сверху два столбца («Кто это»,
 *    «Профиль и дисциплина» и «Экзамены» друг под другом, «Поступление»
 *    справа шире и той же высоты), снизу «Таланты» и «Спорт» в ряд.
 *    На 390 порядок карточек прежний, кнопки — словами.
 *
 * Снимки для отчёта складываются в `shots/phase77/` (каталог вне git).
 */
import {
  expect,
  test,
  type Browser,
  type Locator,
  type Page,
} from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

const LAPTOP = { width: 1440, height: 900 };
const SMALL = { width: 1280, height: 800 };
const PHONE = { width: 390, height: 844 };

const PHONE_NUMBER = "+7 701 234 56 78";
const PASSWORD = "Xk9!vP2mQ7rT4wZ1nB6cL8dF3gH5jK0s";

async function as(
  browser: Browser,
  role: string,
  viewport = LAPTOP,
): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    viewport,
    ...(viewport.width <= 640 ? { isMobile: true, hasTouch: true } : {}),
  });
  const page = await context.newPage();
  await page.addInitScript(() =>
    window.localStorage.setItem("first-run-seen", "1"),
  );
  return page;
}

async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(300);
}

async function csrf(page: Page): Promise<string> {
  return (
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? ""
  );
}

async function studentId(page: Page, email: string): Promise<number> {
  const answer = await page.request.get("/api/students/?page_size=500");
  expect(answer.status(), await answer.text()).toBe(200);
  const list = (await answer.json()) as {
    results?: { id: number; email: string }[];
  };
  const row = (list.results ?? []).find((r) => r.email === email);
  expect(row, `карточка ${email}`).toBeTruthy();
  return row!.id;
}

/** Ученик с телефоном и паролем от почты — данные ставит администратор. */
async function prepared(browser: Browser): Promise<number> {
  const setup = await as(browser, "admin");
  const id = await studentId(setup, probeEmail("pupil03"));
  const token = await csrf(setup);
  expect(
    (
      await setup.request.patch(`/api/profiles/admission/${id}/`, {
        data: { student_phone: PHONE_NUMBER },
        headers: { "X-CSRFToken": token },
      })
    ).status(),
  ).toBe(200);
  expect(
    (
      await setup.request.post(`/api/students/${id}/credentials/set/`, {
        data: { kind: "email", password: PASSWORD },
        headers: { "X-CSRFToken": token },
      })
    ).status(),
  ).toBe(200);
  await setup.context().close();
  return id;
}

/** Строка блока по названию. */
const line = (page: Page, label: string): Locator =>
  page
    .locator(".cadm__pair")
    .filter({ has: page.locator(".cadm__k", { hasText: label }) })
    .first();

/** Кнопка — значок: без видимого текста, с рисунком внутри, поле 44 px. */
async function expectIcon(button: Locator, what: string): Promise<void> {
  await expect(button, what).toBeVisible();
  expect(
    (await button.innerText()).trim(),
    `${what}: текст ушёл с экрана`,
  ).toBe("");
  await expect(button.locator("svg"), `${what}: значок`).toHaveCount(1);
  const box = (await button.boundingBox())!;
  expect(box.width, `${what}: ширина касания`).toBeGreaterThanOrEqual(44);
  expect(box.height, `${what}: высота касания`).toBeGreaterThanOrEqual(44);
}

/** Значение не обрезано: его содержимое помещается в свою ячейку. */
const fits = (text: Locator) =>
  text.evaluate((el) => el.scrollWidth <= el.clientWidth);

async function shotsDir(): Promise<string> {
  const fs = await import("node:fs");
  const path = await import("node:path");
  const dir = path.join(__dirname, "..", "shots", "phase77");
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

test("иконки действий: имя, поле касания, «Скопировать» только когда есть что копировать", async ({
  browser,
}) => {
  const id = await prepared(browser);
  const page = await as(browser, "director_admission");
  const diag = watch(page);
  await page.goto(`/students/${id}`);
  await settle(page);

  // телефон записан: копия и карандаш — значками
  const phone = line(page, "Номер телефона");
  await expect(phone.locator(".cadm__text")).toHaveText(PHONE_NUMBER);
  await expectIcon(
    phone.getByRole("button", { name: "Скопировать" }),
    "копия телефона",
  );
  await expectIcon(
    phone.getByRole("button", { name: "Изменить" }),
    "карандаш телефона",
  );

  // подпись при наведении — та же, что доступное имя
  await phone.getByRole("button", { name: "Изменить" }).hover();
  await expect(page.locator("[data-slot='tooltip-content']")).toHaveText(
    "Изменить",
  );

  // пустое значение: копировать нечего, карандаш есть
  const commonApp = line(page, "Электронный адрес Common App");
  await expect(commonApp.locator(".cadm__empty")).toBeVisible();
  await expect(
    commonApp.getByRole("button", { name: "Скопировать" }),
  ).toHaveCount(0);
  await expectIcon(
    commonApp.getByRole("button", { name: "Изменить" }),
    "карандаш пустого",
  );

  // скрытый пароль: глаз и карандаш, копии нет; показанный — копия, глаз перечёркнутый, карандаш
  const password = line(page, "Пароль от эл. адреса");
  await expect(
    password.getByRole("button", { name: "Скопировать" }),
  ).toHaveCount(0);
  await expectIcon(password.getByRole("button", { name: "Показать" }), "глаз");
  await expectIcon(
    password.getByRole("button", { name: "Изменить" }),
    "карандаш пароля",
  );
  await password.getByRole("button", { name: "Показать" }).click();
  await expect(password.locator(".cadm__text")).toHaveText(PASSWORD);
  await expectIcon(
    password.getByRole("button", { name: "Скопировать" }),
    "копия пароля",
  );
  await expectIcon(
    password.getByRole("button", { name: "Скрыть" }),
    "глаз перечёркнутый",
  );
  await expect(password.getByRole("button", { name: "Показать" })).toHaveCount(
    0,
  );
  await password.getByRole("button", { name: "Скрыть" }).click();
  await expect(
    password.getByRole("button", { name: "Скопировать" }),
  ).toHaveCount(0);

  // отсутствующий пароль — «Записать» словом: заводят впервые, не правят
  // (у pupil10 в посеве нет пароля от почты)
  const bare = await studentId(page, probeEmail("pupil10"));
  const other = await page.context().newPage();
  await other.goto(`/students/${bare}`);
  await settle(other);
  const absent = other
    .locator(".cadm__pair")
    .filter({ hasText: "не записан" })
    .first();
  const write = absent.getByRole("button", { name: "Записать" });
  await expect(write).toHaveText("Записать");
  await expect(write.locator("svg")).toHaveCount(0);
  await other.close();

  // колонка действий одной ширины: значения всех строк начинаются
  // и заканчиваются на одной вертикали
  const values = await page
    .locator(".cadm .cadm__pair > .cadm__v")
    .evaluateAll((els) =>
      els.map((el) => {
        const box = el.getBoundingClientRect();
        return { left: Math.round(box.left), right: Math.round(box.right) };
      }),
    );
  expect(values.length).toBe(17);
  expect(new Set(values.map((v) => v.left)).size, "левый край значений").toBe(
    1,
  );
  expect(new Set(values.map((v) => v.right)).size, "правый край значений").toBe(
    1,
  );

  // режим правки: поле во всю колонку значения, не уже 240, кнопки справа
  await phone.getByRole("button", { name: "Изменить" }).click();
  const input = phone.getByRole("textbox");
  await expect(input).toHaveValue(PHONE_NUMBER);
  const inputBox = (await input.boundingBox())!;
  expect(inputBox.width, "поле ввода").toBeGreaterThanOrEqual(240);
  const save = (await phone
    .getByRole("button", { name: "Сохранить" })
    .boundingBox())!;
  expect(save.x, "«Сохранить» справа от поля").toBeGreaterThanOrEqual(
    inputBox.x + inputBox.width,
  );
  await phone.getByRole("button", { name: "Отмена" }).click();
  await expect(phone.locator(".cadm__text")).toHaveText(PHONE_NUMBER);

  expect(diag.pageErrors, "исключения").toEqual([]);
  expect(diag.consoleErrors, "ошибки консоли").toEqual([]);
  await page.context().close();
});

test("на 1280 телефон и показанный пароль читаются целиком под тремя ролями", async ({
  browser,
}) => {
  const id = await prepared(browser);
  const dir = await shotsDir();
  for (const role of ["director_admission", "curator", "admin"]) {
    const page = await as(browser, role);
    const diag = watch(page);
    await page.setViewportSize(SMALL);
    await page.goto(`/students/${id}`);
    await settle(page);

    if (role === "curator") {
      // у куратора блок стоит в широкой колонке, боковая треть его не вмещала
      await expect(page.locator(".cgrid__main .cadm")).toHaveCount(1);
      await expect(page.locator(".cgrid__side .cadm")).toHaveCount(0);
    }

    const phone = line(page, "Номер телефона").locator(".cadm__text");
    await expect(phone).toHaveText(PHONE_NUMBER);
    expect(await fits(phone), `${role}: телефон целиком на 1280`).toBe(true);

    const password = line(page, "Пароль от эл. адреса");
    await password.getByRole("button", { name: "Показать" }).click();
    const shown = password.locator(".cadm__text");
    await expect(shown).toHaveText(PASSWORD);
    expect(await fits(shown), `${role}: пароль целиком на 1280`).toBe(true);
    const box = (await shown.boundingBox())!;
    expect(box.height, `${role}: пароль одной строкой`).toBeLessThan(32);

    // окно прокручивается внутри каркаса, поэтому «вся страница» — это
    // окно; сетка карточек снимается отдельно, целиком
    const grid = page.locator(role === "curator" ? ".cgrid" : ".card__domains");
    await page.screenshot({ path: `${dir}/${role}-1280.png` });
    await grid.screenshot({ path: `${dir}/${role}-1280-grid.png` });
    await page.setViewportSize(LAPTOP);
    await settle(page);
    await page.screenshot({ path: `${dir}/${role}-1440.png` });
    await grid.screenshot({ path: `${dir}/${role}-1440-grid.png` });

    expect(diag.pageErrors, `${role}: исключения`).toEqual([]);
    await page.context().close();
  }
});

const box = async (l: Locator) => (await l.boundingBox())!;

test("раскладка: два столбца сверху, две карточки снизу; на телефоне порядок прежний", async ({
  browser,
}) => {
  const setup = await as(browser, "admin");
  const id = await studentId(setup, probeEmail("pupil03"));
  await setup.context().close();

  for (const role of ["director_admission", "admin"]) {
    const page = await as(browser, role);
    await page.goto(`/students/${id}`);
    await settle(page);
    // раскладка не шире окна: шесть колонок областей не раздуваются
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
      `${role}: страница не шире окна`,
    ).toBeLessThanOrEqual(LAPTOP.width);
    const who = await box(page.locator(".card__slot--who"));
    const behavior = await box(page.locator(".card__slot--behavior"));
    const admission = await box(page.locator(".card__slot--admission"));
    const exam = await box(page.locator(".card__slot--exam"));
    const talent = await box(page.locator(".card__slot--talent"));
    const sport = await box(page.locator(".card__slot--sport"));

    // левый столбец: «Кто это», «Профиль и дисциплина», «Экзамены» —
    // друг под другом, одной ширины
    for (const [name, card] of [
      ["дисциплина", behavior],
      ["экзамены", exam],
    ] as const) {
      expect(Math.round(card.x), `${role}: левый край ${name}`).toBe(
        Math.round(who.x),
      );
      expect(Math.round(card.width), `${role}: ширина ${name}`).toBe(
        Math.round(who.width),
      );
    }
    expect(behavior.y).toBeGreaterThan(who.y + who.height);
    expect(exam.y).toBeGreaterThan(behavior.y + behavior.height);
    // правый: «Поступление» с той же верхней линии, шире и в стороне
    expect(Math.round(admission.y), `${role}: верхняя линия`).toBe(
      Math.round(who.y),
    );
    expect(admission.x).toBeGreaterThan(who.x + who.width);
    expect(admission.width, `${role}: «Поступление» шире`).toBeGreaterThan(
      who.width * 1.5,
    );
    // столбцы одной высоты — пустоты внизу нет; сколько ушло в растяжку
    // нижней карточки слева, видно по зазору под её строками
    const leftBottom = exam.y + exam.height;
    const rightBottom = admission.y + admission.height;
    expect(
      Math.abs(leftBottom - rightBottom),
      `${role}: низ столбцов`,
    ).toBeLessThanOrEqual(2);
    const examRows = await box(
      page.locator(".card__slot--exam .domain__fields"),
    );
    const slack = leftBottom - (examRows.y + examRows.height);
    expect(slack, `${role}: пустота под строками «Экзаменов»`).toBeLessThan(80);
    // нижний ряд: две карточки на одной линии, под обоими столбцами
    expect(Math.round(sport.y)).toBe(Math.round(talent.y));
    expect(talent.y).toBeGreaterThanOrEqual(Math.max(leftBottom, rightBottom));
    expect(sport.x).toBeGreaterThan(talent.x + talent.width - 1);
    await page.context().close();
  }

  // телефон: одна колонка в прежнем порядке, действия — словами
  const phone = await as(browser, "director_admission", PHONE);
  await phone.goto(`/students/${id}`);
  await settle(phone);
  const order = await Promise.all(
    ["who", "admission", "behavior", "exam", "talent", "sport"].map(
      async (slot) => (await box(phone.locator(`.card__slot--${slot}`))).y,
    ),
  );
  for (let i = 1; i < order.length; i += 1)
    expect(order[i], `порядок карточек на телефоне: ${i}`).toBeGreaterThan(
      order[i - 1],
    );
  const edit = line(phone, "Номер телефона").getByRole("button", {
    name: "Изменить",
  });
  await expect(edit).toHaveText("Изменить");
  await expect(edit.locator("svg")).toHaveCount(0);
  expect(
    await phone.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(PHONE.width);
  await phone.context().close();
});
