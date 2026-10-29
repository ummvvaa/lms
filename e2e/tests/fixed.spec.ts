/**
 * Регрессия по `docs/DEFECTS.md`: каждый закрытый дефект — отдельная проверка,
 * чтобы он не вернулся. Названия тестов ссылаются на номера из реестра.
 */
import { expect, test } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { byKey } from "../helpers/roles";
import { login, watch, unlockTable } from "../helpers/session";

test.describe("B1 · запись из браузера проходит", () => {
  test("под учеником: what-if отвечает 2xx", async ({ page }) => {
    const account = byKey("student");
    await login(page, account);

    // «что откроется, если» переехало в каталог в фазе 10
    await page.goto("/catalog");
    await page.getByRole("button", { name: "Что откроется, если" }).click();
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/match/what-if/")),
      // ступени прибавки — сегменты: «+0.5» к IELTS пересчитывает список
      page.getByRole("group", { name: "IELTS" }).getByRole("button", { name: "+0.5" }).click(),
    ]);
    expect(response.status(), "CSRF снова отбивает запись").toBe(200);
  });

  test("выход из меню профиля действительно выходит", async ({ page }) => {
    const account = byKey("director_talent");
    await login(page, account);

    // с фазы 23 выход живёт в меню по аватару — единственный вход на экран
    await page.getByRole("button", { name: "Меню профиля" }).click();
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/auth/logout/")),
      page.getByRole("menuitem", { name: "Выйти" }).click(),
    ]);
    expect(response.status()).toBeLessThan(400);
    await page.waitForURL(/\/login/);
  });
});

test.describe("I2 · предложения живут дольше одной вкладки", () => {
  test.use({ storageState: statePath("admin") });  // «Предложения» — у администратора: у директоров раздела нет с 24.10.2026

  test("экран предложений открывается из навигации", async ({ page }) => {
    const diag = watch(page);
    await page.goto("/suggestions");
    await expect(page.locator("h1")).toContainText("Предложения");
    expect(diag.failed).toEqual([]);
  });
});

test.describe("I3 · разделы ведут к своей секции", () => {
  test.use({ storageState: statePath("director_exam") });

  test("TOP-30 прокручивает к секции TOP-30", async ({ page }) => {
    await page.goto("/top30");
    const section = page.locator("#top30");
    await expect(section).toBeVisible();
    // панели над секцией догружаются позже и сдвигают её — прокрутка
    // должна это переживать
    await expect
      .poll(
        async () =>
          section.evaluate((el) => {
            const box = el.getBoundingClientRect();
            return box.top >= -40 && box.top < window.innerHeight;
          }),
        { timeout: 15_000 },
      )
      .toBe(true);
  });
});

test.describe("I4 · чужой экран не открывается", () => {
  test.use({ storageState: statePath("director_sport") });

  test("директора уводит с экранов ученика без ошибок в консоли", async ({
    page,
  }) => {
    const diag = watch(page);
    await page.goto("/catalog");
    await page.waitForURL(/\/dashboard/);
    expect(diag.failed, "экран чужой роли снова сыплет 404").toEqual([]);
  });
});

test.describe("I5 · гистограмма экзаменов кликается", () => {
  test.use({ storageState: statePath("director_exam") });

  // с фазы 49 у Кымбат вместо шести плиток-корзин распределение школы
  // полосами, но правило то же: число, в которое нельзя провалиться, —
  // половина ответа
  // гистограммы IELTS на главной Кымбат нет с 24.10.2026 (новая главная по макету);
  // кликабельное распределение на «Результатах экзаменов» — отдельная задача
  test.skip("полоса диапазона открывает этих учеников в таблице", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    // жмём тот диапазон, в котором кто-то есть: пустой открыл бы пустую
    // таблицу, и проверка ничего бы не значила
    const bars = page.locator(".rowline--link").filter({ has: page.locator(".num") });
    await expect(bars.first()).toBeVisible();
    const counts = await bars.locator(".num").allInnerTexts();
    const index = counts.findIndex((text) => Number(text) > 0);
    expect(index, "ни в одном диапазоне нет учеников").toBeGreaterThanOrEqual(
      0,
    );
    await bars.nth(index).click();
    await page.waitForURL(/\/table\?/);
    await expect(page.getByText("Фильтр из дашборда:")).toBeVisible();
    await expect(page.locator("table.grid-tbl tbody tr").first()).toBeVisible();
  });
});

test.describe("I6 · черновик можно отменить", () => {
  test.use({ storageState: statePath("director_exam") });

  test("«Отменить правки» возвращает прежние значения", async ({ page }) => {
    // черновик живёт две секунды до автосохранения: на медленном прогоне
    // таймер успевал сработать раньше клика, и отменять было уже нечего.
    // Часы страницы подменяем до загрузки и даём им идти, пока экран
    // грузится (иначе запросы и отрисовка, завязанные на таймеры, встанут),
    // а остановленными держим только на время правки: таймер автосохранения
    // не сработает, пока его не пустят, — правило «передумал до сохранения»
    // проверяется без гонки со временем
    await page.clock.install();
    await page.goto("/table");
    await unlockTable(page);
    const cell = page.locator('input[data-col="5"]').first();
    await expect(cell).toBeVisible();
    const before = await cell.inputValue();
    const now = await page.evaluate(() => Date.now());
    await page.clock.pauseAt(now + 1_000);

    // значение уникальное: если оно совпадёт с тем, что уже в базе,
    // черновика не возникнет вовсе и отменять будет нечего
    await cell.fill(`Черновик, который передумали ${Date.now()}`);
    // счётчик — индикатор синхронизации, а сам черновик живёт две секунды
    // до автосохранения — часы стоят, успеваем передумать
    await expect(page.locator('[data-sync="dirty"]')).toContainText(
      "есть несохранённые изменения",
    );

    await page.getByRole("button", { name: "Отменить правки" }).click();
    await expect(cell).toHaveValue(before);
    await expect(page.locator('[data-sync="dirty"]')).toHaveCount(0);
  });
});

test.describe("C1 · заголовок не двоится", () => {
  test.use({ storageState: statePath("student") });

  // «Мои вузы» с 07.10.2026 — вкладка каталога, заголовок экрана у неё общий
  for (const [route, title] of [
    ["/essays", "Эссе"],
    ["/catalog?mode=mine", "Каталог вузов"],
  ]) {
    test(`${route}: «${title}» встречается один раз`, async ({ page }) => {
      await page.goto(route);
      await expect(page.locator("h1")).toContainText(title);
      const head = await page.locator(".head").innerText();
      const occurrences = head.split(title).length - 1;
      expect(
        occurrences,
        `заголовок «${title}» напечатан ${occurrences} раза`,
      ).toBe(1);
    });
  }
});

test.describe("C2 · «Позже» в баннере запоминается", () => {
  test.use({ storageState: statePath("student") });

  test("баннер не возвращается при переходе на другой экран", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    await page.waitForTimeout(600);
    const later = page.getByRole("button", { name: "Позже" });
    const wasShown = await later.isVisible().catch(() => false);
    if (wasShown) {
      await later.click();
      await expect(later).toBeHidden();
    }

    // полная перезагрузка, а не переход внутри приложения: раньше баннер
    // возвращался именно так
    await page.goto("/calendar");
    await page.waitForTimeout(800);
    await expect(page.getByRole("button", { name: "Позже" })).toBeHidden();
  });
});

test.describe("C4 · готовность ученика — по пяти доменам", () => {
  test.use({ storageState: statePath("student") });

  // разбивка с сервера по-прежнему знает все пять доменов: с данными —
  // в parts, без данных — в skipped. На главной полосой рисуется только
  // домен с данными: пустая строка с нулём читалась как «ноль готовности»
  test("домены без данных скрыты, а не нулём", async ({ page }) => {
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          new URL(r.url()).pathname === "/api/students/me/" &&
          r.request().method() === "GET",
      ),
      page.goto("/dashboard"),
    ]);
    expect(response.status()).toBe(200);
    const payload = (await response.json()) as {
      readiness: {
        parts: { title: string }[];
        skipped: { title: string }[];
      };
    };
    const parts = payload.readiness.parts.map((p) => p.title);
    const skipped = payload.readiness.skipped.map((p) => p.title);
    expect(
      parts.length + skipped.length,
      "в разбивке должны быть все пять доменов",
    ).toBe(5);

    const ready = page.locator(".stuhome__ready");
    // полос ровно столько, сколько доменов с данными, и подписаны они ими же
    await expect(ready.locator(".stuhome__barrow")).toHaveCount(parts.length);
    if (parts.length > 0)
      await expect(ready.locator(".stuhome__barname")).toHaveText(parts);
    // домен без данных не появляется в разбивке ни строкой, ни нулём
    for (const title of skipped)
      await expect(
        ready.locator(".stuhome__barname", { hasText: title }),
      ).toHaveCount(0);
  });
});
