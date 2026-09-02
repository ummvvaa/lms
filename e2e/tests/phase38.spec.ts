/**
 * Фаза 38 — портфолио.
 *
 * Ученик добавляет достижение с файлом — оно уходит в очередь директора
 * талантов и после подтверждения видно в портфолио. Соревнование уходит
 * директору спорта, не Арману. Документ не открывается без входа.
 * Процент заполнения растёт по мере внесения. CV выгружается с данными.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";

test.describe.configure({ mode: "serial", timeout: 180_000 });

const PDF = Buffer.from(
  "%PDF-1.4\n%probe\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n",
);

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

const stamp = Date.now();
const ACHIEVEMENT = `Хакатон прогона ${stamp}`;
const COMPETITION = `Кубок прогона ${stamp}`;

let percentBefore = 0;
let documentId = 0;

test("портфолио открывается: вкладки, процент, чек-лист документов", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  percentBefore = (
    (await (await page.request.get("/api/portfolio/")).json()) as {
      percent: number;
    }
  ).percent;

  await page.goto("/my-data");
  await expect(
    page.getByRole("heading", { name: "Портфолио", exact: true }),
  ).toBeVisible();
  for (const tab of [
    "Обзор",
    "Достижения",
    "Документы",
    "Спорт",
    "Олимпиады",
    "CV",
  ]) {
    await expect(page.getByRole("tab", { name: tab })).toBeVisible();
  }
  // с фазы 49 процент стоит в карточке заполненности справа: слева —
  // то, что ученик вносит, справа — то, по чему он себя сверяет
  await expect(page.locator(".portfolio__two")).toBeVisible();
  await expect(page.getByText(/Заполнено на \d+%/)).toBeVisible();
});

test("достижение с файлом уходит на проверку и помечается «ждёт проверки»", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  await page.goto("/my-data");
  await page.getByRole("tab", { name: "Достижения" }).click();
  await page.getByRole("button", { name: "Добавить достижение" }).click();

  const card = page.locator("section", { hasText: "Достижения" }).first();
  await card
    .locator("label", { hasText: "Название активности" })
    .locator("input")
    .fill(ACHIEVEMENT);
  await card
    .locator("label", { hasText: "Категория активности" })
    .locator("select")
    .selectOption("project");
  await card.locator('input[type="file"]').setInputFiles({
    name: "diploma.pdf",
    mimeType: "application/pdf",
    buffer: PDF,
  });

  const [upload, propose] = await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().includes("/api/documents/") && r.request().method() === "POST",
    ),
    page.waitForResponse((r) => r.url().includes("/api/suggestions/propose/")),
    card.getByRole("button", { name: "Отправить на проверку" }).click(),
  ]);
  expect(upload.status()).toBe(201);
  expect(propose.status()).toBe(201);
  documentId = ((await upload.json()) as { id: number }).id;

  await expect(card.getByText(ACHIEVEMENT)).toBeVisible();
  await expect(card.getByText("ждёт проверки").first()).toBeVisible();
});

test("файл документа не открывается без входа", async ({ browser }) => {
  const anonymous = await browser.newContext();
  const response = await anonymous.request.get(
    `/api/documents/${documentId}/file/`,
    {
      maxRedirects: 0,
    },
  );
  expect([301, 302, 401, 403]).toContain(response.status());

  const owner = await as(browser, "student");
  const own = await owner.request.get(`/api/documents/${documentId}/file/`);
  expect(own.status()).toBe(200);
});

test("соревнование уходит директору спорта, а достижение — Арману", async ({
  browser,
}) => {
  const student = await as(browser, "student");
  await student.goto("/my-data");
  await student.getByRole("tab", { name: "Спорт" }).click();
  await student.getByRole("button", { name: "Добавить соревнование" }).click();
  const card = student
    .locator("section", { hasText: "Спортивные соревнования" })
    .first();
  await card
    .locator("label", { hasText: "Название соревнования" })
    .locator("input")
    .fill(COMPETITION);
  const [propose] = await Promise.all([
    student.waitForResponse((r) =>
      r.url().includes("/api/suggestions/propose/"),
    ),
    card.getByRole("button", { name: "Отправить на проверку" }).click(),
  ]);
  expect(propose.status()).toBe(201);

  const sport = await as(browser, "director_sport");
  await sport.goto("/suggestions");
  await expect(
    sport.locator("#student-queue").getByText(COMPETITION),
  ).toBeVisible();
  await expect(
    sport.locator("#student-queue").getByText(ACHIEVEMENT),
  ).toHaveCount(0);

  const arman = await as(browser, "director_talent");
  await arman.goto("/suggestions");
  const queue = arman.locator("#student-queue");
  await expect(queue.getByText(ACHIEVEMENT)).toBeVisible();
  await expect(queue.getByText(COMPETITION)).toHaveCount(0);

  // Арман подтверждает — достижение становится записью
  const row = queue.locator(".squeue__row", { hasText: ACHIEVEMENT }).first();
  const [review] = await Promise.all([
    arman.waitForResponse((r) => r.url().includes("/review/")),
    row.getByRole("button", { name: "Подтвердить", exact: true }).click(),
  ]);
  expect(review.status()).toBe(200);
});

test("подтверждённое достижение видно в портфолио, процент вырос", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  await page.goto("/my-data");
  await page.getByRole("tab", { name: "Достижения" }).click();
  const card = page.locator("section", { hasText: "Достижения" }).first();
  await expect(card.getByText(ACHIEVEMENT)).toBeVisible();

  // карточка ученика переживает уборку прогона, и раздел мог быть заполнен
  // прошлым запуском — поэтому «растёт» здесь значит «не ниже и раздел полон»
  const state = (await (await page.request.get("/api/portfolio/")).json()) as {
    percent: number;
    sections: { code: string; value: number }[];
  };
  expect(state.percent).toBeGreaterThanOrEqual(percentBefore);
  expect(state.sections.find((s) => s.code === "achievements")?.value).toBe(
    100,
  );
});

test("документ из чек-листа и экспорт CV", async ({ browser }) => {
  const page = await as(browser, "student");
  await page.goto("/my-data");
  await page.getByRole("tab", { name: "Документы" }).click();

  await page.locator('input[type="file"]').setInputFiles({
    name: "attestat.pdf",
    mimeType: "application/pdf",
    buffer: PDF,
  });
  const [upload] = await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().includes("/api/documents/") && r.request().method() === "POST",
    ),
    page.getByRole("button", { name: "Загрузить", exact: true }).click(),
  ]);
  expect(upload.status()).toBe(201);
  await expect(page.getByText("✓ Аттестат")).toBeVisible();

  const cv = await page.request.get("/api/portfolio/cv/");
  expect(cv.status()).toBe(200);
  const html = await cv.text();
  expect(html).toContain(ACHIEVEMENT);
});
