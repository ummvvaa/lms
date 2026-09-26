/**
 * Квиз без публичных рейтингов и достижения-бейджи в живом браузере.
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

test("в зачёте групп нет строк учеников", async ({ browser }) => {
  const student = await as(browser, "student");
  await student.goto("/quiz");
  // с фазы 48 вкладка называется «Командный зачёт»
  await student.getByRole("tab", { name: "Командный зачёт" }).click();
  await expect(
    student.getByText("Здесь только суммы групп", { exact: false }),
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

  // бейдж прошлого прогона, оставшийся после его падения, убираем заранее:
  // код бейджа уникален, и второй с тем же кодом сервер не заведёт
  const stale = (await (
    await director.request.get("/api/badges/?page_size=100")
  ).json()) as { results: { id: number; name: string }[] };
  for (const row of stale.results.filter((item) => item.name === BADGE))
    await director.request.delete(`/api/badges/${row.id}/`, {
      headers: { "X-CSRFToken": await csrf(director) },
    });
  await director.reload();

  await director
    .getByRole("button", { name: "Добавить бейдж" })
    .first()
    .click();
  // форма — в окне; «Сколько нужно» есть и в каждой карточке бейджа,
  // поэтому поля ищем внутри окна
  const form = director.getByRole("dialog");
  await form.getByLabel("Код бейджа").fill("probe_browser_badge");
  await form.getByLabel("Название бейджа").fill(BADGE);
  await form
    .getByLabel("Что считает бейдж")
    .selectOption({ label: "Решённые упражнения" });
  await form.getByLabel("Сколько нужно").fill("50");
  await form.getByRole("button", { name: "Завести" }).click();

  // бейдж — карточкой: название как увидит ученик и строка «Даётся за: …»
  const card = director.locator(".scard", { hasText: BADGE });
  await expect(card).toBeVisible();
  await expect(card).toContainText("Даётся за:");
  await expect(card).toContainText("Решённые упражнения, нужно 50");

  // порог правится прямо в карточке
  const saved = director.waitForResponse(
    (r) => /\/api\/badges\/\d+\/$/.test(r.url()) && r.request().method() === "PATCH",
  );
  await card.getByLabel("Сколько нужно").fill("60");
  await card.getByRole("button", { name: "Сохранить" }).click();
  expect((await saved).status()).toBe(200);
  await expect(card).toContainText("нужно 60");

  // переключатель «показывать» — там же
  const hidden = director.waitForResponse(
    (r) => /\/api\/badges\/\d+\/$/.test(r.url()) && r.request().method() === "PATCH",
  );
  await card.getByRole("switch").click();
  expect((await hidden).status()).toBe(200);
  await expect(card).toContainText("скрыт");
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
