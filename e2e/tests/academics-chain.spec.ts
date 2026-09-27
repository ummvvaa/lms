/**
 * Сквозная цепочка учебной части в браузере: учитель отметил урок →
 * куратор видит «н» в посещаемости → оформляет уважительную причину
 * за период → в журнале учителя «у» → отчёт собран → PDF скачан →
 * «отправлен родителям».
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { daysAgo, lessonsBetween } from "../helpers/academics";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { apiPost, watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  await page.addInitScript(() => {
    window.localStorage.setItem("first-run-seen", "1");
    window.localStorage.setItem("getting-started-folded", "1");
  });
  return page;
}

let lessonId = 0;
let lessonDate = "";
let courseId = 0;
let groupCode = "";
let studentId = 0;
let studentName = "";
let reportId = 0;

test("учитель: урок отмечен с экрана урока — один «н»", async ({ browser }) => {
  const teacher = await as(browser, "teacher");
  const diag = watch(teacher);
  const mine = (await lessonsBetween(teacher, daysAgo(14), daysAgo(1))).filter(
    (row) => row.date < daysAgo(0),
  );
  expect(mine.length, "у учителя прогона есть прошедшие уроки").toBeGreaterThan(0);
  const lesson = mine[mine.length - 1];
  lessonId = lesson.id;
  lessonDate = lesson.date;
  courseId = lesson.course;
  groupCode = lesson.cohort.group;

  await teacher.goto(`/lessons/${lessonId}`);
  await expect(teacher.locator("h1")).toContainText(lesson.subject.title);
  // ученик прогона — первый в списке: отметка «н» уходит запросом
  const roster = (await (
    await teacher.request.get(`/api/acad/lessons/${lessonId}/`)
  ).json()) as { roster: { id: number; full_name: string; email?: string }[] };
  const pupil =
    roster.roster.find((row) => row.email === probeEmail("student")) ?? roster.roster[0];
  studentId = pupil.id;
  studentName = pupil.full_name;
  const line = teacher.locator(".roster__row", { hasText: studentName }).first();
  await expect(line).toBeVisible();
  const saved = teacher.waitForResponse(
    (r) => r.url().includes(`/acad/lessons/${lessonId}/attendance/`) && r.request().method() === "POST",
  );
  await line.getByRole("button", { name: "н", exact: true }).click();
  expect((await saved).status()).toBe(200);
  await teacher.reload();
  await expect(teacher.locator(".roster__row", { hasText: studentName }).first()).toContainText("н");
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  await teacher.context().close();
});

test("куратор: видит «н» в посещаемости группы за день", async ({ browser }) => {
  const curator = await as(browser, "curator");
  await curator.goto(`/attendance?group=${encodeURIComponent(groupCode)}&date=${lessonDate}`);
  await expect(curator.locator("h1")).toContainText("Посещаемость");
  const grid = curator.locator(".matrix");
  await expect(grid).toBeVisible();
  const row = grid.locator("tr", { hasText: studentName }).first();
  await expect(row).toContainText("н");
  await curator.context().close();
});

test("куратор: уважительная причина за период — «н» стал «у»", async ({ browser }) => {
  const curator = await as(browser, "curator");
  const diag = watch(curator);
  await curator.goto(`/students/${studentId}?tab=grades`);
  await expect(curator.getByRole("button", { name: "Уважительная причина" })).toBeVisible();
  await curator.getByRole("button", { name: "Уважительная причина" }).click();
  const dialog = curator.getByRole("dialog", { name: "Уважительная причина" });
  await dialog.getByLabel("С", { exact: true }).fill(lessonDate);
  await dialog.getByLabel("По", { exact: true }).fill(lessonDate);
  await dialog.getByLabel("Причина").fill("Болезнь: справка");
  const made = curator.waitForResponse(
    (r) => r.url().includes("/api/acad/excuses/") && r.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "Оформить" }).click();
  expect((await made).status()).toBe(201);
  await expect(curator.locator("body")).toContainText("Причина оформлена");
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  await curator.context().close();

  const teacher = await as(browser, "teacher");
  await teacher.goto(`/journals/${courseId}`);
  await expect(teacher.locator(".matrix")).toBeVisible();
  const row = teacher.locator(".matrix tr", { hasText: studentName }).first();
  await expect(row).toContainText("у");
  await teacher.context().close();
});

test("отчёт: собран, проверен, PDF скачан, отправлен родителям", async ({ browser }) => {
  const kymbat = await as(browser, "director_exam");
  await kymbat.goto("/reports");
  await expect(kymbat.locator("h1")).toContainText("Отчёты родителям");
  await kymbat.locator(".head__actions").getByLabel("Ещё действия").click();
  await kymbat.getByRole("menuitem", { name: "Собрать за период" }).click();
  const dialog = kymbat.getByRole("dialog", { name: "Собрать отчёты за период" });
  const built = kymbat.waitForResponse(
    (r) => r.url().includes("/api/acad/reports/build/") && r.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "Собрать", exact: true }).click();
  expect((await built).status()).toBe(200);
  await expect(kymbat.locator("body")).toContainText("Собрано отчётов");
  // Кымбат видит, но не правит слово куратора
  await kymbat.context().close();

  const curator = await as(browser, "curator");
  const diag = watch(curator);
  await curator.goto("/reports");
  const listed = (await (await curator.request.get("/api/acad/reports/")).json()) as {
    rows: { id: number; status: string; student: { id: number } }[];
  };
  const report = listed.rows.find((row) => row.student.id === studentId);
  expect(report, "отчёт ученика прогона собран").toBeTruthy();
  reportId = report!.id;
  // повторный прогон на живой базе: отчёт уже отправлен — отметка снимается,
  // слово и PDF проверяются заново
  if (report!.status === "sent") {
    await apiPost(curator, `/api/acad/reports/${reportId}/sent/`, { sent: false });
  }
  await curator.goto(`/reports?open=${reportId}`);
  const drawer = curator.locator(".drawer");
  await expect(drawer).toBeVisible();
  await drawer.getByLabel("Слово куратора").fill("Молодец, держит темп.");
  const checked = curator.waitForResponse(
    (r) => r.url().includes(`/api/acad/reports/${reportId}/check/`) && r.request().method() === "POST",
  );
  const download = curator.waitForEvent("download");
  await drawer.getByRole("button", { name: "Проверено и скачать" }).click();
  expect((await checked).status()).toBe(200);
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.pdf$/);
  await expect(drawer).toContainText("Выгружен");

  const sent = curator.waitForResponse(
    (r) => r.url().includes(`/api/acad/reports/${reportId}/sent/`) && r.request().method() === "POST",
  );
  await drawer.getByRole("button", { name: "Отправлен родителям" }).click();
  expect((await sent).status()).toBe(200);
  await expect(drawer).toContainText("Отправлен родителям");
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  await curator.context().close();
});

test("Кымбат: отчёты всех групп с фильтрами, слово куратора не правится", async ({ browser }) => {
  const kymbat = await as(browser, "director_exam");
  await kymbat.goto(`/reports?open=${reportId}`);
  const drawer = kymbat.locator(".drawer");
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("button", { name: "Сохранить слово" })).toHaveCount(0);
  await expect(drawer.getByRole("button", { name: "Отправлен родителям" })).toHaveCount(0);
  await expect(drawer).toContainText("Слово куратора");
  await kymbat.goto("/reports");
  await expect(kymbat.locator(".segrow").first()).toBeVisible();
  await kymbat.getByRole("button", { name: /^Отправлен родителям/ }).click();
  await expect(kymbat).toHaveURL(/status=sent/);
  await expect(kymbat.locator("table.tbl tbody tr", { hasText: studentName })).toHaveCount(1);
  await kymbat.context().close();
  // уборка: причина прогона снимается, чтобы посев оставался тем же
  const admin = await as(browser, "admin");
  const excuses = (await (
    await admin.request.get(`/api/acad/excuses/?student=${studentId}`)
  ).json()) as { rows: { id: number }[] };
  for (const row of excuses.rows) {
    await apiPost(admin, `/api/acad/excuses/${row.id}/`, {}).catch(() => undefined);
  }
  await admin.context().close();
});
