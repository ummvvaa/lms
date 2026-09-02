/**
 * Фаза 47 — сквозная проверка пути ученика на чистой базе.
 *
 * Один непрерывный сценарий: администратор заводит ученика списком,
 * ученик входит по временному паролю и идёт весь путь — анкета, портфолио,
 * цели, подбор, план, подготовка, эссе, стипендии, ресурсы, — а директора
 * подтверждают внесённое.
 *
 * Задача не «проверить функции», а поймать места, где непонятно, что делать
 * дальше: каждая заминка записывается в отчёт. Отдельно считается, сколько
 * шагов от первого входа до готового плана по вузу.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { dropUsers, resetAll } from "../helpers/manage";
import { byKey } from "../helpers/roles";
import { login } from "../helpers/session";

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

test.beforeAll(() => {
  resetAll();
  dropUsers("path.");
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
  await adminPage.goto("/users");
  await adminPage
    .getByRole("button", { name: "Завести учеников списком" })
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
  await learner.getByLabel("Пароль").fill(temporary);
  await learner.getByRole("button", { name: "Войти" }).click();
  step("вход по временному паролю");

  // временный пароль обязан смениться при первом входе
  await expect(learner.getByRole("heading", { name: /пароль/i })).toBeVisible();
  await learner.getByLabel("Текущий пароль").fill(temporary);
  await learner.getByLabel("Новый пароль", { exact: true }).fill(NEW_PASSWORD);
  await learner.getByLabel("Ещё раз").fill(NEW_PASSWORD);
  await learner.getByRole("button", { name: "Сохранить и продолжить" }).click();
  await expect(learner.locator(".pmenu__username")).toBeVisible();
  step("смена временного пароля");

  // подсказка первого входа встречает на первом экране; закрываем её,
  // как это сделал бы человек, — дальше она вызывается из шапки
  const firstRun = learner.getByRole("button", { name: "Пропустить" }).first();
  if (await firstRun.count()) await firstRun.click();

  // --- 3. Лестница пяти шагов -------------------------------------------
  await learner.goto("/journey");
  await expect(learner.locator(".journey__step")).toHaveCount(5);
  step("лестница пяти шагов");

  // разделы, до которых ученик ещё не дошёл, показаны с замком
  const locks = (await (
    await learner.request.get("/api/journey/locks/")
  ).json()) as {
    locks: { path: string; locked: boolean; reason: string }[];
  };
  const planLock = locks.locks.find((row) => row.path === "/plan");
  expect(planLock?.locked, "план до выбора вузов закрыт").toBeTruthy();
  await learner.goto("/plan");
  // с фазы 48 закрытый раздел показывается приглушённым поверх настоящего
  // содержимого, а не пустой заглушкой
  await expect(learner.locator(".dimmed")).toBeVisible();
  await expect(learner.locator(".dimmed__veil")).toBeVisible();
  await expect(
    learner.getByText("Откроется, когда выберете вузы"),
  ).toBeVisible();

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
      .locator(".onboarding__input input, .onboarding__input textarea")
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
  await expect(achievements.getByText("ждёт проверки").first()).toBeVisible();
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
  await row.getByLabel(/Целевой балл/).fill("7.0");
  await row.getByLabel(/Дата экзамена/).fill(examDate);
  const goalProposed = learner.waitForResponse((r) =>
    r.url().includes("/api/suggestions/propose/"),
  );
  await row.getByRole("button", { name: "Сохранить" }).click();
  expect((await goalProposed).status()).toBe(201);
  step("цель по экзамену с датой");

  await learner.goto("/calendar");
  await learner.getByRole("tab", { name: "Ближайшие" }).click();
  await expect(
    learner.locator(".rows__item", { hasText: "IELTS" }).first(),
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

  // и заводит стипендию с ресурсом — ученику будет что найти
  const deadline = new Date(Date.now() + 30 * 24 * 3600 * 1000)
    .toISOString()
    .slice(0, 10);
  const scholarship = await admission.request.post("/api/scholarships/", {
    headers: { "X-CSRFToken": admissionToken },
    data: {
      name: "Грант сквозного пути",
      organizer: "Фонд прогона",
      country: "Канада",
      funding_type: "full",
      for_international: true,
      amount_max: "20000",
      currency: "USD",
      deadline,
    },
  });
  expect(scholarship.ok()).toBeTruthy();

  const categories = (await (
    await admission.request.get("/api/resource-categories/")
  ).json()) as {
    results: { id: number; code: string }[];
  };
  const category =
    categories.results.find((c) => c.code === "applications") ??
    categories.results[0];
  const resource = await admission.request.post("/api/resources/", {
    headers: { "X-CSRFToken": admissionToken },
    data: {
      title: "Памятка сквозного пути",
      category: category.id,
      summary: "Что делать после подачи",
      body: "Первый абзац памятки.",
      reading_minutes: 3,
      is_published: true,
    },
  });
  expect(resource.ok()).toBeTruthy();

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

  await learner.goto("/plan");
  await expect(
    learner.locator(".dimmed"),
    "после выбора вузов замок снят",
  ).toHaveCount(0);
  await expect(learner.getByText("Всего задач")).toBeVisible();
  await expect(learner.getByText("Стратегия поступления")).toBeVisible();

  // задачи плана видны и в общем роадмапе — с пометкой вуза
  await learner.goto("/roadmap");
  await expect(learner.locator(".task").first()).toBeVisible();
  step("задачи плана применены и видны в роадмапе");

  // --- 11. Центр подготовки на пустом банке ------------------------------
  await learner.goto("/prep");
  await expect(learner.getByText(/банк|заданий/i).first()).toBeVisible();
  step("центр подготовки объясняет пустой банк");

  // --- 12. Эссе -----------------------------------------------------------
  await learner.goto("/essays");
  await learner.getByRole("button", { name: "Новое эссе" }).first().click();
  await learner.locator(".essay__type").first().click();
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

  // --- 13. Стипендия: находит, сохраняет, видит дедлайн ------------------
  await learner.goto("/scholarships");
  const card = learner
    .locator(".catcard", { hasText: "Грант сквозного пути" })
    .first();
  await expect(card).toBeVisible();
  const savedResponse = learner.waitForResponse(
    (r) =>
      r.url().includes("/api/scholarships-saved/") &&
      r.request().method() === "POST",
  );
  await card.getByRole("button", { name: "Сохранить стипендию" }).click();
  expect((await savedResponse).status()).toBe(201);
  await learner.goto("/calendar");
  await expect(
    learner.getByText("Стипендия: Грант сквозного пути").first(),
  ).toBeVisible();
  step("стипендия сохранена, дедлайн в календаре");

  // --- 14. Ресурсы --------------------------------------------------------
  await learner.goto("/resources");
  const guide = learner
    .locator(".catcard", { hasText: "Памятка сквозного пути" })
    .first();
  await expect(guide).toBeVisible();
  await guide.getByRole("button", { name: "Читать" }).click();
  await expect(learner.getByText("Первый абзац памятки.")).toBeVisible();
  await learner.getByRole("button", { name: "Прочитано" }).click();
  await expect(
    learner.getByRole("button", { name: "Снять отметку" }),
  ).toBeVisible();
  step("материал прочитан");

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
