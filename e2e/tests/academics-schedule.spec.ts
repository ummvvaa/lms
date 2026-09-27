/**
 * Расписание у Кымбат: неделя по группе, панель урока, правка «этот
 * и все следующие» с накладкой и «всё равно сохранить», список изменений;
 * учитель видит новый кабинет у себя.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { daysAgo, lessonsBetween } from "../helpers/academics";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  return page;
}

const daysAhead = (n: number): string => new Date(Date.now() + n * 86_400_000).toISOString().slice(0, 10);

test("неделя по группе: панель урока и правка «этот и все следующие» с накладкой", async ({ browser }) => {
  const kymbat = await as(browser, "director_exam");
  const diag = watch(kymbat);
  // будущий урок учителя прогона на следующей неделе
  const future = (await lessonsBetween(kymbat, daysAhead(1), daysAhead(14))).filter(
    (row) => row.actual_teacher?.short?.includes("Прогон") && row.is_live !== false,
  );
  expect(future.length, "впереди есть уроки учителя прогона").toBeGreaterThan(1);
  const lesson = future[0];
  const other = future.find((row) => row.date === lesson.date && row.slot !== lesson.slot) ?? future[1];

  await kymbat.goto(`/schedule?from=${lesson.date}`);
  await expect(kymbat.locator("h1")).toContainText("Расписание");
  const chip = kymbat.locator(".les", { hasText: lesson.subject.short_title }).first();
  await expect(chip).toBeVisible();
  await chip.click();
  const drawer = kymbat.locator(".drawer");
  await expect(drawer).toContainText(lesson.subject.title);
  await drawer.getByRole("button", { name: "Изменить" }).click();
  const form = kymbat.getByRole("dialog").filter({ hasText: "Изменить урок" });
  await form.getByRole("button", { name: "Этот и все следующие" }).click();
  await form.getByLabel("Кабинет").fill("401");
  // ставим на время другого урока того же учителя: накладка
  await form.getByLabel("Урок", { exact: true }).selectOption(String(other.slot));
  await form.getByLabel("Дата").fill(other.date);
  await expect(form).toContainText("Накладка", { timeout: 15_000 });
  await form.getByLabel("Всё равно сохранить с накладкой").check();
  const saved = kymbat.waitForResponse(
    (r) => r.url().includes(`/acad/lessons/${lesson.id}/edit/`) && r.request().method() === "POST",
  );
  await form.getByRole("button", { name: "Сохранить" }).click();
  expect((await saved).status()).toBe(200);
  await expect(kymbat.locator("body")).toContainText("Изменено с");

  // накладка видна в списке, изменение — в журнале
  await kymbat.goto(`/schedule?from=${other.date}`);
  await expect(kymbat.locator(".datacard", { hasText: "Накладки" })).toContainText(lesson.subject.short_title);
  await expect(kymbat.locator(".datacard", { hasText: "Последние изменения" })).toBeVisible();

  // возвращаем как было: кабинет и время обратно, чтобы посев не расходился
  const back = kymbat.locator(".les", { hasText: lesson.subject.short_title }).first();
  await back.click();
  await kymbat.locator(".drawer").getByRole("button", { name: "Изменить" }).click();
  const undo = kymbat.getByRole("dialog").filter({ hasText: "Изменить урок" });
  await undo.getByRole("button", { name: "Этот и все следующие" }).click();
  await undo.getByLabel("Кабинет").fill("204");
  await undo.getByLabel("Урок", { exact: true }).selectOption(String(lesson.slot));
  await undo.getByLabel("Дата").fill(lesson.date);
  const force = undo.getByLabel("Всё равно сохранить с накладкой");
  if (await force.isVisible().catch(() => false)) await force.check();
  await undo.getByRole("button", { name: "Сохранить" }).click();
  await expect(kymbat.locator("body")).toContainText("Изменено с");
  expect(diag.pageErrors, "исключения").toEqual([]);
  await kymbat.context().close();
});

test("отмена урока с причиной видна учителю и ученику, «Вернуть как было» снимает", async ({ browser }) => {
  const kymbat = await as(browser, "director_exam");
  const future = (await lessonsBetween(kymbat, daysAhead(1), daysAhead(14))).filter(
    (row) => row.actual_teacher?.short?.includes("Прогон") && row.is_live !== false,
  );
  const lesson = future[future.length - 1];
  await kymbat.goto(`/schedule?from=${lesson.date}`);
  await kymbat.locator(".les", { hasText: lesson.subject.short_title }).last().click();
  await kymbat.locator(".drawer").getByRole("button", { name: "Отменить урок" }).click();
  const dialog = kymbat.getByRole("dialog").filter({ hasText: "Отменить урок" });
  await dialog.getByLabel("Причина — её увидят ученики").fill("Учитель на семинаре");
  const cancelled = kymbat.waitForResponse(
    (r) => r.url().includes(`/acad/lessons/${lesson.id}/cancel/`) && r.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "Отменить урок" }).click();
  expect((await cancelled).status()).toBe(200);

  const teacher = await as(browser, "teacher");
  await teacher.goto(`/schedule?from=${lesson.date}`);
  await expect(teacher.locator(".les--off, .les--cancelled").first()).toBeVisible();
  await teacher.context().close();

  await kymbat.goto(`/schedule?from=${lesson.date}`);
  await kymbat.locator(".les", { hasText: lesson.subject.short_title }).last().click();
  const restored = kymbat.waitForResponse(
    (r) => r.url().includes(`/acad/lessons/${lesson.id}/restore/`) && r.request().method() === "POST",
  );
  await kymbat.locator(".drawer").getByRole("button", { name: "Вернуть как было" }).click();
  expect((await restored).status()).toBe(200);
  await kymbat.context().close();
});
