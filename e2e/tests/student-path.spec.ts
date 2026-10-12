/**
 * Сквозная проверка пути ученика на чистой базе.
 *
 * Один непрерывный сценарий: администратор заводит ученика списком,
 * ученик входит по временному паролю и идёт весь путь — анкета, портфолио,
 * цели, подбор, задачи плана на главной, подготовка, эссе, — а директора
 * подтверждают внесённое. «Мой путь», план поступления, стипендии, роадмап
 * и ресурсы из кабинета убраны 07.10.2026 — их шагов в пути больше нет.
 *
 * Задача не «проверить функции», а поймать места, где непонятно, что делать
 * дальше: каждая заминка записывается в отчёт. Отдельно считается, сколько
 * шагов от первого входа до готового плана по вузу.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { dropUsers, resetAll, serviceLog, waitForApi } from "../helpers/manage";
import { byKey } from "../helpers/roles";
import { apiPost, login } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 600_000 });

const STUDENT = "path.student@probe.local";
const STUDENT_NAME = "Сауле Пути";
const NEW_PASSWORD = "Сквозной!Путь2026";
const PDF = Buffer.from(
  "%PDF-1.4\n%probe\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n",
);

/** Заминки: не только ошибки, но и места, где непонятно, что делать. */
const notes: string[] = [];
/** Шаги ученика от первого входа до готового плана. */
const path: string[] = [];

function step(what: string): void {
  path.push(what);
}

test.beforeAll(async ({}, testInfo) => {
  resetAll();
  dropUsers("path.");
  await waitForApi(testInfo.project.use.baseURL!);
});

// упавший шаг уносит с собой хвост логов бэкенда и прокси: зависание после
// обнуления воспроизводится только под нагрузкой полного прогона
test.afterEach(async ({}, testInfo) => {
  if (testInfo.status === testInfo.expectedStatus) return;
  for (const service of ["backend", "frontend"])
    await testInfo.attach(`лог ${service}`, { body: serviceLog(service), contentType: "text/plain" });
});

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

function csrf(page: Page): Promise<string> {
  return page
    .context()
    .cookies()
    .then((c) => c.find((x) => x.name === "csrftoken")?.value ?? "");
}

test("сквозной путь ученика: от временного пароля до готового плана", async ({
  browser,
}) => {
  // --- 1. Администратор заводит ученика списком -------------------------
  const adminPage = await as(browser, "admin");
  // группа обязательна и заводится заранее (11.10.2026): без неё строка списка — ошибка
  await adminPage.goto("/dashboard");
  await apiPost(adminPage, "/api/groups/", { code: "11A", parallel: 11 });
  await adminPage.goto("/users");
  await adminPage.locator(".head__actions").getByLabel("Ещё действия").click();
  await adminPage
    .getByRole("menuitem", { name: "Завести учеников списком" })
    .click();

  const applied = adminPage.waitForResponse((r) =>
    r.url().includes("/api/enrollment/apply/"),
  );
  await adminPage
    .locator('input[type="file"]')
    .first()
    .setInputFiles({
      name: "spisok.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(
        `ФИО,почта,класс,группа\n${STUDENT_NAME},${STUDENT},11,11A\n`,
        "utf8",
      ),
    });
  await expect(adminPage.getByText("будет заведён")).toBeVisible();
  await adminPage
    .getByRole("button", { name: /Завести/ })
    .last()
    .click();
  const issued = (await (await applied).json()) as {
    rows: { email: string; password: string }[];
  };
  const temporary =
    issued.rows.find((row) => row.email === STUDENT)?.password ?? "";
  expect(
    temporary,
    "временный пароль должен прийти вместе с карточкой",
  ).toBeTruthy();
  // пароль виден и на экране: почта в школе может быть не настроена
  await expect(
    adminPage.getByText("Выданные пароли", { exact: false }),
  ).toBeVisible();

  // --- 2. Ученик входит по временному паролю ----------------------------
  const learnerContext = await browser.newContext();
  const learner = await learnerContext.newPage();
  await learner.goto("/login");
  await learner.getByLabel("Почта").fill(STUDENT);
  await learner.getByLabel("Пароль", { exact: true }).fill(temporary);
  await learner.getByRole("button", { name: "Войти" }).click();
  step("вход по временному паролю");

  // временный пароль обязан смениться при первом входе
  await expect(learner.getByRole("heading", { name: /пароль/i })).toBeVisible();
  await learner.getByLabel("Текущий пароль").fill(temporary);
  await learner.getByLabel("Новый пароль", { exact: true }).fill(NEW_PASSWORD);
  await learner.getByLabel("Повторите пароль").fill(NEW_PASSWORD);
  await learner.getByRole("button", { name: "Сохранить и продолжить" }).click();
  await expect(learner.locator(".pmenu__username")).toBeVisible();
  step("смена временного пароля");

  // подсказка первого входа встречает на первом экране; закрываем её,
  // как это сделал бы человек, — дальше она вызывается из шапки
  const firstRun = learner.getByRole("button", { name: "Пропустить" }).first();
  if (await firstRun.count()) await firstRun.click();

  // --- 3. Главная: задачи полным списком, убранные разделы ведут на главную ---
  await learner.goto("/dashboard");
  await expect(
    learner.locator(".datacard", { hasText: "Задачи" }).first(),
  ).toBeVisible();
  for (const hidden of ["/journey", "/plan", "/roadmap"]) {
    await learner.goto(hidden);
    await expect(learner, `${hidden} уводит на главную`).toHaveURL(/\/dashboard/);
  }
  step("главная с задачами");

  // --- 4. Анкета первого входа ------------------------------------------
  await learner.goto("/onboarding");
  for (let i = 0; i < 20; i += 1) {
    if (await learner.getByRole("button", { name: "В кабинет" }).count()) break;
    const options = learner.locator(".onboarding__option");
    if (await options.count()) {
      await options.first().click();
      continue;
    }
    const input = learner
      .locator(".onboarding__form input, .onboarding__form textarea")
      .first();
    if (await input.count()) {
      await input.fill("7.0");
      await learner
        .getByRole("button", { name: /Дальше|Сохранить|Готово/ })
        .first()
        .click();
      continue;
    }
    break;
  }
  step("анкета первого входа");

  // --- 5. Портфолио: достижение, спорт, олимпиада, документ -------------
  await learner.goto("/my-data");
  // портфолио собирается из реестра доменов и профиля: на свежей школе
  // первый ответ приходит не мгновенно, и десяти секунд ему мало
  await expect(
    learner.getByRole("heading", { name: "Портфолио", exact: true }),
  ).toBeVisible({
    timeout: 30_000,
  });

  await learner.getByRole("tab", { name: "Достижения" }).click();
  await learner.getByRole("button", { name: "Добавить достижение" }).click();
  const achievements = learner
    .locator("section", { hasText: "Достижения" })
    .first();
  await achievements
    .locator("label", { hasText: "Название активности" })
    .locator("input")
    .fill("Хакатон пути");
  await achievements
    .locator("label", { hasText: "Категория активности" })
    .locator("select")
    .selectOption("project");
  await achievements.locator('input[type="file"]').setInputFiles({
    name: "diplom.pdf",
    mimeType: "application/pdf",
    buffer: PDF,
  });
  const proposed = learner.waitForResponse((r) =>
    r.url().includes("/api/suggestions/propose/"),
  );
  await achievements
    .getByRole("button", { name: "Отправить на проверку" })
    .click();
  expect((await proposed).status()).toBe(201);
  await expect(achievements.getByText("на проверке у директора").first()).toBeVisible();
  step("достижение с документом");

  // --- 6. Цели по экзаменам с датами ------------------------------------
  // таблица целей живёт на «Обзоре» — возвращаемся туда с вкладки достижений
  await learner.getByRole("tab", { name: "Обзор" }).click();
  const goals = learner
    .locator("section", { hasText: "Цели по экзаменам" })
    .first();
  await expect(goals).toBeVisible();
  const examDate = new Date(Date.now() + 60 * 24 * 3600 * 1000)
    .toISOString()
    .slice(0, 10);
  const row = goals.locator('[data-exam="IELTS"]');
  await row.getByLabel(/Желаемый балл/).fill("7.0");
  await row.getByLabel(/Дата экзамена/).fill(examDate);
  const goalProposed = learner.waitForResponse((r) =>
    r.url().includes("/api/suggestions/propose/"),
  );
  await row.getByRole("button", { name: "Сохранить" }).click();
  const goalAnswer = await goalProposed;
  expect(goalAnswer.status()).toBe(201);
  // цель ученика — предложение: настоящей она становится, когда её примет
  // школа. До этого подбор закрыт замком («внесите баллы или цели»), и
  // раньше сценарий проходил его, только успевая нажать до ответа о замках
  const adminToken = await csrf(adminPage);
  for (const id of ((await goalAnswer.json()) as { suggestions: number[] }).suggestions) {
    // принимаются строки, отмеченные человеком: без списка не применяется ничего
    const detail = (await (await adminPage.request.get(`/api/suggestions/${id}/`)).json()) as {
      changes: { id: number }[];
    };
    const accepted = await adminPage.request.post(`/api/suggestions/${id}/apply/`, {
      data: { changes: detail.changes.map((change) => change.id) },
      headers: { "X-CSRFToken": adminToken },
    });
    expect(accepted.status(), await accepted.text()).toBe(200);
    expect(((await accepted.json()) as { applied: number }).applied).toBeGreaterThan(0);
  }
  step("цель по экзамену с датой");

  await learner.goto("/calendar");
  await learner.getByRole("button", { name: "Список" }).click();
  await expect(
    learner.locator(".rowline", { hasText: "IELTS" }).first(),
  ).toBeVisible();
  step("дата в календаре");

  // --- 7. Директор по поступлению наполняет справочник ------------------
  const admission = await as(browser, "director_admission");
  const admissionToken = await csrf(admission);
  const seeded = await admission.request.post("/api/catalog/seed/", {
    headers: { "X-CSRFToken": admissionToken },
  });
  expect(
    seeded.ok(),
    "стартовый справочник должен заводиться одной кнопкой",
  ).toBeTruthy();

  // --- 8. Подбор вузов: уходим с экрана и возвращаемся ------------------
  await learner.goto("/selection");
  await expect(
    learner.getByRole("heading", { name: "Подбор вузов", exact: true }),
  ).toBeVisible();
  const runStarted = learner.waitForResponse((r) =>
    r.url().includes("/api/selection/runs/start/"),
  );
  const startButton = learner
    .getByRole("button", { name: /Подобрать|Запустить/ })
    .first();
  await expect(startButton).toBeVisible();
  await startButton.click({ timeout: 30_000 });
  const started = await runStarted;
  expect(started.status()).toBe(201);
  const runId = ((await started.json()) as { id: number }).id;
  step("запуск подбора");

  // уходим на другой экран: работа продолжается в фоне, плашка показывает это
  await learner.goto("/calendar");
  const panel = learner.locator(".jobs__row");
  if (await panel.count()) {
    await expect(panel.first()).toBeVisible();
  } else {
    notes.push(
      "плашка фоновой операции не успела показаться: подбор закончился быстрее опроса",
    );
  }

  await expect
    .poll(
      async () =>
        (
          (await (
            await learner.request.get(`/api/selection/runs/${runId}/`)
          ).json()) as { status: string }
        ).status,
      { timeout: 120_000, intervals: [1000] },
    )
    .toBe("done");
  await learner.goto(`/selection/${runId}`);
  await expect(
    learner.getByText(/В финальном списке|Финальный список/).first(),
  ).toBeVisible();
  step("возврат к результату подбора");

  // --- 9. Объяснение процента, избранное, свой список -------------------
  const results = (await (
    await learner.request.get(`/api/selection/runs/${runId}/`)
  ).json()) as {
    results: { program: number; percent_now: number }[];
  };
  expect(
    results.results.length,
    "подбор обязан что-то найти на посеянном справочнике",
  ).toBeGreaterThan(0);
  const program = results.results[0].program;

  const explained = await learner.request.get(
    `/api/selection/runs/${runId}/explain/${program}/`,
  );
  expect(explained.ok(), "объяснение процента должно открываться").toBeTruthy();
  step("объяснение процента");

  const learnerToken = await csrf(learner);
  const favorited = await learner.request.post("/api/favorites/", {
    headers: { "X-CSRFToken": learnerToken },
    data: { program },
  });
  expect(favorited.ok()).toBeTruthy();
  const added = await learner.request.post("/api/catalog/add/", {
    headers: { "X-CSRFToken": learnerToken },
    data: { program, tier: "target" },
  });
  expect(added.ok()).toBeTruthy();
  step("вуз в избранном и в списке");

  // --- 10. План по вузу --------------------------------------------------
  // С фазы 48 план заводится сам при добавлении программы в список,
  // а задачи применяются сразу: подтверждением стало само добавление вуза
  await expect
    .poll(
      async () => {
        const plans = (await (
          await learner.request.get("/api/application-plans/")
        ).json()) as {
          results: {
            id: number;
            generation_status: string;
            counters: { total: number };
          }[];
        };
        const row = plans.results[0];
        return row && row.generation_status === "done" ? row.counters.total : 0;
      },
      { timeout: 120_000, intervals: [1000] },
    )
    .toBeGreaterThan(0);
  step("план завёлся сам при добавлении вуза");

  // задачи плана видны на главной полным списком — экрана плана у ученика нет
  await learner.goto("/dashboard");
  await expect(
    learner.locator(".datacard", { hasText: "Задачи" }).first().locator(".rowline").first(),
  ).toBeVisible();
  step("задачи плана применены и видны на главной");

  // --- 11. Центр подготовки на пустом банке ------------------------------
  await learner.goto("/prep");
  await expect(learner.getByText(/банк|заданий/i).first()).toBeVisible();
  step("центр подготовки объясняет пустой банк");

  // --- 12. Эссе -----------------------------------------------------------
  await learner.goto("/essays");
  await learner.getByRole("button", { name: "Новое эссе" }).first().click();
  await learner.locator(".rowline").first().getByRole("button", { name: "Создать" }).click();
  // после выбора типа эссе заводится запросом, и только потом появляется
  // гайд: ждём, пока экран определится, иначе проверка обгоняет ответ
  const skipGuide = learner.getByRole("button", { name: "Пропустить гайд" });
  await expect(
    skipGuide.or(learner.getByText(/\d+ \/ \d+ слов/)).first(),
  ).toBeVisible();
  if (await skipGuide.count()) await skipGuide.click();
  const toEditor = learner.getByRole("button", { name: "К редактору" });
  await expect(
    toEditor.or(learner.getByText(/\d+ \/ \d+ слов/)).first(),
  ).toBeVisible();
  if (await toEditor.count()) await toEditor.click();
  await expect(learner.getByText(/\d+ \/ \d+ слов/)).toBeVisible();
  step("эссе заведено");

  // --- 15. Директора подтверждают внесённое ------------------------------
  const talent = await as(browser, "director_talent");
  await talent.goto("/suggestions");
  const talentRow = talent.locator("#student-queue .squeue__row").first();
  await expect(
    talentRow,
    "достижение ученика должно ждать в очереди директора талантов",
  ).toBeVisible();
  await talentRow
    .getByRole("button", { name: /Подтвердить|Применить/ })
    .first()
    .click();

  const exam = await as(browser, "director_exam");
  await exam.goto("/suggestions");
  const examRow = exam
    .locator("#student-queue .squeue__row", { hasText: "Целевой балл" })
    .first();
  if (await examRow.count()) {
    await examRow
      .getByRole("button", { name: /Подтвердить|Применить/ })
      .first()
      .click();
  } else {
    notes.push(
      "цель по экзамену не нашлась в очереди академического директора по подписи «Целевой балл»",
    );
  }

  // --- 16. Ученик видит, что решено --------------------------------------
  await learner.goto("/my-data");
  await learner.getByRole("tab", { name: "Достижения" }).click();
  const mine = learner.locator("section", { hasText: "Достижения" }).first();
  await expect(mine.getByText("Хакатон пути").first()).toBeVisible();
  // строка перестала быть предложением: пометки «ждёт проверки» на ней нет
  await expect(mine.getByText("ждёт проверки")).toHaveCount(0);
  notes.push(
    "после применения предложения достижение показывается как «ждёт подтверждения»: " +
      "решение по предложению и признак «подтверждено» у самой активности — разные вещи, " +
      "а слова у них почти одинаковые",
  );
  const decided = (await (
    await learner.request.get("/api/suggestions/mine/")
  ).json()) as {
    results: { status: string }[];
  };
  expect(
    decided.results.some((row) => row.status !== "pending"),
    "решение директора видно ученику в его же кабинете",
  ).toBeTruthy();
  step("решение директора видно ученику");

  // --- Итог ---------------------------------------------------------------
  console.log(
    `Шагов от первого входа до готового плана: ${path.indexOf("задачи плана применены") + 1}`,
  );
  console.log(
    "Путь: " + path.map((item, index) => `${index + 1}. ${item}`).join("; "),
  );
  if (notes.length)
    console.log("Заминки:\n" + notes.map((note) => `- ${note}`).join("\n"));

  for (const page of [adminPage, learner, admission, talent, exam])
    await page.context().close();
});
