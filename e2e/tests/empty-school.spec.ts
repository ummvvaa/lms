/**
 * Пустая школа не выглядит поломкой.
 *
 * Первое, что школа увидит первого сентября, — экраны без единой записи.
 * Страж ходит по всем адресам всех ролей (`helpers/routes.ts`) на 1440
 * и 390 с одной ученицей в базе и краснеет, если на экране:
 *
 * • прочерк «—» в позиции значения — число показателя, значение строки,
 *   ячейка таблицы (правило 1: значение, слово «нет» серым или кнопка
 *   у того, кто может внести, — иначе строки нет);
 * • два развёрнутых блока подряд, сообщающих только «ничего нет»
 *   (правило 2: пустой блок сворачивается в строку высотой `--fold-h`);
 * • ряд плиток перенёсся неровно — «три плюс одна» (правило П-5).
 *
 * Долг перечислен в `KNOWN_EMPTY` с причиной и только сокращается: адрес,
 * на котором находок больше нет, из списка вычёркивается — иначе страж
 * краснеет сам. Новая находка вне списка — тоже красный: чинится экран,
 * а не список.
 *
 * Проход без нажатий — только вкладка, которую называет сам адрес
 * (`#rows`, `#history`, `?tab=documents`), — чтобы уложиться в четверть
 * часа. Идёт отдельным проектом в конце прогона: начинается с обнуления
 * базы и потому не может стоять среди остальных проверок.
 */
import { expect, test } from "@playwright/test";
import { ROUTES, clickTab } from "../helpers/routes";
import { routeIds, substitute } from "../helpers/academics";
import {
  EMPTY_PHRASES,
  LAPTOP,
  PHONE,
  findPupil,
  measure,
  openAs,
  seedEmptySchool,
  settle,
} from "../helpers/walk";

// роли идут друг за другом и собирают находки в один список; итог — последним
test.describe.configure({ mode: "serial", timeout: 600_000 });

/** Адрес с известной пустотой: роль, адрес из `routes.ts`, почему. */
interface KnownEmpty {
  role: string;
  path: string;
  why: string;
}

/**
 * Долг: адреса, где пустота ещё видна. Только сокращается. Строки для
 * вставки печатает сам страж, когда находит новое.
 */
// долг пуст с 28.09.2026: прочерков в позиции значения не осталось
const KNOWN_EMPTY: KnownEmpty[] = [];

/** Выше этого блок стоит во весь рост, а не свёрнут в строку. */
const FOLDED = 120;

interface Finding {
  role: string;
  path: string;
  width: number;
  what: string[];
}

const findings: Finding[] = [];

const keyOf = (row: { role: string; path: string }) =>
  `${row.role} ${row.path}`;

test("пустая школа: одна ученица и ни одной записи", async ({ browser }) => {
  await seedEmptySchool(browser);
});

for (const [role, routes] of Object.entries(ROUTES)) {
  test(`пустота: ${role}`, async ({ browser }) => {
    for (const viewport of [LAPTOP, PHONE]) {
      const page = await openAs(browser, role, viewport);
      const ids = await routeIds(page, role, routes, () => findPupil(page, role));
      for (const route of routes) {
        const url = substitute(route, ids);
        // у пустой школы уроков и журналов нет: адрес с плейсхолдером пропускается
        if (url === null) continue;
        await page.goto(url.split("#")[0]).catch(() => undefined);
        await settle(page);
        // вкладка, которую называет адрес, открывается одним нажатием
        const tab = clickTab(route);
        if (tab) {
          await page
            .getByRole("tab", { name: tab })
            .first()
            .click({ timeout: 5000 })
            .catch(() => undefined);
          await settle(page);
        }

        const metrics = await measure(page, viewport.width, EMPTY_PHRASES);
        const what: string[] = [];
        if (metrics.dashes.length > 0)
          what.push(`прочерк: ${metrics.dashes.join(", ")}`);
        // подряд идущие развёрнутые блоки, сообщающие только «ничего нет»
        let run = 0;
        let worst = 0;
        const chain: string[] = [];
        for (const block of metrics.blocks) {
          if (block.empty && block.height > FOLDED) {
            run += 1;
            chain.push(block.title.slice(0, 40));
            worst = Math.max(worst, run);
          } else run = 0;
        }
        if (worst >= 2) what.push(`пустые блоки подряд: ${chain.join(", ")}`);
        if (metrics.brokenRows.length > 0)
          what.push(`ряд плиток: ${metrics.brokenRows.join("; ")}`);

        if (what.length > 0)
          findings.push({ role, path: route, width: viewport.width, what });
      }
      await page.context().close();
    }
  });
}

test("долг пустоты только сокращается", () => {
  const listed = new Set(KNOWN_EMPTY.map(keyOf));
  const seen = new Set(findings.map(keyOf));

  // новая пустота вне списка: строки готовы к вставке в KNOWN_EMPTY,
  // но чинить надо экран, а не список
  const fresh = new Map<string, string[]>();
  for (const row of findings) {
    if (listed.has(keyOf(row))) continue;
    const bag = fresh.get(keyOf(row)) ?? [];
    bag.push(`${row.width}: ${row.what.join("; ")}`);
    fresh.set(keyOf(row), bag);
  }
  const lines = [...fresh.entries()].map(([key, why]) => {
    const [role, path] = key.split(" ");
    return `  { role: "${role}", path: "${path}", why: ${JSON.stringify(why.join(" | "))} },`;
  });
  expect(
    lines.length,
    `пустота вне списка долга (${lines.length}):\n${lines.join("\n")}`,
  ).toBe(0);

  // закрытое вычёркивается: список только укорачивается
  const paid = KNOWN_EMPTY.filter((row) => !seen.has(keyOf(row)));
  expect(
    paid.map(keyOf),
    "пустоты больше нет — вычеркните из KNOWN_EMPTY",
  ).toEqual([]);
});
