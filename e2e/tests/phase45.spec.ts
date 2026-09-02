/**
 * Фаза 45 — ресурсы и профтест.
 *
 * Директор пишет памятку, ученик находит её по категории, читает
 * и отмечает прочитанной. Профтест: анкета ведётся справочником,
 * разбор называет только программы справочника, а без ключа модели
 * экран честно говорит, что раздел недоступен.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";

test.describe.configure({ mode: "serial", timeout: 240_000 });

const TITLE = "Probe Browser Guide";

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

test("директор пишет памятку с экрана", async ({ browser }) => {
  const director = await as(browser, "director_exam");
  await director.goto("/resources");
  await expect(
    director.getByRole("heading", { name: /Ресурсы/ }),
  ).toBeVisible();

  await director
    .getByRole("button", { name: "Добавить материал" })
    .first()
    .click();
  await director.getByLabel("Заголовок", { exact: true }).fill(TITLE);
  await director.getByLabel("Категория").selectOption({ label: "Подготовка" });
  await director
    .getByLabel("Короткое описание")
    .fill("Как готовиться к пробному экзамену");
  await director
    .getByLabel("Текст материала")
    .fill("Первый абзац памятки.\nВторой абзац памятки.");
  await director.getByLabel("Метки через запятую").fill("пробник, подготовка");
  await director.getByRole("button", { name: "Опубликовать" }).click();

  await expect(director.getByText(TITLE).first()).toBeVisible();
});

test("ученик находит памятку по категории, читает и отмечает прочитанной", async ({
  browser,
}) => {
  const student = await as(browser, "student");
  await student.goto("/resources");
  // с фазы 48 категории — ряд чипов-переключателей, а карточка ведёт
  // на материал ссылкой «Читать» внизу
  await student
    .locator(".segrow")
    .getByRole("button", { name: /^Подготовка/ })
    .click();

  const card = student.locator(".catcard", { hasText: TITLE }).first();
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Читать" }).click();

  // материал открылся своим адресом
  await expect(student).toHaveURL(/\/resources\/\d+$/);
  await expect(student.getByText("Первый абзац памятки.")).toBeVisible();

  const marked = student.waitForResponse(
    (response) =>
      response.url().includes("/read/") &&
      response.request().method() === "POST",
  );
  await student.getByRole("button", { name: "Прочитано" }).click();
  expect((await marked).status()).toBe(200);
  await expect(
    student.getByRole("button", { name: "Снять отметку" }),
  ).toBeVisible();
});

test("директор школы ведёт анкету профтеста", async ({ browser }) => {
  const director = await as(browser, "director_behavior");
  await director.goto("/career-questions");
  await expect(
    director.getByRole("heading", { name: "Вопросы профтеста" }),
  ).toBeVisible();
  // шесть посеянных вопросов на экране
  await expect(
    director.getByText("Какие школьные предметы вам нравятся больше всего?"),
  ).toBeVisible();
});

test("ученик проходит анкету: разбор из справочника либо честное «недоступно»", async ({
  browser,
}) => {
  const student = await as(browser, "student");
  await student.goto("/career");
  await expect(
    student.getByRole("heading", { name: "Профтест", exact: true }),
  ).toBeVisible();

  const state = (await (await student.request.get("/api/career/")).json()) as {
    available: boolean;
    detail: string;
    questions: { code: string }[];
  };

  if (!state.available) {
    // без ключа модели раздел не притворяется работающим
    await expect(student.getByText("Профтест сейчас недоступен")).toBeVisible();
    expect(state.detail.length).toBeGreaterThan(0);
    return;
  }

  // с фазы 48 вопрос отвечается нажатиями по вариантам, а не текстом
  const question = student
    .locator(".career__q", {
      hasText: "Какие школьные предметы вам нравятся больше всего?",
    })
    .first();
  await question
    .getByRole("button", { name: "Математика", exact: true })
    .click();
  await question.getByRole("button", { name: "Физика", exact: true }).click();
  const answer = student.waitForResponse((response) =>
    response.url().includes("/api/career/run/"),
  );
  await student.getByRole("button", { name: "Получить разбор" }).click();
  const response = await answer;

  if (response.status() === 503) {
    await expect(student.getByText(/недоступен|Модель/).first()).toBeVisible();
    return;
  }
  expect(response.status()).toBe(201);
  const run = (await response.json()) as {
    directions: { title: string; programs: { id: number }[] }[];
  };
  expect(run.directions.length).toBeGreaterThan(0);

  // все названные программы есть в справочнике (инвариант №10)
  const catalog = (await (
    await student.request.get("/api/programs/?page_size=500")
  ).json()) as {
    results: { id: number }[];
  };
  const known = new Set(catalog.results.map((row) => row.id));
  for (const direction of run.directions) {
    for (const program of direction.programs)
      expect(known.has(program.id)).toBeTruthy();
  }
});

test("уборка: памятка прогона удалена", async ({ browser }) => {
  const director = await as(browser, "director_exam");
  const token = await csrf(director);
  const listing = (await (
    await director.request.get("/api/resources/?page_size=200")
  ).json()) as {
    results: { id: number; title: string }[];
  };
  for (const row of listing.results.filter((item) => item.title === TITLE)) {
    const gone = await director.request.delete(`/api/resources/${row.id}/`, {
      headers: { "X-CSRFToken": token },
    });
    expect(gone.ok()).toBeTruthy();
  }
});
