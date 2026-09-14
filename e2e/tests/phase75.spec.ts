/**
 * Фаза 75 — телефонная версия: системные правки и семь точечных.
 *
 * Всё на 390×844. Сценарии:
 *
 * 1. Шапка в одну строку: поиск иконкой и раскрывается на всю ширину,
 *    «Ctrl+K» не показывается, «Как начать» лежит в шторке «Ещё».
 * 2. Действия шапки свёрнуты в кнопку «Действия» с меню; окно, которое
 *    открывается из меню, открывается. Модалка «Выдать пароли»: кнопки
 *    своей строкой, подпись отдельным абзацем.
 * 3. Плашки свёрнуты до строки с «подробнее»; «Начало работы» у директора
 *    свёрнута; баннер почты у ученика только на «Главной», «Позже»
 *    запоминается на сервере; подзаголовок «Таблицы» не повторяет плашку.
 * 4. Ленты чипов прокручиваются вбок; вкладки карточки — одна строка.
 * 5. «Пользователи»: строка в две линии, действия в меню, «Удалить» —
 *    в меню и открывает окно.
 * 6. Ни одна страница ни одной роли не шире экрана.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 300_000 });

const PHONE = { width: 390, height: 844 };
const XLSX =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    viewport: PHONE,
    isMobile: true,
    hasTouch: true,
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
  const list = (await (
    await page.request.get("/api/students/?page_size=500")
  ).json()) as { results?: { id: number; email: string }[] };
  const row = (list.results ?? []).find((r) => r.email === email);
  return row?.id ?? (list.results ?? [])[0]?.id ?? 0;
}

/** Ученик куратора — из его же списка: чужая группа отвечает 404. */
async function curatorStudentId(page: Page): Promise<number> {
  const list = (await (
    await page.request.get("/api/curator/students/")
  ).json()) as { results?: { id: number }[] };
  return (list.results ?? [])[0]?.id ?? 0;
}

/* ------------------------------------------------------------------ *
 *  1. Шапка
 * ------------------------------------------------------------------ */

test("шапка в одну строку: поиск иконкой, без Ctrl+K, «Как начать» в «Ещё»", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  const diag = watch(page);
  await page.goto("/dashboard");
  await settle(page);

  const top = page.locator(".shell__top");
  const box = await top.boundingBox();
  expect(box?.height ?? 999, "шапка — одна строка").toBeLessThanOrEqual(56);
  await expect(page.locator(".search__hint")).toBeHidden();
  await expect(page.locator(".shell__actions")).toBeHidden();
  await expect(page.locator(".shell__search")).toBeHidden();

  // поиск раскрывается на всю ширину и берёт курсор
  await page.locator(".shell__searchbtn").click();
  const input = page.locator(".shell__search input");
  await expect(input).toBeVisible();
  await expect(input).toBeFocused();
  const field = await page.locator(".shell__search").boundingBox();
  expect(field?.width ?? 0, "поле во всю ширину").toBeGreaterThan(280);
  const opened = await top.boundingBox();
  expect(opened?.height ?? 999).toBeLessThanOrEqual(56);
  await page.locator(".shell__searchbtn").click();
  await expect(input).toBeHidden();

  // «Как начать» — в шторке «Ещё», а не строкой в шапке
  await page.locator(".tabbar__more").click();
  const guide = page.locator(".moresheet").getByRole("button", {
    name: "Как начать",
  });
  await expect(guide).toBeVisible();
  await guide.click();
  await expect(page.locator(".firstrun")).toBeVisible();

  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

/* ------------------------------------------------------------------ *
 *  2. Действия — в меню
 * ------------------------------------------------------------------ */

test("действия шапки свёрнуты в меню; «Выдать пароли» — кнопки своей строкой", async ({
  browser,
}) => {
  const page = await as(browser, "admin");
  const diag = watch(page);
  await page.goto("/users");
  await settle(page);

  // главное действие остаётся кнопкой, остальные в меню
  await expect(page.getByRole("button", { name: "Завести пользователя" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Выдать пароли" })).toBeHidden();
  const actions = page.locator(".head__actions").getByRole("button", {
    name: "Действия",
  });
  await expect(actions).toBeVisible();
  await actions.click();
  const menu = page.locator(".head__menu");
  for (const label of [
    "Завести учеников списком",
    "Выдать пароли",
    "Массовое приглашение",
  ])
    await expect(menu.getByRole("menuitem", { name: label })).toBeVisible();

  // окно из меню открывается; в нём подпись абзацем, кнопки строкой
  await menu.getByRole("menuitem", { name: "Выдать пароли" }).click();
  const modal = page.getByRole("dialog");
  await expect(modal).toBeVisible();
  await expect(modal.locator(".handout__note")).toContainText(
    "Пароли не рассылаются",
  );
  const buttons = modal.locator(".handout__actions [data-slot='button']");
  await expect(buttons).toHaveCount(2);
  const [a, b] = await Promise.all([
    buttons.nth(0).boundingBox(),
    buttons.nth(1).boundingBox(),
  ]);
  expect(Math.abs((a?.y ?? 0) - (b?.y ?? 1)), "кнопки в одной строке").toBeLessThan(2);
  const row = await modal.locator(".handout__actions").boundingBox();
  expect((a?.width ?? 0) + (b?.width ?? 0), "на всю ширину").toBeGreaterThan(
    (row?.width ?? 999) * 0.9,
  );
  await page.keyboard.press("Escape");
  await expect(modal).toBeHidden();

  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("окно куратора открывается кнопкой шапки; меню ради одной кнопки нет", async ({ browser }) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/students");
  await settle(page);
  await expect(page.getByRole("button", { name: "Задача группе" })).toBeVisible();
  // две кнопки: главная и «Выгрузить» — меню «Действия» ради одной не собирается (фаза 76)
  await expect(page.locator(".head__actions").getByRole("button", { name: "Выгрузить" })).toBeVisible();
  await expect(page.locator(".head__actions").getByRole("button", { name: "Действия" })).toHaveCount(0);
  await page.getByRole("button", { name: "Задача группе" }).click();
  await expect(page.getByRole("dialog")).toContainText("Задача ученику");
  await page.keyboard.press("Escape");

  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

/* ------------------------------------------------------------------ *
 *  3. Плашки
 * ------------------------------------------------------------------ */

test("плашки свёрнуты: письма у администратора, таблица директора, «Начало работы»", async ({
  browser,
}) => {
  const admin = await as(browser, "admin");
  await admin.goto("/users");
  await settle(admin);
  const mail = admin.locator(".users__mail");
  if ((await mail.count()) > 0) {
    await expect(mail).toHaveClass(/notice--folded/);
    await expect(mail.locator(".notice__summary")).toHaveText(
      "Отправка писем не настроена",
    );
    await expect(mail).not.toContainText("EMAIL_HOST");
    await mail.getByRole("button", { name: "подробнее" }).click();
    await expect(mail).toContainText("EMAIL_HOST");
  }
  await admin.context().close();

  const exam = await as(browser, "director_exam");
  await exam.goto("/table");
  await settle(exam);
  const note = exam.locator(".tblnote");
  await expect(note).toHaveClass(/notice--folded/);
  await expect(note.locator(".notice__summary")).toContainText(
    "Значения меняет ученик",
  );
  // подзаголовок больше не повторяет плашку слово в слово
  await expect(exam.locator(".head__sub")).not.toContainText("подтверждаете");
  await note.getByRole("button", { name: "подробнее" }).click();
  await expect(note.locator(".notice__text")).toContainText("в очереди");

  await exam.goto("/dashboard");
  await settle(exam);
  const start = exam.locator(".start");
  if ((await start.count()) > 0) {
    await expect(start.locator(".eyebrow")).toContainText(/ — \d+ из \d+/);
    await expect(start.locator(".start__list")).toHaveCount(0);
    await start.getByRole("button", { name: "Развернуть" }).click();
    await expect(start.locator(".start__list")).toBeVisible();
  }
  await exam.context().close();
});

test("баннер почты у ученика: только на «Главной», «Позже» запоминается на сервере", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  const diag = watch(page);
  const token = await csrf(page);
  // исходное состояние: баннер не закрыт
  await page.request.patch("/api/auth/me/preferences/", {
    data: { link_identity_dismissed: false },
    headers: { "X-CSRFToken": token },
  });
  await page.goto("/calendar");
  await settle(page);
  await expect(page.locator(".banner")).toHaveCount(0);

  await page.goto("/dashboard");
  await settle(page);
  const banner = page.locator(".banner");
  await expect(banner).toBeVisible();
  await expect(banner).toHaveClass(/notice--folded/);
  await banner.getByRole("button", { name: "подробнее" }).click();
  const saved = page.waitForResponse(
    (r) =>
      r.url().includes("/auth/me/preferences/") &&
      r.request().method() === "PATCH",
  );
  await banner.getByRole("button", { name: "Позже" }).click();
  expect((await saved).status()).toBe(200);
  await expect(banner).toHaveCount(0);

  // «Позже» пережило перезагрузку и видно с сервера — значит, и на другом устройстве
  await page.reload();
  await settle(page);
  await expect(page.locator(".banner")).toHaveCount(0);
  const me = (await (await page.request.get("/api/auth/me/")).json()) as {
    link_identity_dismissed: boolean;
  };
  expect(me.link_identity_dismissed).toBe(true);

  // возвращаем как было: остальные сценарии ждут баннер
  await page.request.patch("/api/auth/me/preferences/", {
    data: { link_identity_dismissed: false },
    headers: { "X-CSRFToken": token },
  });
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

/* ------------------------------------------------------------------ *
 *  4. Ленты и вкладки
 * ------------------------------------------------------------------ */

test("лента чипов прокручивается вбок, вкладки карточки — одна строка", async ({
  browser,
}) => {
  const admin = await as(browser, "admin");
  await admin.goto("/users");
  await settle(admin);
  const chips = await admin.locator(".users__chips").evaluate((el) => ({
    overflow: getComputedStyle(el).overflowX,
    wrap: getComputedStyle(el).flexWrap,
    scroll: el.scrollWidth,
    client: el.clientWidth,
    tops: [...el.children].map((c) => c.getBoundingClientRect().top),
  }));
  expect(chips.overflow).toBe("auto");
  expect(chips.wrap).toBe("nowrap");
  expect(chips.scroll, "лента длиннее экрана").toBeGreaterThan(chips.client);
  expect(new Set(chips.tops.map((t) => Math.round(t))).size, "в одну строку").toBe(1);
  await admin.context().close();

  const curator = await as(browser, "curator");
  const id = await curatorStudentId(curator);
  await curator.goto(`/students/${id}?tab=portfolio`);
  await settle(curator);
  const tabs = await curator.locator(".tabs__list").evaluate((el) => ({
    height: el.getBoundingClientRect().height,
    overflow: getComputedStyle(el).overflowX,
    tops: [...el.querySelectorAll(".tabs__tab")].map((c) =>
      Math.round(c.getBoundingClientRect().top),
    ),
    selected: (() => {
      const on = el.querySelector(
        ".tabs__tab[data-selected], .tabs__tab[aria-selected='true']",
      );
      const box = on?.getBoundingClientRect();
      const own = el.getBoundingClientRect();
      return box ? box.left >= own.left - 1 && box.right <= own.right + 1 : false;
    })(),
  }));
  expect(tabs.height, "одна строка вкладок").toBeLessThanOrEqual(52);
  expect(tabs.overflow).toBe("auto");
  expect(new Set(tabs.tops).size).toBe(1);
  expect(tabs.selected, "активная вкладка видна").toBe(true);
  await curator.context().close();
});

/* ------------------------------------------------------------------ *
 *  5. «Пользователи»
 * ------------------------------------------------------------------ */

test("«Пользователи»: строка в две линии, действия в меню, «Удалить» открывает окно", async ({
  browser,
}) => {
  const page = await as(browser, "admin");
  const diag = watch(page);
  await page.goto("/users");
  await settle(page);

  const rows = page.locator(".users__table tbody tr");
  expect(await rows.count()).toBeGreaterThan(0);
  const first = rows.first();
  const box = await first.boundingBox();
  expect(box?.height ?? 999, "не выше двух рядов текста").toBeLessThanOrEqual(72);
  // страница не шире экрана и на этом экране
  const wide = await page.evaluate(
    (limit) => document.documentElement.scrollWidth - limit,
    PHONE.width,
  );
  expect(wide).toBeLessThanOrEqual(0);
  await expect(first.getByRole("button", { name: "Выдать пароль" })).toHaveCount(0);

  await first.locator(".rowmenu__button").click();
  const menu = page.locator(".rowmenu__panel");
  for (const label of ["Выдать пароль", "Изменить", "Удалить"])
    await expect(menu.getByRole("menuitem", { name: label })).toBeVisible();
  await expect(menu.getByRole("menuitemcheckbox", { name: "Видит всю школу" })).toBeVisible();
  // «Удалить»: пункт называется так, окно открывается и не обрезано
  const menuBox = await menu.boundingBox();
  expect((menuBox?.x ?? -1) >= 0 && (menuBox?.x ?? 0) + (menuBox?.width ?? 0) <= 390).toBe(true);
  await menu.getByRole("menuitem", { name: "Удалить" }).click();
  const dialog = page.getByRole("alertdialog").or(page.getByRole("dialog")).first();
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: /Удалить/ })).toBeVisible();
  await page.keyboard.press("Escape");

  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

/* ------------------------------------------------------------------ *
 *  6. Ни одна страница не шире экрана
 * ------------------------------------------------------------------ */

/** Адреса всех ролей — те же, что обошла съёмка фазы 74. `{id}` — карточка ученика. */
const ROUTES: Record<string, string[]> = {
  student: [
    "/dashboard",
    "/journey",
    "/calendar",
    "/my-data",
    "/my-data?tab=documents",
    "/selection",
    "/catalog",
    "/favorites",
    "/universities",
    "/plan",
    "/scholarships",
    "/career",
    "/essays",
    "/prep",
    "/roadmap",
    "/quiz",
    "/achievements",
    "/profile",
  ],
  curator: [
    "/dashboard",
    "/queue",
    "/students",
    "/documents",
    "/tasks",
    "/journal",
    "/attendance",
    "/mock-imports",
    "/students/{id}",
    "/students/{id}?tab=exams",
    "/students/{id}?tab=unis",
    "/students/{id}?tab=portfolio",
    "/students/{id}?tab=documents",
    "/students/{id}?tab=notes",
    "/students/{id}?tab=tasks",
  ],
  director_admission: [
    "/dashboard",
    "/suggestions",
    "/table",
    "/deadlines",
    "/directory",
    "/scholarship-directory",
    "/essay-content",
    "/task-templates",
    "/resources",
    "/import",
    "/digest",
    "/assistant",
    "/students/{id}",
    "/students/{id}#history",
  ],
  director_exam: [
    "/dashboard",
    "/suggestions",
    "/table",
    "/mocks",
    "/mock-imports",
    "/exam-kinds",
    "/top30",
    "/task-templates",
    "/resources",
    "/import",
    "/digest",
    "/assistant",
    "/students/{id}",
    "/students/{id}#history",
  ],
  director_behavior: [
    "/dashboard",
    "/overview",
    "/suggestions",
    "/table",
    "/contacts",
    "/attendance",
    "/groups",
    "/risks",
    "/call-rules",
    "/career-questions",
    "/badges",
    "/home-cues",
    "/resources",
    "/import",
    "/digest",
    "/assistant",
    "/students/{id}",
    "/students/{id}#history",
  ],
  director_talent: [
    "/dashboard",
    "/suggestions",
    "/table",
    "/olympiad-group",
    "/tracks",
    "/subjects",
    "/materials",
    "/resources",
    "/import",
    "/digest",
    "/assistant",
    "/students/{id}",
    "/students/{id}#history",
  ],
  director_sport: [
    "/dashboard",
    "/suggestions",
    "/table",
    "/competitions",
    "/sport-types",
    "/resources",
    "/import",
    "/digest",
    "/assistant",
    "/students/{id}",
    "/students/{id}#history",
  ],
  admin: [
    "/dashboard",
    "/users",
    "/table",
    "/suggestions",
    "/import",
    "/archive",
    "/mail-templates",
    "/spend",
  ],
};

/** Самый широкий элемент страницы — чтобы красный говорил, что чинить. */
async function overflowOf(page: Page): Promise<string | null> {
  // предел — число сценария, а не `innerWidth` или `screen.width`: в мобильной
  // эмуляции окно растягивается вместе с содержимым, и сравнение с ним
  // сходится всегда — так сканер фазы 75 молчал при страницах в 426 px
  return page.evaluate((limit) => {
    const doc = document.documentElement.scrollWidth;
    if (doc <= limit) return null;
    let worst: { el: Element; right: number } | null = null;
    for (const el of document.querySelectorAll("body *")) {
      const box = el.getBoundingClientRect();
      if (box.width === 0) continue;
      if (box.right > limit + 1 && (!worst || box.right > worst.right))
        worst = { el, right: box.right };
    }
    const tag = worst
      ? `${worst.el.tagName.toLowerCase()}.${[...worst.el.classList].join(".")}`
      : "?";
    return `ширина ${doc} при экране ${limit}: ${tag}`;
  }, PHONE.width);
}

test("ни одна страница ни одной роли не шире экрана", async ({ browser }) => {
  const offenders: string[] = [];
  for (const [role, routes] of Object.entries(ROUTES)) {
    const page = await as(browser, role);
    const id = !routes.some((r) => r.includes("{id}"))
      ? 0
      : role === "curator"
        ? await curatorStudentId(page)
        : await studentId(page, probeEmail("pupil01"));
    for (const route of routes) {
      const url = route.replace("{id}", String(id));
      await page.goto(url.replace("#history", ""));
      await settle(page);
      if (url.endsWith("#history")) {
        await page.getByRole("tab", { name: "История изменений" }).click();
        await settle(page);
      }
      const bad = await overflowOf(page);
      if (bad) offenders.push(`${role} ${url} — ${bad}`);
    }
    await page.context().close();
  }

  // мастер импорта: третий шаг виден только после файла
  const admin = await as(browser, "admin");
  await admin.goto("/import");
  await settle(admin);
  const responded = admin.waitForResponse(
    (r) => r.url().includes("/admission-imports/preview/") && r.status() === 200,
  );
  await admin.locator('input[type="file"]').first().setInputFiles({
    name: "admission-table.xlsx",
    mimeType: XLSX,
    buffer: readFileSync(path.join(__dirname, "..", "fixtures", "admission-table.xlsx")),
  });
  await responded;
  for (const step of ["шаг 1 после файла", "шаг 2", "шаг 3"]) {
    const bad = await overflowOf(admin);
    if (bad) offenders.push(`admin /import ${step} — ${bad}`);
    if (step !== "шаг 3") {
      await admin.getByRole("button", { name: "Дальше" }).click();
      await settle(admin);
    }
  }
  await admin.context().close();

  expect(offenders, "страницы, которые едут вбок").toEqual([]);
});

/* ------------------------------------------------------------------ *
 *  7. Герб помощника над баром, запас снизу
 * ------------------------------------------------------------------ */

test("кнопка помощника стоит над нижним баром и меньше, чем на ноутбуке", async ({
  browser,
}) => {
  const page = await as(browser, "director_exam");
  await page.goto("/table");
  await settle(page);
  const measured = await page.evaluate(() => {
    const fab = document.querySelector(".aw__fab")!.getBoundingClientRect();
    const bar = document.querySelector(".tabbar")!.getBoundingClientRect();
    const screen = document.querySelector(".shell__screen") as HTMLElement;
    return {
      fabBottom: fab.bottom,
      fabSize: fab.width,
      barTop: bar.top,
      pad: parseFloat(getComputedStyle(screen).paddingBottom),
      barHeight: bar.height,
    };
  });
  expect(measured.fabBottom, "герб над баром").toBeLessThanOrEqual(measured.barTop);
  expect(measured.fabSize).toBeLessThanOrEqual(48);
  expect(measured.pad, "запас снизу больше бара и герба").toBeGreaterThanOrEqual(
    measured.barHeight + measured.fabSize,
  );
  await page.context().close();
});
