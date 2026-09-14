/**
 * Фаза 74 — съёмка телефонной версии: все экраны в один файл.
 *
 * Это не проверка, а съёмка: ничего не сравнивается и не чинится. Каждая
 * роль обходит все пункты своего меню на ширине 390, снимок — вся страница
 * целиком. Отдельно снимаются состояния, которые легко пропустить: пустые
 * экраны, ошибка, открытые модалки и меню строки, длинный список.
 *
 * Сценарий не входит в обычные проекты прогона (`testIgnore` в конфигурации)
 * и запускается только руками:
 *
 *   MOBILE_REVIEW=1 ./run.sh --project=seed --project=mobile-review tests/seed.spec.ts tests/mobile-review.spec.ts
 *
 * Снимки ложатся в `shots/mobile/`, подписи — в `shots/mobile/manifest.json`;
 * файл для владельца собирает `build_mobile_review.py`.
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";

test.describe.configure({ mode: "serial", timeout: 600_000 });

const DIR = path.join(__dirname, "..", "shots", "mobile");
const PHONE = { width: 390, height: 844 };
const TABLE = readFileSync(
  path.join(__dirname, "..", "fixtures", "admission-table.xlsx"),
);

type Shot = {
  file: string;
  role: string;
  roleTitle: string;
  screen: string;
  state: string;
  url: string;
  seeded?: boolean;
};

const ROLE_TITLES: Record<string, string> = {
  student: "Ученик",
  curator: "Куратор",
  director_admission: "Асем · поступление",
  director_exam: "Кымбат · экзамены",
  director_behavior: "Салтанат · профиль и дисциплина",
  director_talent: "Арман · таланты",
  director_sport: "Нурлыбек · спорт",
  admin: "Администратор",
};

const shots: Shot[] = [];
let counter = 0;

async function csrf(page: Page): Promise<string> {
  return (
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? ""
  );
}

async function open(
  browser: Browser,
  role: string,
  { firstRun = false } = {},
): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    viewport: PHONE,
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  if (!firstRun) {
    await page.addInitScript(() =>
      window.localStorage.setItem("first-run-seen", "1"),
    );
  }
  return page;
}

async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(500);
}

/** Снять страницу целиком и записать подпись. */
async function shoot(
  page: Page,
  role: string,
  screen: string,
  state = "обычное",
  seeded = false,
): Promise<void> {
  counter += 1;
  const slug = `${String(counter).padStart(3, "0")}-${role}-${screen
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .toLowerCase()}`;
  const file = `${slug}.png`;
  await page.screenshot({
    path: path.join(DIR, file),
    fullPage: true,
    animations: "disabled",
  });
  shots.push({
    file,
    role,
    roleTitle: ROLE_TITLES[role] ?? role,
    screen,
    state,
    url: new URL(page.url()).pathname + new URL(page.url()).search,
    seeded,
  });
}

async function visit(
  page: Page,
  role: string,
  url: string,
  screen: string,
  state = "обычное",
): Promise<void> {
  await page.goto(url);
  await settle(page);
  await shoot(page, role, screen, state);
}

async function firstStudentId(page: Page, email: string): Promise<number> {
  const list = (await (
    await page.request.get("/api/students/?page_size=500")
  ).json()) as { results?: { id: number; email: string }[] };
  const row = (list.results ?? []).find((r) => r.email === email);
  return row?.id ?? (list.results ?? [])[0]?.id ?? 0;
}

test.beforeAll(() => {
  mkdirSync(DIR, { recursive: true });
});

test.afterAll(() => {
  writeFileSync(
    path.join(DIR, "manifest.json"),
    JSON.stringify(shots, null, 2),
    "utf8",
  );
});

// --- Ученик -------------------------------------------------------------------

test("ученик", async ({ browser }) => {
  // первый вход: подсказка и анкета — другой экран, чем у обжившегося
  const fresh = await open(browser, "student", { firstRun: true });
  await visit(
    fresh,
    "student",
    "/dashboard",
    "Главная",
    "первый вход: подсказка «Как начать»",
  );
  await visit(
    fresh,
    "student",
    "/onboarding",
    "Анкета первого входа",
    "первый вход",
  );
  await fresh.context().close();

  const page = await open(browser, "student");
  const screens: [string, string][] = [
    ["/dashboard", "Главная"],
    ["/journey", "Мой путь"],
    ["/calendar", "Календарь"],
    ["/my-data", "Портфолио (мои данные)"],
    ["/selection", "Подбор вузов"],
    ["/catalog", "Каталог вузов"],
    ["/favorites", "Избранное"],
    ["/universities", "Мои вузы"],
    ["/plan", "План поступления"],
    ["/scholarships", "Стипендии"],
    ["/career", "Профтест"],
    ["/essays", "Эссе"],
    ["/prep", "Подготовка"],
    ["/roadmap", "Роадмап"],
    ["/quiz", "Квиз"],
    ["/achievements", "Достижения"],
    ["/profile", "Профиль"],
  ];
  for (const [url, title] of screens) await visit(page, "student", url, title);

  // карточка вуза: план по программе из списка, если он есть
  const mine = (await (
    await page.request.get("/api/match/my-universities/")
  ).json()) as { program: number }[];
  if (mine.length > 0) {
    await visit(
      page,
      "student",
      `/plan/${mine[0].program}`,
      "Карточка вуза (план по программе)",
    );
  }
  // документы ученика живут в портфолио — вкладка «Документы»
  await page.goto("/my-data");
  await settle(page);
  const docsTab = page.getByRole("tab", { name: "Документы" });
  if (await docsTab.isVisible().catch(() => false)) {
    await docsTab.click();
    await settle(page);
    await shoot(page, "student", "Портфолио · вкладка «Документы»");
  }
  // задачи — на роадмапе; «Ещё» — нижний бар
  await page.goto("/dashboard");
  await settle(page);
  const more = page.locator(".tabbar__more");
  if (await more.isVisible().catch(() => false)) {
    await more.click();
    await page.waitForTimeout(400);
    await shoot(
      page,
      "student",
      "Нижний бар · шторка «Ещё»",
      "модалка открыта",
    );
  }
  await page.context().close();
});

// --- Пустые и ошибочные состояния ученика ----------------------------------------

test("ученик: пустой и ошибка", async ({ browser }) => {
  // новый ученик без данных: заводит администратор, вход по ссылке не нужен —
  // смотрим его экраны через кабинет самого посеянного ученика с пустыми разделами
  const page = await open(browser, "student");
  await visit(
    page,
    "student",
    "/favorites",
    "Избранное",
    "пусто, если ничего не добавлено",
  );
  await visit(page, "student", "/essays", "Эссе", "пусто, если эссе нет");
  await visit(
    page,
    "student",
    "/plan/999999",
    "План по программе",
    "ошибка: программы нет",
  );
  await visit(
    page,
    "student",
    "/nowhere",
    "Несуществующий адрес",
    "ошибка: экрана нет",
  );
  await page.context().close();
});

// --- Куратор ------------------------------------------------------------------

test("куратор", async ({ browser }) => {
  const page = await open(browser, "curator");
  for (const [url, title] of [
    ["/dashboard", "Главная"],
    ["/queue", "Очередь"],
    ["/students", "Ученики"],
    ["/documents", "Документы"],
    ["/attendance", "Посещаемость"],
    ["/mock-imports", "Пробники"],
    ["/tasks", "Задачи"],
    ["/journal", "Журнал"],
  ] as [string, string][])
    await visit(page, "curator", url, title);

  const id = await firstStudentId(page, probeEmail("pupil01"));
  await page.goto(`/students/${id}`);
  await settle(page);
  await shoot(page, "curator", "Карточка ученика · Обзор");
  for (const tab of [
    "Экзамены",
    "Документы",
    "Вузы",
    "Портфолио",
    "Задачи",
    "Заметки",
  ]) {
    const control = page.getByRole("tab", { name: tab });
    if (await control.isVisible().catch(() => false)) {
      await control.click();
      await settle(page);
      await shoot(page, "curator", `Карточка ученика · ${tab}`);
    }
  }
  // письмо родителям — модалка
  await page.goto(`/students/${id}`);
  await settle(page);
  const write = page
    .getByRole("button", { name: "Написать родителям" })
    .first();
  if (await write.isVisible().catch(() => false)) {
    await write.click();
    await page.waitForTimeout(400);
    await shoot(page, "curator", "Письмо родителям", "модалка открыта");
    await page.keyboard.press("Escape");
  }
  // добавление контакта — модалка
  const addContact = page
    .getByRole("button", { name: "Добавить контакт" })
    .first();
  if (await addContact.isVisible().catch(() => false)) {
    await addContact.click();
    await page.waitForTimeout(400);
    await shoot(page, "curator", "Добавить контакт", "модалка открыта");
    await page.keyboard.press("Escape");
  }
  await page.context().close();
});

// --- Директора ------------------------------------------------------------------

const DIRECTOR_OWN: Record<string, [string, string][]> = {
  director_admission: [
    ["/directory", "Справочник"],
    ["/deadlines", "Дедлайны"],
    ["/essay-content", "Конструктор эссе"],
    ["/scholarship-directory", "Стипендии"],
    ["/task-templates", "Шаблоны задач"],
  ],
  director_exam: [
    ["/top30", "TOP-30"],
    ["/mocks", "Пробные"],
    ["/mock-imports", "Пробники"],
    ["/exam-kinds", "Экзамены"],
    ["/task-templates", "Шаблоны задач"],
  ],
  director_behavior: [
    ["/career-questions", "Вопросы профтеста"],
    ["/badges", "Достижения школы"],
    ["/home-cues", "Сюжеты главной"],
    ["/call-rules", "Правила обзвона"],
    ["/attendance", "Посещаемость"],
    ["/groups", "Группы"],
    ["/contacts", "Контакты родителей"],
    ["/risks", "Риски"],
    ["/overview", "Сводный вид"],
  ],
  director_talent: [
    ["/subjects", "Предметы"],
    ["/tracks", "Треки"],
    ["/materials", "Материалы"],
    ["/olympiad-group", "Олимпиадная группа"],
  ],
  director_sport: [
    ["/sport-types", "Виды спорта"],
    ["/competitions", "Соревнования"],
  ],
};

for (const role of Object.keys(DIRECTOR_OWN)) {
  test(`директор ${role}`, async ({ browser }) => {
    const page = await open(browser, role);
    for (const [url, title] of [
      ["/dashboard", "Дашборд"],
      ["/table", "Таблица"],
      ["/assistant", "Помощник"],
      ["/suggestions", "Предложения"],
      ["/digest", "Дайджест"],
      ["/import", "Импорт"],
      ["/resources", "Ресурсы"],
      ...DIRECTOR_OWN[role],
    ] as [string, string][])
      await visit(page, role, url, title);
    const id = await firstStudentId(page, probeEmail("pupil01"));
    await visit(page, role, `/students/${id}`, "Карточка ученика");
    // история изменений — вторая вкладка карточки
    const history = page.getByRole("tab", { name: "История изменений" });
    if (await history.isVisible().catch(() => false)) {
      await history.click();
      await settle(page);
      await shoot(page, role, "Карточка ученика · История изменений");
    }
    await page.context().close();
  });
}

// --- Администратор --------------------------------------------------------------

test("администратор", async ({ browser }) => {
  const page = await open(browser, "admin");
  for (const [url, title] of [
    ["/dashboard", "Дашборд"],
    ["/table", "Таблица"],
    ["/users", "Пользователи"],
    ["/archive", "Архив"],
    ["/mail-templates", "Шаблоны писем"],
    ["/spend", "Расходы на ИИ"],
    ["/suggestions", "Предложения"],
  ] as [string, string][])
    await visit(page, "admin", url, title);

  // длинный список с прокруткой — «Пользователи» целиком; меню строки открыто
  await page.goto("/users");
  await settle(page);
  const menu = page.getByRole("button", { name: "Ещё действия" }).first();
  if (await menu.isVisible().catch(() => false)) {
    await menu.click();
    await page.waitForTimeout(300);
    await shoot(page, "admin", "Пользователи · меню строки", "меню открыто");
    await page.keyboard.press("Escape");
  }
  // выдача паролей — модалка по отмеченной строке
  const pick = page.getByLabel("Отметить строку").first();
  if (await pick.isVisible().catch(() => false)) {
    await pick.check();
    await page.getByRole("button", { name: "Выдать пароли" }).first().click();
    await page.waitForTimeout(600);
    await shoot(page, "admin", "Выдать пароли", "модалка открыта");
    await page.keyboard.press("Escape");
  }
  // удаление навсегда — модалка из меню строки
  if (await menu.isVisible().catch(() => false)) {
    await menu.click();
    const forever = page.getByRole("menuitem", { name: /навсегда/ }).first();
    if (await forever.isVisible().catch(() => false)) {
      await forever.click();
      await page.waitForTimeout(600);
      await shoot(page, "admin", "Удалить навсегда", "модалка открыта");
      await page.keyboard.press("Escape");
    } else {
      await page.keyboard.press("Escape");
    }
  }

  // мастер импорта: четыре шага
  await page.goto("/import");
  await settle(page);
  await shoot(page, "admin", "Импорт · шаг 1 «Файл»");
  const responded = page.waitForResponse((r) =>
    r.url().includes("/admission-imports/preview/"),
  );
  await page.locator('input[type="file"]').first().setInputFiles({
    name: "admission-table.xlsx",
    mimeType:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: TABLE,
  });
  await responded;
  await settle(page);
  await shoot(
    page,
    "admin",
    "Импорт · шаг 1 после загрузки файла",
    "обычное",
    true,
  );
  await page.getByRole("button", { name: "Дальше" }).click();
  await settle(page);
  await shoot(page, "admin", "Импорт · шаг 2 «Что заполняем»", "обычное", true);
  await page.getByRole("button", { name: "Дальше" }).click();
  await settle(page);
  await shoot(
    page,
    "admin",
    "Импорт · шаг 3 «Проверка строк»",
    "обычное",
    true,
  );
  const pending = page.locator("tr.aimp__row--bad:has(button)");
  while ((await pending.count()) > 0) {
    const again = page.waitForResponse((r) =>
      r.url().includes("/admission-imports/preview/"),
    );
    await pending.first().getByRole("button", { name: "Пропустить" }).click();
    await again;
  }
  const applied = page.waitForResponse((r) =>
    r.url().includes("/admission-imports/apply/"),
  );
  await page.getByRole("button", { name: "Применить" }).click();
  await applied;
  await settle(page);
  await shoot(page, "admin", "Импорт · шаг 4 «Готово»", "обычное", true);
  await page.context().close();
});

// --- Ошибка связи ---------------------------------------------------------------

test("нет связи", async ({ browser }) => {
  const page = await open(browser, "curator");
  await page.goto("/dashboard");
  await settle(page);
  await page.route("**/api/**", (route) => route.abort("connectionrefused"));
  await page.goto("/queue").catch(() => undefined);
  await page.waitForTimeout(1500);
  await shoot(page, "curator", "Очередь", "ошибка: нет связи с сервером");
  await page.context().close();
});
