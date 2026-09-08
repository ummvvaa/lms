/**
 * Фаза 60 — куратор в живом браузере.
 *
 * В pytest матрица прав закрыта статусами; здесь то, чего оттуда не видно:
 * куратор входит и видит заглушку со своими группами, чужие экраны уводят
 * на кабинет, администратор назначает куратора кнопкой и читает историю,
 * а чужая группа для куратора — 404 из его же сессии.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { apiPost, watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 120_000 });

const FOREIGN_GROUP = "ZURICH";
const FOREIGN_PUPIL = probeEmail("zurich-pupil");

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

async function csrf(page: Page): Promise<Record<string, string>> {
  const cookie = (await page.context().cookies()).find(
    (c) => c.name === "csrftoken",
  );
  return { "X-CSRFToken": cookie?.value ?? "" };
}

interface Group {
  id: number;
  code: string;
  curator_user: { full_name: string } | null;
}

let foreignGroup: Group;

/**
 * Группа из архива, если прошлый прогон убрал её туда.
 *
 * Заводить заново нельзя — код уникален и по архивным записям тоже
 * (тот же капкан, что D13 у посева): группу возвращают, а не подменяют.
 */
async function restore(
  admin: Page,
  model: string,
  title: string,
): Promise<boolean> {
  const rows = (await (
    await admin.request.get("/api/archive/?restored=false")
  ).json()) as { id: number; model: string; title: string }[];
  const entry = rows.find(
    (row) => row.model === model && row.title.includes(title),
  );
  if (!entry) return false;
  const back = await admin.request.post(`/api/archive/${entry.id}/restore/`, {
    data: {},
    headers: await csrf(admin),
  });
  return back.ok();
}
let foreignStudent: number;
let ownStudent: number;

test("администратор: чужая группа и ученик в ней", async ({ browser }) => {
  const admin = await as(browser, "admin");
  await admin.goto("/dashboard");
  // группа и ученик в ней живут от прогона к прогону, как CHICAGO и TOKYO:
  // заново их не завести — код и почта уникальны и среди архивных записей
  // (тот же капкан, что D13 у посева). Чужой для куратора группа остаётся
  // сама: назначение уходит вместе с одноразовой записью прошлого прогона
  const groupsOf = async () =>
    (await (await admin.request.get("/api/groups/?page_size=100")).json())
      .results as Group[];
  let groups = await groupsOf();
  if (!groups.some((g) => g.code === FOREIGN_GROUP)) {
    if (await restore(admin, "students.StudyGroup", FOREIGN_GROUP))
      groups = await groupsOf();
    else
      groups = [
        ...groups,
        await apiPost<Group>(admin, "/api/groups/", {
          code: FOREIGN_GROUP,
          grade: 11,
        }),
      ];
  }
  foreignGroup = groups.find((g) => g.code === FOREIGN_GROUP)!;

  const studentsOf = async () =>
    (await (await admin.request.get("/api/students/?page_size=500")).json())
      .results as { id: number; email: string }[];
  let students = await studentsOf();
  if (!students.some((s) => s.email === FOREIGN_PUPIL)) {
    if (await restore(admin, "students.Student", "Цюрихов"))
      students = await studentsOf();
    else {
      await apiPost(admin, "/api/students/", {
        last_name: "Цюрихов",
        first_name: "Чужой",
        email: FOREIGN_PUPIL,
        grade: 11,
        group: foreignGroup.id,
        graduation_year: 2027,
      });
      students = await studentsOf();
    }
  }
  foreignStudent = students.find((s) => s.email === FOREIGN_PUPIL)!.id;
  ownStudent = students.find((s) => s.email === probeEmail("student"))!.id;
  await admin.context().close();
});

test("куратор: кабинет со своими группами, чужие экраны закрыты", async ({
  browser,
}) => {
  // с фазы 61 заглушки нет: свои группы — переключатель в шапке кабинета
  // и экран «Мои группы»; чужая группа не появляется ни там, ни там
  const curator = await as(browser, "curator");
  const diag = watch(curator);
  await curator.goto("/dashboard");
  await expect(curator.locator("h1")).toContainText("Кабинет куратора");
  const groups = curator.locator(".gswitch");
  for (const code of ["CHICAGO", "TOKYO", "BOSTON"]) {
    await expect(groups).toContainText(code);
  }
  await expect(groups).not.toContainText(FOREIGN_GROUP);
  await curator.goto("/my-groups");
  await expect(curator.locator("h1")).toContainText("Мои группы");
  await expect(curator.locator(".datacard")).toHaveCount(3);
  await expect(curator.locator("body")).not.toContainText(FOREIGN_GROUP);

  // в меню — шесть разделов куратора (с фазы 62 ещё документы и журнал), чужих нет
  const nav = curator.locator("nav.shell__menu");
  await expect(nav.getByRole("link")).toHaveCount(6);
  await expect(nav).not.toContainText("Таблица");
  await expect(nav).not.toContainText("Справочник");

  // прямой адрес чужого экрана уводит на кабинет
  for (const route of ["/table", "/users", "/directory", "/suggestions"]) {
    await curator.goto(route);
    await expect(curator).toHaveURL(/\/dashboard$/);
  }
  // карточка своего ученика открывается — с фазы 61 у куратора она своя
  await curator.goto(`/students/${ownStudent}`);
  await expect(curator).toHaveURL(new RegExp(`/students/${ownStudent}`));
  await expect(curator.locator("h1")).toContainText("Прогон");

  expect(diag.consoleErrors, "ошибки консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);

  // сырой API из той же сессии: своя карточка с внутренними метками,
  // чужая — 404, справочники и настройки — 403
  const own = await curator.request.get(`/api/students/${ownStudent}/`);
  expect(own.status()).toBe(200);
  expect(Object.keys((await own.json()).behavior)).toContain("status");
  const foreign = await curator.request.get(`/api/students/${foreignStudent}/`);
  expect(foreign.status(), "чужой ученик").toBe(404);
  const listing = await (
    await curator.request.get("/api/students/?page_size=500")
  ).json();
  expect(
    (listing.results as { id: number }[]).some((s) => s.id === foreignStudent),
  ).toBe(false);
  for (const path of ["/api/prep/theory/", "/api/exam-kinds/", "/api/users/"]) {
    expect((await curator.request.get(path)).status(), path).toBe(403);
  }
  await curator.context().close();
});

test("очередь общая: куратор подтверждает первым, директор получает 409", async ({
  browser,
}) => {
  const student = await as(browser, "student");
  await student.goto("/dashboard");
  const made = await apiPost<{ suggestions: number[] }>(
    student,
    "/api/suggestions/propose/",
    {
      rows: [
        { model: "students.ExamProfile", field: "ielts_current", value: "7.5" },
      ],
    },
  );
  const proposal = made.suggestions[0];

  const curator = await as(browser, "curator");
  await curator.goto("/dashboard");
  const queue = await (
    await curator.request.get("/api/suggestions/from-students/")
  ).json();
  expect(
    (queue.results as { id: number }[]).some((row) => row.id === proposal),
    "куратор видит предложение своего ученика",
  ).toBe(true);
  const confirmed = await curator.request.post(
    `/api/suggestions/${proposal}/review/`,
    { data: { decision: "confirm" }, headers: await csrf(curator) },
  );
  expect(confirmed.status()).toBe(200);

  const director = await as(browser, "director_exam");
  await director.goto("/dashboard");
  const again = await director.request.post(
    `/api/suggestions/${proposal}/review/`,
    { data: { decision: "confirm" }, headers: await csrf(director) },
  );
  expect(again.status()).toBe(409);
  const body = await again.json();
  expect(body.detail).toContain("Уже подтверждено");
  expect(body.detail).toContain("Куратор");

  // ученик видит статус, но не имя куратора
  const mine = await (
    await student.request.get("/api/suggestions/mine/")
  ).text();
  expect(mine).not.toContain("Асель");
  expect(mine).not.toContain("curator@");

  // возвращаем как было: прогон не должен менять состояние школы
  const reverted = await director.request.post(
    `/api/suggestions/${proposal}/revert/`,
    { data: {}, headers: await csrf(director) },
  );
  expect(reverted.status()).toBe(200);
  await student.context().close();
  await curator.context().close();
  await director.context().close();
});

test("администратор: назначить куратора кнопкой, история раскрывается", async ({
  browser,
}) => {
  const admin = await as(browser, "admin");
  const diag = watch(admin);
  await admin.goto("/users");
  const groupsCard = admin.locator(".datacard", { hasText: "Учебные группы" });
  await expect(groupsCard).toContainText("CHICAGO");
  const chicago = groupsCard.locator(".rows__item", { hasText: "CHICAGO" });
  await expect(chicago).toContainText("куратор Асель Прогон");

  // чужая группа без куратора: кнопка «Назначить», выбор человека и дата
  const zurich = groupsCard.locator(".rows__item", { hasText: FOREIGN_GROUP });
  await expect(zurich).toContainText("куратор не назначен");
  await zurich.getByRole("button", { name: "Назначить" }).first().click();
  const mark = diag.mark();
  await zurich.getByLabel("Куратор").selectOption({ label: "Асель Прогон" });
  await zurich.getByRole("button", { name: "Назначить" }).last().click();
  await expect
    .poll(() =>
      diag
        .since(mark)
        .some(
          (c) =>
            c.method === "POST" &&
            c.url.includes("/api/curator-assignments/") &&
            c.status === 201,
        ),
    )
    .toBe(true);
  await expect(zurich).toContainText("куратор Асель Прогон");

  // история назначений — из меню строки
  await zurich.getByLabel("Ещё действия").click();
  await admin.getByRole("menuitem", { name: "История назначений" }).click();
  await expect(zurich).toContainText("действует");

  // карточка кураторов: у Асель теперь четыре группы
  const curators = admin.locator(".datacard", { hasText: "Кураторы" });
  await expect(curators).toContainText("Асель Прогон");
  await expect(curators).toContainText(FOREIGN_GROUP);

  // после перезагрузки назначение на месте — оно в базе, а не в памяти экрана
  await admin.reload();
  await expect(
    admin
      .locator(".datacard", { hasText: "Учебные группы" })
      .locator(".rows__item", { hasText: FOREIGN_GROUP }),
  ).toContainText("куратор Асель Прогон");
  expect(diag.consoleErrors, "ошибки консоли").toEqual([]);

  // теперь чужой ученик стал своим: 200, а не 404
  const curator = await as(browser, "curator");
  await curator.goto("/dashboard");
  expect(
    (await curator.request.get(`/api/students/${foreignStudent}/`)).status(),
  ).toBe(200);
  await curator.context().close();

  await admin.context().close();
});
