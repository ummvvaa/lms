/**
 * Страж высоты: короткий экран — компактный, а не пустой.
 *
 * До 27.09.2026 правило требовало дотягивать содержимое до двух третей
 * окна — и экраны обрастали карточками-пояснениями. Решение владельца
 * это перевернуло: пустота внизу лучше каши, пояснений на экранах нет.
 * Теперь страж ловит два других изъяна:
 *
 * 1. Экран без содержимого — под заголовком ничего нет (ниже `MIN_CONTENT`
 *    от верха окна): экран сломан или пуст без объяснения.
 * 2. Растянутая пустая карточка — блок выше `MAX_EMPTY_BLOCK`, который
 *    сообщает только «ничего нет»: пустая карточка должна сворачиваться
 *    в строку, а не занимать место живых.
 *
 * Ходит по всем адресам всех ролей (`helpers/routes.ts`) на пустой школе
 * в окнах 1440×900 и 390×844, без нажатий — только вкладка, которую
 * называет сам адрес. Идёт отдельным проектом в конце прогона: начинается
 * с обнуления базы.
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

/** Ниже этой высоты от верха окна содержимого нет — только шапка или ничего. */
const MIN_CONTENT = 160;
/** Пустой блок выше этого — растянутая пустая карточка, а не свёрнутая строка. */
const MAX_EMPTY_BLOCK = 200;

interface Finding {
  role: string;
  path: string;
  width: number;
  why: string;
}

const findings: Finding[] = [];

const keyOf = (row: { role: string; path: string }) =>
  `${row.role} ${row.path}`;

test("пустая школа: одна ученица и ни одной записи", async ({ browser }) => {
  await seedEmptySchool(browser);
});

for (const [role, routes] of Object.entries(ROUTES)) {
  test(`высота: ${role}`, async ({ browser }) => {
    for (const viewport of [LAPTOP, PHONE]) {
      const page = await openAs(browser, role, viewport);
      const ids = await routeIds(page, role, routes, () => findPupil(page, role));
      for (const route of routes) {
        const url = substitute(route, ids);
        // у пустой школы уроков и журналов нет: адрес с плейсхолдером пропускается
        if (url === null) continue;
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

        const { contentBottom, blocks } = await measure(
          page,
          viewport.width,
          EMPTY_PHRASES,
        );
        if (contentBottom < MIN_CONTENT)
          findings.push({
            role,
            path: route,
            width: viewport.width,
            why: `содержимое кончается на ${contentBottom}: под заголовком пусто`,
          });
        for (const block of blocks) {
          if (block.empty && block.height > MAX_EMPTY_BLOCK)
            findings.push({
              role,
              path: route,
              width: viewport.width,
              why: `пустая карточка «${block.title}» высотой ${block.height}`,
            });
        }
      }
      await page.context().close();
    }
  });
}

test("экраны без содержимого и растянутых пустых карточек", () => {
  const lines = findings.map(
    (row) => `  ${keyOf(row)} @${row.width}: ${row.why}`,
  );
  expect(
    lines.length,
    `находки стража высоты (${lines.length}):\n${lines.join("\n")}`,
  ).toBe(0);
});
