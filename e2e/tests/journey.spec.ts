/**
 * Фаза 16: сквозной сценарий от очистки базы до восстановления из архива.
 *
 * Один непрерывный путь, как его прошёл бы человек. Задача не «проверить
 * функции», а поймать места, где непонятно, что делать дальше: каждая
 * заминка записывается в отчёт.
 *
 * База очищается перед началом, поэтому сценарий запускается отдельно:
 * `npx playwright test tests/journey.spec.ts`.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { lastLinkToken } from "../helpers/dev-link";
import { dropUsers, resetAll } from "../helpers/manage";
import { byKey } from "../helpers/roles";
import { login } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

/**
 * Шаг 1 сценария — «очистить базу полностью» — выполняет он сам.
 * Иначе путь начинается не с нуля и проверяет не то, что описан.
 */
test.beforeAll(() => {
  resetAll();
  dropUsers("journey.");
});

/** Учётные записи, которые заводит сценарий. Пароль ставим через dev-ссылку. */
const NEW_DIRECTOR = "journey.admission@probe.local";
const NEW_STUDENT = "journey.student@probe.local";
const NEW_PASSWORD = "Сквозной!Сценарий2026";

async function csrfOf(page: Page): Promise<string> {
  return (
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? ""
  );
}

/**
 * Установка пароля по ссылке-приглашению — ровно так это делает человек.
 * Токен берём management-командой: почтового сервера в контуре нет.
 *
 * Своя вкладка на каждого: установка пароля сразу открывает сессию,
 * и в общем контексте она вышибла бы того, кто там уже сидит.
 */
async function setPasswordByLink(
  browser: Browser,
  email: string,
): Promise<void> {
  const token = lastLinkToken(email);
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/login");
  const done = await page.request.post("/api/auth/password/set/", {
    data: { token, new_password: NEW_PASSWORD },
  });
  const ok = done.ok();
  const text = ok ? "" : await done.text();
  await context.close();
  if (!ok) throw new Error(`Не поставили пароль ${email}: ${text}`);
}

test("сквозной путь: от пустой базы до возврата ученика из архива", async ({
  browser,
}) => {
  const notes: string[] = [];

  // --- 1. Очистить базу полностью ---------------------------------------
  // База очищена командой `reset_data --all` с подтверждающей фразой —
  // ровно так это делает администратор школы. Проверяем, что система
  // действительно пуста, а входы при этом работают.
  const admin = await browser.newContext();
  const adminPage = await admin.newPage();
  await login(adminPage, byKey("admin"));
  await expect(adminPage.locator(".pmenu__username")).toBeVisible();

  const emptyStudents = await (
    await adminPage.request.get("/api/students/?page_size=1")
  ).json();
  expect(emptyStudents.count, "после очистки учеников быть не должно").toBe(0);
  const emptyCatalog = await (
    await adminPage.request.get("/api/universities/?page_size=1")
  ).json();
  expect(emptyCatalog.count, "после очистки вузов быть не должно").toBe(0);

  // пустой дашборд объясняет себя, а не показывает белое поле
  await adminPage.goto("/dashboard");
  await expect(adminPage.locator(".empty")).toBeVisible();
  await expect(adminPage.locator(".start")).toBeVisible();

  // --- 2. Создать директора по поступлению и ученика ---------------------
  const csrf = await csrfOf(adminPage);
  const madeDirector = await adminPage.request.post("/api/users/", {
    data: {
      email: NEW_DIRECTOR,
      full_name: "Асем (сквозной)",
      role: "director_admission",
    },
    headers: { "X-CSRFToken": csrf },
  });
  expect(
    madeDirector.ok(),
    "директор должен заводиться из интерфейса",
  ).toBeTruthy();

  const madeUser = await adminPage.request.post("/api/users/", {
    data: { email: NEW_STUDENT, full_name: "Алия (сквозной)", role: "student" },
    headers: { "X-CSRFToken": csrf },
  });
  expect(madeUser.ok()).toBeTruthy();

  // учебная группа и карточка ученика — через интерфейс администратора
  await adminPage.goto("/users");
  // с фазы 31 форма группы открывается кнопкой, а не стоит в потоке
  await adminPage.getByRole("button", { name: "Завести группу" }).click();
  await adminPage.getByLabel("Код группы").fill("11A");
  await adminPage.getByLabel("Класс").fill("11");
  await adminPage.getByLabel("Куратор").fill("Салтанат");
  await adminPage.getByRole("button", { name: "Завести", exact: true }).click();
  // список групп — общий `.rows__list`; обёртки `.groups` с фазы 33 нет
  await expect(
    adminPage.locator(".rows__item", { hasText: "11A" }),
  ).toHaveCount(1);

  await adminPage.goto("/table");
  await adminPage.getByRole("button", { name: "Завести ученика" }).click();
  await adminPage.getByLabel("Фамилия").fill("Ахметова");
  await adminPage.getByLabel("Имя").fill("Алия");
  await adminPage.getByLabel("Почта").fill(NEW_STUDENT);
  await adminPage.getByRole("button", { name: "Завести", exact: true }).click();
  await adminPage.waitForURL(/\/students\/\d+/);
  const studentId = Number(adminPage.url().split("/").pop());
  await expect(adminPage.locator(".card__name")).toContainText("Ахметова Алия");

  // карточка и учётная запись связались сами — по общей почте.
  // Отдельного поля «привязать аккаунт» в интерфейсе нет, и не должно быть
  const card = await (
    await adminPage.request.get(`/api/students/${studentId}/`)
  ).json();
  expect(card.email).toBe(NEW_STUDENT);

  await setPasswordByLink(browser, NEW_DIRECTOR);
  await setPasswordByLink(browser, NEW_STUDENT);

  // --- 3. Стартовый справочник и снятие плашки --------------------------
  const director = await browser.newContext();
  const directorPage = await director.newPage();
  await login(directorPage, {
    key: "x",
    email: NEW_DIRECTOR,
    password: NEW_PASSWORD,
    title: "Асем",
  });

  await directorPage.goto("/directory");
  // пустое состояние с фазы 33 общее для всех разделов (`Empty`)
  await expect(directorPage.locator(".empty")).toBeVisible();
  await directorPage
    .getByRole("button", { name: "Заполнить стартовый справочник" })
    .click();
  await expect
    .poll(
      async () =>
        (await (await directorPage.request.get("/api/catalog/seed/")).json())
          .universities,
    )
    .toBe(20);

  await directorPage.reload();
  const firstRow = directorPage.locator(".dir__row").first();
  await expect(firstRow.locator(".unverified")).toBeVisible();
  const verifiedName = await firstRow.locator(".dir__name").innerText();
  await firstRow.getByRole("button", { name: "Подтвердить данные" }).click();
  await directorPage.reload();
  const verifiedRow = directorPage
    .locator(".dir__row")
    .filter({ hasText: verifiedName })
    .first();
  await expect(
    verifiedRow.getByText("подтверждено", { exact: true }),
  ).toBeVisible();

  // --- 4. Ученик проходит онбординг-квиз --------------------------------
  const learner = await browser.newContext();
  const learnerPage = await learner.newPage();
  await login(learnerPage, {
    key: "x",
    email: NEW_STUDENT,
    password: NEW_PASSWORD,
    title: "Алия",
  });

  await learnerPage.goto("/onboarding");
  await expect(learnerPage.locator(".onboarding__title")).toBeVisible();

  // проходим квиз до конца: у вопроса либо варианты, либо поле ввода
  for (let step = 0; step < 20; step += 1) {
    if (await learnerPage.getByRole("button", { name: "В кабинет" }).count())
      break;
    const options = learnerPage.locator(".onboarding__option");
    if (await options.count()) {
      await options.first().click();
    } else {
      const field = learnerPage.locator(".onboarding__form .input");
      if (!(await field.count())) break;
      await field.fill("6.5");
      await learnerPage.getByRole("button", { name: "Дальше" }).click();
    }
    await learnerPage.waitForTimeout(300);
  }

  const progress = await (
    await learnerPage.request.get("/api/onboarding/")
  ).json();
  expect(progress.answered, "квиз должен сохранять ответы").toBeGreaterThan(0);
  // ответ ученика лёг в профиль, но помечен как непроверенный
  const profileAfterQuiz = await (
    await learnerPage.request.get("/api/students/me/")
  ).json();
  expect(
    profileAfterQuiz.exam,
    "кабинет наполняется ответами квиза",
  ).toBeTruthy();

  // --- 5. Каталог: проценты и добавление двух вузов ----------------------
  await learnerPage.goto("/catalog");
  const cards = learnerPage.locator(".match");
  await expect(cards.first()).toBeVisible();
  await expect(cards.first().locator(".match__value")).toContainText("%");
  // плашка «не подтверждено» стоит рядом с процентом (инвариант №14)
  await expect(learnerPage.locator(".unverified").first()).toBeVisible();

  // карточку держим по номеру: после нажатия «Добавить к себе» текст
  // на ней меняется, и фильтр по этому тексту уводит на соседнюю
  for (let i = 0; i < 2; i += 1) {
    const card = learnerPage.locator(".match").nth(i);
    await card.getByRole("button", { name: "Добавить к себе" }).click();
    await card.getByRole("button", { name: /target/ }).click();
    await expect(card.getByText("уже в вашем списке")).toBeVisible();
  }
  const mine = await (
    await learnerPage.request.get("/api/student-universities/?page_size=50")
  ).json();
  expect(
    mine.count,
    "два вуза должны лечь в список ученика",
  ).toBeGreaterThanOrEqual(2);

  // --- 6. Подбор через ИИ: только вузы справочника -----------------------
  const catalogNames = (
    await (
      await learnerPage.request.get("/api/universities/?page_size=100")
    ).json()
  ).results.map((row: { name: string }) => row.name);
  const picked = await learnerPage.request.post("/api/catalog/pick/", {
    data: { text: "Хочу в Канаду на информатику" },
    headers: { "X-CSRFToken": await csrfOf(learnerPage) },
  });
  expect(picked.ok()).toBeTruthy();
  const pick = await picked.json();
  for (const row of pick.picks ?? []) {
    expect(
      catalogNames,
      `подбор назвал вуз не из справочника: ${row.university_name}`,
    ).toContain(row.university_name);
  }

  // --- 7. Директор видит добавленное учеником на подтверждении -----------
  await directorPage.goto("/dashboard");
  const pending = directorPage
    .locator(".card")
    .filter({ hasText: "Ученики добавили себе" });
  await expect(pending).toBeVisible();
  await expect(pending).toContainText("Ахметова Алия");

  // --- 8. Загрузить файл, отменить импорт, загрузить снова ---------------
  // файл грузит администратор за домен «Экзамены» (фаза 35); директор
  // экзаменов видит загрузку в своей истории и отменяет её
  const uploadContext = await browser.newContext();
  const uploadPage = await uploadContext.newPage();
  await login(uploadPage, byKey("admin"));
  await uploadPage.goto("/import");
  await uploadPage.getByLabel("Домен", { exact: true }).selectOption("exam");

  const upload = async (value: string, name: string) => {
    await Promise.all([
      uploadPage.waitForResponse((r) =>
        r.url().includes("/api/import/preview/"),
      ),
      uploadPage.setInputFiles("input[type=file]", {
        name,
        mimeType: "text/csv",
        buffer: Buffer.from(`email,ielts\n${NEW_STUDENT},${value}\n`, "utf8"),
      }),
    ]);
    const mapping = uploadPage.locator("table.history tbody tr");
    await expect(mapping.first()).toBeVisible();
    await mapping.nth(0).locator("select").selectOption("student");
    await mapping
      .nth(1)
      .locator("select")
      .selectOption("students.ExamProfile.ielts_current");
    await uploadPage
      .getByRole("button", { name: "Показать предпросмотр" })
      .click();
    await uploadPage.getByRole("button", { name: /Применить/ }).click();
    await uploadPage.waitForTimeout(600);
  };

  const examContext = await browser.newContext();
  const examPage = await examContext.newPage();
  await login(examPage, byKey("director_exam"));

  await upload("7.5", "баллы.csv");
  let profile = await (
    await examPage.request.get(`/api/profiles/exam/${studentId}/`)
  ).json();
  expect(profile.ielts_current).toBe("7.5");

  await examPage.goto("/import");
  const batch = examPage
    .locator(".imp__row")
    .filter({ hasText: "баллы.csv" })
    .first();
  await expect(batch).toContainText("администратор за домен «Экзамены»");
  await batch.getByRole("button", { name: "Отменить импорт" }).click();
  await examPage
    .locator(".confirm")
    .getByRole("button", { name: "Отменить импорт" })
    .click();
  await expect(examPage.locator(".imp__report")).toContainText(
    "Возвращено прежних значений",
  );

  profile = await (
    await examPage.request.get(`/api/profiles/exam/${studentId}/`)
  ).json();
  expect(
    profile.ielts_current,
    "отмена импорта должна вернуть прежнее значение",
  ).not.toBe("7.5");

  await upload("8.0", "баллы-заново.csv");
  profile = await (
    await examPage.request.get(`/api/profiles/exam/${studentId}/`)
  ).json();
  expect(profile.ielts_current).toBe("8.0");
  await uploadContext.close();

  // --- 9. Удалить ученика и вернуть его из архива ------------------------
  await adminPage.goto(`/students/${studentId}`);
  await adminPage.getByRole("button", { name: "Удалить ученика" }).click();
  await expect(adminPage.locator(".confirm")).toContainText(
    "Вместе с записью уйдёт связанное",
  );
  await adminPage.getByLabel("Наберите УДАЛИТЬ").fill("УДАЛИТЬ");
  await adminPage
    .locator(".confirm")
    .getByRole("button", { name: "Удалить", exact: true })
    .click();
  await adminPage.waitForURL(/\/table/);

  const afterDelete = await (
    await adminPage.request.get("/api/students/?page_size=10")
  ).json();
  expect(afterDelete.count, "удалённый ученик исчезает из списков").toBe(0);

  await adminPage.goto("/archive");
  const entry = adminPage
    .locator(".arch__row")
    .filter({ hasText: "Ахметова Алия" })
    .first();
  await expect(entry).toBeVisible();
  await entry.getByRole("button", { name: "Восстановить" }).click();
  await expect(adminPage.locator(".arch__flash")).toContainText(
    "Восстановлено записей",
  );

  const afterRestore = await (
    await adminPage.request.get("/api/students/?page_size=10")
  ).json();
  expect(afterRestore.count, "из архива ученик возвращается").toBe(1);
  const backUniversities = await (
    await adminPage.request.get(
      `/api/student-universities/?student=${studentId}&page_size=50`,
    )
  ).json();
  expect(
    backUniversities.count,
    "связи возвращаются вместе с учеником",
  ).toBeGreaterThanOrEqual(2);

  for (const context of [admin, director, learner, examContext])
    await context.close();
  if (notes.length) console.log("Заминки:\n" + notes.join("\n"));
});
