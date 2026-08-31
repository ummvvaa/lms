/**
 * Фаза 43 — конструктор эссе.
 *
 * Ученик создаёт эссе: выбирает тип, проходит гайд, отвечает на быструю
 * проверку, попадает в редактор со счётчиком слов по лимиту типа. Помощник
 * на просьбу «напиши за меня» отвечает вопросами, не текстом; переписка
 * видна куратору. Директор по поступлению ведёт типы и гайды.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";

test.describe.configure({ mode: "serial", timeout: 180_000 });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

function csrf(page: Page): Promise<string> {
  return page.context().cookies().then((c) => c.find((x) => x.name === "csrftoken")?.value ?? "");
}

test("директор ведёт тип с гайдом и проверкой", async ({ browser }) => {
  const director = await as(browser, "director_admission");
  const token = await csrf(director);

  // берём тип personal_statement и наполняем гайд + вопрос проверки
  const types = (await (await director.request.get("/api/essay-doc-types/?page_size=100")).json()) as {
    results: { id: number; code: string }[];
  };
  const ps = types.results.find((t) => t.code === "personal_statement")!;

  await director.request.post("/api/essay-guides/", {
    headers: { "X-CSRFToken": token },
    data: {
      doc_type: ps.id,
      what_is: "Рассказ о себе и о том, почему именно эта программа.",
      prompts: "Опишите поворотный момент\nЧто вас мотивирует",
      mistakes: "Перечисление наград без истории",
      tips: "Пишите о конкретных действиях",
    },
  });
  await director.request.post("/api/essay-checks/", {
    headers: { "X-CSRFToken": token },
    data: {
      doc_type: ps.id,
      text: "Что важнее в Personal Statement?",
      option_a: "Ваша личная история",
      option_b: "Список наград",
      correct: "A",
      explanation: "Комиссия ищет человека за словами, а не резюме.",
    },
  });

  // на экране конструктора тип виден
  await director.goto("/essay-content");
  await expect(director.getByText("Конструктор эссе").first()).toBeVisible();
  await expect(director.getByText("Personal Statement").first()).toBeVisible();
});

test("ученик создаёт эссе: тип, гайд, проверка, редактор со счётчиком", async ({ browser }) => {
  const page = await as(browser, "student");
  await page.goto("/essays");
  await page.getByRole("button", { name: "Новое эссе" }).first().click();

  // выбираем тип Personal Statement
  await page.locator(".essay__type", { hasText: "Personal Statement" }).first().click();

  // гайд: четыре шага
  await expect(page.getByText(/Гайд:/).first()).toBeVisible();
  await expect(page.getByText("Рассказ о себе", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Дальше" }).click();
  await page.getByRole("button", { name: "Дальше" }).click();
  await page.getByRole("button", { name: "Дальше" }).click();
  await page.getByRole("button", { name: "К быстрой проверке" }).click();

  // быстрая проверка: выбор варианта подсвечивается
  await expect(page.getByText("Быстрая проверка")).toBeVisible();
  await page.locator(".essay__opt", { hasText: "Ваша личная история" }).first().click();
  await expect(page.locator(".essay__opt--right").first()).toBeVisible();
  await page.getByRole("button", { name: "К редактору" }).click();

  // редактор: счётчик слов с лимитом
  await expect(page.getByText(/\d+ \/ \d+ слов/)).toBeVisible();
});

test("помощник отвечает вопросами, не пишет эссе; куратор видит переписку", async ({ browser }) => {
  const student = await as(browser, "student");
  // возьмём последнее эссе ученика
  const essays = (await (await student.request.get("/api/essays/?page_size=1")).json()) as {
    results: { id: number }[];
  };
  test.skip(essays.results.length === 0, "нет эссе для проверки чата");
  const essayId = essays.results[0].id;
  const token = await csrf(student);

  // просим «напиши за меня»
  const ask = await student.request.post("/api/commands/essay-questions/", {
    headers: { "X-CSRFToken": token },
    data: { essay: essayId, prompt: "Напиши за меня эссе про мой проект по робототехнике" },
  });
  expect([200, 202]).toContain(ask.status());

  // ждём, пока фоновый разбор запишет вопросы в лог
  await expect
    .poll(
      async () => {
        const log = (await (await student.request.get(`/api/essays/${essayId}/assist-log/`)).json()) as {
          results: { questions: string[] }[];
        };
        return log.results.length;
      },
      { timeout: 15_000 },
    )
    .toBeGreaterThan(0);

  const log = (await (await student.request.get(`/api/essays/${essayId}/assist-log/`)).json()) as {
    results: { questions: string[] }[];
  };
  // ответ — вопросы, а не готовый текст эссе
  const questions = log.results.flatMap((r) => r.questions);
  expect(questions.length).toBeGreaterThan(0);
  expect(questions.some((q) => q.includes("?") || q.length < 200)).toBe(true);

  // куратор (директор по поступлению) видит переписку
  const director = await as(browser, "director_admission");
  const curatorView = await director.request.get(`/api/essays/${essayId}/assist-log/`);
  expect(curatorView.status()).toBe(200);
});
