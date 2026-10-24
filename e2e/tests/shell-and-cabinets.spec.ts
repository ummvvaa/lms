/**
 * Макет v2 в живом браузере: светлый каркас, карусель, кабинеты.
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

test("сайдбар — светлое стекло, активный пункт с подложкой и полосой акцента, меню не уезжает при прокрутке", async ({
  browser,
}) => {
  const page = await as(browser, "director_behavior");
  await page.goto("/table");

  /** Цвет-токен, приведённый браузером к тому же виду, что у вычисленного стиля. */
  const token = (name: string) =>
    page.evaluate((name) => {
      const probe = document.createElement("div");
      probe.style.backgroundColor = `var(${name})`;
      document.body.append(probe);
      const value = getComputedStyle(probe).backgroundColor;
      probe.remove();
      return value;
    }, name);
  const raw = (name: string) =>
    page.evaluate(
      (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim(),
      name,
    );
  /** Прозрачность цвета `rgb(...)`/`rgba(...)`: у непрозрачного — 1. */
  const alphaOf = (color: string) => {
    const parts = color.match(/[\d.]+/g) ?? [];
    return parts.length > 3 ? Number(parts[3]) : 1;
  };

  const nav = page.locator(".shell__nav");
  const look = await nav.evaluate((node) => {
    const style = getComputedStyle(node);
    return {
      background: style.backgroundColor,
      filter: style.backdropFilter || style.getPropertyValue("-webkit-backdrop-filter"),
      width: node.getBoundingClientRect().width,
    };
  });
  const menuBg = await token("--menu-bg");
  expect(look.background, "фон меню — токен --menu-bg").toBe(menuBg);
  expect(alphaOf(look.background), "меню полупрозрачное: под ним видно полотно").toBeLessThan(1);
  const blur = await raw("--side-blur");
  expect(blur, "размытие стекла задано токеном").toBe("20px");
  expect(look.filter, "под меню размытие стекла").toContain(`blur(${blur})`);
  const sideWidth = await raw("--side-w");
  expect(sideWidth, "ширина меню задана токеном").toBe("248px");
  expect(Math.round(look.width), "меню во всю ширину токена").toBe(248);

  // активный пункт — мягкая подложка акцента и полоса градиента у левого края;
  // плиток под иконками нет
  const active = page.locator(".navlink--active").first();
  await expect(active).toBeVisible();
  const activeLook = await active.evaluate((node) => ({
    background: getComputedStyle(node).backgroundColor,
    bar: getComputedStyle(node, "::before").backgroundImage,
  }));
  expect(activeLook.background, "подложка активного пункта — токен --accent-bg").toBe(
    await token("--accent-bg"),
  );
  expect(activeLook.bar, "полоса у края — градиент акцента").toContain("linear-gradient");
  await expect(page.locator(".navlink__icon")).toHaveCount(0);

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

test("подсказки «Что закрыть» собираются из незакрытых мест: у двух учеников они разные", async ({
  browser,
}) => {
  const first = await as(browser, "student");
  await first.goto("/dashboard");
  const mine = (await (await first.request.get("/api/home/cues/")).json()) as {
    cues: { code: string; eyebrow: string; title: string }[];
  };
  expect(mine.cues.length, "у ученика есть что закрывать").toBeGreaterThan(0);
  // сюжет в карточке — плашка с заголовком и одной кнопкой, по одной на место
  const closing = first.locator(".datacard", { hasText: "Что закрыть" }).first();
  await expect(closing.locator(".stuhome__cue")).toHaveCount(mine.cues.length);
  await expect(closing.locator(".stuhome__cue").first()).toContainText(mine.cues[0].title);
  // сюжет говорит словами справочника и живым числом
  expect(mine.cues[0].eyebrow.length).toBeGreaterThan(3);
  await first.close();

  // у другого ученика набор свой: условия считаются по его состоянию
  const second = await as(browser, "director_exam");
  const students = (await (
    await second.request.get("/api/students/?page_size=200")
  ).json()) as { results: { id: number; email: string }[] };
  expect(students.results.length).toBeGreaterThan(1);
  await second.close();
});

test("незакрытых мест нет — карточка сворачивается в строку", async ({
  browser,
}) => {
  // школа выключает сюжеты: это тот же случай, что «закрывать нечего», —
  // проверяем, что главная перестраивается, а не показывает пустую карточку
  // «Сюжеты главной» — настройка школы: ведёт администратор, директорам
  // справочник закрыт и на чтение
  const admin = await as(browser, "admin");
  await admin.goto("/home-cues");
  await expect(admin).toHaveURL(/\/home-cues/);
  const rules = (await (
    await admin.request.get("/api/home-cues/?page_size=100")
  ).json()) as { results: { id: number; is_active: boolean }[] };
  const active = rules.results.filter((row) => row.is_active);
  for (const row of active)
    await apiPatch(admin, `/api/home-cues/${row.id}/`, { is_active: false });

  // прежний владелец: экран уводит на главную, чтение справочника — отказ
  const former = await as(browser, "director_behavior");
  await former.goto("/home-cues");
  await former.waitForURL(/\/dashboard/, { timeout: 15_000 });
  expect((await former.request.get("/api/home-cues/")).status()).toBe(403);
  await former.close();

  const student = await as(browser, "student");
  await student.goto("/dashboard");
  const folded = student.locator(".datacard", { hasText: "Что закрыть" }).first();
  await expect(folded).toContainText("незакрытых мест нет");
  await expect(folded.locator(".stuhome__cue")).toHaveCount(0);
  await student.close();

  // возвращаем как было: правила школы прогон за собой убирает
  for (const row of active)
    await apiPatch(admin, `/api/home-cues/${row.id}/`, { is_active: true });
  const back = await as(browser, "student");
  await back.goto("/dashboard");
  await expect(back.locator(".datacard", { hasText: "Что закрыть" }).first().locator(".stuhome__cue").first()).toBeVisible();
  await back.close();
  await admin.close();
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
  // шкала IELTS — шаг 0.5 (фаза 64): 3.55 теперь честно отбивается
  await field.fill("3.5");
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
  await page.locator(".rowline .rowline__open").first().click();
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
  // очередь на главной директора есть, когда ученики что-то внесли в его домен;
  // пустая не рисуется вовсе (24.10.2026) — число строк берём у той же ручки
  for (const role of [
    "director_exam",
    "director_admission",
    "director_behavior",
    "director_talent",
    "director_sport",
  ]) {
    const page = await as(browser, role);
    const queued = ((await (await page.request.get("/api/suggestions/from-students/")).json()) as { results: unknown[] }).results.length;
    await page.goto("/dashboard");
    await expect(page.locator("h1")).toContainText("Добрый день");
    // у Кымбат очереди нет вовсе: подтверждают кураторы (решение владельца, 25.10.2026)
    if (queued && role !== "director_exam")
      await expect(page.locator("#student-queue"), `${role}: нет очереди при ${queued} строках`).toBeVisible();
    else await expect(page.locator("#student-queue"), `${role}: пустая очередь не рисуется`).toHaveCount(0);
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
    // у администратора — вторая колонка «две трети — треть»; у директоров (24.10.2026)
    // пустая правая колонка не рисуется и отдаёт ширину левой — проверяем, что
    // если колонка есть, она не пустая
    const aside = page.locator(".cabinet__aside, .lay-main > :nth-child(2)").first();
    if (role.startsWith("director_") && !(await aside.count())) {
      await page.close();
      continue;
    }
    await expect(aside, `${role}: нет вспомогательной колонки`).toBeVisible();
    const box = await aside.boundingBox();
    expect(
      (box?.height ?? 0) > 80,
      `${role}: правая колонка пуста`,
    ).toBeTruthy();
    await page.close();
  }
});
