/**
 * Ученик вносит, директор подтверждает: предложения ученика по своим данным.
 *
 * Ученик вносит себе балл IELTS: значение видно сразу с пометкой
 * «на проверке у директора», в профиль ничего не пишется. Директор спорта этой
 * строки в своей очереди не видит; академический директор видит,
 * подтверждает — пометка исчезает, в журнале источник «предложил ученик».
 * Лестница пяти шагов («Мой путь») с 07.10.2026 из кабинета убрана, её API
 * проверяет `api_probe.py`.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { openDirectorQueue } from "../helpers/session";

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

test("ученик вносит балл IELTS — сразу видно «на проверке у директора», профиль не тронут", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  const me = (await (await page.request.get("/api/students/me/")).json()) as {
    exam: { ielts_current: string | null };
  };
  proposed = nextValue(me.exam.ielts_current);

  await page.goto("/my-data");
  // с 07.10.2026 «Обзор» без дублей: баллы вносятся формой «Внести баллы» прямо в карточке
  await page.getByRole("button", { name: "Внести баллы" }).click();
  const form = page.locator(".propose__form").first();
  await expect(form).toBeVisible();
  const field = form.locator("label", { hasText: "IELTS" }).locator("input").first();
  await field.fill(proposed);

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/suggestions/propose/")),
    page.getByRole("button", { name: "Отправить на проверку" }).click(),
  ]);
  expect(response.status()).toBe(201);

  // пометка на месте, значение показывается сразу
  await expect(page.getByText("на проверке у директора").first()).toBeVisible();

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
  // очередь решений — на главной директора (раздела «Предложения» нет с 24.10.2026)
  const page = await as(browser, "director_sport");
  await page.goto("/dashboard");
  await expect(page.locator("h1")).toContainText("Добрый день");
  await expect(
    page.locator("#student-queue").getByText("Текущий балл IELTS"),
  ).toHaveCount(0);
});

test("академический директор видит строку и подтверждает — журнал помнит ученика", async ({
  browser,
}) => {
  const page = await as(browser, "director_exam");
  const queue = await openDirectorQueue(page);
  await expect(queue).toBeVisible();
  const row = queue
    .locator("[data-suggestion]", { hasText: "Текущий балл IELTS" })
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
  await expect(examCard.getByText("на проверке у директора")).toHaveCount(0);
  await expect(
    examCard.getByText(proposed, { exact: true }).first(),
  ).toBeVisible();
});
