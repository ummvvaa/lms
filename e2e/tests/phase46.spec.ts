/**
 * Фаза 46 — квиз без публичных рейтингов и достижения-бейджи.
 *
 * Ученик играет соло и видит свой результат; в зачёте классов — только
 * классы, ни одной строки ученика. Достижения показывают закрытые бейджи
 * с условием и прогрессом. Директор школы ведёт набор бейджей.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";

test.describe.configure({ mode: "serial", timeout: 240_000 });

const BADGE = "Probe Browser Badge";

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

function csrf(page: Page): Promise<string> {
  return page
    .context()
    .cookies()
    .then((c) => c.find((x) => x.name === "csrftoken")?.value ?? "");
}

test("ученик играет соло и видит свой счёт", async ({ browser }) => {
  const student = await as(browser, "student");
  await student.goto("/quiz");
  await expect(
    student.getByRole("heading", { name: "Квиз", exact: true }),
  ).toBeVisible();

  const state = (await (
    await student.request.get("/api/prep/quiz/")
  ).json()) as {
    bank: { ready: boolean; detail: string };
  };
  if (!state.bank.ready) {
    // пустой банк объясняется словами, а не пустым экраном
    await expect(student.getByText("Заданий пока нет")).toBeVisible();
    return;
  }

  // с фазы 48 соло начинается кнопкой «Начать» в крупной карточке раздела
  const started = student.waitForResponse((response) =>
    response.url().includes("/api/prep/quiz/start/"),
  );
  await student.getByRole("button", { name: "Начать", exact: true }).click();
  expect((await started).status()).toBe(201);

  // отвечаем на все вопросы и заканчиваем
  for (let i = 0; i < 30; i += 1) {
    const options = student.locator(".quiz__option");
    await expect(options.first()).toBeVisible();
    await options.first().click();
    const next = student.getByRole("button", { name: "Дальше" });
    if (await next.isVisible()) {
      await next.click();
      continue;
    }
    await student.getByRole("button", { name: "Закончить" }).click();
    break;
  }

  await expect(student.getByText("Мой счёт")).toBeVisible();
});

test("в зачёте классов нет строк учеников", async ({ browser }) => {
  const student = await as(browser, "student");
  await student.goto("/quiz");
  // с фазы 48 вкладка называется «Командный зачёт»
  await student.getByRole("tab", { name: "Командный зачёт" }).click();
  await expect(
    student.getByText("Здесь только суммы классов", { exact: false }),
  ).toBeVisible();

  // проверяем сам ответ: чужих имён и номеров учеников в нём нет
  const payload = (await (
    await student.request.get("/api/prep/quiz/")
  ).json()) as {
    teams: { teams: Record<string, unknown>[] };
  };
  for (const row of payload.teams.teams) {
    expect(Object.keys(row).sort()).toEqual([
      "accuracy",
      "matches",
      "score",
      "team",
    ]);
  }
});

test("закрытые бейджи видны с условием и прогрессом", async ({ browser }) => {
  const student = await as(browser, "student");
  await student.goto("/achievements");
  await expect(
    student.getByRole("heading", { name: "Достижения", exact: true }),
  ).toBeVisible();
  await expect(student.getByText("Ещё не получено")).toBeVisible();
  // у закрытого бейджа виден прогресс «0 из N», а не пустое место
  await expect(student.locator(".badges__card--locked").first()).toBeVisible();
  await expect(
    student.locator(".badges__card--locked .num").first(),
  ).toContainText("из");
});

test("директор школы заводит бейдж", async ({ browser }) => {
  const director = await as(browser, "director_behavior");
  await director.goto("/badges");
  await expect(
    director.getByRole("heading", { name: "Достижения школы" }),
  ).toBeVisible();

  await director
    .getByRole("button", { name: "Добавить бейдж" })
    .first()
    .click();
  await director.getByLabel("Код бейджа").fill("probe_browser_badge");
  await director.getByLabel("Название бейджа").fill(BADGE);
  await director
    .getByLabel("Что считает бейдж")
    .selectOption({ label: "Решённые упражнения" });
  await director.getByLabel("Сколько нужно").fill("50");
  await director.getByRole("button", { name: "Завести" }).click();

  await expect(director.getByText(BADGE).first()).toBeVisible();
});

test("уборка: бейдж прогона удалён", async ({ browser }) => {
  const director = await as(browser, "director_behavior");
  const token = await csrf(director);
  const listing = (await (
    await director.request.get("/api/badges/?page_size=100")
  ).json()) as {
    results: { id: number; name: string }[];
  };
  for (const row of listing.results.filter((item) => item.name === BADGE)) {
    const gone = await director.request.delete(`/api/badges/${row.id}/`, {
      headers: { "X-CSRFToken": token },
    });
    expect(gone.ok()).toBeTruthy();
  }
});
