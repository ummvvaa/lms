/**
 * Фаза 16: поиск по системе и автосохранение в таблице.
 *
 * Приёмка: поиск находит ученика по фамилии, правка в таблице сохраняется
 * без нажатия кнопки и переживает перезагрузку. Ученик не находит
 * одноклассников — только вузы (инвариант №7).
 */
import { expect, test } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { watch } from "../helpers/session";

test.describe("поиск по системе", () => {
  test.use({ storageState: statePath("director_exam") });

  test("находит ученика по фамилии и открывает его карточку", async ({
    page,
  }) => {
    const diag = watch(page);
    await page.goto("/dashboard");

    const list = await (
      await page.request.get("/api/students/?page_size=1")
    ).json();
    const student = list.results[0];
    const surname = student.full_name.split(" ")[0];

    await page.getByLabel("Поиск по системе").fill(surname);
    const drop = page.locator(".search__drop");
    await expect(drop).toBeVisible();
    // результаты сгруппированы по типу, а не свалены в кучу
    await expect(drop.locator("[cmdk-group-heading]").first()).toContainText(
      "Ученики",
    );

    const row = drop
      .locator(".search__row")
      .filter({ hasText: student.full_name })
      .first();
    await expect(row).toBeVisible();
    await row.click();

    await page.waitForURL(/\/students\/\d+/);
    await expect(page.locator(".card__name")).toContainText(surname);
    expect(diag.failed).toEqual([]);
    expect(diag.consoleErrors).toEqual([]);
  });

  test("открывается горячей клавишей с любого экрана", async ({ page }) => {
    await page.goto("/digest");
    // ждём, пока шапка отрисуется: слушатель горячей клавиши живёт в ней
    const box = page.getByLabel("Поиск по системе");
    await expect(box).toBeVisible();
    await page.locator("body").click();
    await page.keyboard.press("Control+KeyK");
    await expect(box).toBeFocused();
  });

  test("находит вуз по названию", async ({ page }) => {
    await page.goto("/dashboard");
    await page.getByLabel("Поиск по системе").fill("Toronto");
    const drop = page.locator(".search__drop");
    await expect(drop).toContainText("Вузы");
    await expect(drop.locator(".search__row").first()).toContainText("Toronto");
  });

  test("ничего не найдя, объясняет это словами", async ({ page }) => {
    await page.goto("/dashboard");
    await page.getByLabel("Поиск по системе").fill("зззчегототакогонет");
    await expect(page.locator(".search__empty")).toContainText(
      "Ничего не нашлось",
    );
  });
});

test.describe("поиск глазами ученика", () => {
  test.use({ storageState: statePath("student") });

  test("ученик не находит одноклассников — только вузы", async ({
    browser,
    page,
  }) => {
    const staff = await browser.newContext({
      storageState: statePath("director_exam"),
    });
    const staffPage = await staff.newPage();
    await staffPage.goto("/dashboard");
    const list = await (
      await staffPage.request.get("/api/students/?page_size=1")
    ).json();
    const surname = list.results[0].full_name.split(" ")[0];
    await staff.close();

    // сырой ответ API: интерфейс мог бы просто не нарисовать группу
    const payload = await (
      await page.request.get(`/api/search/?q=${encodeURIComponent(surname)}`)
    ).json();
    expect(payload.groups.map((g: { code: string }) => g.code)).not.toContain(
      "students",
    );

    await page.goto("/dashboard");
    await page.getByLabel("Поиск по системе").fill("Toronto");
    await expect(page.locator(".search__drop")).toContainText("Вузы");
    await expect(page.locator(".search__drop")).not.toContainText("Ученики");
  });
});

test.describe("автосохранение в таблице", () => {
  test.use({ storageState: statePath("director_exam") });

  test("правка уходит сама и переживает перезагрузку", async ({ page }) => {
    const diag = watch(page);
    await page.goto("/table");

    const cell = page
      .locator(".grid-tbl tbody tr")
      .first()
      .locator("input.cell")
      .first();
    await expect(cell).toBeVisible();

    // первая колонка у академического директора — IELTS: значение должно
    // укладываться в шкалу и отличаться от текущего, иначе черновика
    // не возникнет вовсе и сохранять будет нечего
    const scale = ["6.0", "6.5", "7.0", "7.5", "8.0"];
    const current = await cell.inputValue();
    const value = scale.find((x) => x !== current)!;
    await cell.fill(value);

    // индикатор проходит путь: черновик → сохраняется → сохранено
    await expect(page.locator('[data-sync="dirty"]')).toContainText(
      "есть несохранённые изменения",
    );
    const mark = diag.mark();
    await expect(page.locator('[data-sync="saved"]')).toBeVisible({
      timeout: 15_000,
    });
    // ушёл именно батч-запрос, и он ответил 2xx
    const calls = diag.since(mark).concat(diag.calls);
    expect(
      calls.some((c) => c.url.includes("/batch/save/") && c.status === 200),
    ).toBeTruthy();
    expect(diag.failed).toEqual([]);

    await page.reload();
    const again = page
      .locator(".grid-tbl tbody tr")
      .first()
      .locator("input.cell")
      .first();
    await expect(again).toHaveValue(value);
    expect(diag.consoleErrors).toEqual([]);
  });

  test("кнопка «Сохранить» остаётся и работает", async ({ page }) => {
    const diag = watch(page);
    await page.goto("/table");

    const cell = page
      .locator(".grid-tbl tbody tr")
      .nth(1)
      .locator("input.cell")
      .first();
    const scale = ["6.0", "6.5", "7.0", "7.5", "8.0"];
    const current = await cell.inputValue();
    const value = scale.find((x) => x !== current)!;
    await cell.fill(value);

    const mark = diag.mark();
    await page.getByRole("button", { name: "Сохранить" }).click();
    await expect
      .poll(
        () =>
          diag
            .since(mark)
            .filter((c) => c.url.includes("/batch/save/") && c.status === 200)
            .length,
      )
      .toBeGreaterThan(0);
    await expect(page.locator('[data-sync="saved"]')).toBeVisible();
    expect(diag.consoleErrors).toEqual([]);
  });

  test("без связи правки копятся и уходят, когда связь вернулась", async ({
    page,
    context,
  }) => {
    const diag = watch(page);
    await page.goto("/table");

    const cell = page
      .locator(".grid-tbl tbody tr")
      .nth(2)
      .locator("input.cell")
      .first();
    await expect(cell).toBeVisible();

    await context.setOffline(true);
    const scale = ["6.0", "6.5", "7.0", "7.5", "8.0"];
    const current = await cell.inputValue();
    const value = scale.find((x) => x !== current)!;
    await cell.fill(value);
    await expect(page.locator('[data-sync="offline"]')).toContainText(
      "нет связи",
      { timeout: 15_000 },
    );
    // набранное не потеряно
    await expect(cell).toHaveValue(value);

    await context.setOffline(false);
    await page.evaluate(() => window.dispatchEvent(new Event("online")));
    await expect(page.locator('[data-sync="saved"]')).toBeVisible({
      timeout: 15_000,
    });

    await page.reload();
    const again = page
      .locator(".grid-tbl tbody tr")
      .nth(2)
      .locator("input.cell")
      .first();
    await expect(again).toHaveValue(value);
    expect(diag.consoleErrors).toEqual([]);
  });
});
