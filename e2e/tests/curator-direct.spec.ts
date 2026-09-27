/**
 * Куратор вносит данные ученика напрямую — в живом браузере.
 *
 * Рядом с путём «ученик вносит — куратор подтверждает» стоит второй:
 * куратор вносит сам, по своим группам, и значение сразу настоящее.
 *
 * 1. Карточка под куратором: внести балл, поставить цель, добавить
 *    достижение и вуз, загрузить документ — каждое действие уходит запросом,
 *    отвечает 2xx, строка подписана «внёс куратор».
 * 2. Ученик видит «внёс куратор» у себя; его висящее предложение по тому же
 *    полю закрыто как «куратор внёс за вас», а не отклонено.
 * 3. «Убрать» — с подтверждением, где названо, что уходит; запись в архиве.
 * 4. Мастера импорта у куратора нет: пункта меню нет, `/import` уводит на
 *    главную, API мастера отвечает 404 — файлы грузят администратор и Кымбат.
 *
 * Сценарий убирает за собой: соседние сценарии ходят по тому же ученику.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import {
  expect,
  test,
  type Browser,
  type Locator,
  type Page,
} from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { apiPost, watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

const stamp = Date.now();
const ACHIEVEMENT = `Волонтёр форума ${stamp}`;
const PDF = Buffer.from(
  "%PDF-1.4\n%probe\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n",
);
const TABLE = readFileSync(
  path.join(__dirname, "..", "fixtures", "admission-table.xlsx"),
);
const XLSX =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

let studentId = 0;
let documentId = 0;

interface GoalSnapshot {
  id: number;
  exam_name: string;
  target_score: string | null;
  exam_date: string | null;
}
let satGoalBefore: GoalSnapshot | null = null;

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  await page.addInitScript(() =>
    window.localStorage.setItem("first-run-seen", "1"),
  );
  return page;
}

async function csrf(page: Page): Promise<string> {
  return (
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? ""
  );
}

/** Секция строк по заголовку карточки. */
const section = (page: Page, title: string): Locator =>
  page
    .locator(".datacard")
    .filter({ has: page.locator(".datacard__title", { hasText: title }) })
    .first();

/** Поле формы строки по подписи. */
const field = (scope: Locator, label: string): Locator =>
  scope
    .locator(".rowform__field")
    .filter({
      has: scope.page().locator(".rowform__label", { hasText: label }),
    })
    .first();

test.beforeAll(async ({ browser }) => {
  const student = await as(browser, "student");
  const me = await (await student.request.get("/api/students/me/")).json();
  studentId = me.id;
  expect(studentId, "карточка ученика прогона").toBeGreaterThan(0);
  await student.context().close();
});

test("куратор вносит балл, цель, достижение, вуз и документ — сразу настоящие", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);

  // --- экзамены: «Внести балл» — официальная попытка с датой
  await page.goto(`/students/${studentId}?tab=exams`);
  const attempts = section(page, "Попытки: официальные и пробники");
  await expect(attempts).toBeVisible();
  await attempts.getByRole("button", { name: "Внести балл" }).click();
  await field(attempts, "Экзамен").locator("select").selectOption("SAT");
  await field(attempts, "Дата сдачи").locator("input").fill("2025-03-08");
  await field(attempts, "Общий балл").locator("input").fill("1380");
  const attemptSaved = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/attempts/") && r.request().method() === "POST",
  );
  await attempts.getByRole("button", { name: "Добавить", exact: true }).click();
  expect((await attemptSaved).status()).toBe(201);
  const attemptRow = attempts
    .locator(".rows__item")
    .filter({ hasText: "SAT 1380" })
    .first();
  await expect(attemptRow).toContainText("официальный");
  await expect(attemptRow).toContainText("внёс куратор");

  // прежняя цель SAT запоминается: по дате экзамена строится календарь ученика,
  // и соседние сценарии считают его события — в конце файла цель возвращается
  const goalsBefore = (await (
    await page.request.get(`/api/exam-goals/?student=${studentId}`)
  ).json()) as { results: GoalSnapshot[] };
  satGoalBefore =
    goalsBefore.results.find((row) => row.exam_name === "SAT") ?? null;

  // --- цель с датой экзамена: цель по экзамену у ученика одна, поэтому
  // существующую куратор правит через «Изменить», а новой ставит «Поставить цель»
  const goals = section(page, "Цели и даты экзаменов");
  const existing = goals.locator(".rows__item").filter({ hasText: "SAT" });
  const goalSaved = page.waitForResponse(
    (r) =>
      r.url().includes("/api/exam-goals/") &&
      ["POST", "PATCH"].includes(r.request().method()),
  );
  if ((await existing.count()) > 0) {
    await existing.first().locator(".rowmenu__button").click();
    await page.getByRole("menuitem", { name: "Изменить" }).click();
    await field(goals, "Целевой балл").locator("input").fill("1500");
    await field(goals, "Дата экзамена").locator("input").fill("2026-12-05");
    await goals.getByRole("button", { name: "Сохранить" }).click();
  } else {
    await goals.getByRole("button", { name: "Поставить цель" }).click();
    await field(goals, "Экзамен")
      .locator("select")
      .selectOption({ label: "SAT" });
    await field(goals, "Целевой балл").locator("input").fill("1500");
    await field(goals, "Дата экзамена").locator("input").fill("2026-12-05");
    await goals.getByRole("button", { name: "Добавить", exact: true }).click();
  }
  expect([200, 201]).toContain((await goalSaved).status());
  await expect(
    goals.locator(".rows__item").filter({ hasText: "SAT" }).first(),
  ).toContainText("внёс куратор");

  // --- портфолио: достижение той же формой, что у директора талантов
  await page.goto(`/students/${studentId}?tab=portfolio`);
  const achievements = section(page, "Достижения и олимпиады");
  await achievements
    .getByRole("button", { name: "Добавить", exact: true })
    .click();
  await field(achievements, "Категория")
    .locator("select")
    .selectOption({ index: 0 });
  await field(achievements, "Название").locator("input").fill(ACHIEVEMENT);
  const activitySaved = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/activities/") && r.request().method() === "POST",
  );
  await achievements
    .locator(".rowform__actions")
    .getByRole("button", { name: "Добавить" })
    .click();
  expect((await activitySaved).status()).toBe(201);
  await expect(
    achievements.locator(".rows__item").filter({ hasText: ACHIEVEMENT }),
  ).toContainText("внёс куратор");

  // --- документы: «Загрузить» — файл ложится сразу подтверждённым
  await page.goto(`/students/${studentId}?tab=documents`);
  const recommendation = page
    .locator(".rowline")
    .filter({ hasText: "Рекомендат" })
    .first();
  await expect(recommendation).toBeVisible();
  await recommendation
    .getByRole("button", { name: /Загрузить|Заменить/ })
    .click();
  await page.locator('.modal__box input[type="file"]').first().setInputFiles({
    name: "recommendation.pdf",
    mimeType: "application/pdf",
    buffer: PDF,
  });
  const uploaded = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/documents/") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Загрузить", exact: true })
    .last()
    .click();
  const answer = await uploaded;
  expect(answer.status(), await answer.text()).toBe(201);
  const body = (await answer.json()) as {
    id: number;
    status: string;
    entered_by_curator: boolean;
  };
  documentId = body.id;
  expect([body.status, body.entered_by_curator]).toEqual(["confirmed", true]);
  await expect(recommendation).toContainText("внёс куратор");
  await expect(recommendation).toContainText(/подтвержд/i);

  // после перезагрузки всё на месте — значения настоящие, а не локальные
  await page.reload();
  await expect(
    page.locator(".rowline").filter({ hasText: "Рекомендат" }).first(),
  ).toContainText("внёс куратор");

  expect(diag.pageErrors, "исключения").toEqual([]);
  expect(diag.consoleErrors, "ошибки консоли").toEqual([]);
  await page.context().close();
});

test("вузы: куратор добавляет из каталога, ставит приоритет и убирает с подтверждением", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto(`/students/${studentId}?tab=unis`);

  const picker = page.locator(".rows__picker select");
  await expect(picker).toBeVisible();
  // первый вуз каталога, у которого есть программа
  const options = await picker.locator("option").allInnerTexts();
  expect(
    options.length,
    "в каталоге есть вузы (seed_universities)",
  ).toBeGreaterThan(1);
  const list = section(page, "Список вузов");
  let added = false;
  // программы, которые уже стоят в списке ученика, пропускаем: сервер ответил бы
  // «уже в списке», а соседние сценарии прогона кладут туда свои
  const taken = await list.locator(".rows__label").allInnerTexts();
  for (
    let index = 1;
    index < Math.min(options.length, 10) && !added;
    index += 1
  ) {
    await picker.selectOption({ index });
    await list.getByRole("button", { name: "Добавить из каталога" }).click();
    const program = field(list, "Программа").locator("select");
    await expect(program).toBeVisible();
    await page.waitForTimeout(500);
    const titles = await program.locator("option").allInnerTexts();
    const free = titles.findIndex(
      (title) => title && !taken.some((row) => row.includes(title)),
    );
    if (free < 0) {
      await list.getByRole("button", { name: "Отмена" }).first().click();
      continue;
    }
    await program.selectOption({ index: free });
    const saved = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/catalog/add/") &&
        r.request().method() === "POST",
    );
    await list
      .locator(".rowform__actions")
      .getByRole("button", { name: "Добавить" })
      .click();
    // форма закрывается сама при любом ответе — отказ сервер называет тостом
    added = (await saved).status() === 201;
  }
  expect(added, "программа добавлена в список ученика").toBe(true);

  const row = list
    .locator(".rows__item")
    .filter({ hasText: "внёс куратор" })
    .first();
  await expect(row).toBeVisible();

  // приоритетный — из меню строки
  await row.locator(".rowmenu__button").click();
  const prioritized = page.waitForResponse((r) =>
    r.url().includes("/api/catalog/priority/"),
  );
  await page.getByRole("menuitem", { name: "Сделать приоритетным" }).click();
  expect((await prioritized).status()).toBe(200);
  await expect(
    list.locator(".rows__item").filter({ hasText: "приоритетный" }),
  ).toHaveCount(1);

  // «Убрать» — с подтверждением, где названо, что уходит; строка уходит в архив
  const mine = list
    .locator(".rows__item")
    .filter({ hasText: "внёс куратор" })
    .first();
  const title = ((await mine.locator(".rows__label").innerText()) || "").split(
    " — ",
  )[0];
  await mine.locator(".rowmenu__button").click();
  await page
    .getByRole("menuitem")
    .filter({ hasText: /Удалить|Убрать/ })
    .click();
  const confirm = page.locator(".confirm");
  await expect(confirm).toBeVisible();
  await expect(confirm, "в подтверждении названо, что удаляется").toContainText(
    title.slice(0, 12),
  );
  const removed = page.waitForResponse(
    (r) =>
      r.url().includes("/api/student-universities/") &&
      r.request().method() === "DELETE",
  );
  await confirm
    .getByRole("button", { name: /Удалить|Убрать/ })
    .last()
    .click();
  expect((await removed).status()).toBe(200);
  await expect(
    list.locator(".rows__item").filter({ hasText: "внёс куратор" }),
  ).toHaveCount(0);

  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("ученик видит «внёс куратор», а его предложение перекрыто, не отклонено", async ({
  browser,
}) => {
  // ученик предлагает GPA — строка ждёт решения
  const student = await as(browser, "student");
  await apiPost(student, "/api/suggestions/propose/", {
    rows: [{ model: "students.ExamProfile", field: "gpa", value: "3.1" }],
  });

  // куратор вносит GPA сам — карандашом в блоке «Поступление»
  const curator = await as(browser, "curator");
  const diag = watch(curator);
  await curator.goto(`/students/${studentId}`);
  const gpa = curator
    .locator(".cadm__pair")
    .filter({ has: curator.locator(".cadm__k", { hasText: "Средний GPA" }) })
    .first();
  await gpa.getByRole("button", { name: "Изменить" }).click();
  await gpa.getByRole("textbox").fill("4.2");
  const saved = curator.waitForResponse(
    (r) =>
      r.url().includes(`/api/profiles/exam/${studentId}/`) &&
      r.request().method() === "PATCH",
  );
  await gpa.getByRole("button", { name: "Сохранить" }).click();
  expect((await saved).status()).toBe(200);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await curator.context().close();

  // ученик: значение с подписью, предложение — «куратор внёс за вас»
  const mine = (await (
    await student.request.get("/api/suggestions/mine/")
  ).json()) as {
    results: {
      status: string;
      reject_reason: string;
      changes: { field: string; superseded_value: string }[];
    }[];
  };
  const closed = mine.results.find(
    (row) =>
      row.status === "superseded" && row.changes.some((c) => c.field === "gpa"),
  );
  expect(closed, "предложение перекрыто записью куратора").toBeTruthy();
  expect(closed!.reject_reason, "причины отказа нет — это не отклонение").toBe(
    "",
  );
  expect(Number(closed!.changes[0].superseded_value)).toBe(4.2);

  await student.goto("/my-data");
  await expect(student.getByText("Куратор внёс за вас")).toBeVisible();
  await expect(
    student.getByText("куратор внёс значение").first(),
  ).toBeVisible();
  await expect(student.getByText("внёс куратор").first()).toBeVisible();
  // имени куратора ученик не видит нигде
  await expect(student.locator("body")).not.toContainText("Асель Прогон");
  await student.context().close();
});

test("«Убрать» у попытки — с подтверждением; уборка за сценарием", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  await page.goto(`/students/${studentId}?tab=exams`);
  const attempts = section(page, "Попытки: официальные и пробники");
  const row = attempts
    .locator(".rows__item")
    .filter({ hasText: "SAT 1380" })
    .first();
  await expect(row).toBeVisible();
  // оборванный запуск мог оставить такие же попытки — считаем от того, что есть
  const before = await attempts
    .locator(".rows__item")
    .filter({ hasText: "SAT 1380" })
    .count();
  await row.locator(".rowmenu__button").click();
  await page
    .getByRole("menuitem")
    .filter({ hasText: /Удалить|Убрать/ })
    .click();
  const confirm = page.locator(".confirm");
  await expect(confirm).toContainText("SAT");
  const removed = page.waitForResponse(
    (r) =>
      r.url().includes("/api/attempts/") && r.request().method() === "DELETE",
  );
  await confirm
    .getByRole("button", { name: /Удалить|Убрать/ })
    .last()
    .click();
  const answer = await removed;
  expect(answer.status()).toBe(200);
  expect(((await answer.json()) as { detail: string }).detail).toContain(
    "в архиве",
  );
  await expect(
    attempts.locator(".rows__item").filter({ hasText: "SAT 1380" }),
  ).toHaveCount(before - 1);

  // достижение — тем же путём, запросом: соседям по прогону оно не нужно
  const token = await csrf(page);
  // остатки оборванных запусков этого же сценария — туда же, в архив
  const stale = (await (
    await page.request.get(
      `/api/attempts/?student=${studentId}&exam_type=SAT&page_size=200`,
    )
  ).json()) as { results: { id: number; date: string; total_score: string }[] };
  for (const item of stale.results.filter(
    (a) => a.date === "2025-03-08" && Number(a.total_score) === 1380,
  )) {
    await page.request.delete(`/api/attempts/${item.id}/`, {
      headers: { "X-CSRFToken": token },
    });
  }
  const activities = (await (
    await page.request.get(
      `/api/activities/?student=${studentId}&page_size=200`,
    )
  ).json()) as { results: { id: number; title: string }[] };
  for (const item of activities.results.filter((a) =>
    a.title.startsWith("Волонтёр форума "),
  )) {
    const gone = await page.request.delete(`/api/activities/${item.id}/`, {
      headers: { "X-CSRFToken": token },
    });
    expect(gone.status()).toBe(200);
  }
  // цель SAT — как была до сценария: прежние значения или, если её не было, в архив
  const goalsNow = (await (
    await page.request.get(`/api/exam-goals/?student=${studentId}`)
  ).json()) as { results: GoalSnapshot[] };
  const satGoal = goalsNow.results.find((row) => row.exam_name === "SAT");
  if (satGoal && satGoalBefore) {
    await page.request.patch(`/api/exam-goals/${satGoal.id}/`, {
      data: {
        target_score: satGoalBefore.target_score,
        exam_date: satGoalBefore.exam_date,
      },
      headers: { "X-CSRFToken": token },
    });
  } else if (satGoal) {
    await page.request.delete(`/api/exam-goals/${satGoal.id}/`, {
      headers: { "X-CSRFToken": token },
    });
  }

  // документ куратор удалить не может — это исключение из «убрать всё, что внёс»
  const refused = await page.request.delete(`/api/documents/${documentId}/`, {
    headers: { "X-CSRFToken": token },
  });
  expect(refused.status()).toBe(403);
  await page.context().close();

  // свой документ убирает ученик — чтобы чек-лист соседних сценариев не поехал
  const student = await as(browser, "student");
  const mineToken = await csrf(student);
  const dropped = await student.request.delete(
    `/api/documents/${documentId}/`,
    {
      headers: { "X-CSRFToken": mineToken },
    },
  );
  expect(dropped.ok()).toBe(true);
  await student.context().close();
});

test("мастера импорта у куратора нет: ни пункта меню, ни экрана, ни API", async ({
  browser,
}) => {
  // файлы грузят администратор и академический директор; куратор вносит
  // руками — поэтому мастер для него не «запрещён», а не существует: 404
  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/dashboard");
  const nav = page.locator("nav.shell__menu");
  await expect(
    nav.getByRole("link", { name: "Главная", exact: true }),
  ).toBeVisible();
  await expect(
    nav.getByRole("link", { name: "Импорт", exact: true }),
  ).toHaveCount(0);

  // прямой адрес уводит на главную
  await page.goto("/import");
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 });

  // API мастера: и чтение истории, и разбор файла — 404
  const history = await page.request.get("/api/admission-imports/");
  expect(history.status(), "история загрузок").toBe(404);
  const token = await csrf(page);
  const refused = await page.request.post("/api/admission-imports/preview/", {
    multipart: {
      file: {
        name: "admission-table.xlsx",
        mimeType: XLSX,
        buffer: TABLE,
      },
    },
    headers: { "X-CSRFToken": token },
  });
  expect(refused.status(), "разбор файла").toBe(404);

  expect(diag.pageErrors, "исключения").toEqual([]);
  expect(diag.consoleErrors, "ошибки консоли").toEqual([]);
  await page.context().close();
});
