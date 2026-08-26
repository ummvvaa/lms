/**
 * Фаза 11: онбординг и геймификация.
 *
 * Приёмка: новый ученик проходит квиз, его ответы появляются у директоров
 * на подтверждении с пометкой источника; выполнение задачи начисляет XP
 * и двигает уровень; стрик растёт за день с активностью.
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
      "Вопрос 1 из 8",
    );

    const [answered] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/onboarding/answer/")),
      page.getByRole("button", { name: "Канада", exact: true }).click(),
    ]);
    expect(answered.status()).toBe(200);
    await expect(page.locator(".onboarding__count")).toContainText(
      "Вопрос 2 из 8",
    );

    // ушёл и вернулся — отвечать заново не надо
    await page.goto("/dashboard");
    await page.goto("/onboarding");
    await expect(page.locator(".onboarding__count")).toContainText(
      "Вопрос 2 из 8",
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
  test("Кымбат видит балл ученика отдельным списком и подтверждает", async ({
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

    const directorContext = await browser.newContext({
      storageState: statePath("director_exam"),
    });
    const director = await directorContext.newPage();
    await director.goto("/dashboard");

    const queue = director.locator("#onboarding-queue");
    await expect(queue).toContainText("Ученики заполнили о себе");
    await expect(queue).toContainText("IELTS или TOEFL");

    const [confirmed] = await Promise.all([
      director.waitForResponse((r) =>
        r.url().includes("/api/onboarding/pending/"),
      ),
      queue.getByRole("button", { name: "Подтвердить" }).first().click(),
    ]);
    expect(confirmed.status()).toBe(200);

    // после подтверждения строка уходит из очереди
    await director.reload();
    await expect(director.locator("#onboarding-queue")).toBeHidden();

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

    await expect(director.locator("table.history")).toContainText(/анкета/i);
    await directorContext.close();
  });
});

test.describe("XP и стрик", () => {
  test.use({ storageState: statePath("student") });

  test("выполнение задачи начисляет XP прямо с дашборда", async ({ page }) => {
    await page.goto("/dashboard");
    const before = await (await page.request.get("/api/game/me/")).json();

    const panel = page.locator(".today");
    await expect(panel).toBeVisible();
    const checkbox = panel.locator('input[type="checkbox"]').first();

    if (await checkbox.isVisible().catch(() => false)) {
      const [moved] = await Promise.all([
        page.waitForResponse((r) => r.url().includes("/status/")),
        checkbox.click(),
      ]);
      expect(moved.status()).toBe(200);

      // отмеченная задача уходит из списка, поэтому её след — подтверждение XP
      await expect(panel.locator(".today__earned")).toContainText("XP");
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
    const panel = page.locator(".today");

    await expect(panel).toContainText("уровень");
    await expect(panel).toContainText("Стрик:");
    const state = await (await page.request.get("/api/game/me/")).json();
    if (state.today.length > 0) {
      await expect(
        panel.locator('[data-slot="badge"][data-variant="brand"]').first(),
      ).toContainText("XP");
    }
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
    await expect(page.locator(".today__phrase")).toContainText(
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
