/**
 * Вход в интерфейс и сбор диагностики.
 *
 * Кнопка считается рабочей только если по клику ушёл сетевой запрос,
 * ответ пришёл со статусом 2xx и в консоли не появилось ошибок —
 * поэтому слушатели вешаются до первой навигации.
 */
import type { ConsoleMessage, Page, Request, Response } from "@playwright/test";
import type { RoleAccount } from "./roles";

export interface NetCall {
  method: string;
  url: string;
  status: number;
}

export interface Diagnostics {
  consoleErrors: string[];
  pageErrors: string[];
  calls: NetCall[];
  failed: NetCall[];
  /** Запросы к /api/, ушедшие после отметки. */
  since(mark: number): NetCall[];
  mark(): number;
  reset(): void;
}

/** Шум, не относящийся к приложению: расширения, favicon, HMR Vite. */
function isNoise(text: string): boolean {
  return (
    text.includes("favicon") ||
    text.includes("[vite]") ||
    text.includes("Download the React DevTools") ||
    text.includes("ERR_NETWORK_CHANGED")
  );
}

export function watch(page: Page): Diagnostics {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const calls: NetCall[] = [];
  const failed: NetCall[] = [];

  page.on("console", (message: ConsoleMessage) => {
    if (message.type() !== "error" && message.type() !== "warning") return;
    const text = message.text();
    if (isNoise(text)) return;
    if (message.type() === "error") consoleErrors.push(text);
  });

  page.on("pageerror", (error: Error) => {
    pageErrors.push(error.message);
  });

  page.on("response", (response: Response) => {
    const url = response.url();
    if (!url.includes("/api/")) return;
    const call: NetCall = {
      method: response.request().method(),
      url,
      status: response.status(),
    };
    calls.push(call);
    if (response.status() >= 400) failed.push(call);
  });

  page.on("requestfailed", (request: Request) => {
    const url = request.url();
    if (!url.includes("/api/")) return;
    failed.push({ method: request.method(), url, status: 0 });
  });

  return {
    consoleErrors,
    pageErrors,
    calls,
    failed,
    mark: () => calls.length,
    since: (mark: number) => calls.slice(mark),
    reset() {
      consoleErrors.length = 0;
      pageErrors.length = 0;
      calls.length = 0;
      failed.length = 0;
    },
  };
}

/** Вход через форму на /login — именно так, как это делает человек. */
export async function login(page: Page, account: RoleAccount): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Почта", { exact: true }).fill(account.email);
  await page.getByLabel("Пароль", { exact: true }).fill(account.password);
  await Promise.all([
    page.waitForResponse(
      (r) =>
        r.url().includes("/api/auth/login/") && r.request().method() === "POST",
    ),
    page.getByRole("button", { name: "Войти", exact: true }).click(),
  ]);
  await page.waitForURL(/\/(dashboard|onboarding)/, { timeout: 15_000 });
}

/** Быстрый вход запросом — когда проверяется не форма, а экран за ней. */
export async function loginByApi(
  page: Page,
  account: RoleAccount,
): Promise<void> {
  await page.goto("/login");
  const response = await page.request.post("/api/auth/login/", {
    data: { email: account.email, password: account.password },
  });
  if (!response.ok())
    throw new Error(`Вход ${account.email}: HTTP ${response.status()}`);
}

/**
 * POST к API из теста, с CSRF-заголовком.
 *
 * `page.request` шлёт cookie, но заголовок `X-CSRFToken` не подставляет,
 * и запись отбивается 403 — ровно так же, как отбивалась бы у человека
 * без правильного фронта.
 */
export async function apiPost<T = unknown>(
  page: Page,
  path: string,
  data: unknown,
): Promise<T> {
  const csrf =
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? "";
  const response = await page.request.post(path, {
    data,
    headers: { "X-CSRFToken": csrf },
  });
  if (!response.ok())
    throw new Error(
      `POST ${path} → ${response.status()}: ${await response.text()}`,
    );
  return (await response.json()) as T;
}

/** PATCH к API из теста — с теми же оговорками про CSRF. */
export async function apiPatch<T = unknown>(
  page: Page,
  path: string,
  data: unknown,
): Promise<T> {
  const csrf =
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? "";
  const response = await page.request.patch(path, {
    data,
    headers: { "X-CSRFToken": csrf },
  });
  if (!response.ok())
    throw new Error(
      `PATCH ${path} → ${response.status()}: ${await response.text()}`,
    );
  return (await response.json()) as T;
}

/** DELETE к API из теста — с теми же оговорками про CSRF. */
export async function apiDelete<T = unknown>(
  page: Page,
  path: string,
): Promise<T> {
  const csrf =
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? "";
  const response = await page.request.delete(path, {
    headers: { "X-CSRFToken": csrf },
  });
  if (!response.ok())
    throw new Error(
      `DELETE ${path} → ${response.status()}: ${await response.text()}`,
    );
  return (await response.json()) as T;
}

/**
 * Открыть таблицу директора для правки (фаза 49).
 *
 * С фазы 49 таблица открывается на чтение: данные о себе вносит ученик,
 * директор подтверждает их в очереди. Ручной ввод остался кнопкой
 * «Внести вручную» — и сценарий, который печатает в ячейку, проходит
 * тем же путём, что и человек.
 */
export async function unlockTable(page: Page): Promise<void> {
  const button = page.getByRole("button", { name: "Внести вручную" }).first();
  // кнопка появляется вместе с экраном: без ожидания клик уходит в пустоту,
  // и таблица остаётся на чтении — это и ловил прогон фазы 49
  await button.waitFor({ state: "visible", timeout: 20_000 });
  await button.click();
  await page
    .locator("input.cell:not([readonly])")
    .first()
    .waitFor({ timeout: 20_000 });
}
