/**
 * Механика обхода экранов — инструмент, а не разовый скрипт (фаза 81).
 *
 * Обход повторяется из фазы в фазу, поэтому механика лежит отдельно от
 * сценария: сценарий говорит, под кем и по каким адресам идти, а здесь —
 * как смотреть на экран и что записывать.
 *
 * С каждого экрана снимается не только картинка:
 *
 * • перечень интерактивных элементов — кнопки, вкладки, чипы, значки строк,
 *   переключатели, ссылки-кнопки: что вообще можно нажать и что отключено;
 * • что случилось от нажатия — окно, меню, переход, запрос или ничего;
 * • ошибки консоли и исключения страницы;
 * • коды ответов: всё, что не 2xx, с адресом;
 * • пустые блоки: карточки, в которых нет ни одного значения, — по ним
 *   считается «сколько блоков подряд сообщают только „ничего нет“»;
 * • ряды плиток: сколько плиток в каждом ряду — «три плюс одна» видно числом;
 * • ширина страницы против ширины экрана.
 *
 * Находки снимаются с манифеста, а снимок нужен, чтобы увидеть, как это
 * выглядит, — не наоборот.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { Browser, Page } from "@playwright/test";
import { statePath } from "./auth-state";

export const LAPTOP = { width: 1440, height: 900 };

/** Сколько элементов нажимаем на одном экране и сколько времени на это даём. */
const MAX_CLICKS = 30;
const SCREEN_BUDGET_MS = 150_000;
/** Предел на одно нажатие со всем, что за ним следует: снимок окна и закрытие. */
const CLICK_BUDGET_MS = 25_000;

/**
 * Выполнить с жёстким пределом времени.
 *
 * Пределы самих действий Playwright не спасают: обход вставал на календаре
 * ученика на десять минут внутри одной операции, и предел «на экран», который
 * проверяется между нажатиями, до него не доходил (фаза 81).
 */
async function within<T>(
  ms: number,
  run: () => Promise<T>,
  fallback: T,
): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  const guard = new Promise<T>((resolve) => {
    timer = setTimeout(() => resolve(fallback), ms);
  });
  try {
    return await Promise.race([run(), guard]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}
export const PHONE = { width: 390, height: 844 };

/** Куда ложатся снимки и манифест: состояние данных — своей папкой. */
export const walkDir = (state: string): string =>
  // `WALK_DIR=walk-after` — второй обход теми же глазами после правок: пары
  // «было / стало» собирает `build_before_after.py` (фаза 81)
  path.join(__dirname, "..", "shots", process.env.WALK_DIR || "walk", state);

export interface WalkElement {
  /** что это: кнопка, вкладка, чип, переключатель, ссылка */
  kind: string;
  name: string;
  disabled: boolean;
}

export interface WalkClick {
  name: string;
  /** что открылось: окно, меню, переход, содержимое, запрос, уже выбрано, ничего */
  opened: string;
  requests: string[];
  errors: string[];
  shot?: string;
  note?: string;
}

export interface WalkBlock {
  title: string;
  /** блок не показывает ни одного значения */
  empty: boolean;
  /** фраза, которой блок сообщает о пустоте */
  phrase: string;
  /** высота блока в пикселях: свёрнутый — одна строка */
  height: number;
}

export interface WalkScreen {
  role: string;
  url: string;
  width: number;
  state: string;
  shot: string;
  overflow: number;
  blocks: WalkBlock[];
  /** сколько подряд идущих блоков сообщают только «ничего нет» */
  emptyRun: number;
  tileRows: number[];
  elements: WalkElement[];
  clicks: WalkClick[];
  consoleErrors: string[];
  pageErrors: string[];
  badResponses: string[];
}

/** Кнопки, которые пишут: их обход не нажимает никогда, только записывает. */
const NEVER = [
  "сохранить",
  "подтвердить",
  "отправить",
  "напомнить",
  "применить",
  "выйти",
  "завести",
  "создать",
  "пригласить",
  "выдать",
  "скачать",
  "начать",
  "закончить",
  "сменить",
  "сбросить",
  "задать",
  "перенести",
  "передать",
  "восстановить",
  "вернуть",
  "очистить",
  "запустить",
  "проверить",
  "сверить",
  "разослать",
  "пересобрать",
  "применить шаблон",
  "отметить",
  "зачесть",
];

/** Действия с последствиями: нажимаем, ждём окно подтверждения и отменяем. */
const DESTRUCTIVE = [
  "удалить",
  "убрать",
  "отклонить",
  "архивировать",
  "снять",
  "отозвать",
  "скрыть",
];

const isNever = (name: string) =>
  NEVER.some((word) => name.toLowerCase().startsWith(word));
export const isDestructive = (name: string) =>
  DESTRUCTIVE.some((word) => name.toLowerCase().startsWith(word));

/** Фразы, которыми интерфейс сообщает, что показывать нечего. */
export const EMPTY_PHRASES = [
  "пока нет",
  "пока пусто",
  "ничего нет",
  "ещё не было",
  "ещё нет",
  "нет данных",
  "не заведено",
  "не заведены",
  "нет записей",
  "пусто",
  "ничего не ждёт",
  "никто ничего",
  "не поставлена",
  "не поставлены",
  "не собраны",
  "не внесено",
  "не внесены",
  "нет ни одного",
  "список пуст",
];

export async function openAs(
  browser: Browser,
  role: string,
  viewport: { width: number; height: number },
): Promise<Page> {
  const phone = viewport.width <= 640;
  const context = await browser.newContext({
    storageState: statePath(role),
    viewport,
    deviceScaleFactor: phone ? 2 : 1,
    isMobile: phone,
    hasTouch: phone,
  });
  const page = await context.newPage();
  await page.addInitScript(() => {
    // подсказка первого входа и панель «Начало работы» перекрывают экран;
    // они смотрятся отдельно и в обходе только мешают
    window.localStorage.setItem("first-run-seen", "1");
    window.localStorage.setItem("getting-started-folded", "1");
  });
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

/** Слушатели на страницу: ошибки и неудачные ответы копятся в массивы. */
export function listen(page: Page) {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const badResponses: string[] = [];
  const requests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error")
      consoleErrors.push(message.text().slice(0, 200));
  });
  page.on("pageerror", (error) => pageErrors.push(String(error).slice(0, 200)));
  page.on("response", (response) => {
    const url = new URL(response.url()).pathname;
    if (!url.startsWith("/api/")) return;
    requests.push(`${response.status()} ${url}`);
    // 401 и 403 у чужих ручек — ожидаемая граница прав, а не находка;
    // записываем всё прочее, что не 2xx
    if (
      response.status() >= 400 &&
      response.status() !== 401 &&
      response.status() !== 403
    )
      badResponses.push(`${response.status()} ${url}`);
  });
  return { consoleErrors, pageErrors, badResponses, requests };
}

export async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(400);
}

/** Что на экране: пустые блоки, ряды плиток, ширина. Считает браузер. */
async function measure(page: Page, limit: number, phrases: string[]) {
  return page.evaluate(
    ({ limit, phrases }) => {
      const text = (el: Element) => (el as HTMLElement).innerText ?? "";
      const blocks = [...document.querySelectorAll(".datacard, .card, .pqueue")]
        // вложенные карточки считаем один раз: берём только внешние
        .filter((el) => !el.parentElement?.closest(".datacard, .card, .pqueue"))
        .map((el) => {
          const body = text(el).trim();
          const low = body.toLowerCase();
          const phrase = phrases.find((p) => low.includes(p)) ?? "";
          const lines = body
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean);
          const title = lines[0] ?? "";
          // блок пуст, если он сообщает о пустоте и не показывает ни одного значения,
          // либо все его строки — прочерки
          const values = lines
            .slice(1)
            .filter(
              (line) => !phrases.some((p) => line.toLowerCase().includes(p)),
            );
          const dashes = values.filter(
            (line) => /^[—–-]$/.test(line) || /\s—\s*$/.test(line),
          ).length;
          const numbers = values.filter((line) => /\d/.test(line)).length;
          const empty = Boolean(phrase)
            ? numbers === 0
            : values.length > 0 && dashes >= values.length;
          return {
            title: title.slice(0, 80),
            empty,
            phrase,
            height: Math.round(el.getBoundingClientRect().height),
          };
        });

      // сколько пустых блоков идут подряд — по порядку на экране
      let emptyRun = 0;
      let run = 0;
      for (const block of blocks) {
        run = block.empty ? run + 1 : 0;
        emptyRun = Math.max(emptyRun, run);
      }

      // ряды плиток: группируем по верхней кромке
      const tileRows: number[] = [];
      for (const row of document.querySelectorAll(".statrow")) {
        const tops = new Map<number, number>();
        for (const tile of row.children) {
          const top = Math.round(tile.getBoundingClientRect().top);
          tops.set(top, (tops.get(top) ?? 0) + 1);
        }
        tileRows.push(...tops.values());
      }

      return {
        overflow: Math.max(0, document.documentElement.scrollWidth - limit),
        blocks,
        emptyRun,
        tileRows,
      };
    },
    { limit, phrases },
  );
}

/** Перечень того, что на экране можно нажать. */
async function collect(page: Page): Promise<WalkElement[]> {
  return page.evaluate(() => {
    const seen = new Set<string>();
    const rows: { kind: string; name: string; disabled: boolean }[] = [];
    const nodes = document.querySelectorAll(
      'button, [role="tab"], [role="switch"], [role="menuitem"], a[href], input[type="checkbox"], select',
    );
    for (const node of nodes) {
      const el = node as HTMLElement;
      const box = el.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) continue;
      // меню каркаса на каждом экране одно и то же — оно не про экран
      if (el.closest("nav, .shell__nav, .mobilenav, .profilemenu")) continue;
      const name = (
        el.getAttribute("aria-label") ||
        el.innerText ||
        el.getAttribute("title") ||
        ""
      )
        .trim()
        .replace(/\s+/g, " ")
        .slice(0, 60);
      if (!name) continue;
      const role = el.getAttribute("role");
      const kind =
        role === "tab"
          ? "вкладка"
          : role === "switch"
            ? "переключатель"
            : el.tagName === "A"
              ? "ссылка"
              : el.tagName === "SELECT"
                ? "список"
                : el.classList.contains("gswitch__chip") ||
                    el.classList.contains("cchip")
                  ? "чип"
                  : "кнопка";
      const key = `${kind}:${name}`;
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push({
        kind,
        name,
        disabled: (el as HTMLButtonElement).disabled === true,
      });
    }
    return rows;
  });
}

/** Отпечаток содержимого экрана: по нему видно, изменилось ли что-нибудь. */
async function fingerprint(page: Page): Promise<string> {
  return page
    .evaluate(() => {
      const main = document.querySelector("main") ?? document.body;
      const text = (main as HTMLElement).innerText ?? "";
      // в отпечаток идёт и состояние: выбранная вкладка, нажатый чип, раскрытый
      // список, сдвиг карусели — иначе переключение читалось бы как «ничего»
      const state = [
        ...main.querySelectorAll(
          "[aria-selected],[aria-pressed],[aria-current],[aria-expanded],[style*=transform]",
        ),
      ]
        .map((el) =>
          [
            el.getAttribute("aria-selected"),
            el.getAttribute("aria-pressed"),
            el.getAttribute("aria-current"),
            el.getAttribute("aria-expanded"),
            (el as HTMLElement).style.transform,
          ].join(""),
        )
        .join("|");
      return `${main.querySelectorAll("*").length}:${text.length}:${state.length}:${state.slice(0, 200)}:${text.slice(0, 120)}`;
    })
    .catch(() => "");
}

/** Закрыть то, что открылось: кнопкой отмены, крестиком или Escape. */
async function close(page: Page): Promise<void> {
  const dialog = page.getByRole("dialog");
  if (
    await dialog
      .first()
      .isVisible()
      .catch(() => false)
  ) {
    for (const name of ["Отмена", "Закрыть", "Не удалять", "Назад"]) {
      const button = dialog.first().getByRole("button", { name, exact: true });
      if (
        await button
          .first()
          .isVisible()
          .catch(() => false)
      ) {
        await button
          .first()
          .click()
          .catch(() => undefined);
        await page.waitForTimeout(250);
        if (
          !(await dialog
            .first()
            .isVisible()
            .catch(() => false))
        )
          return;
      }
    }
  }
  await page.keyboard.press("Escape").catch(() => undefined);
  await page.waitForTimeout(250);
  if (
    await dialog
      .first()
      .isVisible()
      .catch(() => false)
  )
    await page.mouse.click(5, 5).catch(() => undefined);
}

/**
 * Обойти один экран: снять, измерить, перечислить элементы, понажимать.
 *
 * `clickable` — имена, которые разрешено нажимать на этой ширине. На телефоне
 * нажимаются только те, что на ноутбуке открыли окно: смотрим ширину окна,
 * а не повторяем весь обход вдвое.
 */
export async function walkScreen(
  page: Page,
  opts: {
    role: string;
    url: string;
    width: number;
    state: string;
    dir: string;
    counter: number;
    clickable?: (name: string) => boolean;
    onDialog?: (name: string) => void;
  },
): Promise<WalkScreen> {
  const { role, url, width, state, dir, counter } = opts;
  const bag = listen(page);
  await page.goto(url).catch(() => undefined);
  await settle(page);

  const slug = `${String(counter).padStart(3, "0")}-${role}-${url
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase()}-${width}`;
  const shot = `${slug}.png`;
  await page.screenshot({
    path: path.join(dir, shot),
    fullPage: true,
    animations: "disabled",
  });

  const metrics = await measure(page, width, EMPTY_PHRASES);
  const elements = await collect(page);
  const clicks: WalkClick[] = [];
  // предохранители: на наполненной школе у экрана бывают десятки строк, и каждая
  // со своими кнопками. Без предела обход одного календаря уходил в десять минут
  const deadline = Date.now() + SCREEN_BUDGET_MS;

  for (const element of elements) {
    if (clicks.length >= MAX_CLICKS || Date.now() > deadline) {
      clicks.push({
        name: "…",
        opened: "предел",
        requests: [],
        errors: [],
        note: `нажатия прерваны: ${clicks.length} из ${elements.length} за отведённое время`,
      });
      break;
    }
    if (element.disabled) continue;
    if (element.kind === "ссылка" || element.kind === "список") continue;
    if (isNever(element.name)) continue;
    if (opts.clickable && !opts.clickable(element.name)) continue;

    const handled = await within(
      CLICK_BUDGET_MS,
      async () => {
        const before = page.url();
        // отпечаток содержимого: вкладка и фильтр не меняют адрес и не шлют запрос,
        // но экран после них другой — без отпечатка это читалось бы как «ничего»
        const printBefore = await fingerprint(page);
        // уже выбранная вкладка или нажатый чип: «ничего» от повторного нажатия — норма
        const wasActive = await page
          .getByRole(element.kind === "вкладка" ? "tab" : "button", {
            name: element.name,
            exact: true,
          })
          .first()
          .evaluate(
            (el) =>
              el.getAttribute("aria-selected") === "true" ||
              el.getAttribute("aria-pressed") === "true" ||
              el.getAttribute("aria-current") === "true" ||
              el.className.includes("--on"),
          )
          .catch(() => false);
        const errorsBefore = bag.consoleErrors.length;
        const requestsBefore = bag.requests.length;
        const target = page
          .getByRole(element.kind === "вкладка" ? "tab" : "button", {
            name: element.name,
            exact: true,
          })
          .first();
        const clicked = await target
          .click({ timeout: 3000 })
          .then(() => true)
          .catch(() => false);
        // элемент не нажался (перекрыт, исчез, переименовался) — не находка
        if (!clicked) return true;
        await page.waitForTimeout(600);

        const dialog = await page
          .getByRole("dialog")
          .first()
          .isVisible()
          .catch(() => false);
        const menu = await page
          .getByRole("menu")
          .first()
          .isVisible()
          .catch(() => false);
        const moved = page.url() !== before;
        const changed = (await fingerprint(page)) !== printBefore;
        const requests = bag.requests.slice(requestsBefore);
        const opened = dialog
          ? "окно"
          : menu
            ? "меню"
            : moved
              ? "переход"
              : changed
                ? "содержимое"
                : requests.length > 0
                  ? "запрос"
                  : "ничего";

        const click: WalkClick = {
          name: element.name,
          opened: opened === "ничего" && wasActive ? "уже выбрано" : opened,
          requests: requests.slice(0, 6),
          errors: bag.consoleErrors.slice(errorsBefore).slice(0, 3),
        };
        if (dialog) {
          opts.onDialog?.(element.name);
          const file = `${slug}-окно-${clicks.length + 1}.png`;
          await page
            .screenshot({ path: path.join(dir, file), animations: "disabled" })
            .catch(() => undefined);
          click.shot = file;
          // ширина окна против ширины экрана — та же мерка, что у страницы
          click.note = await page
            .getByRole("dialog")
            .first()
            .evaluate((el, limit) => {
              const box = el.getBoundingClientRect();
              return box.width > limit
                ? `окно шире экрана: ${Math.round(box.width)} при ${limit}`
                : "";
            }, width)
            .catch(() => "");
        }
        if (isDestructive(element.name) && !dialog && opened !== "ничего")
          click.note = `разрушительное действие без подтверждения (${opened})`;
        clicks.push(click);

        if (dialog || menu) await close(page);
        if (moved) {
          await page.goto(url).catch(() => undefined);
          await settle(page);
        }
        return true;
      },
      false,
    );
    if (!handled) {
      // нажатие зависло: записываем как находку и возвращаем экран на место
      clicks.push({
        name: element.name,
        opened: "зависло",
        requests: [],
        errors: [],
        note: `экран не ответил за ${CLICK_BUDGET_MS / 1000} с после нажатия`,
      });
      await page.goto(url).catch(() => undefined);
      await settle(page);
    }
  }

  return {
    role,
    url,
    width,
    state,
    shot,
    overflow: metrics.overflow,
    blocks: metrics.blocks,
    emptyRun: metrics.emptyRun,
    tileRows: metrics.tileRows,
    elements,
    clicks,
    consoleErrors: [...new Set(bag.consoleErrors)].slice(0, 6),
    pageErrors: [...new Set(bag.pageErrors)].slice(0, 6),
    badResponses: [...new Set(bag.badResponses)].slice(0, 10),
  };
}

/**
 * Записать манифест, не потеряв то, что собрано прежде.
 *
 * Обход одной роли перегоняется отдельно — роль упала, назначение слетело,
 * экран правился — и не должен стирать остальные: прежние записи остаются,
 * новые замещают их по ключу «роль + адрес + ширина» (фаза 81).
 */
export function saveManifest(dir: string, screens: WalkScreen[]): void {
  mkdirSync(dir, { recursive: true });
  const file = path.join(dir, "manifest.json");
  const key = (row: WalkScreen) => `${row.role}|${row.url}|${row.width}`;
  const merged = new Map<string, WalkScreen>();
  if (existsSync(file)) {
    try {
      for (const row of JSON.parse(readFileSync(file, "utf8")) as WalkScreen[])
        merged.set(key(row), row);
    } catch {
      // манифест побился — начинаем с того, что собрали сейчас
    }
  }
  for (const row of screens) merged.set(key(row), row);
  writeFileSync(file, JSON.stringify([...merged.values()], null, 2), "utf8");
}
