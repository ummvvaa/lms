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
];

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

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    viewport: LAPTOP,
  });
  const page = await context.newPage();
  // подсказка первого входа перекрывает экран целиком — она проверяется
  // отдельно и в сравнении раскладки только мешает
  await page.addInitScript(() =>
    window.localStorage.setItem("first-run-seen", "1"),
  );
  await page.clock.setFixedTime(new Date(`${serverToday}T09:30:00Z`));
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
