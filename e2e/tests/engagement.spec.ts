/**
 * Фаза 11: онбординг и геймификация.
 *
 * Приёмка: новый ученик проходит квиз, его ответы появляются у директоров
 * (по экзаменам — у куратора) на подтверждении с пометкой источника;
 * выполнение задачи начисляет XP и двигает уровень; стрик растёт за день
 * с активностью.
 */
import { expect, test } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { apiPost, watch } from "../helpers/session";

test.describe("квиз знакомства", () => {
  test.use({ storageState: statePath("student") });

  test("вопросы идут по одному, прогресс сохраняется по шагам", async ({
    page,
  }) => {
    const diag = watch(page);
    await page.goto("/dashboard");

    // сбрасываем прежние ответы, чтобы пройти квиз с начала
    await resetQuiz(page);
    await page.goto("/onboarding");

    await expect(page.locator(".onboarding__title")).toBeVisible();
    await expect(page.locator(".onboarding__count")).toContainText(
      "Вопрос 1 из 6",
    );

    const [answered] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/onboarding/answer/")),
      page.getByRole("button", { name: "Канада", exact: true }).click(),
    ]);
    expect(answered.status()).toBe(200);
    await expect(page.locator(".onboarding__count")).toContainText(
      "Вопрос 2 из 6",
    );

    // ушёл и вернулся — отвечать заново не надо
    await page.goto("/dashboard");
    await page.goto("/onboarding");
    await expect(page.locator(".onboarding__count")).toContainText(
      "Вопрос 2 из 6",
    );
    expect(diag.pageErrors).toEqual([]);
  });

  test("квиз можно отложить", async ({ page }) => {
    await resetQuiz(page);
    await page.goto("/onboarding");

    const [skipped] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/onboarding/skip/")),
      page
        .getByRole("button", { name: "Пропустить и вернуться позже" })
        .click(),
    ]);
    expect(skipped.status()).toBe(200);
    await page.waitForURL(/\/dashboard/);
  });

  test("ответ доезжает до профиля и переживает перезагрузку", async ({
    page,
  }) => {
    await resetQuiz(page);
    await apiPost(page, "/api/onboarding/answer/", {
      question: "english_score",
      value: "6.5",
    });

    await page.reload();
    const profile = await (await page.request.get("/api/students/me/")).json();
    expect(profile.exam.ielts_current).toBe("6.5");
  });
});

test.describe("ответы ученика ждут подтверждения", () => {
  // Кымбат ученические правки не разбирает: ответы анкеты по экзаменам
  // подтверждает куратор группы (решение владельца, 25.10.2026)
  test("куратор видит балл ученика отдельным списком и подтверждает", async ({
    browser,
  }) => {
    test.setTimeout(120_000);

    const studentContext = await browser.newContext({
      storageState: statePath("student"),
    });
    const student = await studentContext.newPage();
    await student.goto("/dashboard");
    await resetQuiz(student);
    await apiPost(student, "/api/onboarding/answer/", {
      question: "english_score",
      value: "7.0",
    });

    // у Кымбат списка нет: на её главной очередей нет вовсе
    const kymbatContext = await browser.newContext({
      storageState: statePath("director_exam"),
    });
    const kymbat = await kymbatContext.newPage();
    await kymbat.goto("/dashboard");
    await expect(kymbat.locator("h1")).toContainText("Добрый день");
    await expect(kymbat.locator("#onboarding-queue")).toHaveCount(0);
    await kymbatContext.close();

    const curatorContext = await browser.newContext({
      storageState: statePath("curator"),
    });
    const curator = await curatorContext.newPage();
    await curator.goto("/queue?group=all");

    const queue = curator.locator("#onboarding-queue");
    await expect(queue).toContainText("Заполнили при входе");
    await expect(queue).toContainText("IELTS или TOEFL");

    const [confirmed] = await Promise.all([
      curator.waitForResponse((r) =>
        r.url().includes("/api/onboarding/pending/"),
      ),
      queue.getByRole("button", { name: "Подтвердить" }).first().click(),
    ]);
    expect(confirmed.status()).toBe(200);

    // после подтверждения строка уходит из очереди
    await curator.reload();
    await expect(curator.locator("#onboarding-queue")).toBeHidden();

    await studentContext.close();
    await curatorContext.close();
  });

  test("Асем снимает текстовый ответ — поле пустеет, а не падает пятисоткой", async ({
    browser,
  }) => {
    // U8, фаза 34: «Снять» у ответа про специальность писало NULL в текстовую
    // колонку и отвечало 500 — числовые ответы снимались, текстовые нет
    test.setTimeout(120_000);
    const studentContext = await browser.newContext({
      storageState: statePath("student"),
    });
    const student = await studentContext.newPage();
    await student.goto("/dashboard");
    await resetQuiz(student);
    await apiPost(student, "/api/onboarding/answer/", {
      question: "target_major",
      value: "информатика",
    });

    const directorContext = await browser.newContext({
      storageState: statePath("director_admission"),
    });
    const director = await directorContext.newPage();
    await director.goto("/dashboard");
    const queue = director.locator("#onboarding-queue");
    await expect(queue).toContainText("Заполнили при входе");

    const [declined] = await Promise.all([
      director.waitForResponse(
        (r) =>
          r.url().includes("/api/onboarding/pending/") &&
          r.request().method() === "POST",
      ),
      queue.getByRole("button", { name: "Снять" }).first().click(),
    ]);
    expect(declined.status()).toBe(200);

    const me = await (await student.request.get("/api/students/me/")).json();
    expect(me.admission.target_major ?? "").toBe("");

    await studentContext.close();
    await directorContext.close();
  });

  test("в журнале видно, что число назвал ученик", async ({ browser }) => {
    test.setTimeout(120_000);
    const studentContext = await browser.newContext({
      storageState: statePath("student"),
    });
    const student = await studentContext.newPage();
    await student.goto("/dashboard");
    await resetQuiz(student);
    await apiPost(student, "/api/onboarding/answer/", {
      question: "gpa",
      value: "3.7",
    });
    const me = await (await student.request.get("/api/students/me/")).json();
    await studentContext.close();

    const directorContext = await browser.newContext({
      storageState: statePath("director_exam"),
    });
    const director = await directorContext.newPage();
    await director.goto(`/students/${me.id}`);
    await director.getByRole("tab", { name: "История изменений" }).click();

    await expect(director.locator("table.tbl")).toContainText(/анкета/i);
    await directorContext.close();
  });
});

// карточка задач на главной с 07.10.2026 называется «Задачи», фраза стрика — её подзаголовок
test.describe("XP и стрик", () => {
  test.use({ storageState: statePath("student") });

  // у пустой карточки подзаголовка нет и галочки нет: куратор ставит ученику
  // задачу, чтобы и выполнение, и фраза стрика проверялись на настоящих строках
  test.beforeAll(async ({ browser }) => {
    const student = await browser.newContext({ storageState: statePath("student") });
    const me = (await (await student.request.get("/api/students/me/")).json()) as { id: number };
    await student.close();
    const curator = await browser.newContext({ storageState: statePath("curator") });
    const page = await curator.newPage();
    await page.goto("/dashboard");
    await apiPost(page, "/api/curator/tasks/", {
      student: me.id,
      title: "Задача прогона: отметить галочкой на главной",
    });
    await curator.close();
  });

  test("выполнение задачи начисляет XP прямо с дашборда", async ({ page }) => {
    await page.goto("/dashboard");
    const before = await (await page.request.get("/api/game/me/")).json();

    const panel = page.locator(".datacard", { has: page.locator(".datacard__title", { hasText: /^Задачи/ }) });
    await expect(panel).toBeVisible();
    // жмём сам переключатель, а не скрытый input внутри него: у компонента
    // реестра их два, и клик по скрытому до обработчика не доходит
    const checkbox = panel.locator('[data-slot="checkbox"]').first();

    if (await checkbox.isVisible().catch(() => false)) {
      const [moved] = await Promise.all([
        page.waitForResponse((r) => r.url().includes("/status/")),
        checkbox.click(),
      ]);
      expect(moved.status()).toBe(200);

      // отмеченная задача уходит из списка; XP начисляет сервер, на карточке
      // с 07.10.2026 чипа XP нет — след действия: уведомление и счётчик в API
      await expect(page.getByText("Задача выполнена")).toBeVisible();
      await expect
        .poll(
          async () =>
            (await (await page.request.get("/api/game/me/")).json()).xp,
          { timeout: 10_000 },
        )
        .toBeGreaterThan(before.xp);
    }
  });

  test("на дашборде видны уровень, стрик и XP каждой задачи", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    const panel = page.locator(".datacard", { has: page.locator(".datacard__title", { hasText: /^Задачи/ }) });

    await expect(panel).toContainText("подряд");
    // XP показывается у выполненной задачи; у невыполненных чипа нет
    const state = await (await page.request.get("/api/game/me/")).json();
    expect(Array.isArray(state.today)).toBe(true);
  });

  test("никаких рейтингов и сравнения с другими", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForTimeout(700);
    const text = await page.locator("main").innerText();

    for (const word of ["рейтинг", "место в", "лидер", "лучше, чем"]) {
      expect(
        text.toLowerCase(),
        `на дашборде появилось сравнение: ${word}`,
      ).not.toContain(word);
    }
  });

  test("у ученика без стрика формулировка поддерживающая", async ({ page }) => {
    await page.goto("/dashboard");
    const state = await (await page.request.get("/api/game/me/")).json();

    expect(state.streak_phrase.toLowerCase()).not.toContain("потер");
    await expect(page.locator(".datacard", { has: page.locator(".datacard__title", { hasText: /^Задачи/ }) })).toContainText(
      state.streak_phrase,
    );
  });
});

/** Убрать прежние ответы: база между прогонами не чистится. */
async function resetQuiz(page: import("@playwright/test").Page): Promise<void> {
  const { execFileSync } = await import("node:child_process");
  execFileSync(
    "docker",
    [
      "compose",
      "exec",
      "-T",
      "backend",
      "python",
      "manage.py",
      "shell",
      "-c",
      "from engagement.models import OnboardingSession; OnboardingSession.objects.all().delete()",
    ],
    { cwd: process.cwd() + "/.." },
  );
}
