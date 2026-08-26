/**
 * Фаза 7 — сквозной аудит. Ничего не чинит: обходит экраны всех ролей,
 * нажимает всё, что нажимается, и складывает наблюдения в audit-report.json.
 *
 * Кнопка считается рабочей, если по клику ушёл запрос к API и ответ 2xx.
 * Кнопка без запроса и без видимого следа попадает в отчёт — дальше человек
 * решает, задумано так или это дефект.
 *
 * Каждая пара «роль × экран» — отдельный тест со своей вкладкой: состояние
 * одного экрана не должно мешать проверке следующего.
 */
import { test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { ACCOUNTS } from "../helpers/roles";
import {
  DOMAIN_ONLY,
  STAFF_ONLY,
  STUDENT_ONLY,
} from "../../frontend/src/layout/nav";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";

interface Observation {
  role: string;
  screen: string;
  what: string;
  detail: string;
}

const REPORT_DIR = path.join(__dirname, "..", "audit-findings");

/** Кнопки, которые нельзя жать в обходе: уводят из сессии. */
// язык и тема на «Профиле» переключаются на сервере и переживают сессию:
// нажатая в обходе кнопка «English» переводила бы все следующие проверки
const SKIP_BUTTONS = [
  /выйти/i,
  /^назад$/i,
  /← назад/i,
  /^English$/,
  /^Русский$/,
  /^(Светлая|Тёмная|Как в системе)$/,
  // необратимое и меняющее чужие учётные записи: обход проверяет, что кнопка
  // отвечает, а не что удаление работает — для этого есть свои сценарии
  /^Удалить/i,
  /навсегда/i,
  /^Очистить/i,
  /^Выдать пароль/i,
  /^Отключить доступ/i,
  /^Разослать/i,
];

/**
 * Кнопки, которым «не ответить запросом» — нормально, с объяснением почему.
 * Список именно такой: молчаливое исключение по классу спрятало бы дефект.
 */
const NO_REQUEST_EXPECTED: { match: RegExp; why: string }[] = [
  { match: /^Загрузить файл/, why: "открывает системный диалог выбора файла" },
  {
    match: /^Привязать$/,
    why: "форма с пустым обязательным полем — браузер сам не даёт отправить",
  },
  {
    match: /^\?$/,
    why: "подсказка по наведению: отвечает на курсор, а не на щелчок",
  },
  {
    match: /^Завести (предмет|вид спорта)$/,
    why: "форма уже открыта над списком — кнопка только переводит в неё фокус",
  },
];

const ROUTES = [
  "/dashboard",
  "/users",
  "/catalog",
  "/onboarding",
  "/prep",
  "/table",
  "/assistant",
  "/digest",
  "/import",
  "/roadmap",
  "/universities",
  "/essays",
  "/my-data",
  "/groups",
  "/contacts",
  "/task-templates",
  "/risks",
  "/overview",
  "/deadlines",
  "/top30",
  "/mocks",
  "/tracks",
  "/competitions",
  "/directory",
  "/subjects",
  "/sport-types",
  "/materials",
  "/olympiad-group",
  "/archive",
  "/spend",
  "/suggestions",
  "/profile",
];

/** Каждый тест пишет свой файл: параллельные воркеры не затирают друг друга. */
function dump(role: string, route: string, observations: Observation[]): void {
  if (observations.length === 0) return;
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  const name = `${role}${route.replace(/\//g, "_")}.json`;
  fs.writeFileSync(
    path.join(REPORT_DIR, name),
    JSON.stringify(observations, null, 2),
    "utf8",
  );
}

for (const account of ACCOUNTS) {
  test.describe(`роль ${account.key}`, () => {
    test.use({ storageState: statePath(account.key) });

    for (const route of ROUTES) {
      test(`${account.key} · ${route}`, async ({ page }) => {
        test.setTimeout(90_000);
        const diag = watch(page);
        const isStudent = account.key === "student";
        const observations: Observation[] = [];
        const note = (what: string, detail: string) =>
          observations.push({ role: account.key, screen: route, what, detail });

        await page.goto(route, { timeout: 30_000 });
        await page.waitForLoadState("domcontentloaded").catch(() => {});
        // редирект с чужого экрана происходит после ответа /auth/me: под нагрузкой
        // он приходит позже 900 мс, и «Загрузка…» читалась как пустой чужой экран
        await page
          .waitForLoadState("networkidle", { timeout: 5_000 })
          .catch(() => {});
        await page.waitForTimeout(900);

        const url = page.url();
        const body =
          (await page
            .locator("body")
            .innerText()
            .catch(() => "")) ?? "";

        // экран чужой роли обязан уводить на свой дашборд — это не дефект,
        // а починка I4. Дефект — если уводит куда-то ещё
        const foreignScreen =
          (isStudent ? STAFF_ONLY : STUDENT_ONLY).includes(route) ||
          // управление людьми, архив и расходы — только у роли `admin`
          (["/users", "/archive", "/spend"].includes(route) &&
            account.key !== "admin") ||
          // раздел домена — только у его директора (фаза 26)
          (DOMAIN_ONLY[route] !== undefined &&
            DOMAIN_ONLY[route] !== account.key) ||
          // справочники домена и материалы олимпиадников
          (route === "/subjects" && account.key !== "director_talent") ||
          (route === "/sport-types" && account.key !== "director_sport") ||
          (["/materials", "/olympiad-group"].includes(route) &&
            account.key !== "director_talent") ||
          // сводный вид — у `admin` и у того, кому включён флаг «видит всю школу»
          (route === "/overview" &&
            !["admin", "director_behavior"].includes(account.key));
        if (!url.includes(route)) {
          if (!(foreignScreen && url.includes("/dashboard")))
            note("редирект", `увело на ${url}`);
        } else if (foreignScreen) {
          note("чужой экран открылся", `${route} доступен роли ${account.key}`);
        }
        if (diag.pageErrors.length)
          note("исключение в браузере", diag.pageErrors.join(" | "));
        if (diag.consoleErrors.length)
          note("ошибка в консоли", diag.consoleErrors.slice(0, 3).join(" | "));
        if (diag.failed.length) {
          note(
            "запрос не 2xx",
            diag.failed
              .map(
                (c) =>
                  `${c.method} ${c.status} ${c.url.replace(/^https?:\/\/[^/]+/, "")}`,
              )
              .join(" | "),
          );
        }
        if (body.trim().length < 40) note("пустой экран", body.trim());

        // --- жмём кнопки -------------------------------------------------
        // Ссылки на элементы снимаем заранее: клик по одной кнопке может убрать
        // соседние из DOM, и нумерация «n-я кнопка» после этого врёт.
        const handles = await page
          .locator("main button:not([disabled])")
          .elementHandles();
        // одинаково оформленные кнопки списка жмём не больше трёх раз,
        // иначе обход упирается в 87 строк таблицы и не заканчивается
        const perShape = new Map<string, number>();
        const seenLabel = new Set<string>();

        for (const handle of handles) {
          const label = ((await handle.innerText().catch(() => "")) || "")
            .trim()
            .replace(/\s+/g, " ");
          if (!label || SKIP_BUTTONS.some((re) => re.test(label))) continue;
          if (seenLabel.has(label)) continue;
          const shape =
            (await handle.getAttribute("class").catch(() => "")) ?? "";
          // галочки и переключатели реестра — тоже <button>, но это состояние,
          // а не действие: «отметить все строки» плюс «отключить доступ»
          // однажды отключили в обходе все семь учётных записей
          const role =
            (await handle.getAttribute("role").catch(() => "")) ?? "";
          if (role === "checkbox" || role === "switch") continue;
          const repeats = perShape.get(shape) ?? 0;
          if (repeats >= 3) continue;
          perShape.set(shape, repeats + 1);
          seenLabel.add(label);
          if (!(await handle.isVisible().catch(() => false))) continue;

          const mark = diag.mark();
          const before = page.url();
          const beforeBody =
            (await page
              .locator("body")
              .innerText()
              .catch(() => "")) ?? "";
          const clicked = await handle
            .click({ timeout: 4_000 })
            .then(() => true)
            .catch(() => false);
          if (!clicked) continue;
          await page.waitForTimeout(600);
          const sent = diag.since(mark);
          const navigated = page.url() !== before;

          if (sent.length === 0 && !navigated) {
            const after =
              (await page
                .locator("body")
                .innerText()
                .catch(() => "")) ?? "";
            const shape2 =
              (await handle.getAttribute("class").catch(() => "")) ?? "";
            // активная вкладка реестра помечена `aria-selected`, наши — модификатором
            const selected =
              (await handle.getAttribute("aria-selected").catch(() => null)) ===
              "true";
            const alreadyActive =
              selected || /--active|--selected/.test(shape2);
            const excused = NO_REQUEST_EXPECTED.find((rule) =>
              rule.match.test(label),
            );
            if (after === beforeBody && !alreadyActive && !excused) {
              note(
                "кнопка без эффекта",
                `«${label}» — ни запроса, ни перехода, ни изменения на экране`,
              );
            }
          }
          const bad = sent.filter((c) => c.status >= 400 || c.status === 0);
          if (bad.length) {
            note(
              "кнопка отвечает ошибкой",
              `«${label}» → ${bad.map((c) => `${c.status} ${c.url.replace(/^https?:\/\/[^/]+/, "")}`).join(", ")}`,
            );
          }
          if (diag.pageErrors.length) {
            note(
              "исключение после клика",
              `«${label}»: ${diag.pageErrors.join(" | ")}`,
            );
            diag.pageErrors.length = 0;
          }

          if (navigated) {
            await page.goto(route, { timeout: 20_000 }).catch(() => {});
            await page.waitForTimeout(500);
          }
        }

        dump(account.key, route, observations);
      });
    }
  });
}
