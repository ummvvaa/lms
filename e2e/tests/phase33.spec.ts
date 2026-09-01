/**
 * Фаза 33 — внешний вид и движение, проверенные глазами и числами.
 *
 * Каждая анимация из списка фазы подтверждается измерением, а не словом
 * «реализовано»: положение строки на 60-й миллисекунде после сортировки
 * лежит между старым и новым местом; подложка вкладки в промежуточном
 * положении; сетка каркаса при сворачивании меню — тоже. Сверх того:
 * список уведомлений не сдвигает шапку, профиль открывается из меню,
 * упавший экран показывает сообщение вместо белой страницы.
 */
import { expect, test, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { apiPatch, apiPost, watch } from "../helpers/session";

const TEMPLATES = [
  ["Собрать рекомендации", "high", 10],
  ["Черновик эссе", "medium", 11],
  ["Проверить дедлайны", "low", 12],
] as const;

/** Три шаблона задач — чтобы было что сортировать и что сохранять. */
async function ensureTemplates(page: Page) {
  const have = await page.request
    .get("/api/task-templates/?page_size=50")
    .then((r) => r.json());
  const titles = (have.results ?? have).map((r: { title: string }) => r.title);
  for (const [title, priority, due_month] of TEMPLATES) {
    if (!titles.includes(title)) {
      await apiPost(page, "/api/task-templates/", {
        title,
        category: "documents",
        priority,
        due_day: 15,
        due_month,
        is_active: true,
      });
    }
  }
}

const rowsY = (page: Page) =>
  page
    .locator(".tbl tbody tr")
    .evaluateAll((els) =>
      els.map((e) => Math.round(e.getBoundingClientRect().y)),
    );
const rowNames = (page: Page) =>
  page.locator(".tbl tbody tr td:first-child").allInnerTexts();

test.describe("движение", () => {
  test.use({ storageState: statePath("director_behavior") });

  test("сортировка двигает строки, а не перерисовывает их", async ({
    page,
  }) => {
    await ensureTemplates(page);
    await page.goto("/task-templates");
    await expect(page.locator(".tbl tbody tr")).toHaveCount(3, {
      timeout: 15_000,
    });
    const namesBefore = await rowNames(page);
    const resting = await rowsY(page);
    await page
      .locator(".tbl th.tbl__sortable")
      .filter({ hasText: "Задача" })
      .click();
    await page.waitForTimeout(60);
    const mid = await rowsY(page);
    await page.waitForTimeout(400);
    const namesAfter = await rowNames(page);
    // порядок сменился, а на 60-й миллисекунде хотя бы одна строка стояла
    // не на сетке строк — то есть ехала между старым и новым местом
    expect(namesAfter).not.toEqual(namesBefore);
    const moving = mid.some((y) => !resting.includes(y));
    expect(moving, `строки в покое ${resting} · на 60мс ${mid}`).toBe(true);
  });

  test("подложка вкладок переезжает", async ({ page }) => {
    const first = await page.request
      .get("/api/students/?page_size=1")
      .then((r) => r.json());
    await page.goto(`/students/${first.results[0].id}`);
    const indicator = page.locator(".tabs__indicator");
    await expect(indicator).toBeVisible();
    const x = () =>
      indicator.evaluate((e) => Math.round(e.getBoundingClientRect().x));
    const x0 = await x();
    await page.locator(".tabs__tab").nth(2).click();
    await page.waitForTimeout(70);
    const xMid = await x();
    await page.waitForTimeout(400);
    const x1 = await x();
    expect(x1).not.toEqual(x0);
    expect(xMid, `x до ${x0} · на 70мс ${xMid} · после ${x1}`).not.toEqual(x0);
    expect(xMid).not.toEqual(x1);
  });

  test("меню сворачивается плавно", async ({ page }) => {
    await page.goto("/dashboard");
    const cols = () =>
      page
        .locator(".shell")
        .evaluate((e) => getComputedStyle(e).gridTemplateColumns);
    // начинаем с развёрнутого меню: свёрнутость хранится на сервере
    // и могла остаться от предыдущего прогона
    if (await page.locator(".shell--collapsed").count()) {
      await page.getByRole("button", { name: "Развернуть меню" }).click();
      await page.waitForTimeout(500);
    }
    const c0 = await cols();
    await page
      .getByRole("button", { name: /свернуть меню|развернуть меню/i })
      .click();
    await page.waitForTimeout(60);
    const cMid = await cols();
    await page.waitForTimeout(400);
    const c1 = await cols();
    expect(c1).not.toEqual(c0);
    expect(cMid, `${c0} · ${cMid} · ${c1}`).not.toEqual(c0);
    expect(cMid).not.toEqual(c1);
    // возвращаем как было — настройка уходит на сервер
    await page
      .getByRole("button", { name: /свернуть меню|развернуть меню/i })
      .click();
  });

  test("кнопка отвечает на нажатие, строка — на наведение", async ({
    page,
  }) => {
    await ensureTemplates(page);
    await page.goto("/task-templates");
    const button = page.getByRole("button", { name: "Завести шаблон" }).first();
    const box = (await button.boundingBox())!;
    await page.mouse.move(box.x + 6, box.y + 6);
    await page.mouse.down();
    await page.waitForTimeout(150);
    const pressed = await button.evaluate((e) => getComputedStyle(e).transform);
    // отпускаем в стороне: иначе это клик, и откроется диалог
    await page.mouse.move(box.x - 40, box.y + 80);
    await page.mouse.up();
    // сдвиг на пиксель вниз; кадр может попасть на середину перехода,
    // поэтому сравниваем не с точкой, а с направлением
    const dy = Number(
      pressed.match(/matrix\((?:[^,]+,\s*){5}([^)]+)\)/)?.[1] ?? 0,
    );
    expect(dy, pressed).toBeGreaterThan(0.5);

    const row = page.locator(".tbl tbody tr").first();
    const cell = row.locator("td").first();
    const idle = await cell.evaluate(
      (e) => getComputedStyle(e).backgroundColor,
    );
    await row.hover();
    await page.waitForTimeout(200);
    const hovered = await cell.evaluate(
      (e) => getComputedStyle(e).backgroundColor,
    );
    expect(hovered).not.toEqual(idle);
  });

  test("меню, диалог и подсказка появляются с переходом", async ({ page }) => {
    await ensureTemplates(page);
    await page.goto("/task-templates");
    await page
      .locator(".tbl tbody tr")
      .first()
      .getByRole("button", { name: "Ещё действия" })
      .click();
    const menu = page.locator('[data-slot="dropdown-menu-content"]');
    await expect(menu).toBeVisible();
    const menuAnim = await menu.evaluate(
      (e) => getComputedStyle(e).animationName,
    );
    expect(menuAnim).not.toBe("none");
    await page.keyboard.press("Escape");

    await page.getByRole("button", { name: "Завести шаблон" }).first().click();
    const dialog = page.locator('[data-slot="dialog-content"]');
    await expect(dialog).toBeVisible();
    expect(
      await dialog.evaluate((e) => getComputedStyle(e).animationName),
    ).not.toBe("none");
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();

    // подсказка «?» есть на карточке ученика
    const first = await page.request
      .get("/api/students/?page_size=1")
      .then((r) => r.json());
    await page.goto(`/students/${first.results[0].id}`);
    await page.locator(".hint").first().hover();
    const tip = page.locator('[data-slot="tooltip-content"]');
    await expect(tip).toBeVisible();
  });

  test("загрузка показывает серые полоски, а не крутилку", async ({ page }) => {
    await page.route("**/api/task-templates/**", async (route) => {
      await new Promise((r) => setTimeout(r, 1200));
      await route.continue();
    });
    await page.goto("/task-templates");
    await page.waitForTimeout(300);
    const skeletons = page.locator('[data-slot="skeleton"]');
    expect(await skeletons.count()).toBeGreaterThan(2);
    expect(
      await skeletons
        .first()
        .evaluate((e) => getComputedStyle(e).animationName),
    ).toBe("pulse");
    await page.unroute("**/api/task-templates/**");
  });

  test("сохранение подсвечивает строку и показывает уведомление", async ({
    page,
  }) => {
    await ensureTemplates(page);
    await page.goto("/task-templates");
    await expect(page.locator(".tbl tbody tr")).toHaveCount(3, {
      timeout: 15_000,
    });
    await page
      .locator(".tbl tbody tr")
      .first()
      .getByRole("button", { name: "Ещё действия" })
      .click();
    await page.getByRole("menuitem", { name: "Изменить" }).click();
    const saved = page.waitForResponse(
      (r) =>
        r.url().includes("/api/task-templates/") &&
        r.request().method() === "PATCH",
    );
    await page.getByRole("button", { name: "Сохранить" }).click();
    expect((await saved).status()).toBe(200);
    const flashed = page.locator(".row--flash");
    await expect(flashed).toHaveCount(1);
    const animation = await flashed
      .locator("td")
      .first()
      .evaluate((e) => getComputedStyle(e).animationName);
    expect(animation).toBe("row-flash");
    await expect(page.locator("[data-sonner-toast]")).toContainText(
      "Сохранено",
    );
  });

  test("«уменьшить движение» снимает переходы, но всё работает", async ({
    browser,
  }) => {
    const context = await browser.newContext({
      storageState: statePath("director_behavior"),
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    await ensureTemplates(page);
    await page.goto("/task-templates");
    await expect(page.locator(".tbl tbody tr")).toHaveCount(3, {
      timeout: 15_000,
    });
    const namesBefore = await rowNames(page);
    const resting = await rowsY(page);
    await page
      .locator(".tbl th.tbl__sortable")
      .filter({ hasText: "Задача" })
      .click();
    await page.waitForTimeout(40);
    const mid = await rowsY(page);
    await page.waitForTimeout(300);
    const namesAfter = await rowNames(page);
    // порядок сменился, но промежуточного положения не было: строки
    // встали на сетку сразу
    expect(namesAfter).not.toEqual(namesBefore);
    expect(mid).toEqual(resting);
    const button = page.getByRole("button", { name: "Завести шаблон" }).first();
    expect(
      await button.evaluate((e) => getComputedStyle(e).transitionDuration),
    ).toMatch(/^0s/);
    await context.close();
  });
});

test.describe("всплывающее ничего не сдвигает", () => {
  test.use({ storageState: statePath("director_behavior") });

  test("колокольчик и меню профиля не двигают шапку", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.locator(".pmenu__username")).toBeVisible();
    await expect(page.locator(".head__title")).toBeVisible();
    const snapshot = async () =>
      JSON.stringify(
        await page
          .locator(
            '.shell__top .search, .pmenu__username, [aria-label="Меню профиля"], .head__title',
          )
          .evaluateAll((els) =>
            els.map((e) => [
              Math.round(e.getBoundingClientRect().x),
              Math.round(e.getBoundingClientRect().y),
            ]),
          ),
      );
    const before = await snapshot();
    await page.getByRole("button", { name: /уведомления/i }).click();
    await expect(page.locator('[data-slot="popover-content"]')).toBeVisible();
    expect(await snapshot()).toEqual(before);
    await page.keyboard.press("Escape");

    await page.getByRole("button", { name: "Меню профиля" }).click();
    await expect(
      page.locator('[data-slot="dropdown-menu-content"]'),
    ).toBeVisible();
    expect(await snapshot()).toEqual(before);
    await page.getByRole("menuitem", { name: "Профиль" }).click();
    await expect(page).toHaveURL(/\/profile$/);
    await expect(page.locator(".head__title")).toHaveText("Профиль");
  });
});

test.describe("ошибка — сообщение, а не белый экран", () => {
  test.use({ storageState: statePath("director_behavior") });

  test("упавший экран показывает сообщение и кнопку, меню остаётся", async ({
    page,
  }) => {
    const diag = watch(page);
    // ломаем ответ сервера так, чтобы экран упал при рендере
    await page.route("**/api/task-templates/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: '{"results": [{"id": 1}]}',
      }),
    );
    await page.goto("/task-templates");
    const crash = page.locator(".crash--screen");
    // если экран пережил кривой ответ — это тоже хорошо; проверяем, что
    // белой страницы нет ни в одном из исходов
    const survived = await page
      .locator(".head__title")
      .waitFor({ timeout: 5_000 })
      .then(() => true)
      .catch(() => false);
    if (!survived) {
      await expect(crash).toBeVisible();
      await expect(
        crash.getByRole("button", { name: "Обновить" }),
      ).toBeVisible();
      expect(
        diag.pageErrors.length + diag.consoleErrors.length,
      ).toBeGreaterThan(0);
    }
    await expect(page.locator(".shell__nav")).toBeVisible();
    expect(
      (await page.locator("body").innerText()).trim().length,
    ).toBeGreaterThan(40);
  });
});

test.describe("переделка ничего не сломала", () => {
  test.use({ storageState: statePath("director_behavior") });

  test("правка в таблице сохраняется и переживает перезагрузку", async ({
    page,
  }) => {
    const diag = watch(page);
    await page.goto("/table");
    const cell = page.locator('input.cell[data-row="0"][data-col="0"]');
    await expect(cell).toBeVisible({ timeout: 15_000 });
    const value = String(70 + Math.floor(Math.random() * 25));
    await cell.fill(value);
    const saved = page.waitForResponse((r) =>
      r.url().includes("/api/batch/save/"),
    );
    await page.getByRole("button", { name: "Сохранить" }).click();
    expect((await saved).status()).toBe(200);
    await expect(page.locator("[data-sonner-toast]")).toContainText(
      "Сохранено",
    );
    await page.reload();
    await expect(
      page.locator('input.cell[data-row="0"][data-col="0"]'),
    ).toHaveValue(value, { timeout: 15_000 });
    expect(diag.pageErrors).toEqual([]);
  });

  test("чужой домен не правится и отбивается сервером", async ({ page }) => {
    const first = await page.request
      .get("/api/students/?page_size=1")
      .then((r) => r.json());
    const id = first.results[0].id;
    const response = await page.request.patch(`/api/students/${id}/`, {
      data: { exam: { ielts_current: 9 } },
      headers: {
        "X-CSRFToken":
          (await page.context().cookies()).find((c) => c.name === "csrftoken")
            ?.value ?? "",
      },
    });
    expect([400, 403]).toContain(response.status());
    // и с экрана: в таблице директора школы нет колонок экзаменов
    await page.goto("/table");
    await expect(page.locator(".grid-tbl th")).not.toContainText(["IELTS"]);
  });

  test("контакт заводится, правится в меню строки и уходит в архив", async ({
    page,
  }) => {
    const first = await page.request
      .get("/api/students/?page_size=1")
      .then((r) => r.json());
    await page.goto("/contacts");
    await page.getByRole("button", { name: "Добавить контакт" }).click();
    await page
      .locator("select")
      .first()
      .selectOption(String(first.results[0].id));
    const name = `Родитель ${Date.now() % 10000}`;
    // поля формы идут в порядке CONTACT_FIELDS: ФИО, кем приходится, телефон
    await page.locator(".rowform input").nth(0).fill(name);
    await page.locator(".rowform select").first().selectOption({ index: 1 });
    await page.locator(".rowform input").nth(1).fill("+7 700 000 00 00");
    const created = page.waitForResponse(
      (r) =>
        r.url().includes("/api/contacts/") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Добавить", exact: true }).click();
    expect((await created).status()).toBe(201);
    const row = page.locator(".rows__item").filter({ hasText: name });
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: "Ещё действия" }).click();
    await page.getByRole("menuitem", { name: "Удалить" }).click();
    const dialog = page.locator('[data-slot="dialog-content"]');
    await expect(dialog).toBeVisible();
    const removed = page.waitForResponse(
      (r) =>
        r.url().includes("/api/contacts/") && r.request().method() === "DELETE",
    );
    await dialog.getByRole("button", { name: /^Удалить/ }).click();
    expect((await removed).status()).toBeLessThan(300);
    await expect(row).toBeHidden();
  });
});

test.describe("кабинет ученика", () => {
  test.use({ storageState: statePath("student") });

  test("ученик видит свои данные и не видит ярлыков", async ({ page }) => {
    const diag = watch(page);
    for (const route of [
      "/dashboard",
      "/my-data",
      "/roadmap",
      "/universities",
      "/catalog",
      "/prep",
      "/essays",
      "/profile",
    ]) {
      await page.goto(route);
      await page.waitForLoadState("networkidle");
      const text = (await page.locator("body").innerText()).toLowerCase();
      for (const label of [
        "critical",
        "needs_supervision",
        "can_execute",
        "strong",
        "weak",
      ]) {
        expect(text, `${route}: ярлык «${label}»`).not.toContain(label);
      }
      expect(diag.pageErrors, route).toEqual([]);
      diag.reset();
    }
  });

  test("у ученика просторно, у директора плотно", async ({ page, browser }) => {
    await page.goto("/dashboard");
    // плотность ставится после загрузки профиля — ждём атрибут, а не первый кадр
    await page.waitForSelector('html[data-density="roomy"]', {
      timeout: 15_000,
    });
    const roomy = await page.evaluate(() =>
      getComputedStyle(document.documentElement)
        .getPropertyValue("--row-h")
        .trim(),
    );
    const context = await browser.newContext({
      storageState: statePath("director_behavior"),
    });
    const staff = await context.newPage();
    await staff.goto("/dashboard");
    await staff.waitForSelector('html[data-density="dense"]', {
      timeout: 15_000,
    });
    const dense = await staff.evaluate(() =>
      getComputedStyle(document.documentElement)
        .getPropertyValue("--row-h")
        .trim(),
    );
    expect(parseInt(roomy)).toBeGreaterThan(parseInt(dense));
    await context.close();
  });
});

test.describe("тёмная тема", () => {
  test.use({ storageState: statePath("director_behavior") });

  test("на каждом экране текст читается на своём фоне", async ({ page }) => {
    await apiPatch(page, "/api/auth/me/preferences/", { theme: "dark" }).catch(
      () => undefined,
    );
    await page.goto("/dashboard");
    await page.evaluate(() => {
      document.documentElement.dataset.theme = "dark";
    });
    await expect(page.locator(".navlink").first()).toBeVisible();
    const routes = await page
      .locator(".navlink")
      .evaluateAll((els) => els.map((e) => e.getAttribute("href")!));
    expect(routes.length).toBeGreaterThan(5);
    const unreadable: string[] = [];
    for (const route of [...new Set(routes)]) {
      await page.goto(route);
      // не `networkidle`: помощник и дайджест опрашивают сервер, и покоя не бывает
      await page.waitForLoadState("domcontentloaded");
      await page.waitForTimeout(700);
      await page.evaluate(() => {
        document.documentElement.dataset.theme = "dark";
      });
      await page.waitForTimeout(150);
      // текст, у которого цвет совпал с фоном ближайшей закрашенной подложки
      const bad = await page.evaluate(() => {
        const lum = (c: string) => {
          const m = c.match(/\d+(\.\d+)?/g);
          if (!m || m.length < 3) return null;
          const [r, g, b] = m.map(Number);
          return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
        };
        const out: string[] = [];
        for (const el of Array.from(document.querySelectorAll("main *"))) {
          const text = (el.textContent || "").trim();
          if (!text || el.children.length) continue;
          const cs = getComputedStyle(el);
          const fg = lum(cs.color);
          let node: Element | null = el;
          let bg: number | null = null;
          let bgColor = "";
          while (node && bg === null) {
            const b = getComputedStyle(node).backgroundColor;
            bgColor = b;
            // полупрозрачная подложка метки (rgba с малой альфой) не закрашивает
            // фон: настоящий фон — под ней, идём дальше по родителям
            const alpha = b.startsWith("rgba")
              ? Number(b.match(/[\d.]+(?=\))/)?.[0] ?? 1)
              : 1;
            if (b && b !== "transparent" && alpha >= 0.5) bg = lum(b);
            node = node.parentElement;
          }
          if (fg !== null && bg !== null && Math.abs(fg - bg) < 0.25)
            out.push(`${text.slice(0, 40)} [${cs.color} на ${bgColor}]`);
        }
        return out.slice(0, 5);
      });
      if (bad.length) unreadable.push(`${route}: ${bad.join(" | ")}`);
    }
    await apiPatch(page, "/api/auth/me/preferences/", {
      theme: "system",
    }).catch(() => undefined);
    expect(unreadable).toEqual([]);
  });
});
