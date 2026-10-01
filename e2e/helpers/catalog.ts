/**
 * Каталог экранов — режим обходчика, который снимает, а не жмёт всё подряд.
 *
 * Владелец рисует новые макеты по одному документу, где виден весь продукт:
 * что где стоит, где пусто, где тесно. Поэтому снимок здесь — главное,
 * а не приложение к манифесту, как у обхода фазы 81:
 *
 * • экран снимается целиком. Каркас на ноутбуке прокручивает содержимое внутри
 *   себя (`.shell__main`), и снимок страницы обрезал бы низ — окно растёт
 *   в высоту, пока внутри не останется прокрутки;
 * • после экрана — открытые формы и окна. Каталог нажимает кнопки экрана,
 *   и всё, что открылось (окно, окно из меню строки, форма на месте), снимается
 *   вторым снимком. Разрушительное действие доходит до окна подтверждения
 *   и закрывается отменой;
 * • пока жмутся кнопки, запросы на запись гасятся в браузере: «Создать»,
 *   «Завести», «Пригласить» открывают свои формы, а в базу не уходит ничего.
 *   Обход фазы 81 такие кнопки обходил стороной — и их формы не видел никто.
 *
 * Сценарий — тот же `screen-walk.spec.ts` с `WALK_MODE=catalog`, сборка
 * PDF по ролям — `build_screen_catalog.py`.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { Page } from "@playwright/test";
import { clickTab } from "./routes";
import { close, fingerprint, listen, settle, within } from "./walk";
import { audit, LANG, type I18nFinding } from "./i18n-audit";

/** Окно съёмки экрана: высокое, чтобы экран вошёл целиком (и растёт дальше). */
export const CATALOG_LAPTOP = { width: 1440, height: 2000 };
export const CATALOG_PHONE = { width: 390, height: 3400 };

/** Окно, в котором открываются формы: обычный экран, каким его видит человек. */
const SCREEN: Record<number, { width: number; height: number }> = {
  1440: { width: 1440, height: 900 },
  390: { width: 390, height: 844 },
};

/**
 * Предел высоты окна в css-пикселях. На ноутбуке Chromium снимает 40 000
 * точек без искажений (проверено), а архив наполненной школы выходит за
 * 24 000. На телефоне страница прокручивается сама, и снимок во всю
 * страницу забирает низ и выше предела окна; при эмуляции телефона окно
 * в 20 000 снимается белым листом. Упёрлись — снимок помечается.
 */
const MAX_HEIGHT: Record<number, number> = { 1440: 40_000, 390: 12_000 };

/** Предел на экран и на одно нажатие со снимком окна и закрытием. */
const SCREEN_BUDGET_MS = 150_000;
const CLICK_BUDGET_MS = 20_000;

/**
 * Кнопки, которые каталог не жмёт: уводят из системы или со страницы,
 * скачивают файл, сохраняют форму — окна за ними нет. Остальное жмётся:
 * запись погашена, и «Отменить импорт» доходит до своего подтверждения.
 */
const SKIP = ["выйти", "скачать", "назад", "← назад", "сохранить"];

const skipped = (name: string) =>
  SKIP.some((word) => name.toLowerCase().startsWith(word));

/** Куда ложатся снимки каталога: состояние школы — своей папкой. */
export const catalogDir = (state: string): string =>
  path.join(__dirname, "..", "shots", "catalog", LANG ? `${state}-${LANG}` : state);

export interface CatalogShot {
  /** экран, окно (в т.ч. из меню строки) или форма, развернувшаяся на месте */
  kind: "экран" | "окно" | "форма";
  file: string;
  /** высота окна браузера в css-пикселях на момент снимка */
  height: number;
  /** заголовок окна или формы */
  title?: string;
  /** кнопка, которой открыто: «⋯ → Удалить» для пункта меню */
  opener?: string;
  /** высота упёрлась в предел — низ может быть не виден */
  capped?: boolean;
}

export interface CatalogScreen {
  role: string;
  /** адрес из `routes.ts`, с `{id}` */
  route: string;
  /** адрес, по которому ходили на самом деле */
  url: string;
  width: number;
  state: string;
  /** почему экран не снялся: пусто — снялся */
  error: string;
  shots: CatalogShot[];
  /** имена кнопок, которые на этом экране что-то открыли */
  openers: string[];
  /** имена всех кнопок, которые каталог рассматривал */
  candidates: string[];
  consoleErrors: string[];
  pageErrors: string[];
  badResponses: string[];
  /** проверка перевода (`CATALOG_LANG`): что на снимке осталось по-русски или сломалось */
  i18n?: I18nFinding[];
}

/** Видимые поля ввода внутри содержимого: по их числу видно, развернулась ли форма. */
async function fieldCount(page: Page): Promise<number> {
  return page
    .evaluate(() => {
      const root = document.querySelector("main") ?? document.body;
      return [
        ...root.querySelectorAll(
          'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]), textarea, select, [role="combobox"]',
        ),
      ].filter((el) => {
        const box = el.getBoundingClientRect();
        return box.width > 0 && box.height > 0;
      }).length;
    })
    .catch(() => 0);
}

/**
 * Сколько содержимого спрятано под прокруткой: на всей странице или в окне.
 * Считаются только прокручиваемые области, которые растут вместе с окном
 * браузера; список с высотой в пикселях не вырастет, и за ним не гонимся.
 */
async function hidden(page: Page, scope: "page" | "dialog"): Promise<number> {
  return page
    .evaluate((scope) => {
      const dialog = document.querySelector(
        '[role="dialog"], [role="alertdialog"]',
      );
      const nodes: Element[] =
        scope === "dialog"
          ? dialog
            ? [dialog, ...dialog.querySelectorAll("*")]
            : []
          : [
              document.scrollingElement ?? document.documentElement,
              ...document.querySelectorAll(".shell__main, main"),
            ];
      let extra = 0;
      for (const el of nodes) {
        const style = getComputedStyle(el);
        const scrolls =
          el === document.scrollingElement ||
          /(auto|scroll)/.test(style.overflowY);
        if (!scrolls) continue;
        extra = Math.max(extra, el.scrollHeight - el.clientHeight);
      }
      return extra;
    }, scope)
    .catch(() => 0);
}

/** Поднять окно браузера, пока прокрутка не исчезнет. Упёрлись в предел — true. */
async function grow(page: Page, scope: "page" | "dialog"): Promise<boolean> {
  const limit = MAX_HEIGHT[page.viewportSize()?.width ?? 1440] ?? 24_000;
  let previous = Number.POSITIVE_INFINITY;
  for (let step = 0; step < 6; step += 1) {
    const extra = await hidden(page, scope);
    // прокрутки не осталось — или она не уменьшается от роста окна
    if (extra <= 1 || extra >= previous) return false;
    previous = extra;
    const size = page.viewportSize()!;
    const next = Math.min(limit, size.height + extra);
    if (next === size.height) return true;
    await page.setViewportSize({ width: size.width, height: next });
    await page.waitForTimeout(350);
  }
  return (await hidden(page, scope)) > 1;
}

/**
 * Кнопки экрана, за которыми может быть окно или форма.
 *
 * Вкладки, чипы фильтров, переключатели, выпадающие списки, сортировка
 * колонок и подсказки «?» меняют содержимое, а не открывают форм — их
 * каталог не жмёт. У строк
 * списка берётся только первая: остальные повторяют её кнопки.
 */
async function candidates(
  page: Page,
): Promise<{ name: string; outside: boolean }[]> {
  return page
    .evaluate(() => {
      const seen = new Set<string>();
      const out: { name: string; outside: boolean }[] = [];
      for (const node of document.querySelectorAll('button, [role="button"]')) {
        const el = node as HTMLElement;
        const box = el.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) continue;
        if (
          (el as HTMLButtonElement).disabled ||
          el.getAttribute("aria-disabled") === "true"
        )
          continue;
        // меню каркаса одно на все экраны — оно не про экран
        if (el.closest("nav, .shell__nav, .mobilenav, .profilemenu")) continue;
        // выпадающий список поля — часть формы, а не окно
        if (
          el.matches(
            '[role="tab"], [role="switch"], [role="combobox"], [aria-haspopup="listbox"], [aria-pressed], .hint, .segrow__item',
          ) ||
          el.closest("th, [role='dialog'], [role='alertdialog']")
        )
          continue;
        const row = el.closest("tbody tr, [role='row'], li");
        if (row?.parentElement) {
          const same = [...row.parentElement.children].filter(
            (child) => child.tagName === row.tagName,
          );
          if (same.indexOf(row) > 0) continue;
        }
        const name = (
          el.getAttribute("aria-label") ||
          el.innerText ||
          el.getAttribute("title") ||
          ""
        )
          .trim()
          .replace(/\s+/g, " ")
          .slice(0, 80);
        if (!name || seen.has(name)) continue;
        seen.add(name);
        out.push({ name, outside: !el.closest("main") });
      }
      return out;
    })
    .catch(() => []);
}

/**
 * Нажать кнопку по тому же имени, по которому её нашли: имя считает
 * браузер тем же правилом, что в `candidates`, — роль и доступное имя
 * Playwright расходились бы на кнопках со значком и подписью.
 */
async function press(page: Page, name: string): Promise<boolean> {
  const found = await page
    .evaluate((name) => {
      document
        .querySelectorAll("[data-catalog-target]")
        .forEach((el) => el.removeAttribute("data-catalog-target"));
      for (const node of document.querySelectorAll('button, [role="button"]')) {
        const el = node as HTMLElement;
        const box = el.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) continue;
        if (el.closest("nav, .shell__nav, .mobilenav, .profilemenu")) continue;
        const own = (
          el.getAttribute("aria-label") ||
          el.innerText ||
          el.getAttribute("title") ||
          ""
        )
          .trim()
          .replace(/\s+/g, " ")
          .slice(0, 80);
        if (own === name) {
          el.setAttribute("data-catalog-target", "1");
          return true;
        }
      }
      return false;
    }, name)
    .catch(() => false);
  if (!found) return false;
  return page
    .locator("[data-catalog-target]")
    .first()
    .click({ timeout: 3000 })
    .then(() => true)
    .catch(() => false);
}

const dialogOpen = (page: Page) =>
  page
    .locator('[role="dialog"], [role="alertdialog"]')
    .first()
    .isVisible()
    .catch(() => false);

const menuOpen = (page: Page) =>
  page
    .getByRole("menu")
    .first()
    .isVisible()
    .catch(() => false);

/** Заголовок открытого окна: подпись, связанный заголовок или первая строка. */
async function dialogTitle(page: Page): Promise<string> {
  return page
    .locator('[role="dialog"], [role="alertdialog"]')
    .first()
    .evaluate((el) => {
      const labelled = el.getAttribute("aria-labelledby");
      const byId = labelled
        ? document.getElementById(labelled)?.textContent
        : "";
      const heading = el.querySelector(
        "h1, h2, h3, [data-slot$='title']",
      )?.textContent;
      const first = (el as HTMLElement).innerText.split("\n")[0];
      return (el.getAttribute("aria-label") || byId || heading || first || "")
        .trim()
        .replace(/\s+/g, " ")
        .slice(0, 90);
    })
    .catch(() => "");
}

/**
 * Дождаться, пока с экрана уйдут заглушки загрузки.
 *
 * `networkidle` после нажатия на вкладку не ждёт ничего: страница уже была
 * в этом состоянии, и вкладка «Строки и записи» у Асем снялась серыми
 * полосами. Заглушка на экране — значит, данные ещё идут.
 */
async function ready(page: Page): Promise<void> {
  await page
    .waitForFunction(
      () =>
        ![
          ...document.querySelectorAll(
            '[data-slot="skeleton"], [role="status"][aria-label^="Загрузка"]',
          ),
        ].some((el) => el.getBoundingClientRect().height > 0),
      undefined,
      { timeout: 10_000 },
    )
    .catch(() => undefined);
  await page.waitForTimeout(200);
}

/** Открыть адрес заново — с вкладкой, если адрес открывает её нажатием. */
async function load(page: Page, url: string, route: string): Promise<void> {
  await page.goto(url.split("#")[0]).catch(() => undefined);
  await settle(page);
  const tab = clickTab(route);
  if (tab) {
    await page
      .getByRole("tab", { name: tab })
      .first()
      .click({ timeout: 5000 })
      .catch(() => undefined);
    await settle(page);
  }
  await ready(page);
}

/**
 * Снять один адрес: экран целиком, потом открытые формы и окна.
 *
 * `only` — на телефоне жмутся кнопки, которые на ноутбуке что-то открыли,
 * и те, которых на ноутбуке не было вовсе (свои у телефона): окна смотрим
 * на ширине телефона, а не повторяем весь перебор вдвое.
 * `shown` — кнопки каркаса вне содержимого (помощник): их окно одно на роль,
 * снимается один раз. `taken` — окна, уже снятые на этой странице: шапка
 * карточки одна на семь вкладок, и «Позвонить родителям» снимается раз,
 * а не семь.
 */
export async function catalogScreen(
  page: Page,
  opts: {
    role: string;
    route: string;
    url: string;
    width: number;
    state: string;
    dir: string;
    counter: number;
    only?: { hits: Set<string>; seen: Set<string> };
    shown: Set<string>;
    taken: Set<string>;
  },
): Promise<CatalogScreen> {
  const { role, route, url, width, state, dir, counter } = opts;
  const base = width <= 640 ? CATALOG_PHONE : CATALOG_LAPTOP;
  const bag = listen(page);
  const screen: CatalogScreen = {
    role,
    route,
    url,
    width,
    state,
    error: "",
    shots: [],
    openers: [],
    candidates: [],
    consoleErrors: [],
    pageErrors: [],
    badResponses: [],
  };
  const slug = `${String(counter).padStart(3, "0")}-${role}-${route
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase()}-${width}`;

  await page.setViewportSize(base);
  await load(page, url, route);

  // адрес увёл на другой экран — это не тот экран, снимать его под этим адресом нельзя
  const expected = new URL(url.split("#")[0], page.url()).pathname;
  const actual = new URL(page.url()).pathname;
  if (actual !== expected) {
    screen.error = `адрес увёл на ${actual}`;
    return finish(screen, bag);
  }

  const capped = await grow(page, "page");
  await ready(page);
  const file = `${slug}.png`;
  const took = await page
    .screenshot({
      path: path.join(dir, file),
      fullPage: true,
      animations: "disabled",
    })
    .then(() => true)
    .catch((error: unknown) => {
      screen.error = `снимок не вышел: ${String(error).slice(0, 120)}`;
      return false;
    });
  if (!took) return finish(screen, bag);
  const found18 = await audit(page, file, "page", width <= 640).catch(() => null);
  if (found18) (screen.i18n ??= []).push(found18);
  screen.shots.push({
    kind: "экран",
    file,
    height: page.viewportSize()!.height,
    capped: capped || undefined,
  });

  // дальше жмутся кнопки: запись гасится, форма открывается, база не меняется
  let blocked = 0;
  await page.route("**/api/**", (request) => {
    if (["GET", "HEAD", "OPTIONS"].includes(request.request().method()))
      return request.fallback();
    blocked += 1;
    return request.abort("blockedbyclient");
  });
  await page.setViewportSize(SCREEN[width]);
  await page.waitForTimeout(250);

  const found = await candidates(page);
  screen.candidates = found.map((c) => c.name);
  const deadline = Date.now() + SCREEN_BUDGET_MS;
  let windows = 0;

  const shoot = async (
    kind: "окно" | "форма",
    opener: string,
  ): Promise<void> => {
    const title = kind === "окно" ? await dialogTitle(page) : "";
    // то же окно той же кнопкой на той же странице (другая вкладка) — уже снято
    const address = route.split(/[?#]/)[0];
    const key = `${address}|${opener}|${title}`;
    if (kind === "окно" && opts.taken.has(key)) return;
    opts.taken.add(key);
    windows += 1;
    const name = `${slug}-${kind === "окно" ? "window" : "form"}-${windows}.png`;
    let cappedShot = false;
    await ready(page);
    if (kind === "окно") {
      cappedShot = await grow(page, "dialog");
      await page.screenshot({
        path: path.join(dir, name),
        animations: "disabled",
      });
      const inDialog = await audit(page, name, "dialog", base.width <= 640).catch(() => null);
      if (inDialog) (screen.i18n ??= []).push(inDialog);
    } else {
      // форма раскрылась на месте: экран снова высокий и целиком
      await page.setViewportSize(base);
      await page.waitForTimeout(250);
      cappedShot = await grow(page, "page");
      await page.screenshot({
        path: path.join(dir, name),
        fullPage: true,
        animations: "disabled",
      });
    }
    screen.shots.push({
      kind,
      file: name,
      height: page.viewportSize()!.height,
      title: title || undefined,
      opener,
      capped: cappedShot || undefined,
    });
    if (!screen.openers.includes(opener.split(" → ")[0]))
      screen.openers.push(opener.split(" → ")[0]);
  };

  const reset = async (): Promise<void> => {
    await page.setViewportSize(SCREEN[width]);
    await load(page, url, route);
  };

  /**
   * Одна кнопка: нажать и посмотреть, что открылось. Окно и форма снимаются,
   * меню строки раскрывается по пунктам, всё прочее возвращается на место.
   */
  const clickOne = async (candidate: {
    name: string;
    outside: boolean;
  }): Promise<void> => {
    const { name } = candidate;
    const before = page.url();
    const print = await fingerprint(page);
    const fields = await fieldCount(page);
    const blockedBefore = blocked;
    if (!(await press(page, name))) return;
    if (candidate.outside) opts.shown.add(name);
    await page.waitForTimeout(600);

    if (await dialogOpen(page)) {
      await shoot("окно", name);
      await close(page);
      await page.setViewportSize(SCREEN[width]);
      if (await dialogOpen(page)) await reset();
      return;
    }

    if (await menuOpen(page)) {
      // меню строки: окна прячутся за его пунктами — «Удалить», «Архивировать»
      const items = (
        await page
          .getByRole("menu")
          .first()
          .getByRole("menuitem")
          .allInnerTexts()
          .catch(() => [] as string[])
      )
        .map((text) => text.trim().replace(/\s+/g, " "))
        .filter(Boolean)
        .slice(0, 8);
      await page.keyboard.press("Escape").catch(() => undefined);
      for (const item of items) {
        if (skipped(item) || Date.now() > deadline) continue;
        if (!(await press(page, name))) break;
        await page.waitForTimeout(350);
        const clicked = await page
          .getByRole("menu")
          .first()
          .getByRole("menuitem", { name: item, exact: true })
          .first()
          .click({ timeout: 3000 })
          .then(() => true)
          .catch(() => false);
        if (!clicked) {
          await page.keyboard.press("Escape").catch(() => undefined);
          continue;
        }
        await page.waitForTimeout(600);
        if (await dialogOpen(page)) {
          await shoot("окно", `${name} → ${item}`);
          await close(page);
          await page.setViewportSize(SCREEN[width]);
        }
        if (page.url() !== before || (await dialogOpen(page))) await reset();
      }
      return;
    }

    if (page.url() !== before) {
      await reset();
      return;
    }

    if ((await fieldCount(page)) > fields) {
      await shoot("форма", name);
      await reset();
      return;
    }

    // содержимое поменялось или запись погашена с тостом — экран на место
    if (blocked > blockedBefore || (await fingerprint(page)) !== print)
      await reset();
  };

  for (const candidate of found) {
    if (Date.now() > deadline) break;
    const { name } = candidate;
    if (skipped(name)) continue;
    if (opts.only && opts.only.seen.has(name) && !opts.only.hits.has(name))
      continue;
    if (candidate.outside && opts.shown.has(name)) continue;

    // сбой одного нажатия не роняет съёмку роли: обход последовательный,
    // и упавший тест снял бы все роли после этой
    await within(
      CLICK_BUDGET_MS,
      () => clickOne(candidate).catch(() => undefined),
      undefined,
    );
    // нажатие зависло или окно не закрылось — возвращаем экран на место
    const away =
      page.url().split("#")[0] !== new URL(url.split("#")[0], page.url()).href;
    if (away || (await dialogOpen(page)) || (await menuOpen(page)))
      await reset().catch(() => undefined);
  }

  await page.unroute("**/api/**");
  return finish(screen, bag);
}

/** Ошибки экрана без следов погашенной записи: это каталог, а не приложение. */
function finish(
  screen: CatalogScreen,
  bag: ReturnType<typeof listen>,
): CatalogScreen {
  const ours = (text: string) =>
    text.includes("ERR_BLOCKED_BY_CLIENT") ||
    text.includes("blockedbyclient") ||
    text.includes("Failed to fetch");
  screen.consoleErrors = [
    ...new Set(bag.consoleErrors.filter((t) => !ours(t))),
  ].slice(0, 6);
  screen.pageErrors = [
    ...new Set(bag.pageErrors.filter((t) => !ours(t))),
  ].slice(0, 6);
  screen.badResponses = [...new Set(bag.badResponses)].slice(0, 10);
  return screen;
}

/**
 * Записать манифест каталога, не потеряв прежнее: роль перегоняется
 * отдельно, и её строки замещают свои по ключу «роль + адрес + ширина».
 */
export function saveCatalog(dir: string, screens: CatalogScreen[]): void {
  mkdirSync(dir, { recursive: true });
  const file = path.join(dir, "catalog.json");
  const key = (row: CatalogScreen) => `${row.role}|${row.route}|${row.width}`;
  const merged = new Map<string, CatalogScreen>();
  if (existsSync(file)) {
    try {
      for (const row of JSON.parse(
        readFileSync(file, "utf8"),
      ) as CatalogScreen[])
        merged.set(key(row), row);
    } catch {
      // манифест побился — начинаем с того, что собрали сейчас
    }
  }
  for (const row of screens) merged.set(key(row), row);
  writeFileSync(file, JSON.stringify([...merged.values()], null, 2), "utf8");
}
