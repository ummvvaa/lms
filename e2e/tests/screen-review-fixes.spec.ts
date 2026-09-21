/**
 * Именованные исправления обхода (фаза 81).
 *
 * Каждый сценарий — про место, которое владелец назвал прямо или которое
 * обход нашёл как поломку:
 *
 * • проценты портфолио: 67 с сервера — «67 %», а не «6700 %»;
 * • вкладка «Экзамены» у нового ученика: свёрнутые строки вместо стены прочерков;
 * • «цель не поставлена» — одно место на экране;
 * • плитки «Обзора»: по две, а не три плюс одна;
 * • окно «Удалить навсегда» в архиве больше не падает;
 * • фильтр олимпиадной группы не задваивает коды.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";

test.describe.configure({ timeout: 180_000 });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  await page.addInitScript(() =>
    window.localStorage.setItem("first-run-seen", "1"),
  );
  return page;
}

async function pupilOf(page: Page): Promise<number> {
  const body = (await (
    await page.request.get("/api/curator/students/")
  ).json()) as {
    results: { id: number; full_name: string }[];
  };
  expect(body.results.length, "у куратора есть ученики").toBeGreaterThan(0);
  return body.results[0].id;
}

test("процент портфолио не умножается второй раз", async ({ browser }) => {
  const curator = await as(browser, "curator");
  const id = await pupilOf(curator);
  const card = (await (
    await curator.request.get(`/api/curator/students/${id}/`)
  ).json()) as {
    portfolio: {
      percent: number;
      sections: { code: string; title: string; value: number }[];
    };
  };

  await curator.goto(`/students/${id}?tab=portfolio`);
  const block = curator.locator(".datacard", { hasText: "Портфолио" }).first();
  await expect(block).toBeVisible();
  for (const section of card.portfolio.sections.slice(0, 3)) {
    // на экране ровно то число, что пришло с сервера: ни доли, ни сотен процентов
    await expect(block).toContainText(`${Math.round(section.value)}%`);
  }
  const shown = await block.locator(".num").allInnerTexts();
  for (const value of shown) {
    const number = Number(value.replace(/[^\d]/g, ""));
    if (value.includes("%"))
      expect(number, `процент вне 0…100: ${value}`).toBeLessThanOrEqual(100);
  }
  await curator.context().close();
});

test("вкладка «Экзамены» у ученика без баллов — строки, а не стена прочерков", async ({
  browser,
}) => {
  const curator = await as(browser, "curator");
  const rows = (await (
    await curator.request.get("/api/curator/students/")
  ).json()) as {
    results: {
      id: number;
      ielts_current: number | null;
      sat_current: number | null;
    }[];
  };
  const blank = rows.results.find(
    (row) => row.ielts_current === null && row.sat_current === null,
  );
  test.skip(!blank, "в посеве нет ученика без баллов");

  await curator.goto(`/students/${blank!.id}?tab=exams`);
  // заголовок точный: «пробника IELTS ещё не было» — другой блок, тоже со словом IELTS
  const folded = curator.locator(".datacard--folded");
  for (const exam of ["IELTS", "SAT"]) {
    const card = folded.filter({
      has: curator.locator(".datacard__title", {
        hasText: new RegExp(`^${exam}$`),
      }),
    });
    await expect(card).toHaveCount(1);
    await expect(card).toContainText("балла ещё нет");
  }

  // «цель не поставлена» — одно место на экране, и рядом с ним кнопка
  const goals = curator.locator(".datacard", {
    hasText: "Цели и даты экзаменов",
  });
  await expect(goals).toContainText("ведёт: Кымбат");
  await expect(
    goals.getByRole("button", { name: "Поставить цель" }),
  ).toBeVisible();
  await expect(
    curator.getByText("не поставлена", { exact: false }),
  ).toHaveCount(0);
  await expect(curator.getByText("Целей нет", { exact: true })).toHaveCount(0);
  await curator.context().close();
});

test("плитки «Обзора» встают по две, а не три плюс одна", async ({
  browser,
}) => {
  const curator = await as(browser, "curator");
  const id = await pupilOf(curator);
  await curator.goto(`/students/${id}`);
  const row = curator.locator(".statrow").first();
  await expect(row).toBeVisible();

  const rows = await row.evaluate((el) => {
    const tops = new Map<number, number>();
    for (const tile of el.children) {
      const top = Math.round(tile.getBoundingClientRect().top);
      tops.set(top, (tops.get(top) ?? 0) + 1);
    }
    return [...tops.values()];
  });
  expect(rows, `ряды плиток: ${rows}`).not.toContain(3);
  await curator.context().close();
});

test("архив: окно «Удалить навсегда» открывается, а не падает", async ({
  browser,
}) => {
  const admin = await as(browser, "admin");
  const errors: string[] = [];
  admin.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await admin.goto("/archive");
  const purge = admin.getByRole("button", { name: "Удалить навсегда" }).first();
  test.skip(
    !(await purge.isVisible().catch(() => false)),
    "в архиве нет записей",
  );

  await purge.click();
  // окно спрашивает подтверждение словом или почтой и показывает последствия
  await expect(
    admin.getByText("чтобы подтвердить", { exact: false }).first(),
  ).toBeVisible();
  expect(
    errors.filter((line) => line.includes("TypeError")),
    "падений в окне нет",
  ).toEqual([]);
  await admin.getByRole("button", { name: "Отмена" }).first().click();
  await admin.context().close();
});

test("фильтр олимпиадной группы не задваивает коды", async ({ browser }) => {
  const talent = await as(browser, "director_talent");
  const errors: string[] = [];
  talent.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await talent.goto("/olympiad-group");
  await talent.waitForLoadState("networkidle").catch(() => undefined);

  const body = (await (
    await talent.request.get("/api/olympiad-group/")
  ).json()) as { groups: string[] };
  expect(new Set(body.groups).size, "коды групп в фильтре не повторяются").toBe(
    body.groups.length,
  );
  expect(
    errors.filter((line) => line.includes("same key")),
    "React не ругается на ключи",
  ).toEqual([]);
  await talent.context().close();
});

test("ученик: экраны пустой школы объясняют, кто заполняет", async ({
  browser,
}) => {
  const student = await as(browser, "student");
  await student.goto("/my-data");
  // общий компонент: фраза одна и та же по всему интерфейсу
  const notes = student.locator(".emptynote");
  if ((await notes.count()) > 0) await expect(notes.first()).toBeVisible();
  // своих серых абзацев «ничего нет» на экране не осталось
  const own = await student.locator("p.muted").allInnerTexts();
  for (const line of own) {
    expect(
      /^(пока нет|ничего нет|пусто)$/i.test(line.trim()),
      `свой текст пустоты: ${line}`,
    ).toBeFalsy();
  }
  await student.context().close();
});
