/**
 * Рассылка приглашений с журналом писем и дневным пределом (07.10.2026).
 *
 * Предел «Писем в день» опускается до одного и возвращается по умолчанию
 * в конце, даже если проверка упала. Где почта настроена (`EMAIL_HOST`),
 * из двух приглашений первое уходит, второе встаёт в очередь с датой,
 * очередь отменяется кнопкой, повтор без галочки «Всё равно выслать»
 * пропускается. В контуре разработки почты нет: отправка отвечает отказом
 * «Отправка писем не настроена», и проверяется то, что видно и здесь —
 * итог с причинами на экране, запись в журнале «Письма» у человека,
 * фильтр «Не входили ни разу». Очередь на границе суток и настоящая
 * доставка остаются за ручной приёмкой на проде (D91).
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { apiPatch, apiPost, watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

const STAMP = String(Date.now()).slice(-6);
const FIRST = probeEmail(`invite-a-${STAMP}`);
const SECOND = probeEmail(`invite-b-${STAMP}`);

interface MailResult {
  sent: number;
  queued: number;
  failed: number;
  skipped: { email: string; reason: string }[];
  failures?: { email: string; reason: string }[];
  detail: string;
}

/** Почта в контуре есть, если хоть одно письмо ушло или встало в очередь. */
let mailWorks = false;

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  return page;
}

test.afterAll(async ({ browser }) => {
  const admin = await as(browser, "admin");
  await apiPost(admin, "/api/school-rules/mail_daily_limit/reset/", {}).catch(() => undefined);
  await apiPost(admin, "/api/users/mail-queue/cancel/", {}).catch(() => undefined);
  await admin.context().close();
});

test("предел в одно письмо: два приглашения из окна, итог с причинами на экране", async ({ browser }) => {
  const admin = await as(browser, "admin");
  const diag = watch(admin);
  await apiPatch(admin, "/api/school-rules/mail_daily_limit/", { value: 1 });

  await admin.goto("/users");
  await admin.locator(".head__actions").getByLabel("Ещё действия").click();
  await admin.getByRole("menuitem", { name: "Массовое приглашение" }).click();
  const dialog = admin.getByRole("dialog");
  await expect(dialog).toContainText("Массовое приглашение");
  await dialog.getByLabel("Почты через запятую или с новой строки").fill(`${FIRST}\n${SECOND}`);
  await expect(dialog).toContainText("Распознано адресов: 2");
  await dialog.getByLabel("Роль", { exact: true }).selectOption("student");
  const [response] = await Promise.all([
    admin.waitForResponse((r) => r.url().includes("/api/users/invite/") && r.request().method() === "POST"),
    dialog.getByRole("button", { name: "Разослать приглашения" }).click(),
  ]);
  expect(response.status(), await response.text()).toBe(200);
  const result = (await response.json()) as MailResult & { created: number };
  expect(result.created, "обе записи заведены").toBe(2);
  expect(result.sent + result.queued + result.failed, "оба письма учтены").toBe(2);
  mailWorks = result.sent + result.queued > 0;

  // итог на экране — словами сервера, с причинами у неудач
  const outcome = admin.locator(".datacard", { hasText: "Результат рассылки" });
  await expect(outcome).toContainText(result.detail);
  for (const row of result.failures ?? []) await expect(outcome).toContainText(row.reason);

  if (mailWorks) {
    // почта есть: предел пропустил одно письмо, второе ждёт следующего дня
    expect(result.queued, "второе письмо ждёт").toBeGreaterThanOrEqual(1);
    const queue = admin.locator(".datacard", { hasText: "Очередь писем" });
    await expect(queue).toContainText(/В очереди: \d+|Ожидают отправки: \d+/);
    const [cancelled] = await Promise.all([
      admin.waitForResponse((r) => r.url().includes("/api/users/mail-queue/cancel/")),
      queue.getByRole("button", { name: "Отменить очередь" }).click(),
    ]);
    expect(cancelled.status()).toBe(200);
    const pending = (await (await admin.request.get("/api/users/mail-queue/")).json()) as { pending: number };
    expect(pending.pending, "очередь пуста").toBe(0);
  } else {
    // почты нет: отказ с причиной, в очередь ничего не встаёт
    expect(result.failed).toBe(2);
    await expect(admin.locator(".datacard", { hasText: "Очередь писем" })).toHaveCount(0);
  }

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  await admin.context().close();
});

test("повтор без галочки и журнал писем в строке человека", async ({ browser }) => {
  const admin = await as(browser, "admin");
  const repeat = await apiPost<MailResult>(admin, "/api/users/invite/", {
    emails: [FIRST, SECOND],
    role: "student",
    force: false,
  });
  if (mailWorks) {
    // ссылка жива или письмо ждёт — повтор пропускается, а не шлётся второй раз
    expect(repeat.sent, "повторно не отправляется").toBe(0);
    expect(repeat.skipped.length + repeat.queued, "повторы пропущены или ждут").toBe(2);
  } else {
    expect(repeat.failed, "без почты повтор снова отказ").toBe(2);
  }

  // журнал писем у человека — через меню строки; состояние — по факту ссылки
  await admin.goto(`/users?search=${encodeURIComponent(FIRST)}`);
  const row = admin.locator("tr", { hasText: FIRST });
  await expect(row).toBeVisible();
  // ссылка выпускается перед отправкой: состояние «Ссылка выдана» и при отказе почты
  await expect(row).toContainText(/Ссылка выдана|Ждёт смены пароля/);
  await row.getByRole("button", { name: "Ещё действия" }).click();
  await admin.getByRole("menuitem", { name: "Письма" }).click();
  const history = admin.getByRole("dialog");
  await expect(history).toContainText("Письма:");
  await expect(history).toContainText(/Отправлено|Запрошено/);
  if (!mailWorks) await expect(history).toContainText("Отправка писем не настроена");
  await admin.keyboard.press("Escape");

  // «Не входили ни разу» находит приглашённых
  await admin.goto(`/users?search=${encodeURIComponent("invite-")}&never_logged_in=true`);
  await expect(admin.locator("tr", { hasText: FIRST })).toBeVisible();
  await admin.context().close();
});
