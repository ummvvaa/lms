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
import { wizardApply, wizardApplyByApi, wizardFile, wizardToColumns, wizardToRows } from "../helpers/wizard";

test.describe("первый вход", () => {
  test.use({ storageState: statePath("director_exam") });

  test("три шага показываются, прячутся и вызываются заново", async ({
    page,
  }) => {
    const diag = watch(page);
    // приходим как человек, который здесь впервые
    await page.addInitScript(() => window.localStorage.clear());
    await page.goto("/dashboard");

    // сами три шага не показываются: только по «Как начать» из меню профиля
    const guide = page.locator(".firstrun");
    await expect(page.locator("h1")).toBeVisible();
    await expect(guide).toHaveCount(0);
    await page.getByRole("button", { name: "Меню профиля" }).click();
    await page.getByRole("menuitem", { name: "Как начать" }).click();
    await expect(guide).toBeVisible();
    await expect(guide.locator(".firstrun__step")).toHaveCount(3);

    await guide.getByRole("button", { name: "Пропустить" }).click();
    await expect(guide).toHaveCount(0);

    // после перезагрузки не возвращается сам
    await page.reload();
    await expect(page.locator(".firstrun")).toHaveCount(0);

    // но вызывается из меню пользователя
    await page.getByRole("button", { name: "Меню профиля" }).click();
    await page.getByRole("menuitem", { name: "Как начать" }).click();
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
      .locator(".rowline")
      .filter({ hasText: "Вузы заведены" });
    await expect(step).toBeVisible();
    await step.locator(".rowline__open").click();
    await page.waitForURL(/\/directory/);

    // сворачивается и остаётся свёрнутой
    await page.goto("/dashboard");
    await page
      .locator(".start")
      .getByRole("button", { name: "Свернуть" })
      .click();
    await expect(page.locator(".start .rowline")).toHaveCount(0);
    await page.reload();
    await expect(page.locator(".start .rowline")).toHaveCount(0);
    await page
      .locator(".start")
      .getByRole("button", { name: "Развернуть" })
      .click();
    await expect(page.locator(".start .rowline").first()).toBeVisible();
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
  // поля профилей грузит мастер импорта: файл-список с почтой ученика
  test.use({ storageState: statePath("admin") });

  test("одна кривая строка не отменяет файл", async ({ page }) => {
    const diag = watch(page);
    await page.goto("/import");

    // берём трёх настоящих учеников и приводим их к известному состоянию:
    // сценарий не должен зависеть от того, что оставил прошлый прогон
    const list = await (
      await page.request.get("/api/students/?page_size=3")
    ).json();
    const emails = list.results.map((row: { email: string }) => row.email);
    // администратор в таблицу не пишет: известное состояние ставим той же
    // загрузкой за домен «Экзамены», что и проверяем
    const prepared = await wizardApplyByApi(
      page,
      "подготовка.csv",
      `email,ielts\n${emails.map((email: string) => `${email},5.5`).join("\n")}\n`,
      ["exam"],
    );
    expect(prepared.status()).toBe(201);
    await page.reload();
    const csv = `email,ielts\n${emails[0]},7.0\n${emails[1]},12.5\n${emails[2]},6.5\n`;

    await wizardFile(page, "баллы.csv", csv);
    await wizardToColumns(page);
    // колонку мастер узнал сам: «ielts» — текущий балл домена «Экзамены»
    await expect(page.locator("table.tbl tbody tr").filter({ hasText: "Текущий балл IELTS" }).first()).toContainText("Экзамены");
    await wizardToRows(page);

    // сообщение называет поле, значение и допустимый диапазон — в строке ученика
    const bad = page.locator("table.tbl tbody tr.aimp__row--bad");
    await expect(bad).toHaveCount(1);
    await expect(bad).toContainText(emails[1]);
    await expect(bad).toContainText("Текущий балл IELTS");
    await expect(bad).toContainText("12.5");
    await expect(bad).toContainText("максимальный балл — 9");
    await expect(bad).toContainText("от 0 до 9 баллов");

    // пока строка с ошибкой не разобрана, применить нельзя; её пропускают —
    // и применяются правильные строки, а не отвергается весь файл
    const apply = page.getByRole("button", { name: "Применить", exact: true });
    await expect(apply).toBeDisabled();
    await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/admission-imports/preview/") && r.status() === 200),
      page.getByRole("button", { name: "Пропустить строки с ошибкой" }).click(),
    ]);
    await expect(apply).toBeEnabled();
    await wizardApply(page);

    // исправляем файл и грузим заново — теперь проходит целиком
    const fixed = `email,ielts\n${emails[0]},7.5\n${emails[1]},6.0\n${emails[2]},6.5\n`;
    await page.goto("/import");
    await wizardFile(page, "баллы-исправленный.csv", fixed);
    await wizardToColumns(page);
    await wizardToRows(page);
    await expect(page.locator("table.tbl tbody tr.aimp__row--bad")).toHaveCount(0);
    await wizardApply(page);

    // значение видно в базе после перезагрузки
    await page.reload();
    const profile = await (
      await page.request.get(`/api/profiles/exam/${list.results[1].id}/`)
    ).json();
    expect(profile.ielts_current).toBe("6.0");
    expect(diag.consoleErrors).toEqual([]);
  });
});
