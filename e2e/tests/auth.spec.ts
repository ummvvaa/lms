/**
 * Фаза 9: вход по почте и паролю.
 *
 * Проверяется путь целиком, как его проходит человек: администратор заводит
 * учётную запись, приглашённый ставит пароль, входит и попадает на экраны
 * своей роли. Плюс блокировка перебора и отключённый доступ.
 */
import { expect, test } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { byKey } from "../helpers/roles";
import { apiPatch, apiPost, login, watch } from "../helpers/session";
import { lastLinkToken, requirePasswordChange } from "../helpers/dev-link";

/** Уникальная почта на прогон: база между запусками не чистится. */
// под доменом прогона: такую запись уборка после прогона заберёт вместе с остальными
const freshEmail = () => `invited.${Date.now().toString(36)}@probe.local`;

/**
 * Установить пароль по ссылке в чистом окне.
 *
 * Отдельный контекст обязателен: `login` на сервере проворачивает ключ
 * сессии и стирает прежнюю запись. Сделай это в окне администратора —
 * и сохранённая сессия администратора умрёт вместе с ней.
 */
async function setPasswordByLink(
  context: import("@playwright/test").BrowserContext,
  token: string,
  password: string,
): Promise<void> {
  // storageState: undefined обязателен: контекст, созданный из фикстуры
  // `browser`, наследует настройки теста вместе с чужой сессией
  const fresh = await context
    .browser()!
    .newContext({ storageState: undefined });
  const page = await fresh.newPage();
  await page.goto("/login");
  await apiPost(page, "/api/auth/password/set/", {
    token,
    new_password: password,
  });
  await fresh.close();
}

test.describe("вход", () => {
  test("верные почта и пароль пускают на экраны своей роли", async ({
    page,
  }) => {
    const diag = watch(page);
    await login(page, byKey("director_exam"));
    // до входа /api/auth/me/ честно отвечает 403 — считаем только то,
    // что произошло уже в сессии
    diag.reset();

    await expect(page.locator("h1")).toContainText("Экзамены");
    // с фазы 48 роль стоит в блоке пользователя внизу меню, а не в шапке
    await expect(page.locator(".pmenu__userrole")).toContainText(
      "Академический директор",
    );
    expect(diag.failed).toEqual([]);
  });

  test("неверный пароль объясняется, но не выдаёт, есть ли такой человек", async ({
    page,
  }) => {
    await page.goto("/login");
    await page
      .getByLabel("Почта", { exact: true })
      .fill(byKey("director_exam").email);
    await page
      .getByLabel("Пароль", { exact: true })
      .fill("точно-не-тот-пароль");
    await page.getByRole("button", { name: "Войти", exact: true }).click();

    await expect(
      page.locator('[data-slot="badge"][data-variant="risk"]'),
    ).toContainText("Неверная почта или пароль");
    await expect(page).toHaveURL(/\/login/);
  });

  test("на экране входа нет ни одного упоминания Microsoft", async ({
    page,
  }) => {
    await page.goto("/login");
    const text = await page.locator("body").innerText();
    expect(text).not.toMatch(/Microsoft|Entra|MSAL/i);
  });

  test("шесть неверных паролей подряд дают блокировку", async ({
    page,
    context,
  }) => {
    test.setTimeout(120_000);
    // одноразовая учётная запись: блокировка держится час, и запирать
    // ею рабочего директора нельзя — следующий прогон не войдёт
    const email = freshEmail();
    const password = "Запираемый!Тест2026";

    const admin = await context
      .browser()!
      .newContext({ storageState: statePath("admin") });
    const adminPage = await admin.newPage();
    await adminPage.goto("/dashboard");
    await apiPost(adminPage, "/api/users/", { email, role: "student" });
    const token = lastLinkToken(email);
    await admin.close();
    await setPasswordByLink(context, token, password);

    await page.goto("/login");
    for (let attempt = 1; attempt <= 5; attempt += 1) {
      const response = await page.request.post("/api/auth/login/", {
        data: { email, password: `мимо-${attempt}` },
      });
      expect(response.status(), `попытка ${attempt} должна отвечать 401`).toBe(
        401,
      );
    }

    const sixth = await page.request.post("/api/auth/login/", {
      data: { email, password: "мимо-6" },
    });
    expect(sixth.status()).toBe(429);
    expect((await sixth.json()).detail).toMatch(/попыток/);

    // даже верный пароль в блокировку не проходит
    const correct = await page.request.post("/api/auth/login/", {
      data: { email, password },
    });
    expect(correct.status()).toBe(429);
  });
});

test.describe("администратор заводит человека", () => {
  test.use({ storageState: statePath("admin") });

  test("созданный пользователь ставит пароль по ссылке и входит", async ({
    page,
    context,
  }) => {
    test.setTimeout(120_000);
    const email = freshEmail();

    await page.goto("/users");
    await expect(page.locator("h1")).toContainText("Пользователи");

    await page.getByRole("button", { name: "Завести пользователя" }).click();
    await page.getByPlaceholder("почта").fill(email);
    await page.getByPlaceholder("ФИО").fill("Приглашённый Директор");
    await page.locator(".users__form select").selectOption("director_sport");

    const [created] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().endsWith("/api/users/") && r.request().method() === "POST",
      ),
      page.getByRole("button", { name: "Завести и пригласить" }).click(),
    ]);
    expect(created.status()).toBe(201);
    await expect(
      page.locator('[data-slot="badge"][data-variant="ok"]').first(),
    ).toContainText(email);

    // в списке он виден и помечен как «пароль не задан»
    await page.getByPlaceholder("Поиск по имени или почте").fill(email);
    await expect(page.locator(".users__table tbody tr")).toHaveCount(1);
    await expect(page.locator(".users__table tbody tr")).toContainText(
      "пароль не задан",
    );

    // ссылку из письма берём из журнала: почтового сервера в контуре нет
    const token = lastLinkToken(email);
    expect(token, "приглашение должно уйти ссылкой").toBeTruthy();

    const fresh = await context
      .browser()!
      .newContext({ storageState: undefined });
    const invited = await fresh.newPage();
    await invited.goto(`/set-password?token=${token}`);
    await invited
      .getByLabel("Новый пароль", { exact: true })
      .fill("Приглашённый!Спорт26");
    await invited
      .getByLabel("Ещё раз", { exact: true })
      .fill("Приглашённый!Спорт26");
    await invited.getByRole("button", { name: "Сохранить пароль" }).click();

    await invited.waitForURL(/\/dashboard/);
    await expect(invited.locator("h1")).toContainText("Спорт");
    await fresh.close();
  });

  test("отключённый пользователь не входит, а запись остаётся", async ({
    page,
    context,
  }) => {
    test.setTimeout(120_000);
    const email = freshEmail();
    const password = "Отключаемый!Тест26";

    // заходим на страницу до запросов: контекст должен «прогреться» cookie
    await page.goto("/dashboard");
    await apiPost(page, "/api/users/", { email, role: "student" });
    const token = lastLinkToken(email);
    await setPasswordByLink(context, token, password);

    const found = await page.request.get(
      `/api/users/?search=${encodeURIComponent(email)}`,
    );
    const list = await found.json();
    expect(
      Array.isArray(list) && list.length === 1,
      `поиск вернул ${JSON.stringify(list)}`,
    ).toBe(true);
    const id = list[0].id;
    const off = await apiPatch<{ is_active: boolean }>(
      page,
      `/api/users/${id}/`,
      { is_active: false },
    );
    expect(off.is_active).toBe(false);

    // отключённый не входит даже с верным паролем
    const other = await context
      .browser()!
      .newContext({ storageState: undefined });
    const denied = await other.request.post("/api/auth/login/", {
      data: { email, password },
    });
    expect([401, 403]).toContain(denied.status());
    await other.close();

    // запись на месте — на ней держится аудит
    const still = await (
      await page.request.get(`/api/users/?search=${encodeURIComponent(email)}`)
    ).json();
    expect(still).toHaveLength(1);
    expect(still[0].is_active).toBe(false);
  });
});

test.describe("обязательная смена пароля", () => {
  test("до смены дальше экрана не пускают", async ({ page, context }) => {
    test.setTimeout(120_000);
    const email = freshEmail();
    const issued = "Выданный!Школой26";

    // администратор заводит и выдаёт временный пароль напрямую
    const admin = await context
      .browser()!
      .newContext({ storageState: statePath("admin") });
    const adminPage = await admin.newPage();
    await adminPage.goto("/dashboard");
    await apiPost(adminPage, "/api/users/", { email, role: "director_exam" });
    const token = lastLinkToken(email);
    await admin.close();
    await setPasswordByLink(context, token, issued);
    // помечаем, что пароль надо сменить — так же выглядит выданный временный
    requirePasswordChange(email);

    await page.goto("/login");
    await page.getByLabel("Почта", { exact: true }).fill(email);
    await page.getByLabel("Пароль", { exact: true }).fill(issued);
    await page.getByRole("button", { name: "Войти", exact: true }).click();

    await expect(page.locator("h1")).toContainText("Смените пароль");

    // API тоже закрыт: обойти форму запросом не выйдет
    const blocked = await page.request.get("/api/students/");
    expect(blocked.status()).toBe(403);
    expect((await blocked.json()).code).toBe("password_change_required");

    await page.getByLabel("Текущий пароль", { exact: true }).fill(issued);
    await page
      .getByLabel("Новый пароль", { exact: true })
      .fill("Свой!Собственный2026");
    await page
      .getByLabel("Ещё раз", { exact: true })
      .fill("Свой!Собственный2026");
    await page.getByRole("button", { name: "Сохранить и продолжить" }).click();

    await expect(page.locator("h1")).toContainText("Экзамены");
    expect((await page.request.get("/api/students/")).status()).toBe(200);
  });
});
