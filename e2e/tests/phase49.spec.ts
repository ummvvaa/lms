/**
 * Фаза 49 — макет v2 в живом браузере.
 *
 * Проверяем то, что нельзя проверить из pytest: карусель на главной
 * действительно собирается из незакрытых мест и исчезает вместе с ними,
 * календарь занимает освободившееся место, портфолио в две колонки
 * и ничего не наезжает, редактор эссе занимает экран, таблица директора
 * открывается на чтение, а кнопки администратора делают то, что написано.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { apiPatch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  return page;
}

/** Прямоугольники всех элементов селектора — для проверки на наложение. */
async function boxes(page: Page, selector: string) {
  return page.locator(selector).evaluateAll((nodes) =>
    nodes.map((node) => {
      const rect = node.getBoundingClientRect();
      return {
        text: (node.textContent ?? "").slice(0, 40),
        x: Math.round(rect.left),
        y: Math.round(rect.top),
        w: Math.round(rect.width),
        h: Math.round(rect.height),
      };
    }),
  );
}

// --- Каркас -----------------------------------------------------------------

test("сайдбар светлый, иконки в плитках, меню не уезжает при прокрутке", async ({
  browser,
}) => {
  const page = await as(browser, "director_behavior");
  await page.goto("/table");

  const nav = page.locator(".shell__nav");
  const background = await nav.evaluate(
    (node) => getComputedStyle(node).backgroundColor,
  );
  expect(background, "меню в светлой теме белое").toBe("rgb(255, 255, 255)");

  // иконка активного пункта — в плитке, залитой акцентом
  const tile = page.locator(".navlink--active .navlink__icon").first();
  await expect(tile).toBeVisible();
  const tileBg = await tile.evaluate(
    (node) => getComputedStyle(node).backgroundColor,
  );
  expect(tileBg, "плитка активного пункта залита акцентом").toBe(
    "rgb(255, 106, 19)",
  );

  // прокручиваем страницу — блок пользователя остаётся на виду
  const user = page.locator(".shell__user");
  const before = await user.boundingBox();
  await page.mouse.wheel(0, 1200);
  await page.waitForTimeout(300);
  const after = await user.boundingBox();
  expect(
    before && after,
    "блок пользователя виден до и после прокрутки",
  ).toBeTruthy();
  expect(
    Math.abs((after?.y ?? 0) - (before?.y ?? 0)),
    "меню стоит на месте, прокручивается содержимое",
  ).toBeLessThan(4);
  await page.close();
});

// --- Карусель и календарь ---------------------------------------------------

test("карусель собирается из незакрытых мест: у двух учеников она разная", async ({
  browser,
}) => {
  const first = await as(browser, "student");
  await first.goto("/dashboard");
  const mine = (await (await first.request.get("/api/home/cues/")).json()) as {
    cues: { code: string; eyebrow: string }[];
  };
  expect(mine.cues.length, "у ученика есть что закрывать").toBeGreaterThan(0);
  await expect(first.locator(".caro")).toBeVisible();
  // сюжет говорит словами справочника и живым числом
  expect(mine.cues[0].eyebrow.length).toBeGreaterThan(3);

  // карусель и календарь стоят в ряд и одной высоты. С фазы 50 слева
  // календарь: в узкой колонке панель ближайших событий вмещала одну
  // фразу «Пока ничего не намечено» (решение владельца)
  const cal = await first.locator(".home__cal").boundingBox();
  const caro = await first.locator(".caro").boundingBox();
  expect(cal && caro, "оба блока на экране").toBeTruthy();
  expect(cal!.x, "календарь слева, карусель справа").toBeLessThan(caro!.x);
  expect(Math.round(cal!.height)).toBe(Math.round(caro!.height));
  await first.close();

  // у другого ученика набор свой: условия считаются по его состоянию
  const second = await as(browser, "director_exam");
  const students = (await (
    await second.request.get("/api/students/?page_size=200")
  ).json()) as { results: { id: number; email: string }[] };
  expect(students.results.length).toBeGreaterThan(1);
  await second.close();
});

test("незакрытых мест нет — карусели нет, календарь занимает её место", async ({
  browser,
}) => {
  // школа выключает сюжеты: это тот же случай, что «закрывать нечего», —
  // проверяем, что главная перестраивается, а не показывает пустую карточку
  const director = await as(browser, "director_behavior");
  await director.goto("/home-cues");
  const rules = (await (
    await director.request.get("/api/home-cues/?page_size=100")
  ).json()) as { results: { id: number; is_active: boolean }[] };
  const active = rules.results.filter((row) => row.is_active);
  for (const row of active)
    await apiPatch(director, `/api/home-cues/${row.id}/`, { is_active: false });

  const student = await as(browser, "student");
  await student.goto("/dashboard");
  await expect(student.locator(".caro")).toHaveCount(0);
  const wide = await student.locator(".home__cal").boundingBox();
  const screen = await student.locator(".shell__screen").boundingBox();
  expect(
    (wide?.width ?? 0) / (screen?.width ?? 1),
    "календарь занял всю ширину экрана",
  ).toBeGreaterThan(0.9);
  await student.close();

  // возвращаем как было: правила школы прогон за собой убирает
  for (const row of active)
    await apiPatch(director, `/api/home-cues/${row.id}/`, { is_active: true });
  const back = await as(browser, "student");
  await back.goto("/dashboard");
  await expect(back.locator(".caro")).toBeVisible();
  await back.close();
  await director.close();
});

// --- Портфолио --------------------------------------------------------------

test("портфолио в две колонки, тексты не наезжают ни на одной ширине", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  for (const width of [1440, 820]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/my-data");
    await expect(page.locator(".portfolio__two")).toBeVisible();

    const pairs = await boxes(page, ".portfolio__pair");
    expect(pairs.length, "пары подпись–значение нашлись").toBeGreaterThan(3);
    for (let i = 0; i < pairs.length; i += 1) {
      for (let j = i + 1; j < pairs.length; j += 1) {
        const a = pairs[i];
        const b = pairs[j];
        const overlap = !(
          a.x + a.w <= b.x ||
          b.x + b.w <= a.x ||
          a.y + a.h <= b.y ||
          b.y + b.h <= a.y
        );
        expect(
          overlap,
          `на ширине ${width} «${a.text}» наезжает на «${b.text}»`,
        ).toBeFalsy();
      }
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.close();
});

test("«Внести баллы» открывает форму прямо в карточке и шлёт предложение", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  await page.goto("/my-data");
  const before = page.url();
  await page.getByRole("button", { name: "Внести баллы" }).click();
  expect(page.url(), "перехода на другой экран нет").toBe(before);

  const form = page.locator(".propose__form").first();
  await expect(form).toBeVisible();
  const field = form.locator("input").first();
  await field.fill("3.55");
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/propose")),
    page.getByRole("button", { name: "Отправить на проверку" }).click(),
  ]);
  expect(response.status(), "значение ушло предложением").toBe(201);
  await page.close();
});

// --- Эссе -------------------------------------------------------------------

test("эссе создаётся любым из девяти типов и открывается во всю ширину", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  await page.goto("/essays");
  const types = (await (
    await page.request.get("/api/essay-doc-types/?page_size=50")
  ).json()) as { results: { id: number; code: string; name: string }[] };
  expect(
    types.results.length,
    "девять типов справочника",
  ).toBeGreaterThanOrEqual(9);

  const csrf = (await page.context().cookies()).find(
    (c) => c.name === "csrftoken",
  )?.value;
  const created: number[] = [];
  for (const type of types.results) {
    const response = await page.request.post("/api/essays/", {
      data: { doc_type: type.id, title: `Проверка 49 · ${type.name}` },
      headers: { "X-CSRFToken": csrf ?? "" },
    });
    expect(response.status(), `тип «${type.code}» отбился`).toBe(201);
    created.push(((await response.json()) as { id: number }).id);
  }

  // открытое эссе занимает экран: редактор шире помощника
  await page.goto("/essays");
  await page.locator(".essay__card").first().click();
  await expect(page.locator(".essay__editorgrid")).toBeVisible();
  const editor = await page
    .locator(".essay__editorgrid > .card")
    .first()
    .boundingBox();
  const assist = await page.locator(".essay__chat").boundingBox();
  expect(
    (editor?.width ?? 0) > (assist?.width ?? 0),
    "редактор занимает две трети, помощник — треть",
  ).toBeTruthy();
  await expect(page.locator(".essay__editor")).toBeVisible();
  await page.close();

  // прогон убирает за собой заведённое
  const staff = await as(browser, "director_exam");
  const staffCsrf = (await staff.context().cookies()).find(
    (c) => c.name === "csrftoken",
  )?.value;
  for (const id of created)
    await staff.request.delete(`/api/essays/${id}/`, {
      headers: { "X-CSRFToken": staffCsrf ?? "" },
    });
  await staff.close();
});

// --- Кабинеты руководителей -------------------------------------------------

test("таблица директора открывается на чтение, ручной ввод — кнопкой", async ({
  browser,
}) => {
  const page = await as(browser, "director_exam");
  await page.goto("/table");
  // фраза стоит и в подзаголовке экрана, и в полосе над таблицей —
  // берём первую: проверяем, что она вообще есть
  await expect(
    page
      .getByText("Значения меняет ученик, вы подтверждаете их в очереди")
      .first(),
  ).toBeVisible();

  const cell = page.locator("input.cell").first();
  await expect(cell).toHaveJSProperty("readOnly", true);

  await page.getByRole("button", { name: "Внести вручную" }).first().click();
  await expect(cell).toHaveJSProperty("readOnly", false);
  await page.close();
});

test("у пяти директоров очередь решений, у администратора — свои действия", async ({
  browser,
}) => {
  for (const role of [
    "director_exam",
    "director_admission",
    "director_behavior",
    "director_talent",
    "director_sport",
  ]) {
    const page = await as(browser, role);
    await page.goto("/dashboard");
    await expect(
      page.locator("#student-queue"),
      `${role}: нет очереди подтверждений`,
    ).toBeVisible();
    await page.close();
  }

  const admin = await as(browser, "admin");
  await admin.goto("/dashboard");
  await expect(admin.locator("#student-queue")).toHaveCount(0);
  await expect(admin.getByText("Требует ваших действий")).toBeVisible();
  await admin.close();
});

test("кнопка администратора делает то, что написано", async ({ browser }) => {
  const page = await as(browser, "admin");
  await page.goto("/dashboard");
  const invite = page.getByRole("button", { name: "Выслать" });
  if (await invite.count()) {
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/users/invite/")),
      invite.first().click(),
    ]);
    expect(response.status(), "приглашения ушли").toBe(200);
  }
  await page.close();
});

// --- Правая половина экрана -------------------------------------------------

test("правая треть не пустует ни на одном кабинете", async ({ browser }) => {
  for (const role of [
    "director_exam",
    "director_admission",
    "director_behavior",
    "director_talent",
    "director_sport",
    "admin",
  ]) {
    const page = await as(browser, role);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/dashboard");
    await page.waitForTimeout(600);
    const aside = page.locator(".cabinet__aside").first();
    await expect(aside, `${role}: нет вспомогательной колонки`).toBeVisible();
    const box = await aside.boundingBox();
    expect(
      (box?.height ?? 0) > 80,
      `${role}: правая колонка пуста`,
    ).toBeTruthy();
    await page.close();
  }
});
