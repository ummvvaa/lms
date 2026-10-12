/**
 * «Пользователи» — одно место о человеке (11.10.2026): окно по центру заводит
 * и правит человека по роли.
 *
 * 1. Ученик без школьной почты: логин «имя.фамилия» и временный пароль, карточка
 *    сразу в «Таблице» и в группе; вход логином со сменой пароля.
 * 2. Ученик со школьной почтой — карточка с почтой.
 * 3. Учитель с предметами и кабинетом: «Завести учителя» в «Учителях» ведёт
 *    в окно; сотрудник с почтой получает ссылку; виден в «Учителях».
 * 4. Куратор с группами: назначение с сегодняшнего дня; «Изменить» — тем же окном.
 * 5. Карточка «Кто это» — только чтение, «Изменить на «Пользователях»» открывает окно.
 *
 * Заведённое сценарием уходит в архив им же: записи — на домене прогона,
 * ученик без почты — архивом карточки и учётной записи.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { apiDelete, apiPost, watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

const STAMP = String(Date.now()).slice(-6);
const PUPIL = { last: "Окнов", first: `Ернар${STAMP}` };
const MAILED = { last: "Почтова", first: "Дана", email: probeEmail(`one-pupil-${STAMP}`) };
const TEACHER = { name: `Окнова Алия ${STAMP}`, email: probeEmail(`one-teacher-${STAMP}`) };
const CURATOR = { name: `Окнов Куратор ${STAMP}`, email: probeEmail(`one-curator-${STAMP}`) };
const NEW_PASSWORD = "Одно!Окно2026";
const GROUP = `OKNO${STAMP}`;

type Made = { id: number; login: string | null; email: string | null; password?: { login: string; password: string } };

const made: { pupil?: Made; mailed?: Made; teacher?: Made; curator?: Made; pupilCard?: number } = {};

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  return page;
}

/** Окно человека: открыть кнопкой и дождаться поля роли. */
async function openPerson(page: Page) {
  await page.goto("/users");
  await page.getByRole("button", { name: "Завести пользователя" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Завести пользователя");
  return dialog;
}

/** «Завести» — ждём ответ записи и возвращаем его. */
async function submit(page: Page, dialog: ReturnType<Page["getByRole"]>): Promise<Made> {
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/api/users/") && r.request().method() === "POST"),
    dialog.getByRole("button", { name: "Завести", exact: true }).click(),
  ]);
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()) as Made;
}

test("ученик без почты: логин и временный пароль, сразу в «Таблице» и группе", async ({ browser }) => {
  const admin = await as(browser, "admin");
  const diag = watch(admin);
  const dialog = await openPerson(admin);
  await dialog.getByLabel("Роль", { exact: true }).selectOption("student");
  await dialog.getByLabel("Фамилия", { exact: true }).fill(PUPIL.last);
  await dialog.getByLabel("Имя", { exact: true }).fill(PUPIL.first);
  await dialog.getByLabel("Учебная группа").selectOption({ label: "CHICAGO · 11" });
  await expect(dialog).toContainText("Параллель 11; год выпуска считается от группы");
  await expect(dialog).toContainText("вход по логину «имя.фамилия»");
  made.pupil = await submit(admin, dialog);
  expect(made.pupil.login, "логин выдался сам").toMatch(/^[a-z0-9.]+$/);
  expect(made.pupil.password?.password, "временный пароль").toBeTruthy();
  // пароль показывается один раз вместе с логином
  const shown = admin.getByRole("dialog");
  await expect(shown).toContainText("Временный пароль");
  await expect(shown).toContainText(made.pupil.login!);
  await admin.keyboard.press("Escape");

  // карточка заведена той же транзакцией: в «Таблице» и в группе
  const found = (await (
    await admin.request.get(`/api/students/?search=${encodeURIComponent(PUPIL.last)}&page_size=10`)
  ).json()) as { results: { id: number; full_name: string; group_code?: string; group: number | null }[] };
  const card = found.results.find((row) => row.full_name.includes(PUPIL.first));
  expect(card, "карточка в реестре").toBeTruthy();
  made.pupilCard = card!.id;
  await admin.goto("/table");
  await expect(admin.locator("body")).toContainText(PUPIL.last);
  await admin.goto(`/students/${card!.id}`);
  await expect(admin.locator(".card__name")).toContainText(`${PUPIL.last} ${PUPIL.first}`);
  await expect(admin.locator("body")).toContainText("CHICAGO");
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  await admin.context().close();
});

test("ученик входит логином и временным паролем, меняет его", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/login");
  await page.getByLabel("Почта или логин", { exact: true }).fill(made.pupil!.login!);
  await page.getByLabel("Пароль", { exact: true }).fill(made.pupil!.password!.password);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page.getByRole("heading", { name: /пароль/i })).toBeVisible({ timeout: 15_000 });
  await page.getByLabel("Текущий пароль").fill(made.pupil!.password!.password);
  await page.getByLabel("Новый пароль", { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel("Повторите пароль").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Сохранить и продолжить" }).click();
  await expect(page.locator(".pmenu__username")).toBeVisible({ timeout: 15_000 });
  await context.close();
});

test("ученик со школьной почтой: карточка с почтой", async ({ browser }) => {
  const admin = await as(browser, "admin");
  const dialog = await openPerson(admin);
  await dialog.getByLabel("Роль", { exact: true }).selectOption("student");
  await dialog.getByLabel("Фамилия", { exact: true }).fill(MAILED.last);
  await dialog.getByLabel("Имя", { exact: true }).fill(MAILED.first);
  await dialog.getByLabel("Учебная группа").selectOption({ label: "TOKYO · 11" });
  await dialog.getByLabel("Школьная почта").fill(MAILED.email);
  made.mailed = await submit(admin, dialog);
  expect(made.mailed.email).toBe(MAILED.email);
  await admin.keyboard.press("Escape");
  const found = (await (
    await admin.request.get(`/api/students/?search=${encodeURIComponent(MAILED.email)}&page_size=10`)
  ).json()) as { results: { id: number; email: string }[] };
  expect(found.results.some((row) => row.email === MAILED.email), "карточка привязана по почте").toBeTruthy();
  await admin.context().close();
});

test("учитель: «Завести учителя» ведёт в окно, предметы чипами, ссылка на пароль, виден в «Учителях»", async ({
  browser,
}) => {
  const admin = await as(browser, "admin");
  const diag = watch(admin);
  await admin.goto("/teachers");
  await admin.getByRole("button", { name: "Завести учителя" }).click();
  await admin.waitForURL(/\/users\?new=teacher/);
  const dialog = admin.getByRole("dialog");
  await expect(dialog.getByLabel("Роль", { exact: true })).toHaveValue("teacher");
  await dialog.getByLabel("Фамилия и имя").fill(TEACHER.name);
  await dialog.getByLabel("Почта или логин").fill(TEACHER.email);
  await dialog.getByLabel("Добавить предмет").selectOption({ label: "Алгебра" });
  await expect(dialog.getByRole("button", { name: "Снять предмет Алгебра" })).toBeVisible();
  await dialog.getByLabel("Кабинет").fill("301");
  made.teacher = await submit(admin, dialog);
  // сотрудник с почтой получает ссылку на пароль — показывается один раз
  await expect(admin.getByRole("dialog")).toContainText("Ссылка на установку пароля");
  await admin.keyboard.press("Escape");

  await admin.goto("/teachers");
  await expect(admin.locator("body")).toContainText(TEACHER.name);
  await expect(admin.locator("body")).toContainText("Алгебра");
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  await admin.context().close();
});

test("куратор с группами: назначение с сегодняшнего дня; «Изменить» тем же окном", async ({ browser }) => {
  const admin = await as(browser, "admin");
  // группы посева уже с кураторами — заводим свою, без куратора
  const boston = await apiPost<{ id: number; code: string }>(admin, "/api/groups/", { code: GROUP, parallel: 11 });

  const dialog = await openPerson(admin);
  await dialog.getByLabel("Роль", { exact: true }).selectOption("curator");
  await dialog.getByLabel("Фамилия и имя").fill(CURATOR.name);
  await dialog.getByLabel("Почта или логин").fill(CURATOR.email);
  await dialog.getByLabel("Добавить группу").selectOption(String(boston.id));
  await expect(dialog.getByRole("button", { name: `Снять группу ${GROUP}` })).toBeVisible();
  await expect(dialog).toContainText("Назначение действует с сегодняшнего дня");
  made.curator = await submit(admin, dialog);
  await admin.keyboard.press("Escape");

  const detail = (await (await admin.request.get(`/api/users/${made.curator.id}/`)).json()) as {
    curator?: { groups: { code: string; since: string }[] };
  };
  expect(detail.curator?.groups.map((g) => g.code)).toEqual([GROUP]);

  // «Изменить» из меню строки — то же окно с заполненными полями
  await admin.goto(`/users?search=${encodeURIComponent(CURATOR.email)}`);
  const row = admin.locator("tr", { hasText: CURATOR.email });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Ещё действия" }).click();
  await admin.getByRole("menuitem", { name: "Изменить" }).click();
  const edit = admin.getByRole("dialog");
  await expect(edit).toContainText("Изменить:");
  await expect(edit.getByRole("button", { name: `Снять группу ${GROUP}` })).toBeVisible();
  await edit.getByLabel("Фамилия и имя").fill(`${CURATOR.name} изм.`);
  const [saved] = await Promise.all([
    admin.waitForResponse((r) => r.url().includes(`/api/users/${made.curator!.id}/`) && r.request().method() === "PATCH"),
    edit.getByRole("button", { name: "Сохранить" }).click(),
  ]);
  expect(saved.status()).toBe(200);
  await admin.reload();
  await expect(admin.locator("tr", { hasText: CURATOR.email })).toContainText("изм.");
  await admin.context().close();
});

test("карточка «Кто это» — только чтение, ссылка ведёт в окно «Изменить»", async ({ browser }) => {
  const admin = await as(browser, "admin");
  await admin.goto(`/students/${made.pupilCard}`);
  const who = admin.locator(".datacard", { hasText: "Кто это" }).first();
  await expect(who).toBeVisible();
  await expect(who.locator("input")).toHaveCount(0);
  await who.getByRole("button", { name: "Изменить на «Пользователях»" }).click();
  await admin.waitForURL(/\/users\?search=.*&edit=\d+/);
  const edit = admin.getByRole("dialog");
  await expect(edit).toContainText("Изменить:");
  await expect(edit.getByLabel("Фамилия", { exact: true })).toHaveValue(PUPIL.last);
  await expect(edit.getByLabel("Роль", { exact: true })).toBeDisabled();
  await admin.keyboard.press("Escape");
  await admin.context().close();
});

test("уборка: заведённые сценарием уходят в архив", async ({ browser }) => {
  const admin = await as(browser, "admin");
  if (made.pupilCard) await apiDelete(admin, `/api/students/${made.pupilCard}/`);
  for (const person of [made.pupil, made.mailed, made.teacher, made.curator])
    if (person?.id) await apiDelete(admin, `/api/users/${person.id}/`);
  await admin.context().close();
});
