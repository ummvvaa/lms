/**
 * Страница не заканчивается пустотой.
 *
 * Главная болезнь прежних экранов: содержимое кончалось на четырёхстах
 * пикселях, а дальше до низа окна шёл голый фон. Правило 3 нового языка:
 * содержимое короче двух третей окна получает вторую колонку — ближайшие
 * даты, как устроено, связанное, история — или ширину по себе.
 *
 * Страж ходит по всем адресам всех ролей (`helpers/routes.ts`) на пустой
 * школе — там пустоты больше всего — в окнах 1440×900 и 390×844 и меряет
 * нижний край последнего листа содержимого относительно документа
 * (`measure()` в `helpers/walk.ts`). Пустота больше трети высоты окна —
 * находка.
 *
 * Долг перечислен в `KNOWN_SHORT` с причиной и только сокращается: адрес,
 * который дотянулся до двух третей, из списка вычёркивается. Проход без
 * нажатий — только вкладка, которую называет сам адрес. Идёт отдельным
 * проектом в конце прогона: начинается с обнуления базы.
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

/** Адрес, который кончается пустотой: роль, адрес из `routes.ts`, почему. */
interface KnownShort {
  role: string;
  path: string;
  why: string;
  /** Высота зависит от журнала за сутки, который сброс базы не трогает:
   *  строку не вычёркивают, когда экран случайно дотянулся. */
  volatile?: true;
}

/**
 * Долг: адреса, где содержимое ещё не дотягивается до двух третей окна.
 * Только сокращается. Строки для вставки печатает сам страж.
 */
const KNOWN_SHORT: KnownShort[] = [
  {
    role: "student",
    path: "/calendar",
    why: "1440: содержимое кончается на 573 из 900 | 390: содержимое кончается на 303 из 844",
  },
  {
    role: "student",
    path: "/my-data?tab=documents",
    why: "1440: содержимое кончается на 588 из 900",
  },
  {
    role: "student",
    path: "/catalog",
    why: "1440: содержимое кончается на 412 из 900 | 390: содержимое кончается на 496 из 844",
  },
  {
    role: "student",
    path: "/favorites",
    why: "1440: содержимое кончается на 310 из 900 | 390: содержимое кончается на 368 из 844",
  },
  {
    role: "student",
    path: "/universities",
    why: "1440: содержимое кончается на 324 из 900 | 390: содержимое кончается на 471 из 844",
  },
  {
    role: "student",
    path: "/plan",
    why: "1440: содержимое кончается на 494 из 900",
  },
  {
    role: "student",
    path: "/essays",
    why: "1440: содержимое кончается на 290 из 900",
  },
  {
    role: "student",
    path: "/prep",
    why: "1440: содержимое кончается на 369 из 900 | 390: содержимое кончается на 535 из 844",
  },
  {
    role: "student",
    path: "/roadmap",
    why: "1440: содержимое кончается на 345 из 900 | 390: содержимое кончается на 408 из 844",
  },
  {
    role: "student",
    path: "/quiz",
    why: "1440: содержимое кончается на 497 из 900",
  },
  {
    role: "curator",
    path: "/dashboard",
    why: "1440: содержимое кончается на 567 из 900",
  },
  {
    role: "curator",
    path: "/queue",
    why: "1440: содержимое кончается на 291 из 900 | 390: содержимое кончается на 406 из 844",
  },
  {
    role: "curator",
    path: "/students",
    why: "1440: содержимое кончается на 393 из 900",
  },
  {
    role: "curator",
    path: "/documents",
    why: "1440: содержимое кончается на 401 из 900",
  },
  {
    role: "curator",
    path: "/tasks",
    why: "1440: содержимое кончается на 239 из 900 | 390: содержимое кончается на 347 из 844",
  },
  {
    role: "curator",
    path: "/attendance",
    why: "1440: содержимое кончается на 393 из 900",
  },
  {
    role: "curator",
    path: "/mock-imports",
    why: "1440: содержимое кончается на 342 из 900 | 390: содержимое кончается на 390 из 844",
  },
  {
    role: "curator",
    path: "/students/{id}?tab=exams",
    why: "1440: содержимое кончается на 586 из 900",
  },
  {
    role: "curator",
    path: "/students/{id}?tab=unis",
    why: "1440: содержимое кончается на 327 из 900 | 390: содержимое кончается на 496 из 844",
  },
  {
    role: "curator",
    path: "/students/{id}?tab=documents",
    why: "1440: содержимое кончается на 567 из 900",
  },
  {
    role: "curator",
    path: "/students/{id}?tab=notes",
    why: "1440: содержимое кончается на 430 из 900",
  },
  {
    role: "curator",
    path: "/students/{id}?tab=tasks",
    why: "1440: содержимое кончается на 230 из 900 | 390: содержимое кончается на 348 из 844",
  },
  {
    role: "director_admission",
    path: "/dashboard",
    why: "1440: содержимое кончается на 599 из 900",
  },
  {
    role: "director_admission",
    path: "/suggestions",
    why: "1440: содержимое кончается на 310 из 900 | 390: содержимое кончается на 351 из 844",
  },
  {
    role: "director_admission",
    path: "/table",
    why: "1440: содержимое кончается на 362 из 900",
  },
  {
    role: "director_admission",
    path: "/deadlines",
    why: "1440: содержимое кончается на 327 из 900 | 390: содержимое кончается на 385 из 844",
  },
  {
    role: "director_admission",
    path: "/directory",
    why: "1440: содержимое кончается на 497 из 900",
  },
  {
    role: "director_admission",
    path: "/scholarship-directory",
    why: "1440: содержимое кончается на 428 из 900 | 390: содержимое кончается на 537 из 844",
  },
  {
    role: "director_admission",
    path: "/task-templates",
    why: "1440: содержимое кончается на 428 из 900",
  },
  {
    role: "director_admission",
    path: "/resources",
    why: "1440: содержимое кончается на 483 из 900",
  },
  {
    role: "director_admission",
    path: "/assistant",
    why: "1440: содержимое кончается на 492 из 900",
  },
  {
    role: "director_admission",
    path: "/students/{id}#rows",
    why: "1440: содержимое кончается на 553 из 900",
  },
  {
    role: "director_admission",
    path: "/students/{id}#history",
    why: "1440: содержимое кончается на 306 из 900 | 390: содержимое кончается на 358 из 844",
  },
  {
    role: "director_exam",
    path: "/dashboard",
    why: "1440: содержимое кончается на 517 из 900",
  },
  {
    role: "director_exam",
    path: "/suggestions",
    why: "1440: содержимое кончается на 310 из 900 | 390: содержимое кончается на 351 из 844",
  },
  {
    role: "director_exam",
    path: "/table",
    why: "1440: содержимое кончается на 362 из 900",
  },
  {
    role: "director_exam",
    path: "/mocks",
    why: "1440: содержимое кончается на 350 из 900 | 390: содержимое кончается на 439 из 844",
  },
  {
    role: "director_exam",
    path: "/mock-imports",
    why: "1440: содержимое кончается на 342 из 900 | 390: содержимое кончается на 390 из 844",
  },
  {
    role: "director_exam",
    path: "/top30",
    why: "1440: содержимое кончается на 194 из 900 | 390: содержимое кончается на 367 из 844",
  },
  {
    role: "director_exam",
    path: "/task-templates",
    why: "1440: содержимое кончается на 428 из 900",
  },
  {
    role: "director_exam",
    path: "/resources",
    why: "1440: содержимое кончается на 483 из 900",
  },
  {
    role: "director_exam",
    path: "/assistant",
    why: "1440: содержимое кончается на 494 из 900",
  },
  {
    role: "director_exam",
    path: "/students/{id}#rows",
    why: "1440: содержимое кончается на 513 из 900",
  },
  {
    role: "director_exam",
    path: "/students/{id}#history",
    why: "1440: содержимое кончается на 306 из 900 | 390: содержимое кончается на 358 из 844",
  },
  {
    role: "director_behavior",
    path: "/overview",
    why: "1440: содержимое кончается на 585 из 900",
  },
  {
    role: "director_behavior",
    path: "/suggestions",
    why: "1440: содержимое кончается на 310 из 900 | 390: содержимое кончается на 351 из 844",
  },
  {
    role: "director_behavior",
    path: "/table",
    why: "1440: содержимое кончается на 362 из 900 | 390: содержимое кончается на 506 из 844",
  },
  {
    role: "director_behavior",
    path: "/contacts",
    why: "1440: содержимое кончается на 422 из 900 | 390: содержимое кончается на 517 из 844",
  },
  {
    role: "director_behavior",
    path: "/attendance",
    why: "1440: содержимое кончается на 393 из 900 | 390: содержимое кончается на 542 из 844",
  },
  {
    role: "director_behavior",
    path: "/groups",
    why: "1440: содержимое кончается на 174 из 900 | 390: содержимое кончается на 226 из 844",
  },
  {
    role: "director_behavior",
    path: "/risks",
    why: "1440: содержимое кончается на 292 из 900 | 390: содержимое кончается на 448 из 844",
  },
  {
    role: "director_behavior",
    path: "/call-rules",
    why: "1440: содержимое кончается на 444 из 900",
  },
  {
    role: "director_behavior",
    path: "/resources",
    why: "1440: содержимое кончается на 483 из 900",
  },
  {
    role: "director_behavior",
    path: "/assistant",
    why: "1440: содержимое кончается на 478 из 900",
  },
  {
    role: "director_behavior",
    path: "/students/{id}#rows",
    why: "1440: содержимое кончается на 499 из 900",
  },
  {
    role: "director_behavior",
    path: "/students/{id}#history",
    why: "1440: содержимое кончается на 306 из 900 | 390: содержимое кончается на 358 из 844",
  },
  {
    role: "director_talent",
    path: "/dashboard",
    why: "1440: содержимое кончается на 568 из 900",
  },
  {
    role: "director_talent",
    path: "/suggestions",
    why: "1440: содержимое кончается на 310 из 900 | 390: содержимое кончается на 351 из 844",
  },
  {
    role: "director_talent",
    path: "/table",
    why: "1440: содержимое кончается на 362 из 900 | 390: содержимое кончается на 454 из 844",
  },
  {
    role: "director_talent",
    path: "/olympiad-group",
    why: "1440: содержимое кончается на 357 из 900 | 390: содержимое кончается на 545 из 844",
  },
  {
    role: "director_talent",
    path: "/tracks",
    why: "1440: содержимое кончается на 594 из 900",
  },
  {
    role: "director_talent",
    path: "/subjects",
    why: "1440: содержимое кончается на 538 из 900",
  },
  {
    role: "director_talent",
    path: "/materials",
    why: "1440: содержимое кончается на 364 из 900 | 390: содержимое кончается на 403 из 844",
  },
  {
    role: "director_talent",
    path: "/resources",
    why: "1440: содержимое кончается на 483 из 900",
  },
  {
    role: "director_talent",
    path: "/digest",
    why: "1440: содержимое кончается на 287 из 900 | 390: содержимое кончается на 338 из 844; растёт с записями журнала за сутки",
    volatile: true,
  },
  {
    role: "director_talent",
    path: "/assistant",
    why: "1440: содержимое кончается на 476 из 900",
  },
  {
    role: "director_talent",
    path: "/students/{id}#rows",
    why: "1440: содержимое кончается на 513 из 900",
  },
  {
    role: "director_talent",
    path: "/students/{id}#history",
    why: "1440: содержимое кончается на 306 из 900 | 390: содержимое кончается на 358 из 844",
  },
  {
    role: "director_sport",
    path: "/suggestions",
    why: "1440: содержимое кончается на 310 из 900 | 390: содержимое кончается на 351 из 844",
  },
  {
    role: "director_sport",
    path: "/table",
    why: "1440: содержимое кончается на 362 из 900 | 390: содержимое кончается на 480 из 844",
  },
  {
    role: "director_sport",
    path: "/competitions",
    why: "1440: содержимое кончается на 402 из 900 | 390: содержимое кончается на 523 из 844",
  },
  {
    role: "director_sport",
    path: "/sport-types",
    why: "1440: содержимое кончается на 538 из 900",
  },
  {
    role: "director_sport",
    path: "/resources",
    why: "1440: содержимое кончается на 483 из 900",
  },
  {
    role: "director_sport",
    path: "/digest",
    why: "1440: содержимое кончается на 287 из 900 | 390: содержимое кончается на 338 из 844; растёт с записями журнала за сутки",
    volatile: true,
  },
  {
    role: "director_sport",
    path: "/assistant",
    why: "1440: содержимое кончается на 460 из 900",
  },
  {
    role: "director_sport",
    path: "/students/{id}#rows",
    why: "1440: содержимое кончается на 499 из 900",
  },
  {
    role: "director_sport",
    path: "/students/{id}#history",
    why: "1440: содержимое кончается на 306 из 900 | 390: содержимое кончается на 358 из 844",
  },
  {
    role: "admin",
    path: "/table",
    why: "1440: содержимое кончается на 266 из 900 | 390: содержимое кончается на 429 из 844",
  },
  {
    role: "admin",
    path: "/suggestions",
    why: "1440: содержимое кончается на 310 из 900 | 390: содержимое кончается на 351 из 844",
  },
  {
    role: "admin",
    path: "/spend",
    why: "1440: содержимое кончается на 399 из 900",
  },
  {
    role: "admin",
    path: "/students/{id}#rows",
    why: "1440: содержимое кончается на 555 из 900",
  },
  {
    role: "admin",
    path: "/students/{id}#history",
    why: "1440: содержимое кончается на 420 из 900 | 390: содержимое кончается на 528 из 844",
  },
];

interface Finding {
  role: string;
  path: string;
  width: number;
  bottom: number;
  height: number;
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

        const { contentBottom } = await measure(
          page,
          viewport.width,
          EMPTY_PHRASES,
        );
        // пустота больше трети окна: содержимое кончилось выше двух третей
        if (viewport.height - contentBottom > viewport.height / 3)
          findings.push({
            role,
            path: route,
            width: viewport.width,
            bottom: contentBottom,
            height: viewport.height,
          });
      }
      await page.context().close();
    }
  });
}

test("долг высоты только сокращается", () => {
  const listed = new Set(KNOWN_SHORT.map(keyOf));
  const seen = new Set(findings.map(keyOf));

  const fresh = new Map<string, string[]>();
  for (const row of findings) {
    if (listed.has(keyOf(row))) continue;
    const bag = fresh.get(keyOf(row)) ?? [];
    bag.push(
      `${row.width}: содержимое кончается на ${row.bottom} из ${row.height}`,
    );
    fresh.set(keyOf(row), bag);
  }
  const lines = [...fresh.entries()].map(([key, why]) => {
    const [role, path] = key.split(" ");
    return `  { role: "${role}", path: "${path}", why: ${JSON.stringify(why.join(" | "))} },`;
  });
  expect(
    lines.length,
    `экраны, которые кончаются пустотой, вне списка долга (${lines.length}):\n${lines.join("\n")}`,
  ).toBe(0);

  const paid = KNOWN_SHORT.filter(
    (row) => !row.volatile && !seen.has(keyOf(row)),
  );
  expect(
    paid.map(keyOf),
    "экран дотянулся до двух третей — вычеркните из KNOWN_SHORT",
  ).toEqual([]);
});
