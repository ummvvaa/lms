/**
 * Фаза 36 — три дефекта «до запуска».
 *
 * D1: смена пароля при первом входе десять раз подряд — ни одной потери
 * сессии (через порт 5173, где гонка воспроизводилась). D2: пять неверных
 * паролей запирают запись с понятным отказом, администратор видит блокировку
 * в «Пользователях» и снимает её кнопкой, после чего вход проходит.
 * D3: бэкенд остановлен — приложение показывает полосу «нет связи»
 * и остаётся на экране с черновиком; бэкенд поднят — черновик досылается,
 * входить заново не нужно.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { apiPost, watch, unlockTable } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

const ROOT = path.join(__dirname, "..", "..");
const compose = (...args: string[]) =>
  execFileSync("docker", ["compose", ...args], { cwd: ROOT, encoding: "utf8" });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  await page.goto("/dashboard");
  return page;
}

interface Managed {
  id: number;
  email: string;
}

/** Учётная запись под прогон: заводит администратор, уборка снимает по домену. */
async function ensureUser(
  admin: Page,
  email: string,
  fullName: string,
): Promise<Managed> {
  const list = (await (
    await admin.request.get("/api/users/?search=" + encodeURIComponent(email))
  ).json()) as Managed[] | { results: Managed[] };
  const rows = Array.isArray(list) ? list : list.results;
  const found = rows.find((row) => row.email === email);
  if (found) return found;
  return apiPost<Managed>(admin, "/api/users/", {
    email,
    full_name: fullName,
    role: "director_talent",
  });
}

async function issuePassword(admin: Page, user: Managed): Promise<string> {
  const issued = await apiPost<{ password: string }>(
    admin,
    `/api/users/${user.id}/temp-password/`,
    {},
  );
  return issued.password;
}

test("D1: смена пароля десять раз подряд — сессия ни разу не теряется", async ({
  browser,
}) => {
  const admin = await as(browser, "admin");
  const user = await ensureUser(
    admin,
    probeEmail("p36.change"),
    "Айгерим Прогон",
  );

  for (let round = 1; round <= 10; round += 1) {
    const temp = await issuePassword(admin, user);
    const context = await browser.newContext();
    const page = await context.newPage();
    const diag = watch(page);

    await page.goto("/login");
    await page.getByLabel("Почта", { exact: true }).fill(user.email);
    await page.getByLabel("Пароль", { exact: true }).fill(temp);
    await page.getByRole("button", { name: "Войти", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Смените пароль" }),
    ).toBeVisible();

    const fresh = `Фаза36!Раунд${round}Пароль`;
    await page.locator("#current-password").fill(temp);
    await page.locator("#next-password").fill(fresh);
    await page.locator("#repeat-new-password").fill(fresh);
    // считаем только то, что ушло после смены: `me` со страницы входа
    // до аутентификации отвечает 403 по праву
    const mark = diag.mark();
    await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/api/auth/password/change/") && r.status() === 200,
      ),
      page.getByRole("button", { name: "Сохранить и продолжить" }).click(),
    ]);

    // оболочка поднялась и живёт: ни одного 401/403 после смены
    await expect(page.locator("nav")).toBeVisible();
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await page.goto("/profile");
    await expect(page.locator("h1")).toBeVisible();
    expect(page.url(), `раунд ${round}: увело на вход`).not.toContain("/login");
    const me = await page.request.get("/api/auth/me/");
    expect(me.status(), `раунд ${round}: сессия потеряна`).toBe(200);
    const denied = diag
      .since(mark)
      .filter((c) => c.status === 401 || c.status === 403);
    expect(denied, `раунд ${round}: отказы после смены пароля`).toEqual([]);
    await context.close();
  }
  await admin.context().close();
});

test("D2: блокировка объясняет, когда и к кому; администратор снимает её кнопкой", async ({
  browser,
}) => {
  const admin = await as(browser, "admin");
  const user = await ensureUser(admin, probeEmail("p36.lock"), "Данияр Прогон");
  const temp = await issuePassword(admin, user);
  // остаток от прошлого прогона: блокировка держится час, сценарий должен начинать с чистой
  await apiPost(admin, "/api/auth/locks/unlock/", {
    scope: "account",
    value: user.email,
  });

  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/login");
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    const response = await page.request.post("/api/auth/login/", {
      data: { email: user.email, password: "мимо" },
    });
    expect(response.status(), `попытка ${attempt}`).toBe(401);
  }
  // шестая — отказ с объяснением; верный пароль тоже не проходит
  await page.getByLabel("Почта", { exact: true }).fill(user.email);
  await page.getByLabel("Пароль", { exact: true }).fill(temp);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  const refusal = page.locator("[data-slot='badge'][data-variant='risk']");
  await expect(refusal).toContainText(
    "Слишком много попыток входа в эту учётную запись",
  );
  await expect(refusal).toContainText("Вход откроется через");
  await expect(refusal).toContainText("администратору школы");

  // администратор видит блокировку и снимает её
  await admin.goto("/users");
  const locks = admin
    .locator(".datacard")
    .filter({ hasText: "Блокировки входа" });
  await expect(locks).toBeVisible();
  const row = locks.locator(".locks__row").filter({ hasText: user.email });
  await expect(row).toBeVisible();
  await expect(row).toContainText("вход откроется через");
  await Promise.all([
    admin.waitForResponse(
      (r) => r.url().includes("/api/auth/locks/unlock/") && r.status() === 200,
    ),
    row.getByRole("button", { name: "Снять блокировку" }).click(),
  ]);
  await expect(
    locks.locator(".locks__row").filter({ hasText: user.email }),
  ).toHaveCount(0);

  // вход открыт сразу
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Смените пароль" }),
  ).toBeVisible();
  await context.close();
  await admin.context().close();
});

test("D3: бэкенд остановлен — полоса «нет связи», экран и черновик на месте; поднят — работа продолжается", async ({
  browser,
}) => {
  const page = await as(browser, "director_exam");
  const diag = watch(page);
  await page.goto("/table");
  await unlockTable(page);
  const cell = page.locator('.cell[data-row="0"][data-col="4"]');
  await expect(cell).toBeVisible();
  const list = await (
    await page.request.get("/api/students/?page_size=1&ordering=id")
  ).json();
  const studentId = list.results[0].id as number;
  const before = (
    await (await page.request.get(`/api/profiles/exam/${studentId}/`)).json()
  ).hours_per_week as number | null;

  let stopped = false;
  try {
    compose("stop", "backend");
    stopped = true;
    // черновик набирается без связи и никуда не уходит
    await cell.fill("7");
    await expect(page.locator(".connection")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".connection")).toContainText(
      "Нет связи с сервером",
    );
    await page.waitForTimeout(6_000);
    expect(page.url()).toContain("/table");
    await expect(page.locator("h1")).toContainText("Таблица");
    await expect(cell).toHaveValue("7");
    await expect(page.locator("[data-sync]")).toHaveAttribute(
      "data-sync",
      /offline|dirty|saving/,
    );

    compose("start", "backend");
    stopped = false;
    await expect(page.locator(".connection")).toHaveCount(0, {
      timeout: 90_000,
    });
    // черновик дослан сам, без перезагрузки и без входа
    await expect(page.locator("[data-sync]")).toHaveAttribute(
      "data-sync",
      "saved",
      { timeout: 30_000 },
    );
    expect(page.url()).toContain("/table");
    const saved = await (
      await page.request.get(`/api/profiles/exam/${studentId}/`)
    ).json();
    expect(saved.hours_per_week).toBe(7);
    expect(diag.pageErrors).toEqual([]);
  } finally {
    if (stopped) compose("start", "backend");
    // ждём, пока бэкенд снова отвечает: уборка после прогона ходит в него
    await expect
      .poll(
        async () =>
          (
            await page.request.get("/api/auth/me/").catch(() => null)
          )?.status() ?? 0,
        {
          timeout: 90_000,
        },
      )
      .toBe(200);
  }

  // возвращаем посев к прежнему значению тем же API
  await apiPost(page, "/api/batch/save/", {
    changes: [
      {
        student: studentId,
        model: "students.ExamProfile",
        field: "hours_per_week",
        value: before,
        expected: "7",
      },
    ],
  });
  await page.context().close();
});
