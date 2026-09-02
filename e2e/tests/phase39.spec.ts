/**
 * Фаза 39 — цели по экзаменам, календарь, напоминания.
 *
 * Ученик ставит цель IELTS на дату — она видна в календаре с пометкой,
 * после подтверждения — без; на главной обратный отсчёт. Дневной прогон
 * напоминаний приносит уведомление и задачу «Зарегистрироваться»;
 * сдвиг даты экзамена сдвигает срок задачи, а не оставляет старый.
 * ЕНТ остаётся в справочнике, но с фазы 48 школа показывает два
 * экзамена — SAT и IELTS; скрытый в списке целей не появляется.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { statePath } from "../helpers/auth-state";
import { apiDelete, apiPatch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

const ROOT = path.join(__dirname, "..", "..");

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

function isoInDays(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

const EXAM_DATE = isoInDays(14);

test("ученик ставит цель IELTS с датой — строка уходит на проверку", async ({
  browser,
}) => {
  // уборка целей прошлого прогона: с совпадающими значениями форма честно
  // говорит «менять нечего», и сценарий перестаёт быть повторяемым
  const director = await as(browser, "director_exam");
  const stale = (await (
    await director.request.get("/api/exam-goals/?page_size=200")
  ).json()) as {
    results: { id: number; exam_name: string }[];
  };
  for (const goal of stale.results.filter((g) => g.exam_name === "IELTS")) {
    await apiDelete(director, `/api/exam-goals/${goal.id}/`);
  }

  const page = await as(browser, "student");
  await page.goto("/my-data");

  const goals = page
    .locator("section", { hasText: "Цели по экзаменам" })
    .first();
  await expect(goals).toBeVisible();
  // С фазы 48 школа показывает два экзамена — SAT и IELTS; остальные
  // скрыты признаком показа у записи справочника, а не удалены.
  // Строка ЕНТ вернётся в список, как только его включат галочкой
  await expect(goals.locator('[data-exam="SAT"]')).toBeVisible();
  await expect(goals.locator('[data-exam="ЕНТ"]')).toHaveCount(0);

  const row = goals.locator('[data-exam="IELTS"]');
  await row.getByLabel(/Целевой балл/).fill("7.0");
  await row.getByLabel(/Дата экзамена/).fill(EXAM_DATE);

  const [propose] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/suggestions/propose/")),
    row.getByRole("button", { name: "Сохранить" }).click(),
  ]);
  expect(propose.status()).toBe(201);
  await expect(row.getByText("ждёт проверки")).toBeVisible();
});

test("цель видна в календаре с пометкой, после подтверждения — без", async ({
  browser,
}) => {
  const student = await as(browser, "student");
  await student.goto("/calendar");
  await student.getByRole("tab", { name: "Ближайшие" }).click();
  const pendingRow = student
    .locator(".rows__item", { hasText: "IELTS" })
    .first();
  await expect(pendingRow).toBeVisible();
  await expect(pendingRow.getByText("ждёт проверки")).toBeVisible();

  const director = await as(browser, "director_exam");
  await director.goto("/suggestions");
  const row = director
    .locator("#student-queue .squeue__row", {
      hasText: "Целевой балл экзамена",
    })
    .first();
  const [review] = await Promise.all([
    director.waitForResponse((r) => r.url().includes("/review/")),
    row.getByRole("button", { name: "Подтвердить", exact: true }).click(),
  ]);
  expect(review.status()).toBe(200);

  await student.goto("/calendar");
  await student.getByRole("tab", { name: "Ближайшие" }).click();
  const confirmed = student
    .locator(".rows__item", { hasText: "Экзамен: IELTS" })
    .first();
  await expect(confirmed).toBeVisible();
  await expect(confirmed.getByText("ждёт проверки")).toHaveCount(0);
});

test("на главной — календарь месяца и ближайшие события", async ({
  browser,
}) => {
  // С фазы 48 главная показывает месяц и панель ближайших событий рядом
  // с карточкой призыва: одна строка с отсчётом заменена списком
  const page = await as(browser, "student");
  await page.goto("/dashboard");
  await expect(page.getByText("Ближайшие события")).toBeVisible();
  await expect(page.locator(".home__calday--today")).toBeVisible();
});

test("дневной прогон: уведомление и задача о регистрации; сдвиг даты двигает срок", async ({
  browser,
}) => {
  const output = execFileSync(
    "docker",
    [
      "compose",
      "exec",
      "-T",
      "backend",
      "python",
      "manage.py",
      "shell",
      "-c",
      "from roadmap.reminders import run_daily; print(run_daily())",
    ],
    { cwd: ROOT, encoding: "utf8" },
  );
  expect(output).toContain("tasks_created");

  const student = await as(browser, "student");
  // уведомление в колокольчик
  const notes = (await (
    await student.request.get("/api/notifications/")
  ).json()) as {
    rows: { text: string }[];
  };
  expect(notes.rows.some((n) => n.text.includes("IELTS"))).toBe(true);

  // задача в роадмапе со сроком из цели
  await student.goto("/roadmap");
  await expect(
    student.getByText("Зарегистрироваться на экзамен IELTS").first(),
  ).toBeVisible();

  const before = (await (
    await student.request.get("/api/tasks/?page_size=200")
  ).json()) as {
    results: { id: number; title: string; due_date_effective: string | null }[];
  };
  const task = before.results.find((t) =>
    t.title.includes("Зарегистрироваться на экзамен IELTS"),
  );
  expect(task?.due_date_effective).toBe(EXAM_DATE);

  // директор сдвигает дату экзамена — срок задачи едет за ней (инвариант №4)
  const director = await as(browser, "director_exam");
  const goals = (await (
    await director.request.get("/api/exam-goals/?page_size=200")
  ).json()) as {
    results: { id: number; exam_name: string }[];
  };
  const goal = goals.results.find((g) => g.exam_name === "IELTS");
  expect(goal).toBeTruthy();
  const moved = isoInDays(24);
  await apiPatch(director, `/api/exam-goals/${goal!.id}/`, {
    exam_date: moved,
  });

  const after = (await (
    await student.request.get("/api/tasks/?page_size=200")
  ).json()) as {
    results: { id: number; due_date_effective: string | null }[];
  };
  expect(after.results.find((t) => t.id === task!.id)?.due_date_effective).toBe(
    moved,
  );
});

test("директор видит списки внимания на «Пробных»", async ({ browser }) => {
  const page = await as(browser, "director_exam");
  await page.goto("/mocks");
  await page.getByRole("tab", { name: "Цели по экзаменам" }).click();
  await expect(page.getByText("Целей пока нет", { exact: true })).toBeVisible();
  await expect(page.getByText("Экзамен на неделе")).toBeVisible();
  await expect(page.getByText("Все цели")).toBeVisible();
  await expect(
    page.locator(".history").getByText("IELTS").first(),
  ).toBeVisible();

  // уборка: цель прогона уходит в архив, чтобы прогон не менял школу
  const goals = (await (
    await page.request.get("/api/exam-goals/?page_size=200")
  ).json()) as {
    results: { id: number; exam_name: string }[];
  };
  for (const goal of goals.results.filter((g) => g.exam_name === "IELTS")) {
    await apiDelete(page, `/api/exam-goals/${goal.id}/`);
  }
});
