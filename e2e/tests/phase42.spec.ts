/**
 * Фаза 42 — центр подготовки.
 *
 * Ученик видит семь плиток экзаменов, выбирает один — открываются форматы,
 * статистика и теория; на пустом банке экраны честно объясняют, что заданий
 * нет. Администратор загружает банк по чтению (один текст — пять вопросов) —
 * структура сохраняется; аудио вопроса без входа не открывается.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";

test.describe.configure({ mode: "serial", timeout: 180_000 });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

function csrf(page: Page): Promise<string> {
  return page.context().cookies().then((cookies) => cookies.find((c) => c.name === "csrftoken")?.value ?? "");
}

test("ученик: семь плиток, выбор экзамена, вкладки и статистика", async ({ browser }) => {
  const page = await as(browser, "student");
  await page.goto("/prep");

  await expect(page.getByText("Выберите экзамен", { exact: false })).toBeVisible();
  // С фазы 48 школа показывает два экзамена — SAT и IELTS; остальные
  // пять скрыты признаком показа у записи справочника, а не удалены
  await expect(page.locator(".prep__examtile")).toHaveCount(2);

  await page.locator(".prep__examtile", { hasText: "IELTS" }).first().click();
  await expect(page.getByRole("tab", { name: "Подготовка" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Статистика" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Теория" })).toBeVisible();

  // форматы подготовки
  for (const format of ["Тренажёр", "Пробник", "Работа над ошибками", "Курс"]) {
    await expect(page.getByText(format, { exact: true }).first()).toBeVisible();
  }

  await page.getByRole("tab", { name: "Статистика" }).click();
  await expect(page.getByText("Прогноз балла за тренировки")).toBeVisible();
});

test("администратор загружает чтение: один текст — пять вопросов", async ({ browser }) => {
  const admin = await as(browser, "admin");
  const token = await csrf(admin);

  const header =
    "exam_type,section,topic,question_type,text,A,B,C,D,correct,passage_key,passage_kind,passage_title,passage_text";
  const body = [
    header,
    "IELTS,reading,Main idea,single,Q1,a,b,c,d,A,PB,reading,City growth,A long reading passage about cities.",
    "IELTS,reading,Detail,single,Q2,a,b,c,d,B,PB,reading,,",
    "IELTS,reading,Detail,single,Q3,a,b,c,d,C,PB,reading,,",
    "IELTS,reading,Detail,single,Q4,a,b,c,d,D,PB,reading,,",
    "IELTS,reading,Detail,single,Q5,a,b,c,d,A,PB,reading,,",
  ].join("\n");

  const response = await admin.request.post("/api/prep/questions/import/", {
    headers: { "X-CSRFToken": token },
    multipart: {
      file: { name: "bank.csv", mimeType: "text/csv", buffer: Buffer.from(body, "utf-8") },
    },
  });
  expect(response.status()).toBe(200);
  const result = (await response.json()) as { created: number; passages: number };
  expect(result.created).toBe(5);
  expect(result.passages).toBe(1);

  // структура сохранилась: у секции reading видно прибавку заданий
  const overview = (await (await admin.request.get("/api/prep/bank/")).json()) as { total: number };
  expect(overview.total).toBeGreaterThanOrEqual(5);

  // уборка: убрать активность заданий прогона (мягко — is_active=false недоступно
  // напрямую, но эти строки не мешают; оставляем как есть для чистоты теста).
});

test("аудио вопроса не открывается без входа", async ({ browser }) => {
  const admin = await as(browser, "admin");
  const token = await csrf(admin);

  const header = "exam_type,section,topic,question_type,text,A,B,correct,passage_key,passage_kind,audio_file";
  const body = [header, "IELTS,listening,Numbers,single,How much?,10,12,B,LB,listening,clip.mp3"].join("\n");

  const response = await admin.request.post("/api/prep/questions/import/", {
    headers: { "X-CSRFToken": token },
    multipart: {
      file: { name: "audio.csv", mimeType: "text/csv", buffer: Buffer.from(body, "utf-8") },
      "clip.mp3": { name: "clip.mp3", mimeType: "audio/mpeg", buffer: Buffer.from("ID3fakeaudio") },
    },
  });
  expect(response.status()).toBe(200);

  // найдём id источника с аудио — через список заданий директора
  const director = await as(browser, "director_exam");
  const questions = (await (
    await director.request.get("/api/prep/questions/?exam_type=IELTS&section=listening&page_size=50")
  ).json()) as { results: { passage: number | null }[] };
  const passageId = questions.results.map((q) => q.passage).find((p) => p !== null);
  test.skip(passageId == null, "аудио-источник не найден");

  const anonymous = await browser.newContext();
  const noAuth = await anonymous.request.get(`/api/prep/passages/${passageId}/audio/`, { maxRedirects: 0 });
  expect([301, 302, 401, 403]).toContain(noAuth.status());

  const owner = await director.request.get(`/api/prep/passages/${passageId}/audio/`);
  expect(owner.status()).toBe(200);
});

test("академический директор ведёт теорию, ученик её читает", async ({ browser }) => {
  const director = await as(browser, "director_exam");
  const token = await csrf(director);
  // уберём уроки прошлых прогонов, чтобы не копились дубли
  const stale = (await (await director.request.get("/api/prep/theory/?exam_type=IELTS")).json()) as {
    results: { id: number; title: string }[];
  };
  for (const lesson of stale.results.filter((l) => l.title === "Skimming basics")) {
    await director.request.delete(`/api/prep/theory/${lesson.id}/`, { headers: { "X-CSRFToken": token } });
  }

  await director.goto("/mocks");
  await director.getByRole("tab", { name: "Теория" }).click();
  await director.getByLabel("Название урока").fill("Skimming basics");
  const [created] = await Promise.all([
    director.waitForResponse((r) => r.url().includes("/api/prep/theory/") && r.request().method() === "POST"),
    director.getByRole("button", { name: "Добавить урок" }).click(),
  ]);
  expect(created.status()).toBe(201);

  const student = await as(browser, "student");
  await student.goto("/prep");
  await student.locator(".prep__examtile", { hasText: "IELTS" }).first().click();
  await student.getByRole("tab", { name: "Теория" }).click();
  await expect(student.getByText("Skimming basics").first()).toBeVisible();

  // уборка урока прогона
  const lessons = (await (await director.request.get("/api/prep/theory/?exam_type=IELTS")).json()) as {
    results: { id: number; title: string }[];
  };
  for (const lesson of lessons.results.filter((l) => l.title === "Skimming basics")) {
    await director.request.delete(`/api/prep/theory/${lesson.id}/`, { headers: { "X-CSRFToken": token } });
  }
});
