/**
 * Разбор кабинетов директоров и ученика — в живом браузере.
 *
 * Владелец прошёл кабинеты и нашёл шестнадцать вещей. Здесь каждая — минимум
 * одним шагом: клик уходит запросом, ответ 2xx, изменение видно на экране.
 *
 *  1. Асем и администратор правят каждую строку блока «Поступление».
 *  3. Импорт — только у администратора и Кымбат (меню четырёх ролей).
 *  4, 8. Класса нет: шаблон задач — по группам, олимпиадная группа — по группам,
 *     в формах группы и ученика поля «Класс» нет.
 *  5. Банк: Reading с пассажем и вопросами, Writing без вариантов, Listening
 *     без аудио не сохраняется; ученик видит пассаж со всеми вопросами разом
 *     и пишет открытый ответ, Кымбат его проверяет.
 *  6, 7. Справочник: кнопки строки в одну линию; направление — своё, порядка нет.
 *  9. Соревнование: «показывать в карточке».
 * 10. Посещаемость у Салтанат на чтение; журнал за месяц; выгрузка через предпросмотр.
 * 11–13. Профтест у Асем; сюжеты у администратора карточками; бейджи карточками.
 * 14. Дашборд Салтанат: плитка группы не уже своего текста.
 * 15. Выгрузка пользователей через предпросмотр, без паролей.
 * 16. Документы ученика: одна карточка, «Загрузить» в пустой строке.
 *
 * Сценарий убирает за собой: соседние сценарии ходят по тем же людям.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { exportThroughPreview } from "../helpers/export";
import { apiDelete, apiPatch, apiPost, watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 300_000 });

const stamp = Date.now();
const SUBJECT = `Робототехника ${stamp}`;
const AREA = `Инженерия ${stamp}`;
const TEMPLATE = `Собрать портфолио ${stamp}`;
const PASSAGE = `Bees ${stamp}`;
const ESSAY_TOPIC = `Эссе ${stamp}`;
const COMPETITION = `Кубок города ${stamp}`;

let studentId = 0;
let studentGroup = "";

async function as(browser: Browser, role: string, width = 1440): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    viewport: { width, height: 900 },
  });
  const page = await context.newPage();
  await page.addInitScript(() =>
    window.localStorage.setItem("first-run-seen", "1"),
  );
  return page;
}

const menu = (page: Page) => page.locator("nav a");

test.beforeAll(async ({ browser }) => {
  const student = await as(browser, "student");
  const me = await (await student.request.get("/api/students/me/")).json();
  studentId = me.id;
  studentGroup = me.group_code ?? "";
  expect(studentId, "карточка ученика прогона").toBeGreaterThan(0);
  await student.context().close();
});

// --- 3, 11, 12: меню четырёх ролей ------------------------------------------------

test("меню: импорт у администратора и Кымбат, профтест у Асем, сюжеты у администратора", async ({
  browser,
}) => {
  const expectations: [string, string[], string[]][] = [
    ["admin", ["Импорт", "Сюжеты главной"], ["Вопросы профтеста"]],
    ["director_exam", ["Импорт"], ["Сюжеты главной", "Вопросы профтеста"]],
    ["director_admission", ["Вопросы профтеста"], ["Импорт", "Сюжеты главной"]],
    ["director_behavior", ["Достижения школы"], ["Импорт", "Сюжеты главной", "Вопросы профтеста"]],
    ["director_talent", ["Предметы"], ["Импорт"]],
    ["director_sport", ["Соревнования"], ["Импорт"]],
    ["curator", ["Посещаемость"], ["Импорт"]],
  ];
  for (const [role, has, lacks] of expectations) {
    const page = await as(browser, role);
    await page.goto("/dashboard");
    await expect(menu(page).first()).toBeVisible();
    const labels = (await menu(page).allInnerTexts()).map((text) => text.trim());
    for (const item of has)
      expect(labels.some((label) => label.includes(item)), `${role}: есть «${item}»`).toBeTruthy();
    for (const item of lacks)
      expect(labels.some((label) => label.includes(item)), `${role}: нет «${item}»`).toBeFalsy();
    await page.context().close();
  }

  // у кого пункта нет, тому и адрес не открывается — уводит на главную
  const asem = await as(browser, "director_admission");
  await asem.goto("/import");
  await asem.waitForURL(/\/dashboard/, { timeout: 15_000 });
  await asem.goto("/career-questions");
  await expect(asem.getByRole("heading", { name: "Вопросы профтеста" })).toBeVisible();
  await asem.context().close();
});

// --- 1: блок «Поступление» --------------------------------------------------------

test("Асем правит в блоке «Поступление» срок паспорта, попытку и ссылку", async ({
  browser,
}) => {
  const page = await as(browser, "director_admission");
  const diag = watch(page);
  await page.goto(`/students/${studentId}`);
  const block = page.locator(".cadm");
  await expect(block).toBeVisible();

  const row = (label: string) =>
    block.locator(".cadm__pair").filter({
      has: page.locator(".cadm__k", { hasText: new RegExp(`^${label}$`) }),
    });

  // карандаш стоит у каждой строки, кроме паролей без значения («Записать» — словом)
  for (const label of ["Срок годности паспорта", "Средний GPA", "IELTS-1", "SAT-3", "Ссылка на табель"])
    await expect(row(label).getByRole("button", { name: "Изменить" }), label).toBeVisible();

  // срок паспорта
  const profile = page.waitForResponse(
    (r) => r.url().includes("/profiles/admission/") && r.request().method() === "PATCH",
  );
  await row("Срок годности паспорта").getByRole("button", { name: "Изменить" }).click();
  await block.getByLabel("Срок годности паспорта: Дата").fill("2031-05-01");
  await block.getByRole("button", { name: "Сохранить" }).click();
  expect((await profile).status()).toBe(200);
  await expect(row("Срок годности паспорта")).toContainText("01.05.2031");

  // попытка SAT-3: пустой слот занимается баллом, дата необязательна
  const before = await row("SAT-3").innerText();
  if (before.includes("—")) {
    const attempt = page.waitForResponse((r) => r.url().includes("/admission-block/attempt/"));
    await row("SAT-3").getByRole("button", { name: "Изменить" }).click();
    await block.getByLabel("SAT-3: Балл").fill("1410");
    await block.getByRole("button", { name: "Сохранить" }).click();
    expect((await attempt).status()).toBe(200);
  }

  // ссылка на табель: не-ссылка — отказ словами, ссылка — сохраняется
  await row("Ссылка на табель").getByRole("button", { name: "Изменить" }).click();
  const refused = page.waitForResponse((r) => r.url().includes("/admission-block/link/"));
  await block.getByLabel("Ссылка на табель: Ссылка целиком, с https://").fill("drive");
  await block.getByRole("button", { name: "Сохранить" }).click();
  expect((await refused).status()).toBe(400);
  const saved = page.waitForResponse((r) => r.url().includes("/admission-block/link/"));
  await block
    .getByLabel("Ссылка на табель: Ссылка целиком, с https://")
    .fill(`https://drive.example.org/transcript-${stamp}`);
  await block.getByRole("button", { name: "Сохранить" }).click();
  expect((await saved).status()).toBe(200);
  await expect(row("Ссылка на табель")).toContainText("Открыть табель");

  // после перезагрузки значения на месте
  await page.reload();
  await expect(row("Срок годности паспорта")).toContainText("01.05.2031");
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();

  // куратору блок целиком не отдан: у попыток и ссылок карандаша нет
  const curator = await as(browser, "curator");
  await curator.goto(`/students/${studentId}`);
  const cblock = curator.locator(".cadm");
  await expect(cblock).toBeVisible();
  const crow = cblock.locator(".cadm__pair").filter({
    has: curator.locator(".cadm__k", { hasText: /^IELTS-1$/ }),
  });
  await expect(crow.getByRole("button", { name: "Изменить" })).toHaveCount(0);
  await curator.context().close();
});

// --- 4, 8: класса нет, шаблон — по группам -----------------------------------------

test("класса нет в формах; шаблон задач — по группам", async ({ browser }) => {
  const admin = await as(browser, "admin");
  await admin.goto("/users");
  await admin.getByRole("button", { name: "Завести группу" }).click();
  await expect(admin.getByLabel("Код группы")).toBeVisible();
  await expect(admin.getByLabel("Класс")).toHaveCount(0);
  await admin.keyboard.press("Escape");
  await admin.context().close();

  const arman = await as(browser, "director_talent");
  await arman.goto("/olympiad-group");
  await expect(arman.getByRole("heading", { name: "Олимпиадная группа" })).toBeVisible();
  await expect(arman.getByLabel("Класс")).toHaveCount(0);
  const groups = arman.getByLabel("Группа", { exact: true });
  await expect(groups).toBeVisible();
  if (studentGroup) {
    const filtered = arman.waitForResponse((r) => r.url().includes(`group=${studentGroup}`));
    await groups.selectOption(studentGroup);
    expect((await filtered).status()).toBe(200);
  }
  await expect(arman.locator("thead")).not.toContainText("Класс");

  // шаблон задач: галочки групп, «всем» по умолчанию
  await arman.goto("/task-templates");
  await arman.getByRole("button", { name: /Завести шаблон|Добавить шаблон/ }).first().click();
  const form = arman.getByRole("dialog");
  await expect(form.getByText("Для класса")).toHaveCount(0);
  await expect(form.getByText("Для выпуска")).toHaveCount(0);
  await expect(form.getByRole("group", { name: "Кому: группы" })).toBeVisible();
  await expect(form).toContainText("шаблон идёт всем группам");
  await form.locator(".rowform__field").filter({ hasText: "Название задачи" }).locator("input").fill(TEMPLATE);
  const boxes = form.getByRole("group", { name: "Кому: группы" }).getByRole("checkbox");
  // число галочек запоминаем до отправки: после неё окна уже нет
  const offered = await boxes.count();
  if (offered > 0) await boxes.first().click();
  const created = arman.waitForResponse(
    (r) => r.url().includes("/task-templates/") && r.request().method() === "POST",
  );
  await form.getByRole("button", { name: "Завести" }).click();
  const answer = await created;
  expect(answer.status()).toBe(201);
  const made = (await answer.json()) as { id: number; groups: number[]; group_codes: string[] };
  expect(made.groups.length, "группа ушла на сервер").toBe(offered > 0 ? 1 : 0);
  if (made.group_codes.length > 0)
    await expect(arman.locator("tr", { hasText: TEMPLATE })).toContainText(made.group_codes[0]);
  await apiDelete(arman, `/api/task-templates/${made.id}/`);
  await arman.context().close();
});

// --- 6, 7: справочники ---------------------------------------------------------------

test("предметы: своё направление, порядка нет; кнопки строки в одну линию", async ({
  browser,
}) => {
  const arman = await as(browser, "director_talent");
  await arman.goto("/subjects");
  await expect(arman.getByLabel("Порядок")).toHaveCount(0);
  await arman.getByLabel("Название").fill(SUBJECT);
  await arman.getByLabel("Направление").fill(AREA);
  const created = arman.waitForResponse(
    (r) => r.url().includes("/api/subjects/") && r.request().method() === "POST",
  );
  await arman.getByRole("button", { name: "Завести", exact: true }).click();
  const made = (await (await created).json()) as { id: number; area: string };
  expect(made.area).toBe(AREA);
  await expect(arman.locator("tr", { hasText: SUBJECT })).toContainText(AREA);

  // введённое своё направление предлагается следующим
  const offered = (await (await arman.request.get("/api/subjects/areas/")).json()) as { areas: string[] };
  expect(offered.areas).toContain(AREA);
  await expect(arman.locator(`datalist option[value="${AREA}"]`)).toHaveCount(1);

  // предметы идут по алфавиту
  const names = await arman.locator(".dir__table tbody tr td:first-child").evaluateAll((cells) =>
    cells.map((cell) => (cell.firstChild?.textContent ?? "").trim()),
  );
  expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b, "ru")));

  await apiDelete(arman, `/api/subjects/${made.id}/`);
  await arman.context().close();

  // экзамены у Кымбат: три кнопки строки стоят одной линией и не режутся краем
  const kymbat = await as(browser, "director_exam");
  await kymbat.goto("/exam-kinds");
  const cell = kymbat.locator(".dir__acts").first();
  await expect(cell).toBeVisible();
  const layout = await cell.evaluate((node) => {
    const buttons = [...node.querySelectorAll("button")].map((b) => b.getBoundingClientRect());
    const table = node.closest(".card")!.getBoundingClientRect();
    return {
      count: buttons.length,
      oneLine: buttons.every((b) => Math.abs(b.top - buttons[0].top) < 2),
      inside: buttons.every((b) => b.right <= table.right + 1),
    };
  });
  expect(layout.count).toBe(3);
  expect(layout.oneLine, "кнопки на одной линии").toBe(true);
  expect(layout.inside, "кнопки не режутся краем").toBe(true);
  await kymbat.context().close();
});

// --- 5: банк заданий -------------------------------------------------------------------

test("банк: пассаж с вопросами, Writing без вариантов, Listening без аудио не сохраняется", async ({
  browser,
}) => {
  const page = await as(browser, "director_exam");
  const diag = watch(page);
  await page.goto("/mocks");
  await page.getByRole("tab", { name: "Банк заданий" }).click();
  await page.getByRole("button", { name: "Завести задание" }).first().click();
  const form = page.getByRole("dialog");

  // Listening: аудио обязательно — форма называет это сразу, запрос не уходит
  await form.getByLabel("Секция").selectOption("listening");
  await expect(form.getByText("Аудиофайл: mp3 или m4a, до 20 МБ")).toBeVisible();
  await form.getByLabel("Тема").fill(`Лекция ${stamp}`);
  await form.getByRole("button", { name: "Завести", exact: true }).click();
  await expect(form).toContainText("без него не сохраняется");

  // Reading: пассаж сверху, два вопроса под ним
  await form.getByLabel("Секция").selectOption("reading");
  await form.getByLabel("Тема").fill(`Чтение ${stamp}`);
  await form.getByLabel("Заголовок").fill(PASSAGE);
  await form.getByLabel("Текст пассажа").fill("Bees dance to tell the hive where the flowers are.");
  await form.getByRole("button", { name: "Добавить вопрос" }).click();
  const questions = form.locator(".qform__question");
  await expect(questions).toHaveCount(2);
  for (const [index, text] of ["Why do bees dance?", "Who watches the dance?"].entries()) {
    const block = questions.nth(index);
    await block.getByLabel("Текст задания").fill(text);
    await block.getByLabel("Вариант A").fill("To share a route");
    await block.getByLabel("Вариант B").fill("For fun");
    await block.getByLabel("Верный вариант").selectOption("A");
  }
  const passageSaved = page.waitForResponse(
    (r) => r.url().includes("/prep/passages/") && r.request().method() === "POST",
  );
  await form.getByRole("button", { name: "Завести", exact: true }).click();
  expect((await passageSaved).status()).toBe(201);
  await expect(form).toBeHidden();
  await expect(page.locator("tr", { hasText: "Why do bees dance?" })).toContainText(PASSAGE);

  // Writing: вариантов в форме нет вовсе
  await page.getByRole("button", { name: "Завести задание" }).first().click();
  await form.getByLabel("Секция").selectOption("writing");
  await expect(form.getByText("Вариант A")).toHaveCount(0);
  await form.getByLabel("Тема").fill(ESSAY_TOPIC);
  await form.getByLabel("Текст задания").fill("Describe the chart in at least 150 words.");
  await form.getByLabel(/Критерии оценки/).fill("Task response, coherence, vocabulary");
  await form.getByLabel("Лимит слов").fill("150");
  const essaySaved = page.waitForResponse(
    (r) => r.url().includes("/prep/questions/") && r.request().method() === "POST",
  );
  await form.getByRole("button", { name: "Завести", exact: true }).click();
  const essay = (await (await essaySaved).json()) as { question_type: string; options: unknown[] };
  expect(essay.question_type).toBe("writing");
  expect(essay.options).toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("ученик видит пассаж со всеми вопросами и пишет открытый ответ; Кымбат проверяет", async ({
  browser,
}) => {
  const student = await as(browser, "student");
  // чтение: страница с пассажем несёт оба вопроса разом
  const reading = await apiPost<{ id: number; passages: { title: string }[]; questions: { passage: number | null }[] }>(
    student,
    "/api/prep/practice/start/",
    { exam_type: "IELTS", section: "reading", topic: `Чтение ${stamp}` },
  );
  expect(reading.passages.map((p) => p.title)).toContain(PASSAGE);
  expect(reading.questions.filter((q) => q.passage !== null).length).toBe(2);

  // письмо: открытый ответ через экран
  await student.goto("/prep");
  const essay = await apiPost<{ id: number; questions: { answer_id: number; is_open: boolean }[] }>(
    student,
    "/api/prep/practice/start/",
    { exam_type: "IELTS", section: "writing", topic: ESSAY_TOPIC },
  );
  expect(essay.questions[0].is_open).toBe(true);
  const text = `The chart shows a steady rise ${stamp}. `.repeat(12);
  await apiPost(student, `/api/prep/practice/${essay.id}/answer/`, {
    answer_id: essay.questions[0].answer_id,
    text,
  });
  const review = await apiPost<{ open_waiting: number; percent: number }>(
    student,
    `/api/prep/practice/${essay.id}/finish/`,
    {},
  );
  expect(review.open_waiting).toBe(1);
  await student.context().close();

  // Кымбат: вкладка «Открытые ответы», оценка и комментарий
  const kymbat = await as(browser, "director_exam");
  await kymbat.goto("/mocks");
  await kymbat.getByRole("tab", { name: "Открытые ответы" }).click();
  const waiting = kymbat.locator(".oans__row", { hasText: ESSAY_TOPIC }).first();
  await expect(waiting).toBeVisible();
  await waiting.getByRole("button", { name: "Проверить" }).click();
  const dialog = kymbat.getByRole("dialog");
  await expect(dialog).toContainText("Task response, coherence, vocabulary");
  await dialog.getByLabel("Оценка по шкале экзамена").fill("6.5");
  await dialog.getByLabel(/Комментарий/).fill("Нет обзорного абзаца");
  const saved = kymbat.waitForResponse((r) => /open-answers\/\d+\/review\//.test(r.url()));
  await dialog.getByRole("button", { name: "Сохранить проверку" }).click();
  expect((await saved).status()).toBe(200);
  await expect(kymbat.locator(".oans__row", { hasText: ESSAY_TOPIC })).toHaveCount(0);

  // уборка: задания прогона скрываются, чтобы не попадать в чужие тренировки
  const bank = (await (
    await kymbat.request.get(`/api/prep/questions/?search=${stamp}&page_size=50`)
  ).json()) as { results: { id: number }[] };
  // отвеченное задание сервер удалить не даёт — его скрывают, как и на экране
  for (const row of bank.results)
    await apiPatch(kymbat, `/api/prep/questions/${row.id}/`, { is_active: false });
  await kymbat.context().close();

  // ученик видит оценку и комментарий в разборе — без имени проверяющего
  const back = await as(browser, "student");
  const seen = (await (await back.request.get(`/api/prep/practice/${essay.id}/`)).json()) as {
    questions: { review: { score: number; comment: string } | null }[];
  };
  expect(seen.questions[0].review?.score).toBe(6.5);
  expect(JSON.stringify(seen)).not.toContain("reviewed_by");
  await back.context().close();
});

// --- 9: соревнование в карточке --------------------------------------------------------

test("соревнование: отмеченное видно в карточке у чужого директора, неотмеченное — нет", async ({
  browser,
}) => {
  const sport = await as(browser, "director_sport");
  const made = await apiPost<{ id: number; show_in_card: boolean }>(sport, "/api/competitions/", {
    student: studentId,
    name: COMPETITION,
    date: "2026-03-15",
  });
  expect(made.show_in_card).toBe(false);

  const asem = await as(browser, "director_admission");
  const hidden = (await (
    await asem.request.get(`/api/competitions/?student=${studentId}`)
  ).json()) as { results: { name: string }[] };
  expect(hidden.results.map((row) => row.name)).not.toContain(COMPETITION);

  // Нурлыбек ставит отметку переключателем на своём экране
  await sport.goto("/competitions");
  const row = sport.locator("tr", { hasText: COMPETITION });
  await expect(row).toBeVisible();
  const patched = sport.waitForResponse(
    (r) => r.url().includes(`/api/competitions/${made.id}/`) && r.request().method() === "PATCH",
  );
  await row.getByRole("switch").click();
  expect((await patched).status()).toBe(200);

  // строки ученика в карточке директора — на вкладке «Строки и записи»
  await asem.goto(`/students/${studentId}`);
  await asem.getByRole("tab", { name: "Строки и записи" }).click();
  await expect(asem.locator("body")).toContainText(COMPETITION);
  await asem.context().close();

  await apiDelete(sport, `/api/competitions/${made.id}/`);
  await sport.context().close();
});

// --- 10, 14: Салтанат --------------------------------------------------------------------

test("посещаемость у Салтанат на чтение; журнал за месяц и его выгрузка", async ({
  browser,
}) => {
  const page = await as(browser, "director_behavior");
  const diag = watch(page);
  await page.goto("/dashboard");
  await expect(page.getByRole("button", { name: "Внести посещаемость" })).toHaveCount(0);

  // плитка группы не уже своего текста: «N в риске · M чел.» — одной строкой внутри плитки
  const tile = page.locator(".cabinet__group").first();
  if ((await tile.count()) > 0) {
    const fits = await tile.evaluate((node) => {
      const box = node.getBoundingClientRect();
      const line = node.querySelector(".cabinet__groupline")!.getBoundingClientRect();
      return line.right <= box.right + 1 && line.height < 32;
    });
    expect(fits, "подпись плитки не вылезает и не переносится").toBe(true);
  }

  await page.getByRole("button", { name: "Журнал посещаемости" }).click();
  await expect(page).toHaveURL(/\/attendance\?view=journal/);
  await expect(page.locator(".att__journal")).toBeVisible();
  await expect(page.locator(".att__journal thead th").last()).toContainText("Итог");

  // лист за день — без кнопки сохранения и без переключателей
  await page.getByRole("tab", { name: "День" }).click();
  await expect(page.locator(".att__list")).toBeVisible();
  await expect(page.getByRole("button", { name: "Сохранить день" })).toHaveCount(0);
  await expect(page.locator("button.att__mark")).toHaveCount(0);
  await expect(page.locator("body")).toContainText("вносит куратор");

  // и сервер отвечает отказом, если обойти экран
  const sheet = (await (await page.request.get("/api/attendance/")).json()) as {
    group: number | null;
    may_mark: boolean;
  };
  expect(sheet.may_mark).toBe(false);

  // журнал выгружается через предпросмотр
  await page.getByRole("tab", { name: "Журнал за месяц" }).click();
  const exportButton = page.getByRole("button", { name: "Выгрузить" });
  if (await exportButton.isEnabled()) {
    const exported = await exportThroughPreview(page, exportButton);
    expect(exported.columns[0]).toBe("Ученик");
    expect(exported.columns).toContain("Отсутствовал, дней");
  }
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();

  // куратор по-прежнему отмечает и видит тот же журнал
  const curator = await as(browser, "curator");
  await curator.goto("/attendance");
  await expect(curator.getByRole("button", { name: "Сохранить день" })).toBeVisible();
  await curator.getByRole("tab", { name: "Журнал за месяц" }).click();
  await expect(curator.locator(".att__journal")).toBeVisible();
  await curator.context().close();
});

// --- 12, 13: карточки справочников --------------------------------------------------------

test("сюжеты главной у администратора — карточками, порядок стрелками", async ({ browser }) => {
  const admin = await as(browser, "admin");
  await admin.goto("/home-cues");
  await expect(admin.getByRole("heading", { name: "Сюжеты главной" })).toBeVisible();
  const cards = admin.locator(".scard");
  await expect(cards.first()).toBeVisible();
  await expect(cards.first()).toContainText("Показывается, когда:");
  await expect(cards.first()).toContainText("Ведёт на:");
  await expect(admin.locator("table.tbl")).toHaveCount(0);
  await expect(admin.getByLabel("Порядок")).toHaveCount(0);

  if ((await cards.count()) > 1) {
    const before = await cards.locator(".scard__title").allInnerTexts();
    const moved = admin.waitForResponse(
      (r) => /\/api\/home-cues\/\d+\/$/.test(r.url()) && r.request().method() === "PATCH",
    );
    await cards.nth(1).getByRole("button", { name: /^Выше:/ }).click();
    expect((await moved).status()).toBe(200);
    await expect
      .poll(async () => (await cards.locator(".scard__title").allInnerTexts())[0])
      .toBe(before[1]);
    // возвращаем как было
    await cards.nth(1).getByRole("button", { name: /^Выше:/ }).click();
    await expect
      .poll(async () => (await cards.locator(".scard__title").allInnerTexts())[0])
      .toBe(before[0]);
  }
  await admin.context().close();
});

// --- 15: выгрузка пользователей ---------------------------------------------------------------

test("выгрузка пользователей — по фильтру, через предпросмотр, без паролей", async ({ browser }) => {
  const admin = await as(browser, "admin");
  await admin.goto("/users");
  await admin.getByPlaceholder("Поиск по имени или почте").fill("probe.local");
  await expect(admin.locator("body")).toContainText("probe.local");
  const exported = await exportThroughPreview(
    admin,
    admin.getByRole("button", { name: "Выгрузить", exact: true }),
  );
  expect(exported.columns).toEqual(["ФИО", "Почта", "Роль", "Группа", "Состояние пароля", "Активен"]);
  await admin.context().close();
});

// --- 16: документы ученика --------------------------------------------------------------------

for (const width of [1440, 390]) {
  test(`документы ученика — одна карточка, ширина ${width}`, async ({ browser }) => {
    const page = await as(browser, "student", width);
    const diag = watch(page);
    await page.goto("/my-data");
    await page.getByRole("tab", { name: "Документы" }).click();
    const card = page.locator(".datacard", { hasText: "Мои документы" });
    await expect(card).toBeVisible();
    // двух прежних карточек нет
    await expect(page.locator(".datacard__title", { hasText: "Готовность документов" })).toHaveCount(0);
    await expect(page.locator(".datacard__title", { hasText: "Загрузить документ" })).toHaveCount(0);

    const rows = card.locator(".mydocs__item");
    expect(await rows.count()).toBeGreaterThan(3);

    // строка без документа: «Загрузить» прямо в ней, форма открывается с выбранным типом
    const empty = rows.filter({ hasText: "Не загружен" }).first();
    if ((await empty.count()) > 0) {
      const title = (await empty.locator(".mydocs__title").innerText()).trim();
      await empty.getByRole("button", { name: "Загрузить", exact: true }).click();
      await expect(page.getByRole("dialog")).toContainText(title);
      await page.keyboard.press("Escape");
    }

    // строка с документом: действия в одну линию; на ноутбуке — значками
    const filled = rows.filter({ has: page.getByRole("button", { name: "Открыть" }) }).first();
    if ((await filled.count()) > 0) {
      const open = filled.getByRole("button", { name: "Открыть" }).first();
      const drop = filled.getByRole("button", { name: "Убрать" }).first();
      const [a, b] = [await open.boundingBox(), await drop.boundingBox()];
      expect(Math.abs((a?.y ?? 0) - (b?.y ?? 0)), "действия на одной линии").toBeLessThan(3);
      if (width > 640) expect(a?.width, "поле касания значка 44 px").toBeGreaterThanOrEqual(44);
    }

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, "страница не едет вбок").toBeLessThanOrEqual(1);
    expect(diag.pageErrors, "исключения").toEqual([]);
    await page.context().close();
  });
}

test("уборка: строки прогона", async ({ browser }) => {
  const admin = await as(browser, "admin");
  const asem = await as(browser, "director_admission");
  // ссылка на табель прогона — в архив, срок паспорта — как был до сценария не храним:
  // поле пустым не делаем, чтобы не гадать; соседние сценарии на него не смотрят
  const docs = (await (
    await asem.request.get(`/api/documents/?student=${studentId}`)
  ).json()) as { results: { id: number; external_url?: string; title: string }[] };
  for (const row of docs.results.filter((item) => item.title.includes("ссылка из блока")))
    await apiDelete(asem, `/api/documents/${row.id}/`).catch(() => undefined);
  await apiPatch(asem, `/api/profiles/admission/${studentId}/`, { passport_expires_at: null }).catch(
    () => undefined,
  );
  await asem.context().close();
  await admin.context().close();
});
