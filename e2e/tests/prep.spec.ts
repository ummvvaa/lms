/**
 * Фаза 12: центр подготовки.
 *
 * Приёмка: ученик проходит мок, результат появляется в `ExamAttempt`
 * с источником `platform`, виден на графике динамики и у Кымбат в списке
 * платформенных моков. Текущий балл в `ExamProfile` при этом не меняется.
 */
import { expect, test } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { apiPost, watch } from "../helpers/session";

test.describe("тренировка", () => {
  test.use({ storageState: statePath("student") });

  test("вопросы берутся из банка, разбор объясняет ошибки", async ({
    page,
  }) => {
    const diag = watch(page);
    await page.goto("/prep");
    await expect(page.locator("h1")).toContainText("Центр подготовки");

    const [started] = await Promise.all([
      page.waitForResponse((r) =>
        r.url().includes("/api/prep/practice/start/"),
      ),
      page.getByRole("button", { name: "Начать", exact: true }).click(),
    ]);
    expect(started.status()).toBe(201);

    const session = await started.json();
    expect(session.total).toBeGreaterThan(0);
    // до конца сессии верный ответ не отдаётся
    expect(session.questions[0].correct_option).toBeUndefined();

    await expect(page.locator(".prep__runner")).toBeVisible();

    // отвечаем на все вопросы и завершаем
    for (let i = 0; i < session.total; i += 1) {
      await page.locator(".prep__option").first().click();
      const next = page.getByRole("button", { name: "Дальше →" });
      if (await next.isVisible().catch(() => false)) await next.click();
    }

    const [finished] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/finish/")),
      page
        .getByRole("button", { name: /Завершить и посмотреть разбор/ })
        .click(),
    ]);
    expect(finished.status()).toBe(200);

    await expect(page.locator(".prep__score")).toContainText("из");
    await expect(page.locator(".prep__recommend")).not.toBeEmpty();
    expect(diag.pageErrors).toEqual([]);
  });

  test("пустой банк объясняется, а не выглядит поломкой", async ({ page }) => {
    await page.goto("/prep");
    const response = await apiPost(page, "/api/prep/practice/start/", {
      exam_type: "ACT",
      section: "science",
    }).catch((e) => e);
    expect(String(response)).toMatch(/нет заданий|400/);
  });
});

test.describe("пробный экзамен", () => {
  test("результат виден на графике и у Кымбат, текущий балл не меняется", async ({
    browser,
  }) => {
    test.setTimeout(180_000);

    const studentContext = await browser.newContext({
      storageState: statePath("student"),
    });
    const student = await studentContext.newPage();
    await student.goto("/prep");

    const before = await (
      await student.request.get("/api/students/me/")
    ).json();
    const scoreBefore = before.exam.ielts_current;

    // проходим мок целиком
    const mocks = await (await student.request.get("/api/prep/mocks/")).json();
    const mock = mocks.results.find(
      (m: { exam_type: string }) => m.exam_type === "IELTS",
    );
    expect(mock, "нужен пробный IELTS в справочнике").toBeTruthy();

    const run = await apiPost<{
      id: number;
      run: number;
      questions: { answer_id: number; options: { id: number }[] }[];
    }>(student, `/api/prep/mocks/${mock.id}/start/`, {});
    for (const question of run.questions) {
      await apiPost(student, `/api/prep/practice/${run.id}/answer/`, {
        answer_id: question.answer_id,
        option: question.options[0].id,
      });
    }
    const review = await apiPost<{ score: number; note: string }>(
      student,
      `/api/prep/practice/${run.id}/finish/`,
      { seconds: 120 },
    );
    expect(review.score).not.toBeNull();
    expect(review.note).toContain("не меняет текущий балл");

    // попытка записана с источником platform
    const attempts = await (
      await student.request.get("/api/attempts/?exam_type=IELTS&page_size=200")
    ).json();
    const platform = attempts.results.filter(
      (a: { source: string }) => a.source === "platform",
    );
    expect(platform.length).toBeGreaterThan(0);
    expect(platform[platform.length - 1].attempt_format).toBe("mock");

    // текущий балл в профиле не изменился
    const after = await (await student.request.get("/api/students/me/")).json();
    expect(after.exam.ielts_current).toBe(scoreBefore);

    // и виден на графике динамики
    await student.goto("/prep");
    await expect(student.locator(".trend").first()).toBeVisible();
    await expect(student.locator(".trend").first()).toContainText("IELTS");

    // Кымбат видит его отдельным списком
    const directorContext = await browser.newContext({
      storageState: statePath("director_exam"),
    });
    const director = await directorContext.newPage();
    // список пройденных на платформе живёт на экране «Пробные» (фаза 26: разделы — отдельные экраны)
    await director.goto("/mocks");

    const list = director.locator("#platform-mocks");
    await expect(list).toContainText("Пробные, пройденные на платформе");
    await expect(list).toContainText(before.full_name);
    await expect(
      list.locator('[data-slot="badge"][data-variant="warn"]').first(),
    ).toContainText("ждёт решения");

    await studentContext.close();
    await directorContext.close();
  });

  test("директор решает, учитывать ли балл", async ({ browser }) => {
    test.setTimeout(180_000);

    const studentContext = await browser.newContext({
      storageState: statePath("student"),
    });
    const student = await studentContext.newPage();
    await student.goto("/prep");

    const mocks = await (await student.request.get("/api/prep/mocks/")).json();
    const mock = mocks.results.find(
      (m: { exam_type: string }) => m.exam_type === "IELTS",
    );
    const run = await apiPost<{
      id: number;
      questions: { answer_id: number; options: { id: number }[] }[];
    }>(student, `/api/prep/mocks/${mock.id}/start/`, {});
    for (const question of run.questions) {
      await apiPost(student, `/api/prep/practice/${run.id}/answer/`, {
        answer_id: question.answer_id,
        option: question.options[0].id,
      });
    }
    const review = await apiPost<{ score: number }>(
      student,
      `/api/prep/practice/${run.id}/finish/`,
      {},
    );

    const directorContext = await browser.newContext({
      storageState: statePath("director_exam"),
    });
    const director = await directorContext.newPage();
    // список пройденных на платформе живёт на экране «Пробные» (фаза 26: разделы — отдельные экраны)
    await director.goto("/mocks");

    const list = director.locator("#platform-mocks");
    const [decided] = await Promise.all([
      director.waitForResponse((r) => r.url().includes("/review/")),
      list.getByRole("button", { name: "Учесть в баллах" }).first().click(),
    ]);
    expect(decided.status()).toBe(200);

    // решение доехало до профиля ученика
    // в JSON балл приходит числом, а из профиля — строкой Decimal
    await expect
      .poll(
        async () =>
          Number(
            (await (await student.request.get("/api/students/me/")).json()).exam
              .ielts_current,
          ),
        { timeout: 10_000 },
      )
      .toBe(Number(review.score));

    await studentContext.close();
    await directorContext.close();
  });

  test("слабые темы превращаются в задачи роадмапа", async ({ page }) => {
    test.setTimeout(120_000);
    const context = await page
      .context()
      .browser()!
      .newContext({ storageState: statePath("student") });
    const student = await context.newPage();
    await student.goto("/prep");

    const mocks = await (await student.request.get("/api/prep/mocks/")).json();
    const mock = mocks.results[0];
    const run = await apiPost<{
      id: number;
      questions: { answer_id: number; options: { id: number }[] }[];
    }>(student, `/api/prep/mocks/${mock.id}/start/`, {});
    for (const question of run.questions) {
      await apiPost(student, `/api/prep/practice/${run.id}/answer/`, {
        answer_id: question.answer_id,
        option: question.options[question.options.length - 1].id,
      });
    }
    await apiPost(student, `/api/prep/practice/${run.id}/finish/`, {});

    const tasks = await (await student.request.get("/api/tasks/my/")).json();
    expect(
      tasks.some((t: { title: string }) => t.title.includes("Подтянуть тему")),
    ).toBe(true);
    await context.close();
  });
});

test.describe("банк заданий", () => {
  test.use({ storageState: statePath("director_exam") });

  test("академический директор видит состав банка", async ({ page }) => {
    await page.goto("/dashboard");
    const bank = await (await page.request.get("/api/prep/bank/")).json();
    expect(bank.total).toBeGreaterThan(0);
    expect(bank.rows.length).toBeGreaterThan(0);
  });

  test("чужой директор банк не ведёт", async ({ browser }) => {
    const context = await browser.newContext({
      storageState: statePath("director_sport"),
    });
    const page = await context.newPage();
    await page.goto("/dashboard");

    const denied = await apiPost(page, "/api/prep/questions/", {
      exam_type: "IELTS",
      section: "reading",
      topic: "Чужая тема",
      text: "Вопрос",
    }).catch((e) => String(e));
    expect(String(denied)).toContain("403");
    await context.close();
  });
});
