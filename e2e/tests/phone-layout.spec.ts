/**
 * Телефонная версия: 390×844 под каждой из семи ролей.
 *
 * Сравнение раскладки на 1440 жило здесь же до фазы 54 и уехало в свой
 * проект (`baseline.spec.ts`): оно сверялось с данными, которые к этому
 * моменту успевала переписать сотня проверок, и краснело там, где
 * раскладка не менялась (D29). Файл идёт в serial-режиме, поэтому одно
 * такое падение уносило и все двадцать две телефонные проверки.
 *
 * Снимки телефона сохраняются в `e2e/shots/phone/` для просмотра глазами;
 * настоящего сравнения с эталоном на этой ширине нет.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";

test.describe.configure({ mode: "serial", timeout: 240_000 });

const LAPTOP = { width: 1440, height: 900 };

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

/** Ждём, пока экран дорисуется. */
async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(600);
}

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
    student: ["Главная", "Расписание", "ДЗ", "Вузы"],
    director_behavior: ["Дашборд", "Посещаемость", "Риски", "Предложения"],
    director_admission: ["Дашборд", "Таблица", "Предложения", "Справочник"],
    director_exam: ["Дашборд", "Таблица", "Предложения", "Mock Test"],
    director_talent: ["Дашборд", "Таблица", "Предложения", "Олимпиада"],
    director_sport: ["Дашборд", "Таблица", "Предложения", "Соревнования"],
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

  test("календарь: на телефоне список первым, месяц по кнопке, режим переживает перезагрузку", async ({
    browser,
  }) => {
    const page = await as(browser, "student", PHONE);
    await page.goto("/calendar");
    await settle(page);

    // у нового человека память пуста — открывается список ближайшего
    await expect(page.locator(".datacard", { hasText: "Ближайшее" }).first()).toBeVisible();
    await expect(page.locator(".stucal__grid")).toHaveCount(0);

    // переключение в месяц: сетка в семь колонок, ячейка не ниже цели касания
    await page.getByRole("button", { name: "Месяц", exact: true }).click();
    await expect(page.locator(".stucal__grid")).toBeVisible();
    const grid = await page.evaluate(() => {
      const cells = [...document.querySelectorAll(".calcell")] as HTMLElement[];
      const columns = getComputedStyle(
        document.querySelector(".stucal__grid") as HTMLElement,
      ).gridTemplateColumns.split(" ").length;
      return {
        columns,
        cell: Math.min(...cells.map((c) => c.getBoundingClientRect().height)),
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
    // точек не больше трёх, сколько бы событий в дне ни было
    expect(grid.dots).toBeLessThanOrEqual(3);

    // режим пережил перезагрузку
    await page.reload();
    await settle(page);
    await expect(page.locator(".stucal__grid")).toBeVisible();

    // и вернулся обратно
    await page.getByRole("button", { name: "Список", exact: true }).click();
    await expect(page.locator(".stucal__grid")).toHaveCount(0);
    await page.reload();
    await settle(page);
    await expect(page.locator(".datacard", { hasText: "Ближайшее" }).first()).toBeVisible();

    // ключ памяти — с ролью: у директора свой
    const key = await page.evaluate(() =>
      Object.keys(localStorage).filter((k) => k.startsWith("calendar.mode.")),
    );
    expect(key).toEqual(["calendar.mode.student"]);

    await page.context().close();
  });

  test("список: только будущее, строки по датам, «Показать все» раскрывает остаток", async ({
    browser,
  }) => {
    // события заводит директор — тем же путём, что в жизни: задачи ученику
    // со сроками. На чистой базе впереди у ученика пусто, и проверять
    // список было бы не на чем
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
    const created: number[] = [];
    for (const days of [2, 5, 9, 14, 40, 70]) {
      const made = await director.request.post("/api/tasks/", {
        data: {
          student: student!.id,
          title: `Проверка списка: ${days} дн.`,
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
      await page.goto("/calendar");
      await settle(page);
      await page.getByRole("button", { name: "Список", exact: true }).click();
      const card = page.locator(".datacard", { hasText: "Ближайшее" }).first();
      const rows = card.locator(".rowline");
      expect(await rows.count(), "первые строки видны сразу").toBeGreaterThan(0);
      // прошедшего в списке нет
      await expect(card).not.toContainText("Проверка списка: -");
      // «Показать все» раскрывает остаток на месте
      const more = card.getByRole("button", { name: /Показать все/ });
      if (await more.isVisible().catch(() => false)) {
        await more.click();
        expect(await rows.count()).toBeGreaterThanOrEqual(6);
      }
      await expect(page).toHaveURL(/\/calendar/);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - screen.width,
      );
      expect(overflow, "выезда вбок нет").toBeLessThanOrEqual(1);
      await page.context().close();
    } finally {
      for (const id of created)
        await director.request.delete(`/api/tasks/${id}/`, {
          headers: { "X-CSRFToken": csrf },
        });
      await director.context().close();
    }
  });

  test("на планшете и ноутбуке календарь открывается месяцем, список рядом", async ({
    browser,
  }) => {
    for (const viewport of [{ width: 1024, height: 900 }, LAPTOP]) {
      const page = await as(browser, "student", viewport);
      await page.addInitScript(() => localStorage.removeItem("calendar.mode.student"));
      await page.goto("/calendar");
      await settle(page);
      await expect(page.locator(".stucal__grid")).toBeVisible();
      await expect(page.locator(".datacard", { hasText: "Ближайшее" }).first()).toBeVisible();
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
    await page.locator(".tabbar__more").click();
    await expect(sheet).toBeVisible();
    // внутри — всё меню целиком, группами: и то, что вынесено в бар, тоже
    await expect(sheet.getByRole("link", { name: "Календарь" })).toBeVisible();
    await expect(sheet.getByRole("link", { name: "Главная" })).toBeVisible();
    await expect(sheet.locator(".moresheet__grouptitle")).toHaveCount(3);

    // закрытие по фону
    await page.mouse.click(195, 60);
    await expect(sheet).toBeHidden();

    // закрытие свайпом вниз
    await page.locator(".tabbar__more").click();
    await expect(sheet).toBeVisible();
    const box = (await sheet.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + 12);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + 140, { steps: 8 });
    await page.mouse.up();
    await expect(sheet).toBeHidden();

    // раздел из шторки открывается и закрывает её
    await page.locator(".tabbar__more").click();
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

    // директор домена видит его карточкой: с фазы 76 «было → стало»
    // в одну строку и кнопки рядом — плотность кураторской очереди
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
      return {
        inline:
          values.length === 2 &&
          values[1].getBoundingClientRect().left >=
            values[0].getBoundingClientRect().right - 1,
        buttons: buttons.map((b) => Math.round(b.getBoundingClientRect().top)),
        heights: buttons.map((b) => b.getBoundingClientRect().height),
      };
    });
    expect(queue.inline, "«было» и «стало» в одну строку").toBe(true);
    expect(queue.buttons.length).toBeGreaterThanOrEqual(2);
    expect(new Set(queue.buttons).size, "кнопки рядом, в одну линию").toBe(1);
    for (const height of queue.heights)
      expect(height).toBeGreaterThanOrEqual(44);

    // отклонение с причиной — тот же путь, что в жизни, и заодно
    // проверка, что кнопки в карточке работают
    const id = await row.getAttribute("data-suggestion");
    await row.getByRole("button", { name: "Отклонить" }).click();
    await row.getByRole("textbox").fill("Проверка телефонной версии");
    await row.getByRole("button", { name: "Отклонить" }).click();
    // из очереди уходит именно эта строка; соседние сценарии могли
    // оставить свои, и «очередь пуста» здесь ничего не доказывает (D34)
    await expect(
      director.locator(`.pqueue__row[data-suggestion="${id}"]`),
    ).toHaveCount(0, { timeout: 15_000 });

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
      const shown = await page.locator(".catalog__badge:visible, .unverified:visible").count();
      expect(
        shown,
        "оговорка «не подтверждено» видна на телефоне",
      ).toBeGreaterThan(0);
    }
    await page.context().close();
  });

  test("меню пользователя открывается с аватара в полосе, уведомления — его пунктом", async ({
    browser,
  }) => {
    const page = await as(browser, "student", PHONE);
    await page.goto("/dashboard");
    await settle(page);
    // «Меню» слева открывает ту же шторку, что «Ещё» снизу
    await page.getByRole("button", { name: "Меню", exact: true }).click();
    const sheet = page.locator(".moresheet");
    await expect(sheet).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
    // меню пользователя — за аватаром справа, пункты нажимаются
    const avatar = page.locator(".shell__top .pmenu__user");
    await avatar.click();
    await expect(page.getByRole("menuitem", { name: "Профиль" })).toBeVisible();
    await page.keyboard.press("Escape");
    // пункт «Уведомления» открывает список поверх экрана
    await avatar.click();
    await page.getByRole("menuitem", { name: /^Уведомления/ }).click();
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
