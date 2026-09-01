/**
 * Фаза 44 — стипендии.
 *
 * Директор по поступлению заводит стипендию с экрана, ученик находит её
 * фильтром, сохраняет сердечком и видит дедлайн в календаре. Подбор
 * называет только записи справочника (инвариант №10).
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";

test.describe.configure({ mode: "serial", timeout: 180_000 });

const NAME = "Probe Browser Scholarship";

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

function csrf(page: Page): Promise<string> {
  return page.context().cookies().then((c) => c.find((x) => x.name === "csrftoken")?.value ?? "");
}

/** Дата на год вперёд — чтобы срок не прошёл, пока прогон идёт. */
function nextYear(): string {
  const date = new Date();
  date.setFullYear(date.getFullYear() + 1);
  return date.toISOString().slice(0, 10);
}

test("директор заводит стипендию с экрана", async ({ browser }) => {
  const director = await as(browser, "director_admission");
  await director.goto("/scholarship-directory");
  await expect(director.getByRole("heading", { name: "Стипендии" })).toBeVisible();

  // кнопка есть и в шапке экрана, и в пустом состоянии — берём первую
  await director.getByRole("button", { name: "Добавить стипендию" }).first().click();
  await director.getByLabel("Название стипендии").fill(NAME);
  await director.getByLabel("Страна", { exact: true }).fill("Канада");
  await director.getByLabel("Организатор").fill("Probe Foundation");
  await director.getByLabel("Сумма до").fill("15000");
  await director.getByLabel("Валюта").fill("USD");
  await director.getByLabel("Дедлайн подачи").fill(nextYear());
  await director.getByRole("checkbox", { name: "Для иностранцев" }).click();
  await director.getByRole("button", { name: "Завести" }).click();

  // строка появилась в таблице справочника
  await expect(director.getByText(NAME).first()).toBeVisible();
});

test("ученик фильтрует, сохраняет и видит дедлайн в календаре", async ({ browser }) => {
  const student = await as(browser, "student");
  await student.goto("/scholarships");
  await expect(student.getByRole("heading", { name: "Стипендии", exact: true })).toBeVisible();

  // три карточки-числа сверху (с фазы 48 — общий вид карточки-числа)
  await expect(
    student.getByText("Доступно стипендий", { exact: true }),
  ).toBeVisible();
  await expect(student.getByText("Дедлайн близко", { exact: true })).toBeVisible();

  // фильтр по стране сужает выдачу
  await student.getByLabel("Страна").selectOption("Канада");
  const card = student.locator(".catcard", { hasText: NAME }).first();
  await expect(card).toBeVisible();
  await expect(card.getByText("Для иностранцев")).toBeVisible();

  // Сохраняем сердечком. Прогон мог оставить её сохранённой с прошлого
  // раза — тогда сначала снимаем: у отметки нет истории, и заново она
  // ставится тем же нажатием
  const unsave = card.getByRole("button", { name: "Убрать из сохранённых" });
  if (await unsave.count()) {
    await unsave.click();
    await expect(card.getByRole("button", { name: "Сохранить стипендию" })).toBeVisible();
  }
  const saveRequest = student.waitForResponse(
    (response) => response.url().includes("/api/scholarships-saved/") && response.request().method() === "POST",
  );
  await card.getByRole("button", { name: "Сохранить стипендию" }).click();
  expect((await saveRequest).status()).toBe(201);

  // она в «Сохранённых»
  await student.getByRole("tab", { name: /Сохранённые/ }).click();
  await expect(student.locator(".catcard", { hasText: NAME }).first()).toBeVisible();

  // и её дедлайн в календаре
  // дедлайн живёт у самой стипендии: он же в календаре. Смотрим список
  // ближайших, а не сетку месяца — срок стоит через год
  await student.goto("/calendar");
  await student.getByRole("tab", { name: "Ближайшие" }).click();
  await expect(student.getByText(`Стипендия: ${NAME}`).first()).toBeVisible();
});

test("подбор называет только записи справочника", async ({ browser }) => {
  const student = await as(browser, "student");
  await student.goto("/scholarships");
  await student.getByRole("tab", { name: "Подобрать под меня" }).click();

  const answer = student.waitForResponse((response) => response.url().includes("/api/scholarships-pick/"));
  await student.getByRole("button", { name: "Подобрать под меня" }).click();
  const payload = (await (await answer).json()) as { picks: { id: number; name: string }[]; note: string };

  const known = (await (await student.request.get("/api/scholarships/?page_size=200")).json()) as {
    results: { id: number }[];
  };
  const ids = new Set(known.results.map((row) => row.id));
  for (const pick of payload.picks) {
    expect(ids.has(pick.id)).toBeTruthy();
  }
  // пустой ответ обязан объясняться словами, а не пустым экраном
  if (payload.picks.length === 0) expect(payload.note.length).toBeGreaterThan(0);
});

test("уборка: стипендия прогона удалена", async ({ browser }) => {
  const director = await as(browser, "director_admission");
  const token = await csrf(director);
  const listing = (await (await director.request.get("/api/scholarships/?page_size=200")).json()) as {
    results: { id: number; name: string }[];
  };
  for (const row of listing.results.filter((item) => item.name === NAME)) {
    const gone = await director.request.delete(`/api/scholarships/${row.id}/`, {
      headers: { "X-CSRFToken": token },
    });
    expect(gone.ok()).toBeTruthy();
  }
});
