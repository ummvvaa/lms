/**
 * Расписание у Кымбат: неделя по группе, панель урока, правка «этот
 * и все следующие» с накладкой и «всё равно сохранить», список изменений;
 * учитель видит новый кабинет у себя.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { almatyDay, lessonsBetween, type LessonRow } from "../helpers/academics";
import { statePath } from "../helpers/auth-state";
import { apiPost, watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  return page;
}

/** День через `n` дней по Алматы: по UTC ночью «завтра» было бы сегодняшним днём. */
const daysAhead = (n: number): string => almatyDay(n);

/** Неделя урока в редакторе: вид «по группе» открывает первую группу, а не группу урока. */
const weekOf = (lesson: LessonRow): string =>
  `/schedule?from=${lesson.date}&key=${encodeURIComponent(lesson.cohort.group)}`;

test("неделя по группе: панель урока и правка «этот и все следующие» с накладкой", async ({ browser }) => {
  const kymbat = await as(browser, "director_exam");
  const diag = watch(kymbat);
  // будущий урок учителя прогона на следующей неделе — урок всей группы:
  // неделя группы показывает его наверняка, урок потока может стоять у другой группы
  const future = (await lessonsBetween(kymbat, daysAhead(1), daysAhead(14))).filter(
    (row) =>
      row.actual_teacher?.short?.includes("Прогон") &&
      row.is_live !== false &&
      row.cohort.kind === "group" &&
      Boolean(row.cohort.group),
  );
  expect(future.length, "впереди есть уроки учителя прогона").toBeGreaterThan(1);
  // учителей «Прогон» в посеве четверо (12.10.2026): накладка — только у одного
  // и того же человека, поэтому второй урок берём у учителя первого
  const lesson = future[0];
  const same = future.filter((row) => row.actual_teacher?.id === lesson.actual_teacher?.id);
  expect(same.length, "у учителя первого урока есть и другие уроки").toBeGreaterThan(1);
  const other = same.find((row) => row.date === lesson.date && row.slot !== lesson.slot) ?? same[1];

  await kymbat.goto(weekOf(lesson));
  await expect(kymbat.locator("h1")).toContainText("Расписание");
  // фишка урока — с предметом и кодом группы: у потока на той же неделе
  // может стоять урок того же предмета другой группы
  const chip = kymbat
    .locator(".les", { hasText: lesson.subject.title })
    .filter({ hasText: lesson.cohort.group })
    .first();
  await expect(chip).toBeVisible();
  await chip.click();
  const drawer = kymbat.locator(".drawer");
  await expect(drawer).toContainText(lesson.subject.title);
  await drawer.getByRole("button", { name: "Изменить" }).click();
  const form = kymbat.getByRole("dialog", { name: "Изменить урок" });
  await form.getByRole("button", { name: "Этот и все следующие" }).click();
  await form.getByLabel("Кабинет").fill("401");
  // ставим на время другого урока того же учителя: накладка
  await form.getByLabel("Урок", { exact: true }).selectOption(String(other.slot));
  await form.getByLabel("Дата").fill(other.date);
  await expect(form).toContainText("Накладка", { timeout: 15_000 });
  // флажок Base UI: роль у span, скрытый input дублирует подпись
  await form.getByRole("checkbox", { name: "Всё равно сохранить с накладкой" }).click();
  const saved = kymbat.waitForResponse(
    (r) => r.url().includes("/acad/lessons/") && r.url().endsWith("/edit/") && r.request().method() === "POST",
  );
  await form.getByRole("button", { name: "Сохранить" }).click();
  const answer = await saved;
  expect(answer.status()).toBe(200);
  const moved = ((await answer.json()) as { lesson: { id: number } | null }).lesson;
  expect(moved, "сервер вернул перенесённый урок").toBeTruthy();
  await expect(kymbat.locator("body")).toContainText("Изменена серия с");

  // накладка видна в списке, изменение — в журнале
  await kymbat.goto(`/schedule?from=${other.date}&key=${encodeURIComponent(lesson.cohort.group)}`);
  // накладка описана словами: учитель ведёт два урока сразу
  await expect(kymbat.locator(".datacard", { hasText: "Накладки" })).toContainText("ведёт два урока сразу");
  await expect(kymbat.locator(".datacard", { hasText: "Последние изменения" })).toBeVisible();

  // возвращаем как было: кабинет и время обратно, чтобы посев не расходился.
  // Правку формой сценарий уже проверил — возврат запросом к перенесённому уроку
  await apiPost(kymbat, `/api/acad/lessons/${moved!.id}/edit/`, {
    id: moved!.id,
    scope: "next",
    date: lesson.date,
    slot: lesson.slot,
    room: lesson.room ?? "",
    force: true,
  });
  expect(diag.pageErrors, "исключения").toEqual([]);
  await kymbat.context().close();
});

test("отмена урока с причиной видна учителю и ученику, «Вернуть как было» снимает", async ({ browser }) => {
  // урок берём из расписания самого учителя прогона: в посеве есть второй учитель
  // с той же фамилией, а его уроков учитель не увидит
  const teacher = await as(browser, "teacher");
  const future = (await lessonsBetween(teacher, daysAhead(1), daysAhead(14))).filter(
    (row) => row.is_live !== false && row.cohort.kind === "group" && Boolean(row.cohort.group),
  );
  expect(future.length, "впереди есть уроки учителя прогона").toBeGreaterThan(0);
  const lesson = future[future.length - 1];
  const kymbat = await as(browser, "director_exam");
  await kymbat.goto(weekOf(lesson));
  const own = kymbat.locator(".les", { hasText: lesson.subject.title }).filter({ hasText: lesson.actual_teacher?.short ?? "" });
  await own.last().click();
  await kymbat.locator(".drawer").getByRole("button", { name: "Отменить урок" }).click();
  const dialog = kymbat.getByRole("dialog", { name: "Отменить урок" });
  await dialog.getByLabel("Причина — её увидят ученики").fill("Учитель на семинаре");
  const cancelled = kymbat.waitForResponse(
    (r) => r.url().includes("/acad/lessons/") && r.url().endsWith("/cancel/") && r.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "Отменить урок", exact: true }).click();
  expect((await cancelled).status()).toBe(200);

  await teacher.goto(`/schedule?from=${lesson.date}`);
  await expect(teacher.locator(".les--off, .les--cancelled").first()).toBeVisible();
  await teacher.context().close();

  await kymbat.goto(weekOf(lesson));
  await kymbat.locator(".les--off, .les--cancelled").filter({ hasText: lesson.subject.title }).last().click();
  const restored = kymbat.waitForResponse(
    (r) => r.url().includes("/acad/lessons/") && r.url().endsWith("/restore/") && r.request().method() === "POST",
  );
  await kymbat.locator(".drawer").getByRole("button", { name: "Вернуть как было" }).click();
  expect((await restored).status()).toBe(200);
  await kymbat.context().close();
});
