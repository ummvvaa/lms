/**
 * Пустая школа не выглядит поломкой (фаза 81).
 *
 * Первое, что школа увидит первого сентября, — экраны без единой записи.
 * Обход показал, что там было: во вкладке «Экзамены» шесть блоков подряд
 * сообщали «ничего нет», на «Обзоре» плитки стояли три плюс одна, а «цель
 * не поставлена» было написано четырежды на двух экранах.
 *
 * Страж ходит по экранам, где пустота копилась, и требует: ни на одном
 * нет двух развёрнутых блоков подряд, сообщающих только «ничего нет».
 * Свёрнутая строка (правило П-2) нарушением не считается — она и есть цель.
 *
 * Идёт последним проектом: начинается с обнуления базы, как посев эталонов,
 * и потому не может стоять среди остальных проверок. Полный обход всех ста
 * семи адресов — отдельный инструмент (`screen-walk.spec.ts`), в прогон он
 * не входит: тридцать минут на каждую проверку никто не станет ждать.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { resetAll } from "../helpers/manage";
import { probeEmail } from "../helpers/roles";
import { apiPost } from "../helpers/session";
import { EMPTY_PHRASES, LAPTOP, PHONE, openAs, settle } from "../helpers/walk";

test.describe.configure({ mode: "serial", timeout: 600_000 });

/** Экраны, на которых пустота копилась гуще всего. */
const SCREENS: { role: string; path: string }[] = [
  { role: "student", path: "/dashboard" },
  { role: "student", path: "/my-data" },
  { role: "student", path: "/plan" },
  { role: "student", path: "/prep" },
  { role: "curator", path: "/dashboard" },
  { role: "curator", path: "/students/{id}" },
  { role: "curator", path: "/students/{id}?tab=exams" },
  { role: "curator", path: "/students/{id}?tab=unis" },
  { role: "curator", path: "/students/{id}?tab=tasks" },
  { role: "director_exam", path: "/dashboard" },
  { role: "director_admission", path: "/dashboard" },
  { role: "director_behavior", path: "/dashboard" },
];

/** Выше этого блок стоит во весь рост, а не свёрнут в строку. */
const FOLDED = 120;

let pupil = 0;

test("пустая школа: один ученик и ни одной записи", async ({ browser }) => {
  resetAll();
  const context = await browser.newContext({
    storageState: statePath("admin"),
  });
  const page = await context.newPage();
  await page.goto("/dashboard");
  const group = await apiPost<{ id: number }>(page, "/api/groups/", {
    code: "11A",
    grade: 11,
  });
  const made = await apiPost<{ id: number }>(page, "/api/students/", {
    last_name: "Первый",
    first_name: "Ученик",
    email: probeEmail("student"),
    group: group.id,
    graduation_year: 2027,
  });
  pupil = made.id;
  const users = (await (
    await page.request.get(`/api/users/?search=${probeEmail("curator")}`)
  ).json()) as {
    results: { id: number; email: string }[];
  };
  const curator = users.results.find(
    (row) => row.email === probeEmail("curator"),
  )!;
  await apiPost(page, "/api/curator-assignments/", {
    group: group.id,
    curator: curator.id,
    since: "2026-09-01",
  });
  await context.close();
});

/** Развёрнутые блоки, которые сообщают только «здесь ничего нет». */
async function emptyBlocks(page: Page, folded: number, phrases: string[]) {
  return page.evaluate(
    ({ folded, phrases }) =>
      [...document.querySelectorAll(".datacard, .card, .pqueue")]
        .filter((el) => !el.parentElement?.closest(".datacard, .card, .pqueue"))
        .map((el) => {
          const body = ((el as HTMLElement).innerText ?? "").trim();
          const lines = body
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean);
          const low = body.toLowerCase();
          const phrase = phrases.find((p) => low.includes(p)) ?? "";
          const values = lines
            .slice(1)
            .filter(
              (line) => !phrases.some((p) => line.toLowerCase().includes(p)),
            );
          const dashes = values.filter((line) => /^[—–-]$/.test(line)).length;
          const numbers = values.filter((line) => /\d/.test(line)).length;
          const empty = phrase
            ? numbers === 0
            : values.length > 0 && dashes >= values.length;
          return {
            title: (lines[0] ?? "").slice(0, 60),
            empty,
            tall: Math.round(el.getBoundingClientRect().height) > folded,
          };
        }),
    { folded, phrases },
  );
}

for (const width of [LAPTOP, PHONE]) {
  for (const screen of SCREENS) {
    test(`${width.width}: ${screen.role} ${screen.path} не начинается с пустоты`, async ({
      browser,
    }) => {
      const page = await openAs(browser, screen.role, width);
      await page.goto(screen.path.replace("{id}", String(pupil)));
      await settle(page);

      const blocks = await emptyBlocks(page, FOLDED, EMPTY_PHRASES);
      let run = 0;
      let worst = 0;
      const chain: string[] = [];
      for (const block of blocks) {
        if (block.empty && block.tall) {
          run += 1;
          chain.push(block.title);
          worst = Math.max(worst, run);
        } else run = 0;
      }
      expect(
        worst,
        `подряд идущие блоки, сообщающие только «ничего нет»: ${chain.join(", ")}. ` +
          "Пустой блок сворачивается в строку (правило П-2)",
      ).toBeLessThan(2);

      // ряд плиток добит или перестроен: «три плюс одна» — нет (правило П-5)
      const rows = await page.evaluate(() =>
        [...document.querySelectorAll(".statrow")].flatMap((row) => {
          const tops = new Map<number, number>();
          for (const tile of row.children) {
            const top = Math.round(tile.getBoundingClientRect().top);
            tops.set(top, (tops.get(top) ?? 0) + 1);
          }
          return [...tops.values()];
        }),
      );
      expect(
        rows.filter((n) => n === 3).length === 0 || rows.length === 1,
        `ряды плиток: ${rows}`,
      ).toBeTruthy();

      await page.context().close();
    });
  }
}
