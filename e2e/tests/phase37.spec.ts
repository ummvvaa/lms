/**
 * Фаза 37 — ученик вносит, директор подтверждает.
 *
 * Ученик вносит себе балл IELTS: значение видно сразу с пометкой
 * «ждёт проверки», в профиль ничего не пишется. Директор спорта этой
 * строки в своей очереди не видит; академический директор видит,
 * подтверждает — пометка исчезает, в журнале источник «предложил ученик».
 * Плюс лестница пяти шагов на месте и с запертым пятым, пока нет вузов.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";

test.describe.configure({ mode: "serial", timeout: 180_000 });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  return page;
}

/** Значение, заведомо отличное от текущего: применение обязано попасть в журнал.
 *  С одним знаком после запятой — так его хранит и показывает профиль. */
function nextValue(current: string | null): string {
  return current === "7.5" ? "6.5" : "7.5";
}

let proposed = "";

test("ученик вносит балл IELTS — сразу видно «ждёт проверки», профиль не тронут", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  const me = (await (await page.request.get("/api/students/me/")).json()) as {
    exam: { ielts_current: string | null };
  };
  proposed = nextValue(me.exam.ielts_current);

  await page.goto("/my-data");
  const examCard = page.locator("section", { hasText: "Ваши баллы" }).first();
  await examCard.getByRole("button", { name: "Внести данные" }).click();

  const field = examCard
    .locator("label", { hasText: "Текущий балл IELTS" })
    .locator("input");
  await field.fill(proposed);

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/suggestions/propose/")),
    examCard.getByRole("button", { name: "Отправить на проверку" }).click(),
  ]);
  expect(response.status()).toBe(201);

  // пометка на месте, значение показывается сразу
  await expect(examCard.getByText("ждёт проверки").first()).toBeVisible();

  // а профиль не изменился: решение ещё не принято
  const after = (await (
    await page.request.get("/api/students/me/")
  ).json()) as {
    exam: { ielts_current: string | null };
  };
  expect(after.exam.ielts_current).toEqual(me.exam.ielts_current);
});

test("директор спорта не видит балл экзамена в своей очереди", async ({
  browser,
}) => {
  const page = await as(browser, "director_sport");
  await page.goto("/suggestions");
  await expect(page.getByText("Предложения").first()).toBeVisible();
  await expect(
    page.locator("#student-queue").getByText("Текущий балл IELTS"),
  ).toHaveCount(0);
});

test("академический директор видит строку и подтверждает — журнал помнит ученика", async ({
  browser,
}) => {
  const page = await as(browser, "director_exam");
  await page.goto("/suggestions");

  const queue = page.locator("#student-queue");
  await expect(queue).toBeVisible();
  const row = queue
    .locator(".squeue__row", { hasText: "Текущий балл IELTS" })
    .first();
  await expect(row).toBeVisible();

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/review/")),
    row.getByRole("button", { name: "Подтвердить", exact: true }).click(),
  ]);
  expect(response.status()).toBe(200);

  // значение легло в профиль, источник в журнале — «предложил ученик»
  const students = (await (
    await page.request.get("/api/students/?page_size=500")
  ).json()) as { results: { id: number; email: string }[] };
  const card = students.results.find((r) => r.email === "student@probe.local");
  expect(card).toBeTruthy();
  const history = (await (
    await page.request.get(`/api/students/${card!.id}/history/`)
  ).json()) as {
    source: string;
  }[];
  expect(history.some((entry) => entry.source === "student_proposal")).toBe(
    true,
  );
});

test("после подтверждения пометка у ученика исчезает, значение остаётся", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  await page.goto("/my-data");
  const examCard = page.locator("section", { hasText: "Ваши баллы" }).first();
  await expect(examCard.getByText("ждёт проверки")).toHaveCount(0);
  await expect(
    examCard.getByText(proposed, { exact: true }).first(),
  ).toBeVisible();
});

test("лестница пяти шагов открывается и честно показывает состояние", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  const journey = (await (await page.request.get("/api/journey/")).json()) as {
    total: number;
    complete: boolean;
    steps: { code: string; locked: boolean }[];
  };
  expect(journey.total).toBe(5);

  await page.goto("/journey");
  await expect(page.getByText("Ваш путь к поступлению")).toBeVisible();
  await expect(page.locator(".journey__step")).toHaveCount(5);
  await expect(
    page.locator(".journey__progress").getByText(/\d+ из \d+/),
  ).toBeVisible();

  const plan = journey.steps.find((s) => s.code === "plan")!;
  const planCard = page.locator('[data-step="plan"]');
  if (plan.locked) {
    await expect(planCard.getByText("Пока закрыто")).toBeVisible();
  } else {
    await expect(planCard.getByRole("button").first()).toBeVisible();
  }

  // Главная: с фазы 48 лестница осталась своим экраном, а на главной
  // стоит карточка призыва со следующим шагом — человек, зашедший
  // в кабинет, должен видеть свои дела, а не список несделанного
  await page.goto("/dashboard");
  await expect(
    page.getByRole("heading", { name: "Главная", exact: true }),
  ).toBeVisible();
  // с фазы 49 на месте карточки призыва — карусель незакрытых мест;
  // закрывать нечего — её нет вовсе, и календарь занимает её место
  const cues = (await (await page.request.get("/api/home/cues/")).json()) as {
    cues: { title: string }[];
  };
  if (cues.cues.length > 0) {
    await expect(page.locator(".caro")).toBeVisible();
  } else {
    await expect(page.locator(".caro")).toHaveCount(0);
    await expect(page.locator(".home__cal")).toBeVisible();
  }
});
