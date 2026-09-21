/**
 * Куратор видит только свои группы (фаза 80).
 *
 * Владелец вошёл новым куратором группы «тест» и увидел в шапке кабинета
 * «AMSTERDAM · 0 учеников»: вкладка помнила группу прежнего куратора,
 * выбор уходил в запросы как есть, а у куратора с одной группой нет
 * переключателя, чтобы из этого выбраться.
 *
 * Здесь — глазами куратора:
 * • в памяти вкладки чужая группа — кабинет показывает свою, чужой код
 *   не уходит ни в один запрос и не остаётся ни в адресе, ни в памяти;
 * • во вкладке работал другой человек — память вкладки стирается целиком;
 * • переключение группы перерисовывает карточки без перезагрузки;
 * • администратор передал группу другому — куратор не видит её на
 *   следующем же переходе, без выхода; с одной группой переключателя нет;
 * • групп не осталось — одно пустое состояние, меню работает.
 *
 * Кураторы здесь свои, одноразовые: назначения основного куратора прогона
 * сценарий не трогает — на них стоят остальные сценарии кабинета.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { apiPost } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

const GROUP_A = "PG80A";
const GROUP_B = "PG80B";
const PUPIL = probeEmail("pg80-pupil");
const PUPIL_NAME = "Восьмидесятов";
const ALIEN = "AMSTERDAM";
const OWN_PASSWORD = "Свой!Собственный2026";

interface Group {
  id: number;
  code: string;
}

let groupA: Group;
let groupB: Group;
let curatorId = 0;
let spareId = 0;
let curator: Page;

async function admin(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath("admin") });
  const page = await context.newPage();
  await page.goto("/dashboard");
  return page;
}

const today = () => new Date().toISOString().slice(0, 10);
const yesterday = () => new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);

async function restore(page: Page, model: string, title: string): Promise<boolean> {
  const rows = (await (await page.request.get("/api/archive/?restored=false")).json()) as {
    id: number;
    model: string;
    title: string;
  }[];
  const entry = rows.find((row) => row.model === model && row.title.includes(title));
  if (!entry) return false;
  const token = (await page.context().cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
  const back = await page.request.post(`/api/archive/${entry.id}/restore/`, {
    data: {},
    headers: { "X-CSRFToken": token },
  });
  return back.ok();
}

/** Группа живёт от прогона к прогону: код уникален и среди архивных (как ZURICH в фазе 60). */
async function groupOf(page: Page, code: string): Promise<Group> {
  const list = async () =>
    ((await (await page.request.get("/api/groups/?page_size=100")).json()).results as Group[]).find(
      (g) => g.code === code,
    );
  const found = (await list()) ?? ((await restore(page, "students.StudyGroup", code)) ? await list() : undefined);
  return found ?? (await apiPost<Group>(page, "/api/groups/", { code, grade: 11 }));
}

/** Одноразовый куратор: заведён администратором, вошёл по выданному паролю и сменил его. */
async function freshCurator(browser: Browser, office: Page, local: string): Promise<{ id: number; page: Page }> {
  const email = probeEmail(local);
  const made = await apiPost<{ id: number }>(office, "/api/users/", {
    email,
    role: "curator",
    full_name: `Куратор ${local}`,
  });
  const issued = await apiPost<{ password: string }>(office, `/api/users/${made.id}/temp-password/`, {});

  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/login");
  const entered = await page.request.post("/api/auth/login/", { data: { email, password: issued.password } });
  expect(entered.ok(), `вход ${email}`).toBeTruthy();
  await apiPost(page, "/api/auth/password/change/", {
    current_password: issued.password,
    new_password: OWN_PASSWORD,
  });
  return { id: made.id, page };
}

/**
 * Положить в память вкладки то, что осталось бы от прежней работы.
 * Один раз на вкладку: `window.name` переживает переходы, а сам сценарий
 * проверяет как раз то, что кабинет эту память стирает.
 */
async function remember(page: Page, values: Record<string, string>): Promise<void> {
  await page.addInitScript((seed) => {
    window.localStorage.setItem("first-run-seen", "1");
    if (window.name === "seeded") return;
    window.name = "seeded";
    for (const [key, value] of Object.entries(seed)) window.sessionStorage.setItem(key, value);
  }, values);
}

test("администратор: две группы, ученик и два куратора", async ({ browser }) => {
  const office = await admin(browser);
  groupA = await groupOf(office, GROUP_A);
  groupB = await groupOf(office, GROUP_B);

  const studentsOf = async () =>
    (await (await office.request.get("/api/students/?page_size=500")).json()).results as { email: string }[];
  if (!(await studentsOf()).some((s) => s.email === PUPIL)) {
    if (!(await restore(office, "students.Student", PUPIL_NAME)))
      await apiPost(office, "/api/students/", {
        last_name: PUPIL_NAME,
        first_name: "Свой",
        email: PUPIL,
        group: groupA.id,
        graduation_year: 2027,
      });
  }

  const own = await freshCurator(browser, office, "curator80");
  curatorId = own.id;
  await own.page.context().close();
  const spare = await freshCurator(browser, office, "curator80-spare");
  spareId = spare.id;
  await spare.page.context().close();

  for (const group of [groupA, groupB])
    await apiPost(office, "/api/curator-assignments/", {
      group: group.id,
      curator: curatorId,
      since: yesterday(),
    });
  await office.context().close();
});

test("в памяти вкладки AMSTERDAM — куратор видит свою группу", async ({ browser }) => {
  const context = await browser.newContext();
  curator = await context.newPage();
  await curator.goto("/login");
  const entered = await curator.request.post("/api/auth/login/", {
    data: { email: probeEmail("curator80"), password: OWN_PASSWORD },
  });
  expect(entered.ok()).toBeTruthy();

  // вкладка «своя» (хозяин записан), но группа в ней — чужая: так выглядит
  // снятое назначение и группа, ушедшая в архив
  await remember(curator, { owner: String(curatorId), "curator-group": ALIEN });
  const asked: string[] = [];
  curator.on("request", (request) => {
    if (request.url().includes("/api/")) asked.push(request.url());
  });

  await curator.goto("/dashboard");
  const head = curator.locator(".screenhead, header").filter({ hasText: "Кабинет куратора" }).first();
  await expect(head).toContainText(`${GROUP_A} · 1 ученик`);
  await expect(curator.getByText(ALIEN)).toHaveCount(0);
  // чип «Все мои группы» на месте: первая назначенная — только замена чужому значению
  await expect(curator.getByRole("button", { name: "Все мои группы" })).toBeVisible();
  await expect(curator.locator(".gswitch__chip--on")).toContainText(GROUP_A);

  expect(asked.filter((url) => url.includes(ALIEN)), "чужой код не уходит в запросы").toEqual([]);
  expect(await curator.evaluate(() => window.sessionStorage.getItem("curator-group"))).toBe(GROUP_A);

  // то же из адреса: закладка на чужую группу
  await curator.goto(`/students?group=${ALIEN}`);
  await expect(curator.getByText(PUPIL_NAME).first()).toBeVisible();
  await expect(curator).toHaveURL(new RegExp(`group=${GROUP_A}`));
  expect(asked.filter((url) => url.includes(ALIEN))).toEqual([]);
});

test("во вкладке работал другой человек — память вкладки стёрта целиком", async ({ browser }) => {
  const context = await browser.newContext({ storageState: await curator.context().storageState() });
  const page = await context.newPage();
  await remember(page, {
    owner: "999999",
    "curator-group": GROUP_B,
    "journey.stepbar.hidden": '["essay"]',
  });
  await page.goto("/dashboard");
  await expect(page.locator("body")).toContainText("2 группы, 1 ученик");
  const left = await page.evaluate(() => ({ ...window.sessionStorage }));
  expect(left).toEqual({ owner: String(curatorId) });
  await context.close();
});

test("переключение группы перерисовывает карточки без перезагрузки", async () => {
  await curator.goto("/dashboard");
  await curator.evaluate(() => ((window as unknown as { stayed: boolean }).stayed = true));
  const answered = curator.waitForResponse((r) => r.url().includes(`/api/curator/overview/?group=${GROUP_B}`));
  await curator.getByRole("button", { name: new RegExp(`^${GROUP_B}`) }).click();
  expect((await answered).status()).toBe(200);
  await expect(curator.locator("body")).toContainText(`${GROUP_B} · 0 учеников`);
  // очередь и документы — с числом в заголовке; у пустой группы карточка в одну строку
  await expect(curator.locator(".datacard--folded", { hasText: "Очередь подтверждений" })).toBeVisible();
  expect(await curator.evaluate(() => (window as unknown as { stayed?: boolean }).stayed)).toBe(true);
});

test("группу передали другому — куратор не видит её без выхода, переключателя нет", async ({ browser }) => {
  const office = await admin(browser);
  await apiPost(office, "/api/curator-assignments/", { group: groupB.id, curator: spareId, since: today() });
  await office.context().close();

  // куратор стоял на переданной группе и просто перешёл в другой раздел
  await curator.getByRole("link", { name: "Ученики", exact: true }).first().click();
  await expect(curator.getByText(PUPIL_NAME).first()).toBeVisible();
  await expect(curator.locator(".gswitch__chip")).toHaveCount(0);
  await expect(curator.locator(".gswitch--one")).toContainText(`Группа ${GROUP_A}`);
  await expect(curator.getByText(GROUP_B)).toHaveCount(0);
  await expect(curator).not.toHaveURL(new RegExp(GROUP_B));

  await curator.getByRole("link", { name: "Главная", exact: true }).first().click();
  await expect(curator.locator("body")).toContainText(`${GROUP_A} · 1 ученик`);
  const mine = (await (await curator.request.get(`/api/curator/overview/?group=${GROUP_B}`)).json()) as {
    group: string;
    groups: { code: string }[];
  };
  expect(mine.group).toBe(GROUP_A);
  expect(mine.groups.map((g) => g.code)).toEqual([GROUP_A]);
});

test("групп нет — одно пустое состояние, меню работает", async ({ browser }) => {
  const office = await admin(browser);
  await apiPost(office, "/api/curator-assignments/", { group: groupA.id, curator: spareId, since: today() });
  await office.context().close();

  for (const item of ["Очередь", "Ученики", "Документы", "Главная"]) {
    await curator.getByRole("link", { name: item, exact: true }).first().click();
    await expect(curator.getByText("Вам не назначены группы")).toBeVisible();
    await expect(curator.getByText("Обратитесь к администратору")).toBeVisible();
    await expect(curator.locator(".datacard, .statcard, .gswitch")).toHaveCount(0);
    await expect(curator.getByText(PUPIL_NAME)).toHaveCount(0);
  }
  const home = (await (await curator.request.get("/api/curator/overview/")).json()) as {
    students_total: number;
    groups: unknown[];
  };
  expect(home.students_total).toBe(0);
  expect(home.groups).toEqual([]);

  // профиль — не про группы: он открыт и без назначений
  await curator.goto("/profile");
  await expect(curator.getByText("Вам не назначены группы")).toHaveCount(0);
  await expect(curator.locator("h1")).toBeVisible();
  await curator.context().close();
});
