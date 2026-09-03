/**
 * Фаза 51 — телефонная версия.
 *
 * Две части. Первая доказывает, что десктоп не поехал: снимки на 1440
 * сверяются с эталонами, снятыми до первой правки фазы. Расхождение —
 * повод посмотреть глазами, поэтому порог задан долей пикселей, а не
 * нулём: сглаживание шрифтов даёт фон само по себе.
 *
 * Вторая — телефон: 390×844 под каждой из семи ролей.
 *
 * Эталоны лежат в `e2e/shots/baseline/` (каталог снимков в git не идёт).
 * Снять заново: E2E_UPDATE_BASELINE=1 npx playwright test tests/phase51.spec.ts
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";

test.describe.configure({ mode: "serial", timeout: 240_000 });

const LAPTOP = { width: 1440, height: 900 };

/** Экраны, которые фаза задевает сильнее всего: каркас, календарь,
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
        // сглаживание шрифтов и субпиксельный сдвиг тени дают до процента
        // отличий сами по себе; настоящая правка раскладки даёт больше
        threshold: 0.25,
        maxDiffPixelRatio: 0.02,
      });
      await page.context().close();
    });
  }
});

/* ------------------------------------------------------------------ *
 *  Телефон: 390×844
 * ------------------------------------------------------------------ */

const PHONE = { width: 390, height: 844 };

/** Экраны, которые смотрим глазами на телефоне у каждой роли. */
const PHONE_SHOTS: Record<string, string[]> = {
  student: [
    "/dashboard",
    "/my-data",
    "/calendar",
    "/roadmap",
    "/universities",
    "/catalog",
    "/scholarships",
  ],
  director_exam: ["/dashboard", "/table", "/suggestions", "/digest"],
  director_admission: ["/dashboard", "/table"],
  director_behavior: ["/dashboard", "/table"],
  director_talent: ["/dashboard", "/table"],
  director_sport: ["/dashboard", "/table"],
  admin: ["/dashboard", "/users"],
};

test.describe("телефон 390×844", () => {
  /** Разделы бара у каждой роли — те же четвёрки, что в `nav.ts`. */
  const TABS: Record<string, string[]> = {
    student: ["Главная", "Портфолио", "Роадмап", "Вузы"],
    director_behavior: ["Дашборд", "Предложения", "Таблица", "Контакты"],
    director_admission: ["Дашборд", "Предложения", "Таблица", "Дедлайны"],
    director_exam: ["Дашборд", "Предложения", "Таблица", "Пробные"],
    director_talent: ["Дашборд", "Предложения", "Таблица", "Материалы"],
    director_sport: ["Дашборд", "Предложения", "Таблица", "Соревнования"],
    admin: ["Дашборд", "Пользователи", "Таблица", "Предложения"],
  };

  test("нижний бар: четыре раздела роли, «Ещё» и запас под баром", async ({
    browser,
  }) => {
    for (const [role, labels] of Object.entries(TABS)) {
      const page = await as(browser, role, PHONE);
      await page.goto("/dashboard");
      await settle(page);

      // бокового меню на телефоне нет вовсе — ни полосы, ни ленты
      await expect(page.locator(".shell__nav")).toBeHidden();

      const bar = page.locator(".tabbar");
      await expect(bar).toBeVisible();
      const items = bar.locator(".tabbar__item");
      await expect(items).toHaveCount(5);

      const measured = await page.evaluate(() => {
        const nav = document.querySelector(".tabbar") as HTMLElement;
        const screen = document.querySelector(".shell__screen") as HTMLElement;
        const items = [
          ...nav.querySelectorAll(".tabbar__item"),
        ] as HTMLElement[];
        return {
          labels: items.map((item) =>
            (item.querySelector(".tabbar__label")?.textContent ?? "").trim(),
          ),
          heights: items.map((item) => item.getBoundingClientRect().height),
          barTop: nav.getBoundingClientRect().top,
          barBottom: nav.getBoundingClientRect().bottom,
          viewport: window.innerHeight,
          padBottom: parseFloat(getComputedStyle(screen).paddingBottom),
          barHeight: nav.getBoundingClientRect().height,
          // самое нижнее содержимое экрана: оно не должно уходить под бар
          contentBottom: screen.getBoundingClientRect().bottom,
          docBottom: document.documentElement.scrollHeight,
        };
      });

      expect(measured.labels).toEqual([...labels, "Ещё"]);
      for (const height of measured.heights)
        expect(height).toBeGreaterThanOrEqual(44);
      // бар стоит у нижнего края окна, а не посреди страницы
      expect(
        Math.abs(measured.barBottom - measured.viewport),
      ).toBeLessThanOrEqual(1);
      // запас снизу больше высоты бара: под ним не остаётся ничего,
      // до чего нельзя дотянуться
      expect(measured.padBottom).toBeGreaterThan(measured.barHeight);

      // подпись — одно слово и целиком, без многоточия от обрезки
      const clipped = await page.evaluate(() =>
        [...document.querySelectorAll(".tabbar__label")].some(
          (node) => node.scrollWidth > node.clientWidth,
        ),
      );
      expect(clipped, `${role}: подпись в баре не помещается`).toBe(false);

      await page.context().close();
    }
  });

  test("горизонтального выезда нет ни на одном экране ни в одной роли", async ({
    browser,
  }) => {
    for (const [role, screens] of Object.entries(PHONE_SHOTS)) {
      const page = await as(browser, role, PHONE);
      for (const screen of screens) {
        await page.goto(screen);
        await settle(page);
        const overflow = await page.evaluate(() => {
          // блок за правым краем считается выехавшим, только если его
          // никто не обрезает: у карусели дорожка шире экрана всегда —
          // на то она и карусель, и прокрутки страницы это не даёт
          const escaped: string[] = [];
          for (const node of document.querySelectorAll("body *")) {
            const box = node.getBoundingClientRect();
            if (box.width === 0 || box.right <= window.innerWidth + 1) continue;
            let clipped = false;
            for (
              let parent = node.parentElement;
              parent;
              parent = parent.parentElement
            ) {
              if (getComputedStyle(parent).overflowX !== "visible") {
                clipped = true;
                break;
              }
            }
            if (!clipped) escaped.push(`${node.tagName}.${node.className}`);
          }
          return {
            doc: document.documentElement.scrollWidth,
            win: window.innerWidth,
            escaped: escaped.slice(0, 5),
          };
        });
        expect(
          overflow.doc,
          `${role} ${screen}: страница едет вбок`,
        ).toBeLessThanOrEqual(overflow.win + 1);
        expect(
          overflow.escaped,
          `${role} ${screen}: блок торчит за правый край`,
        ).toEqual([]);
      }
      await page.context().close();
    }
  });

  test("календарь: лента первой, месяц по кнопке, режим переживает перезагрузку", async ({
    browser,
  }) => {
    const page = await as(browser, "student", PHONE);
    await page.goto("/dashboard");
    await settle(page);

    // у нового человека память пуста — открывается лента
    const feed = page.locator(".calfeed");
    await expect(feed).toBeVisible();
    await expect(page.locator(".calgrid--phone")).toHaveCount(0);

    // переключение в месяц: сетка, ячейка не ниже 34px, число в кружке 24px
    await page.getByRole("button", { name: "Месяц", exact: true }).click();
    await expect(page.locator(".calgrid--phone")).toBeVisible();
    const grid = await page.evaluate(() => {
      const cells = [...document.querySelectorAll(".calcell")] as HTMLElement[];
      const day = document.querySelector(".calcell__day") as HTMLElement;
      const columns = getComputedStyle(
        document.querySelector(".calgrid--phone") as HTMLElement,
      ).gridTemplateColumns.split(" ").length;
      return {
        columns,
        cell: Math.min(...cells.map((c) => c.getBoundingClientRect().height)),
        day: day.getBoundingClientRect().width,
        picked: document.querySelectorAll(".calcell--picked").length,
        dots: Math.max(
          0,
          ...[...document.querySelectorAll(".calcell__dots")].map(
            (node) => node.childElementCount,
          ),
        ),
      };
    });
    expect(grid.columns).toBe(7);
    expect(grid.cell).toBeGreaterThanOrEqual(34);
    expect(Math.round(grid.day)).toBe(24);
    // по умолчанию выбран сегодняшний день
    expect(grid.picked).toBe(1);
    // точек не больше трёх, сколько бы событий в дне ни было
    expect(grid.dots).toBeLessThanOrEqual(3);
    // панель выбранного дня — под сеткой, а не сбоку
    await expect(page.locator(".calday")).toBeVisible();

    // режим пережил перезагрузку
    await page.reload();
    await settle(page);
    await expect(page.locator(".calgrid--phone")).toBeVisible();
    await expect(page.locator(".calfeed")).toHaveCount(0);

    // и вернулся обратно
    await page.getByRole("button", { name: "Лента", exact: true }).click();
    await expect(page.locator(".calfeed")).toBeVisible();
    await page.reload();
    await settle(page);
    await expect(page.locator(".calfeed")).toBeVisible();

    // ключ памяти — с ролью: у директора свой
    const key = await page.evaluate(() =>
      Object.keys(localStorage).filter((k) => k.startsWith("calendar.mode.")),
    );
    expect(key).toEqual(["calendar.mode.student"]);

    await page.context().close();
  });

  test("лента: события по месяцам, четыре строки и «Ещё N событий»", async ({
    browser,
  }) => {
    // события заводит директор — тем же путём, что в жизни: задачи ученику
    // со сроками. На чистой базе впереди у ученика пусто, и проверять
    // ленту было бы не на чем
    const director = await as(browser, "director_exam", LAPTOP);
    await director.goto("/dashboard");
    const students = (await (
      await director.request.get(
        `/api/students/?search=${encodeURIComponent("student@probe.local")}`,
      )
    ).json()) as { results: { id: number; email: string }[] };
    const student = students.results.find(
      (row) => row.email === "student@probe.local",
    );
    expect(student, "ученик прогона на месте").toBeTruthy();

    const csrf =
      (await director.context().cookies()).find((c) => c.name === "csrftoken")
        ?.value ?? "";
    const shift = (days: number) => {
      const date = new Date();
      date.setDate(date.getDate() + days);
      return date.toISOString().slice(0, 10);
    };
    // шесть событий в трёх месяцах: четыре видны сразу, две прячутся
    // за «Ещё 2 события»
    const created: number[] = [];
    for (const days of [2, 5, 9, 14, 40, 70]) {
      const made = await director.request.post("/api/tasks/", {
        data: {
          student: student!.id,
          title: `Проверка ленты: ${days} дн.`,
          category: "documents",
          due_date: shift(days),
        },
        headers: { "X-CSRFToken": csrf },
      });
      expect(made.ok(), await made.text()).toBe(true);
      created.push(((await made.json()) as { id: number }).id);
    }

    try {
      const page = await as(browser, "student", PHONE);
      await page.goto("/dashboard");
      await settle(page);

      const feed = await page.evaluate(() => {
        const card = document.querySelector(".home__cal--phone") as HTMLElement;
        const head = document.querySelector(
          ".screenhead",
        ) as HTMLElement | null;
        const rows = [...document.querySelectorAll(".calfeed__row")];
        return {
          rows: rows.length,
          months: [...document.querySelectorAll(".calfeed__month")].map(
            (node) => (node.textContent ?? "").trim(),
          ),
          more: (
            document.querySelector(".calfeed__more")?.textContent ?? ""
          ).trim(),
          cardHeight: card.getBoundingClientRect().height,
          headHeight: head ? head.getBoundingClientRect().height : 0,
          // название события переносится по словам, а не режется
          clipped: rows.some((row) => {
            const title = row.querySelector(".calfeed__title") as HTMLElement;
            return title.scrollWidth > title.clientWidth + 1;
          }),
          // прошедшего в ленте нет
          past: rows.some((row) =>
            (row.textContent ?? "").includes("Проверка ленты: -"),
          ),
        };
      });

      expect(feed.rows, "в ленте видно четыре строки").toBe(4);
      expect(feed.months.length, "у группы есть заголовок месяца").toBe(1);
      expect(feed.more).toContain("Ещё");
      expect(feed.clipped, "название события не режется").toBe(false);
      expect(feed.past, "прошедших событий в ленте нет").toBe(false);
      // карточка вместе с заголовком экрана и шапкой помещается в первый
      // экран телефона: 56 — высота шапки поиска
      expect(feed.cardHeight + feed.headHeight + 56).toBeLessThanOrEqual(844);

      // кадр с живыми событиями — для просмотра глазами: на чистой базе
      // впереди у ученика пусто, и лента на снимках пустая
      const fs = await import("node:fs");
      const path = await import("node:path");
      const dir = path.join(__dirname, "..", "shots", "phone");
      fs.mkdirSync(dir, { recursive: true });
      await page.screenshot({
        path: path.join(dir, "student_feed.png"),
        fullPage: true,
      });

      // «Ещё N событий» раскрывает остаток на месте, а не уводит на экран
      await page.locator(".calfeed__more").click();
      await expect(page.locator(".calfeed__row")).toHaveCount(6);
      await expect(page.locator(".calfeed__more")).toHaveCount(0);
      await expect(page).toHaveURL(/\/dashboard/);
      // раскрытая лента разбита по месяцам: события заведены в трёх
      const months = await page.evaluate(() =>
        [...document.querySelectorAll(".calfeed__month")].map((node) =>
          (node.textContent ?? "").trim(),
        ),
      );
      expect(months.length, "события сгруппированы по месяцам").toBeGreaterThan(
        1,
      );
      expect(new Set(months).size, "заголовки месяцев не повторяются").toBe(
        months.length,
      );

      // в месяце те же события — точками под числами
      await page.getByRole("button", { name: "Месяц", exact: true }).click();
      const dots = await page.evaluate(() =>
        [...document.querySelectorAll(".calcell__dots")].reduce(
          (sum, node) => sum + node.childElementCount,
          0,
        ),
      );
      expect(dots, "дни с событиями помечены точками").toBeGreaterThan(0);
      await page.context().close();
    } finally {
      for (const id of created)
        await director.request.delete(`/api/tasks/${id}/`, {
          headers: { "X-CSRFToken": csrf },
        });
      await director.context().close();
    }
  });

  test("переключателя режимов нет ни на планшете, ни на ноутбуке", async ({
    browser,
  }) => {
    for (const viewport of [{ width: 1024, height: 900 }, LAPTOP]) {
      const page = await as(browser, "student", viewport);
      await page.goto("/dashboard");
      await settle(page);
      await expect(page.locator(".calmode")).toHaveCount(0);
      await expect(page.locator(".calfeed")).toHaveCount(0);
      // и сетка месяца на месте — ровно как после фазы 50
      await expect(page.locator(".home__calgrid")).toBeVisible();
      await page.context().close();
    }
  });

  test("шторка «Ещё»: открывается, закрывается по фону и свайпом вниз", async ({
    browser,
  }) => {
    const page = await as(browser, "student", PHONE);
    await page.goto("/dashboard");
    await settle(page);

    const sheet = page.locator(".moresheet");
    await page.getByRole("button", { name: "Ещё" }).click();
    await expect(sheet).toBeVisible();
    // внутри — остальные разделы и блок пользователя с колокольчиком
    await expect(sheet.getByRole("link", { name: "Календарь" })).toBeVisible();
    await expect(sheet.locator(".moresheet__user")).toBeVisible();

    // закрытие по фону
    await page.mouse.click(195, 60);
    await expect(sheet).toBeHidden();

    // закрытие свайпом вниз
    await page.getByRole("button", { name: "Ещё" }).click();
    await expect(sheet).toBeVisible();
    const box = (await sheet.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + 12);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + 140, { steps: 8 });
    await page.mouse.up();
    await expect(sheet).toBeHidden();

    // раздел из шторки открывается и закрывает её
    await page.getByRole("button", { name: "Ещё" }).click();
    await sheet.getByRole("link", { name: "Календарь" }).click();
    await expect(page).toHaveURL(/\/calendar/);
    await expect(sheet).toBeHidden();

    await page.context().close();
  });

  test("ученик вносит балл с телефона: список листом, кнопка на месте, директор видит карточку", async ({
    browser,
  }) => {
    const student = await as(browser, "student", PHONE);
    await student.goto("/my-data");
    await settle(student);

    await student.getByRole("button", { name: "Внести баллы" }).click();
    const form = student.locator(".propose__form").first();
    await expect(form).toBeVisible();

    // поля в один столбец, во всю ширину и не ниже 44px
    const fields = await student.evaluate(() => {
      const form = document.querySelector(".propose__form") as HTMLElement;
      const controls = [
        ...form.querySelectorAll("input, .selfield, textarea"),
      ] as HTMLElement[];
      const width = form.getBoundingClientRect().width;
      return controls.map((node) => ({
        height: node.getBoundingClientRect().height,
        wide: node.getBoundingClientRect().width >= width - 2,
      }));
    });
    expect(fields.length).toBeGreaterThan(0);
    for (const field of fields) {
      expect(field.height).toBeGreaterThanOrEqual(44);
      expect(field.wide).toBe(true);
    }

    // список открывается листом снизу, а не нативным окном в углу
    const picker = form.locator(".selfield").first();
    if (await picker.count()) {
      await picker.click();
      await expect(student.locator(".selsheet")).toBeVisible();
      await student.locator(".selsheet__item").first().click();
      await expect(student.locator(".selsheet")).toBeHidden();
    }

    // кнопка отправки видна без прокрутки до конца формы
    const send = student.getByRole("button", { name: "Отправить на проверку" });
    const sendBox = (await send.boundingBox())!;
    expect(sendBox.y + sendBox.height).toBeLessThanOrEqual(844);

    const input = form.locator("input").first();
    await input.fill("7.5");
    await send.click();
    // ушло предложение: строка помечена «ждёт проверки»
    await expect(student.getByText("ждёт проверки").first()).toBeVisible({
      timeout: 15_000,
    });
    await student.context().close();

    // директор домена видит его карточкой: было и стало друг над другом,
    // кнопки во всю ширину
    const director = await as(browser, "director_exam", PHONE);
    await director.goto("/dashboard");
    await settle(director);
    const row = director.locator(".pqueue__row").first();
    await expect(row).toBeVisible({ timeout: 15_000 });
    const queue = await director.evaluate(() => {
      const row = document.querySelector(".pqueue__row") as HTMLElement;
      const values = [
        ...row.querySelectorAll(".pqueue__values [data-slot='badge']"),
      ] as HTMLElement[];
      const buttons = [
        ...row.querySelectorAll(".pqueue__actions [data-slot='button']"),
      ] as HTMLElement[];
      const width = row.getBoundingClientRect().width;
      return {
        stacked:
          values.length === 2 &&
          values[1].getBoundingClientRect().top >=
            values[0].getBoundingClientRect().bottom - 1,
        buttons: buttons.map((b) => b.getBoundingClientRect().width),
        inner: width - 26,
      };
    });
    expect(queue.stacked, "«было» и «стало» стоят друг над другом").toBe(true);
    expect(queue.buttons.length).toBeGreaterThanOrEqual(2);
    for (const width of queue.buttons)
      expect(width).toBeGreaterThan(queue.inner * 0.8);

    // отклонение с причиной — тот же путь, что в жизни, и заодно
    // проверка, что кнопки в карточке работают
    const id = await row.getAttribute("data-suggestion");
    await row.getByRole("button", { name: "Отклонить" }).click();
    await row.getByRole("textbox").fill("Проверка телефонной версии");
    await row.getByRole("button", { name: "Отклонить" }).click();
    await expect(director.locator(".pqueue__row")).toHaveCount(0, {
      timeout: 15_000,
    });

    // и убираем за собой совсем: отклонённое предложение видно ученику
    // в портфолио, а сценарий не должен оставлять следов на экранах.
    // Удаление отвечает 204 без тела, поэтому запрос идёт напрямую
    const csrf =
      (await director.context().cookies()).find((c) => c.name === "csrftoken")
        ?.value ?? "";
    const gone = await director.request.delete(`/api/suggestions/${id}/`, {
      headers: { "X-CSRFToken": csrf },
    });
    expect(gone.ok(), "предложение прогона убрано").toBe(true);
    await director.context().close();
  });

  test("плашка «не подтверждено» не пропадает при сжатии карточки", async ({
    browser,
  }) => {
    const page = await as(browser, "student", PHONE);
    await page.goto("/catalog");
    await settle(page);
    // сколько карточек первой страницы каталог считает непроверенными —
    // столько же оговорок обязано стоять на экране
    const unverified = await page.evaluate(async () => {
      const response = await fetch("/api/catalog/", {
        credentials: "same-origin",
      });
      const data = (await response.json()) as {
        results?: { verification_note?: string | null }[];
      };
      return (data.results ?? []).filter((row) => row.verification_note).length;
    });
    if (unverified > 0) {
      const shown = await page.locator(".unverified:visible").count();
      expect(
        shown,
        "оговорка «не подтверждено» видна на телефоне",
      ).toBeGreaterThan(0);
    }
    await page.context().close();
  });

  test("меню профиля и колокольчик работают из шторки «Ещё»", async ({
    browser,
  }) => {
    const page = await as(browser, "student", PHONE);
    await page.goto("/dashboard");
    await settle(page);
    await page.getByRole("button", { name: "Ещё" }).click();
    const sheet = page.locator(".moresheet");
    await expect(sheet).toBeVisible();
    // меню профиля открывается поверх шторки, пункты нажимаются
    await sheet.locator(".pmenu__user").click();
    await expect(page.getByText("Профиль", { exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    // колокольчик открывает список уведомлений поверх шторки
    await sheet.locator(".notif__button").click();
    await expect(
      page.locator(".notif__list, .notif__empty").first(),
    ).toBeVisible();
    await page.context().close();
  });

  test("внутренних ярлыков ученику не видно и на телефоне", async ({
    browser,
  }) => {
    const page = await as(browser, "student", PHONE);
    const forbidden = [
      "critical",
      "needs_supervision",
      "strong",
      "medium",
      "weak",
      "portfolio_status",
    ];
    for (const screen of PHONE_SHOTS.student) {
      await page.goto(screen);
      await settle(page);
      const text = (
        (await page.locator("body").textContent()) ?? ""
      ).toLowerCase();
      for (const word of forbidden)
        expect(text.includes(word), `${screen}: наружу вышло «${word}»`).toBe(
          false,
        );
      // Процент нигде не назван шансом (инвариант №11). Оговорка
      // «это соответствие требованиям, а не шанс поступления» — как раз
      // соблюдение правила, поэтому её из текста вычитаем
      expect(
        text.replace(/не\s+шанс/g, "").includes("шанс"),
        `${screen}: процент назван шансом`,
      ).toBe(false);
    }
    await page.context().close();
  });

  test("снимки экранов всех ролей в обеих темах", async ({ browser }) => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const dir = path.join(__dirname, "..", "shots", "phone");
    fs.mkdirSync(dir, { recursive: true });
    for (const [role, screens] of Object.entries(PHONE_SHOTS)) {
      const page = await as(browser, role, PHONE);
      await page.goto("/dashboard");
      const csrf =
        (await page.context().cookies()).find((c) => c.name === "csrftoken")
          ?.value ?? "";
      const theme = async (value: string) =>
        page.request.patch("/api/auth/me/preferences/", {
          data: { theme: value },
          headers: { "X-CSRFToken": csrf },
        });

      // светлая тема: все экраны роли
      for (const screen of screens) {
        await page.goto(screen);
        await settle(page);
        await page.screenshot({
          path: path.join(dir, `${role}${screen.replace(/\//g, "_")}.png`),
          fullPage: true,
        });
      }

      // тёмная: главная каждой роли — там весь каркас телефона разом
      await theme("dark");
      await page.goto("/dashboard");
      await settle(page);
      await page.screenshot({
        path: path.join(dir, `${role}_dashboard-dark.png`),
        fullPage: true,
      });
      // тема — настройка учётной записи: возвращаем, чтобы следующие
      // проверки не шли в тёмной
      await theme("system").catch(() => undefined);
      await page.context().close();
    }
  });
});
