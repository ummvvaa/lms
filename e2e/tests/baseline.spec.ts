/**
 * Эталоны раскладки: десктоп 1440 не поехал (фазы 51 и 54).
 *
 * До фазы 54 эти снимки жили внутри `phase51.spec.ts` и сравнивались
 * с тем, что оставила в базе сотня проверок, отработавших раньше:
 * у ученика каждый раз были другие GPA, IELTS и процент портфолио,
 * а условная плашка «Привяжите личную почту» то показывалась, то нет
 * и сдвигала всё содержимое вниз. Сравнение краснело там, где раскладка
 * не менялась (D29), и уносило за собой 22 телефонные проверки: файл
 * идёт в serial-режиме.
 *
 * Теперь снимки живут своим проектом в самом конце прогона, а перед ними
 * работает `seed-baseline.spec.ts`: обнуление базы и школа, заведённая
 * закреплёнными числами. Порог остался долей пикселей, а не нулём —
 * сглаживание шрифтов даёт фон само по себе, — но краснеть ему теперь
 * не от чего, кроме настоящего сдвига раскладки.
 *
 * Снять заново: npm test -- --project=baseline-seed --project=baseline --update-snapshots
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";

test.describe.configure({ mode: "serial", timeout: 240_000 });

const LAPTOP = { width: 1440, height: 900 };

/** Экраны, которые фазы 49–51 задели сильнее всего: каркас, календарь,
 *  формы внесения, таблицы и очередь подтверждений. */
const DESKTOP_SCREENS: { role: string; path: string }[] = [
  { role: "student", path: "/dashboard" },
  { role: "student", path: "/my-data" },
  { role: "student", path: "/calendar" },
  { role: "student", path: "/roadmap" },
  { role: "director_exam", path: "/dashboard" },
  { role: "director_exam", path: "/table" },
  { role: "director_exam", path: "/suggestions" },
  { role: "director_admission", path: "/dashboard" },
  { role: "director_behavior", path: "/dashboard" },
  { role: "director_talent", path: "/dashboard" },
  { role: "director_sport", path: "/dashboard" },
  { role: "admin", path: "/dashboard" },
  { role: "admin", path: "/users" },
  // кабинет куратора (фазы 60 и 61): главная, очередь, ученики
  { role: "curator", path: "/dashboard" },
  { role: "curator", path: "/queue" },
  { role: "curator", path: "/students" },
  { role: "curator", path: "/documents" },
  { role: "curator", path: "/mock-imports" },
];

/** Экраны, которые проверяются ещё и на телефоне (фаза 61).
 *
 *  Кабинет куратора — первый раздел, собранный сразу под две ширины:
 *  куратор смотрит очередь с телефона чаще, чем за столом. */
const PHONE_SCREENS: { role: string; path: string }[] = [
  { role: "curator", path: "/dashboard" },
  { role: "curator", path: "/queue" },
  { role: "curator", path: "/documents" },
  { role: "curator", path: "/mock-imports" },
];

const PHONE = { width: 390, height: 844 };

/**
 * Что маскируем — и почему именно это.
 *
 * Даты в базе закреплены, но «сколько дней осталось» считает сервер от
 * своего настоящего сегодня, и число меняется каждые сутки. Маскируется
 * ровно это число, а не карточка вокруг него: порог — не лечение, но
 * и прятать половину экрана ради одной цифры незачем.
 */
const MASKS = [
  // «Ближайшее событие» на экране календаря: справа обратный отсчёт
  ".cal__nearestrow .t-figure",
  // время подачи в строке очереди: настоящее, меняется каждым прогоном.
  // Маскируется только оно, а не строка целиком — раскладку строки
  // эталон обязан ловить (фаза 61)
  ".squeue__when",
];

/**
 * Часы браузера, остановленные на сегодняшнем дне сервера.
 *
 * Календарь берёт день из ответа API, а не из часов страницы, поэтому
 * сетку месяца это не двигает. Но всё, что фронт считает сам от
 * `new Date()`, перестаёт зависеть от того, в какую минуту пошёл прогон:
 * снимок в 23:59 и снимок в 00:01 больше не разные.
 */
let serverToday = "";

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({
    storageState: statePath("student"),
  });
  const state = await (await context.request.get("/api/calendar/")).json();
  serverToday = String(state.today ?? "");
  await context.close();
  expect(serverToday, "сервер не сказал, какое сегодня число").toMatch(
    /^\d{4}-\d{2}-\d{2}$/,
  );
});

async function as(
  browser: Browser,
  role: string,
  viewport = LAPTOP,
): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    viewport,
  });
  const page = await context.newPage();
  // подсказка первого входа перекрывает экран целиком — она проверяется
  // отдельно и в сравнении раскладки только мешает
  await page.addInitScript(() =>
    window.localStorage.setItem("first-run-seen", "1"),
  );
  await page.clock.setFixedTime(new Date(`${serverToday}T09:30:00Z`));
  // тема — светлая явно: она хранится на сервере, и упавшая раньше съёмка
  // тёмной темы иначе красила эталон в тёмный (фаза 63). Меню — раскрытым
  // по той же причине (фаза 70): сценарий, свернувший его, оставляет
  // настройку в базе, и весь снимок уезжает вбок на ширину меню
  const csrf =
    (await context.cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
  await page.request
    .patch("/api/auth/me/preferences/", {
      data: { theme: "light", sidebar_collapsed: false },
      headers: { "X-CSRFToken": csrf },
    })
    .catch(() => undefined);
  return page;
}

/** Ждём, пока экран дорисуется, и останавливаем карусель.
 *
 *  Карусель листается сама раз в семь секунд: без остановки два снимка
 *  одного и того же экрана показывают разные сюжеты. Останавливается
 *  она наведением — тем же способом, что у живого человека. */
async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(600);
  const caro = page.locator(".home__caro").first();
  if (await caro.isVisible().catch(() => false)) {
    await caro.hover().catch(() => undefined);
    await page.waitForTimeout(200);
  }
}

test.describe("телефон 390 не изменился", () => {
  for (const screen of PHONE_SCREENS) {
    const name = `phone-${screen.role}${screen.path.replace(/\//g, "_")}.png`;
    test(`телефон ${screen.role} ${screen.path}`, async ({ browser }) => {
      const page = await as(browser, screen.role, PHONE);
      await page.goto(screen.path);
      await settle(page);
      await expect(page).toHaveScreenshot(name, {
        fullPage: true,
        animations: "disabled",
        caret: "hide",
        scale: "css",
        mask: MASKS.map((selector) => page.locator(selector)),
        threshold: 0.25,
        maxDiffPixelRatio: 0.02,
      });
      await page.context().close();
    });
  }
});

/** Карточка ученика под пятью ролями на двух ширинах (фаза 73): блок
 *  «Поступление» один у всех, и вид его — тоже. Ученик — первый из посева
 *  эталонов, его id приходит из API, а не из адреса. */
const CARD_ROLES = [
  "curator",
  "director_admission",
  "admin",
  "director_exam",
  "director_behavior",
];

async function firstPupil(page: Page): Promise<number> {
  const list = (await (
    await page.request.get("/api/students/?page_size=500")
  ).json()) as { results: { id: number; email: string }[] };
  const row = list.results.find((r) => r.email === probeEmail("base01"));
  expect(row, "ученик посева эталонов").toBeTruthy();
  return row!.id;
}

test.describe("карточка ученика не изменилась", () => {
  for (const role of CARD_ROLES) {
    for (const [tag, viewport] of [
      ["", LAPTOP],
      ["phone-", PHONE],
    ] as const) {
      const name = `${tag}${role}_students_card.png`;
      test(`карточка ${tag ? "телефон" : "раскладка"} ${role}`, async ({
        browser,
      }) => {
        const page = await as(browser, role, viewport);
        const id = await firstPupil(page);
        await page.goto(`/students/${id}`);
        await settle(page);
        await expect(page).toHaveScreenshot(name, {
          fullPage: true,
          animations: "disabled",
          caret: "hide",
          scale: "css",
          mask: MASKS.map((selector) => page.locator(selector)),
          threshold: 0.25,
          maxDiffPixelRatio: 0.02,
        });
        await page.context().close();
      });
    }
  }
});

test.describe("десктоп 1440 не изменился", () => {
  for (const screen of DESKTOP_SCREENS) {
    const name = `${screen.role}${screen.path.replace(/\//g, "_")}.png`;
    test(`раскладка ${screen.role} ${screen.path}`, async ({ browser }) => {
      const page = await as(browser, screen.role);
      await page.goto(screen.path);
      await settle(page);
      await expect(page).toHaveScreenshot(name, {
        fullPage: true,
        animations: "disabled",
        caret: "hide",
        scale: "css",
        mask: MASKS.map((selector) => page.locator(selector)),
        // сглаживание шрифтов и субпиксельный сдвиг тени дают до процента
        // отличий сами по себе; настоящая правка раскладки даёт больше
        threshold: 0.25,
        maxDiffPixelRatio: 0.02,
      });
      await page.context().close();
    });
  }
});
