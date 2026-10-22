/**
 * Профтест в живом браузере (08.10.2026): тесты профориентации файлом.
 *
 * Тест «Карта интересов» грузит посев учителем профориентации
 * (`career@probe.local`, `seed.spec.ts`) и открывает группе CHICAGO. Здесь:
 *
 * 1. Учитель видит тест в «Профтесте», «Кому» показывает назначение.
 * 2. Ученик проходит тест по пять утверждений, сдаёт, видит баллы по шкалам
 *    и не видит разбора — разборы ученику не отдаются (09.10.2026).
 * 3. Учитель видит результат по группе; у куратора профтеста нет: адрес уводит на главную.
 * 4. Журнал профориентации — без оценок: колонка «Профтест», «сдан DD.MM»
 *    при выключенном правиле «нужен разбор»; у ученика в «Оценках» — чип.
 *
 * Кнопка считается рабочей, только если по клику ушёл запрос, ответ 2xx
 * и в консоли пусто — за этим следит `watch()`.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail, probePassword } from "../helpers/roles";
import { apiPatch, apiPost, watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

const TEST_TITLE = "Карта интересов";
const STUDENT_NAME = "Прогон Айгерим";

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  return page;
}

/** Учитель профориентации входит через форму: сохранённой сессии у него нет. */
async function asCareerTeacher(browser: Browser): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.setItem("first-run-seen", "1"));
  await page.goto("/login");
  await page.getByLabel("Почта или логин", { exact: true }).fill(probeEmail("career"));
  await page.getByLabel("Пароль", { exact: true }).fill(probePassword());
  await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/auth/login/")),
    page.getByRole("button", { name: "Войти", exact: true }).click(),
  ]);
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 });
  return page;
}

let attemptId = 0;

test("учитель профориентации: тест в списке, «Кому» показывает назначение группе", async ({ browser }) => {
  const teacher = await asCareerTeacher(browser);
  const diag = watch(teacher);
  // пункт меню есть только у того, кто ведёт профориентацию
  await expect(teacher.locator("nav.shell__menu")).toContainText("Профтест");
  await teacher.goto("/career-tests");
  await expect(teacher.getByRole("heading", { name: "Профтест", exact: true })).toBeVisible();
  await expect(teacher.getByRole("button", { name: "Загрузить тест" })).toBeVisible();

  // у администратора тест — карточка в ряду, у учителя профориентации — строка таблицы
  const row = teacher.locator(".ctl-test, .ctl-row").filter({ hasText: TEST_TITLE }).first();
  await expect(row).toBeVisible();
  await expect(row).toContainText("включён");
  await row.getByRole("button", { name: "Кому" }).click();
  const dialog = teacher.getByRole("dialog");
  await expect(dialog).toContainText("Кому открыт тест");
  await expect(dialog.getByRole("checkbox", { name: /CHICAGO/ })).toBeChecked();
  await teacher.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.failed, "отказы API").toEqual([]);
  await teacher.context().close();
});

test("ученик: проходит по пять утверждений, сдаёт, видит баллы и не видит разбора", async ({ browser }) => {
  const student = await as(browser, "student");
  const diag = watch(student);
  await student.goto("/career");
  await expect(student.getByRole("heading", { name: "Профтест", exact: true })).toBeVisible();
  const tests = student.locator(".datacard", { hasText: "Тесты" }).first();
  await expect(tests).toContainText(TEST_TITLE);
  const open = tests.getByRole("button", { name: /Начать|Продолжить/ }).first();
  await Promise.all([
    student.waitForResponse((r) => /\/api\/career\/my\/(tests\/\d+\/start|attempts\/\d+)\//.test(r.url())),
    open.click(),
  ]);
  await student.waitForURL(/\/career\/\d+$/);
  attemptId = Number(student.url().split("/").pop());
  expect(attemptId).toBeGreaterThan(0);

  // ноутбук: пятёрка утверждений, у каждого — ряд кнопок ответа
  await expect(student.getByText(/Утверждения \d+–\d+ из \d+/)).toBeVisible();
  const items = student.locator(".ctake__item");
  await expect(items).toHaveCount(5);
  for (let i = 0; i < 5; i += 1) {
    const answers = items.nth(i).getByRole("group");
    const first = answers.getByRole("button").first();
    if ((await first.getAttribute("aria-pressed")) !== "true") await first.click();
  }
  // черновик уходит на сервер пачкой с задержкой — ждём все пять ответов
  await expect
    .poll(
      async () =>
        Object.keys(
          ((await (await student.request.get(`/api/career/my/attempts/${attemptId}/`)).json()) as { answers: Record<string, unknown> })
            .answers,
        ).length,
      { timeout: 20_000 },
    )
    .toBeGreaterThanOrEqual(5);

  // остальные утверждения — тем же API, что черновик экрана: 144 клика ничего не добавят
  const attempt = (await (await student.request.get(`/api/career/my/attempts/${attemptId}/`)).json()) as {
    items: { id: number; choices: { id: number }[] }[];
    options: { id: number }[];
    answers: Record<string, { option: number | null; choice: number | null }>;
  };
  const rest = attempt.items
    .filter((item) => !attempt.answers[String(item.id)])
    .map((item, index) =>
      item.choices.length
        ? { item: item.id, choice: item.choices[index % item.choices.length].id }
        : { item: item.id, option: attempt.options[index % attempt.options.length].id },
    );
  expect(rest.length, "неотвеченных осталось меньше всех").toBeLessThan(attempt.items.length);
  await apiPost(student, `/api/career/my/attempts/${attemptId}/answers/`, { answers: rest });

  // после перезагрузки экран открывается на последней странице — там «Сдать тест»
  await student.reload();
  // кнопка сдачи есть в подвале пятёрки и в шапке — жмём ту, что в подвале
  const submit = student.locator(".ctake__foot").getByRole("button", { name: "Сдать тест" });
  await expect(submit).toBeEnabled();
  const [finished] = await Promise.all([
    student.waitForResponse((r) => r.url().includes(`/api/career/my/attempts/${attemptId}/finish/`)),
    submit.click(),
  ]);
  expect(finished.status(), "сдача отвечает").toBe(200);
  await expect(student.getByText("Баллы по шкалам")).toBeVisible();
  await expect(student.locator(".cbars__title").first()).toBeVisible();
  // ключ и разбор ученику не отдаются: только баллы
  await expect(student.getByText("Разбор от учителя")).toHaveCount(0);
  const mine = (await (await student.request.get("/api/career/my/")).json()) as {
    tests: { status: string }[];
    analyses: unknown[];
  };
  expect(mine.tests.some((t) => t.status === "done")).toBeTruthy();
  expect(mine.analyses, "разборов ученику нет").toEqual([]);

  await student.goto("/career");
  const done = student.locator(".datacard", { hasText: "Тесты" }).first();
  await expect(done).toContainText("сдан");
  await expect(done.getByRole("button", { name: "Результат" })).toBeVisible();
  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  await student.context().close();
});

test("учитель видит результат по CHICAGO; куратору профтест закрыт — адрес ведёт на главную", async ({ browser }) => {
  const teacher = await asCareerTeacher(browser);
  await teacher.goto("/career-tests?tab=results&group=CHICAGO");
  const results = teacher.locator(".datacard", { hasText: "Результаты" }).first();
  await expect(results).toBeVisible();
  await expect(results).toContainText(STUDENT_NAME);
  await expect(results).toContainText(/Сдали все открытые тесты: \d+ из \d+/);
  await teacher.context().close();

  // профтест сдают ученики, ведут профориентолог и администратор (22.10.2026):
  // у куратора нет ни пункта меню, ни экрана — прямой адрес уводит на главную
  const curator = await as(browser, "curator");
  await curator.goto("/career-tests?tab=results&group=CHICAGO");
  await expect(curator).toHaveURL(/\/dashboard/);
  await expect(curator.locator(".shell__nav").getByRole("link", { name: "Профтест" })).toHaveCount(0);
  await curator.context().close();
});

test("журнал профориентации без оценок: «Профтест» и «сдан», у ученика в «Оценках» чип", async ({ browser }) => {
  // по умолчанию для «сдан» нужен готовый разбор моделью; ключа в разработке
  // нет — правило выключаем на время проверки и возвращаем по умолчанию
  const admin = await as(browser, "admin");
  await apiPatch(admin, "/api/school-rules/career_pass_needs_analysis/", { value: 0 });

  try {
    const teacher = await asCareerTeacher(browser);
    const diag = watch(teacher);
    await teacher.goto("/journals");
    // журнал той группы, которой открыт тест: у учителя по журналу на группу
    const journal = teacher.locator("table.tbl tbody tr").filter({ hasText: "Профориентация" }).filter({ hasText: "CHICAGO" }).first();
    await expect(journal).toBeVisible();
    await journal.getByRole("button", { name: "Открыть" }).click();
    await teacher.waitForURL(/\/journals\/\d+/);
    await expect(teacher.locator("thead")).toContainText("Профтест");
    // под датами — только дни недели, вида урока «ФО» у предмета без оценок нет (D102)
    await expect(teacher.locator("thead")).not.toContainText("ФО");
    const pupil = teacher.locator("tbody tr", { hasText: STUDENT_NAME }).first();
    await expect(pupil).toContainText("сдан");
    // оценка по профориентации отвечает 403 — у предмета нет оценок
    const lessons = (await (await teacher.request.get(`/api/acad/lessons/?from=2026-09-01&to=2027-06-30`)).json()) as {
      lessons: { id: number; subject: { is_career?: boolean; title: string } }[];
    };
    const lesson = lessons.lessons.find((row) => row.subject.title === "Профориентация");
    expect(lesson, "урок профориентации в расписании учителя").toBeTruthy();
    const csrf = (await teacher.context().cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
    const refused = await teacher.request.post(`/api/acad/lessons/${lesson!.id}/grade/`, {
      data: { student: 0, value: 10 },
      headers: { "X-CSRFToken": csrf },
    });
    expect(refused.status(), "оценка по профориентации отбивается").toBe(403);
    expect(diag.failed.filter((c) => c.status >= 500), "ошибки сервера").toEqual([]);
    await teacher.context().close();

    const student = await as(browser, "student");
    await student.goto("/grades");
    const subjects = student.locator(".datacard", { hasText: "По предметам" }).first();
    await expect(subjects).toContainText("Профориентация");
    await expect(subjects).toContainText("тест сдан");
    await student.context().close();
  } finally {
    await apiPost(admin, "/api/school-rules/career_pass_needs_analysis/reset/", {});
    await admin.context().close();
  }
});
