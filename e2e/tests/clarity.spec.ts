/**
 * Фаза 15: понятность интерфейса.
 *
 * Приёмка: три шага при первом входе, панель «Начало работы» ведёт на
 * нужный экран, файл с одной намеренной ошибкой не отвергается целиком,
 * а сообщение называет строку, колонку и допустимый диапазон.
 */
import { expect, test } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";

test.describe("первый вход", () => {
  test.use({ storageState: statePath("director_exam") });

  test("три шага показываются, прячутся и вызываются заново", async ({
    page,
  }) => {
    const diag = watch(page);
    // приходим как человек, который здесь впервые
    await page.addInitScript(() => window.localStorage.clear());
    await page.goto("/dashboard");

    const guide = page.locator(".firstrun");
    await expect(guide).toBeVisible();
    await expect(guide.locator(".firstrun__step")).toHaveCount(3);

    await guide.getByRole("button", { name: "Пропустить" }).click();
    await expect(guide).toHaveCount(0);

    // после перезагрузки не возвращается сам
    await page.reload();
    await expect(page.locator(".firstrun")).toHaveCount(0);

    // но вызывается из шапки
    await page.getByRole("button", { name: "Как начать" }).click();
    await expect(page.locator(".firstrun")).toBeVisible();
    expect(diag.consoleErrors).toEqual([]);
  });
});

test.describe("панель «Начало работы»", () => {
  test.use({ storageState: statePath("director_admission") });

  test("строка чеклиста ведёт на свой экран", async ({ page }) => {
    const diag = watch(page);
    await page.goto("/dashboard");

    const panel = page.locator(".start");
    await expect(panel).toBeVisible();
    await expect(panel).toContainText("Выполнено");

    const step = panel
      .locator(".start__step")
      .filter({ hasText: "Вузы заведены" });
    await expect(step).toBeVisible();
    await step.click();
    await page.waitForURL(/\/directory/);

    // сворачивается и остаётся свёрнутой
    await page.goto("/dashboard");
    await page
      .locator(".start")
      .getByRole("button", { name: "Свернуть" })
      .click();
    await expect(page.locator(".start__list")).toHaveCount(0);
    await page.reload();
    await expect(page.locator(".start__list")).toHaveCount(0);
    await page
      .locator(".start")
      .getByRole("button", { name: "Развернуть" })
      .click();
    await expect(page.locator(".start__list")).toBeVisible();
    expect(diag.consoleErrors).toEqual([]);
  });
});

test.describe("пустой экран объясняет себя", () => {
  test.use({ storageState: statePath("director_exam") });

  test("поиск, который никого не нашёл, предлагает снять фильтры", async ({
    page,
  }) => {
    const diag = watch(page);
    await page.goto("/table");

    await page
      .getByPlaceholder("Поиск по имени")
      .fill("такого-человека-нет-зззз");
    const empty = page.locator(".empty");
    await expect(empty).toBeVisible();
    await expect(empty).toContainText("По этому фильтру никого нет");

    await empty.getByRole("button", { name: "Снять фильтры" }).click();
    await expect(page.locator(".grid-tbl tbody tr").first()).toBeVisible();
    expect(diag.failed).toEqual([]);
    expect(diag.consoleErrors).toEqual([]);
  });
});

test.describe("ошибка в файле объясняется по-человечески", () => {
  test.use({ storageState: statePath("director_exam") });

  test("одна кривая строка не отменяет файл", async ({ page }) => {
    const diag = watch(page);
    await page.goto("/import");

    // берём трёх настоящих учеников и приводим их к известному состоянию:
    // сценарий не должен зависеть от того, что оставил прошлый прогон
    const list = await (
      await page.request.get("/api/students/?page_size=3")
    ).json();
    const emails = list.results.map((row: { email: string }) => row.email);
    const csrf = (await page.context().cookies()).find(
      (c) => c.name === "csrftoken",
    )!.value;
    await page.request.post("/api/batch/save/", {
      data: {
        changes: list.results.map((row: { id: number }) => ({
          student: row.id,
          model: "students.ExamProfile",
          field: "ielts_current",
          value: "5.5",
        })),
      },
      headers: { "X-CSRFToken": csrf },
    });
    await page.reload();
    const csv = `email,ielts\n${emails[0]},7.0\n${emails[1]},12.5\n${emails[2]},6.5\n`;

    await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/import/preview/")),
      page.setInputFiles("input[type=file]", {
        name: "баллы.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(csv, "utf8"),
      }),
    ]);

    // колонку сопоставляем руками — так это и делает человек.
    // Строки берём по порядку: по тексту их не различить, слово «email»
    // встречается и в подписи варианта «Ученик (email)»
    const mapping = page.locator("table.history tbody tr");
    await expect(mapping.first()).toBeVisible();
    await mapping.nth(0).locator("select").selectOption("student");
    await mapping
      .nth(1)
      .locator("select")
      .selectOption({ label: "IELTS текущий" });
    await page.getByRole("button", { name: "Показать предпросмотр" }).click();

    // сообщение называет строку, колонку, значение и допустимый диапазон
    const problems = page.locator(".imp__problems").first();
    await expect(problems).toBeVisible();
    await expect(problems).toContainText("Строка 3");
    await expect(problems).toContainText("колонка «ielts»");
    await expect(problems).toContainText("12.5");
    await expect(problems).toContainText("максимальный балл — 9");
    await expect(problems).toContainText("от 0 до 9 баллов");

    // применяются только правильные строки, а не отвергается весь файл
    const apply = page.getByRole("button", { name: /Применить/ });
    await expect(apply).toContainText("правильных строк");
    const mark = diag.mark();
    await apply.click();
    await expect
      .poll(
        () =>
          diag
            .since(mark)
            .filter((c) => c.url.includes("/import/apply/") && c.status === 200)
            .length,
      )
      .toBeGreaterThan(0);

    // исправляем файл и грузим заново — теперь проходит целиком
    const fixed = `email,ielts\n${emails[0]},7.5\n${emails[1]},6.0\n${emails[2]},6.5\n`;
    // ждём, пока файл прочитается: до этого сопоставление колонок
    // ещё принадлежит прошлому файлу и будет заменено
    await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/import/preview/")),
      page.setInputFiles("input[type=file]", {
        name: "баллы-исправленный.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(fixed, "utf8"),
      }),
    ]);
    await mapping.nth(0).locator("select").selectOption("student");
    await mapping
      .nth(1)
      .locator("select")
      .selectOption({ label: "IELTS текущий" });
    await page.getByRole("button", { name: "Показать предпросмотр" }).click();
    await expect(page.locator(".imp__problems")).toHaveCount(0);
    await page.getByRole("button", { name: "Применить", exact: true }).click();

    // значение видно в базе после перезагрузки
    await page.reload();
    const profile = await (
      await page.request.get(`/api/profiles/exam/${list.results[1].id}/`)
    ).json();
    expect(profile.ielts_current).toBe("6.0");
    expect(diag.consoleErrors).toEqual([]);
  });
});
