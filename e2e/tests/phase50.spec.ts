/**
 * Фаза 50 — календарь и карусель поменялись местами.
 *
 * Решение владельца: слева широкий календарь, справа узкая карусель.
 * Проверяем то, чего из pytest не видно: кто где стоит на самом деле,
 * помещается ли строка события в одну линию, не меняются ли размеры
 * текста, когда карусель исчезает, и что видит человек на планшете.
 *
 * Оба состояния — на живых данных: сюжеты карусели считает сервер
 * по состоянию ученика, события календаря заводятся через API теми же
 * ролями, что и в жизни.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { apiDelete, apiPatch, apiPost } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

const LAPTOP = { width: 1440, height: 900 };
const TABLET = { width: 1024, height: 900 };

/** Второй ученик прогона: заводится этим же сценарием, как в жизни. */
const SECOND = probeEmail("home.student");
const SECOND_NAME = "Айсулу Главная";
const SECOND_PASSWORD = "Главная!Экран2026";

async function as(
  browser: Browser,
  role: string,
  viewport = LAPTOP,
): Promise<Page> {
  const context = await browser.newContext({
    storageState: statePath(role),
    viewport,
  });
  return context.newPage();
}

interface TopLayout {
  cal: { x: number; y: number; w: number; h: number } | null;
  caro: { x: number; y: number; w: number; h: number } | null;
  screenWidth: number;
  fonts: Record<string, string>;
  rows: {
    when: string;
    whenLines: number;
    title: string;
    titleLines: number;
  }[];
  panel: { w: number; scrollH: number; clientH: number } | null;
  caroTitle: { lines: number; clipped: boolean } | null;
  arrows: number;
  dots: number;
  actionInside: boolean;
  pageOverflow: number;
}

/** Числа верха главной: кто где стоит, какими буквами и что переносится. */
async function topLayout(page: Page): Promise<TopLayout> {
  await page.waitForSelector(".home__cal");
  await page.waitForTimeout(400);
  return page.evaluate(() => {
    const box = (selector: string) => {
      const node = document.querySelector(selector);
      if (!node) return null;
      const rect = node.getBoundingClientRect();
      return {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        w: Math.round(rect.width),
        h: Math.round(rect.height),
      };
    };
    const lines = (node: Element | null) =>
      node
        ? Math.round(
            node.getBoundingClientRect().height /
              parseFloat(getComputedStyle(node).lineHeight),
          )
        : 0;
    const font = (selector: string) => {
      const node = document.querySelector(selector);
      return node ? getComputedStyle(node).fontSize : "";
    };
    const panel = document.querySelector(".home__calpanel");
    const caro = document.querySelector(".caro");
    const caroTitle = document.querySelector(".home__caro .hero__title");
    const action = document.querySelector(".home__caro .hero__action");
    return {
      cal: box(".home__cal"),
      caro: box(".caro"),
      screenWidth: Math.round(
        document.querySelector(".shell__screen")?.getBoundingClientRect()
          .width ?? 0,
      ),
      fonts: {
        day: font(".home__calday"),
        weekday: font(".home__calweekday"),
        month: font(".home__calhead b"),
        title: font(".home__calpanel .rowline__title"),
        when: font(".home__when"),
      },
      rows: [...document.querySelectorAll(".home__calpanel .rowline")].map(
        (row) => ({
          when: row.querySelector(".home__when")?.textContent ?? "",
          whenLines: lines(row.querySelector(".home__when")),
          title: row.querySelector(".rowline__title")?.textContent ?? "",
          titleLines: lines(row.querySelector(".rowline__title")),
        }),
      ),
      panel: panel
        ? {
            w: Math.round(panel.getBoundingClientRect().width),
            scrollH: panel.scrollHeight,
            clientH: panel.clientHeight,
          }
        : null,
      caroTitle: caroTitle
        ? {
            lines: lines(caroTitle),
            // «не режется» — многоточия нет и текст не обрезан по ширине
            clipped:
              getComputedStyle(caroTitle).textOverflow === "ellipsis" ||
              caroTitle.scrollWidth > caroTitle.clientWidth + 1,
          }
        : null,
      arrows: document.querySelectorAll(".home__caro .caro__arrow").length,
      dots: document.querySelectorAll(".home__caro .caro__dot").length,
      actionInside:
        !!caro &&
        !!action &&
        action.getBoundingClientRect().bottom <=
          caro.getBoundingClientRect().bottom + 1,
      pageOverflow:
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    };
  });
}

// --- Раскладка верха главной ------------------------------------------------

test("календарь слева и широкий, карусель справа и узкая", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  await page.goto("/dashboard");
  const cues = (await (await page.request.get("/api/home/cues/")).json()) as {
    cues: { code: string }[];
  };
  expect(cues.cues.length, "у ученика есть что закрывать").toBeGreaterThan(0);

  const top = await topLayout(page);
  expect(top.cal && top.caro, "оба блока на экране").toBeTruthy();
  expect(top.cal!.x, "календарь слева от карусели").toBeLessThan(top.caro!.x);
  expect(top.cal!.y, "оба блока в одном ряду").toBe(top.caro!.y);
  expect(top.cal!.w, "календарь в широкой колонке").toBeGreaterThan(
    top.caro!.w,
  );
  // соотношение колонок прежнее — 1.35 к 1, поменялись только места
  expect(top.cal!.w / top.caro!.w).toBeGreaterThan(1.25);
  expect(top.cal!.w / top.caro!.w).toBeLessThan(1.45);

  // карусель в узкой колонке читается целиком: заголовок в две строки,
  // ничего не обрезано, кнопка и стрелки на месте, точки — вверху справа
  expect(
    top.caroTitle!.lines,
    "заголовок карусели в две строки",
  ).toBeLessThanOrEqual(2);
  expect(top.caroTitle!.clipped, "заголовок карусели не режется").toBe(false);
  expect(top.actionInside, "кнопка карусели внутри карточки").toBe(true);
  expect(top.arrows, "стрелки на месте").toBe(2);
  expect(top.dots, "точки на месте").toBe(cues.cues.length);
  const dot = await page
    .locator(".home__caro .caro__dot")
    .first()
    .boundingBox();
  expect(dot!.y - top.caro!.y, "точки в верхней части карточки").toBeLessThan(
    top.caro!.h / 4,
  );
  expect(top.pageOverflow, "экран не уезжает вбок").toBeLessThanOrEqual(0);
  await page.close();
});

test("панель ближайших событий держит пять строк в одну линию", async ({
  browser,
}) => {
  // события заводит академический директор — тот же путь, что в жизни:
  // цель по экзамену с датой регистрации и датой самого экзамена
  const director = await as(browser, "director_exam");
  await director.goto("/dashboard");
  const students = (await (
    await director.request.get(
      `/api/students/?search=${encodeURIComponent(probeEmail("student"))}`,
    )
  ).json()) as { results: { id: number; email: string }[] };
  const student = students.results.find(
    (row) => row.email === probeEmail("student"),
  );
  expect(student, "ученик прогона на месте").toBeTruthy();

  const kinds = (await (
    await director.request.get("/api/exam-kinds/?page_size=100")
  ).json()) as { results: { id: number; name: string }[] };
  const pick = (name: string) =>
    kinds.results.find((row) => row.name === name)?.id;

  // живая цель на экзамен одна: то, что уже стоит, правим и возвращаем
  // как было, чего нет — заводим и убираем за собой
  const before = (await (
    await director.request.get(
      `/api/exam-goals/?student=${student!.id}&page_size=100`,
    )
  ).json()) as {
    results: {
      id: number;
      exam: number;
      exam_date: string | null;
      registration_date: string | null;
    }[];
  };
  const created: number[] = [];
  const touched: {
    id: number;
    exam_date: string | null;
    registration_date: string | null;
  }[] = [];
  const goals = [
    {
      name: "IELTS",
      registration: "2026-09-20",
      exam: "2026-10-25",
      target: 7,
    },
    {
      name: "SAT",
      registration: "2026-10-05",
      exam: "2026-11-07",
      target: 1350,
    },
    {
      name: "ЕНТ",
      registration: "2026-10-12",
      exam: "2026-11-20",
      target: 100,
    },
  ];
  for (const goal of goals) {
    const kind = pick(goal.name);
    if (!kind) continue;
    const dates = {
      registration_date: goal.registration,
      exam_date: goal.exam,
    };
    const already = before.results.find((row) => row.exam === kind);
    if (already) {
      touched.push({
        id: already.id,
        exam_date: already.exam_date,
        registration_date: already.registration_date,
      });
      await apiPatch(director, `/api/exam-goals/${already.id}/`, dates);
      continue;
    }
    const row = await apiPost<{ id: number }>(director, "/api/exam-goals/", {
      student: student!.id,
      exam: kind,
      target_score: goal.target,
      ...dates,
    });
    created.push(row.id);
  }
  expect(
    created.length + touched.length,
    "цели по экзаменам с датами на месте",
  ).toBeGreaterThan(1);

  const page = await as(browser, "student");
  await page.goto("/dashboard");
  const top = await topLayout(page);
  expect(top.rows.length, "в панели пять ближайших событий").toBe(5);
  const five = top.rows.slice(0, 5);
  for (const row of five) {
    expect(row.whenLines, `дата «${row.when}» в одну строку`).toBe(1);
  }
  // строки, названия которых школа пишет сама («Экзамен: IELTS»,
  // «Регистрация: SAT»), обязаны помещаться в линию целиком
  const short = five.filter((row) => row.title.length <= 32);
  expect(short.length, "коротких названий в панели хватает").toBeGreaterThan(3);
  for (const row of short) {
    expect(row.titleLines, `название «${row.title}» в одну строку`).toBe(1);
  }
  // и пять таких строк помещаются в панель целиком, без прокрутки:
  // считаем по высоте самой строки, а не по тому, что за события
  // оказались в базе на момент прогона
  const room = await page.evaluate(() => {
    const panel = document.querySelector(".home__calpanel");
    const rows = [...document.querySelectorAll(".home__calpanel .rowline")];
    const single = rows.find(
      (row) =>
        Math.round(
          (
            row.querySelector(".rowline__title") as HTMLElement
          ).getBoundingClientRect().height /
            parseFloat(
              getComputedStyle(
                row.querySelector(".rowline__title") as HTMLElement,
              ).lineHeight,
            ),
        ) === 1,
    );
    const head = document.querySelector(
      ".home__panelhead",
    ) as HTMLElement | null;
    return {
      rowHeight: single ? single.getBoundingClientRect().height : 0,
      headHeight: head ? head.getBoundingClientRect().height + 4 : 0,
      clientH: panel ? panel.clientHeight : 0,
    };
  });
  expect(room.rowHeight, "строка события измерена").toBeGreaterThan(0);
  expect(
    room.headHeight + room.rowHeight * 5,
    "пять строк в одну линию помещаются в панель без прокрутки",
  ).toBeLessThanOrEqual(room.clientH);
  // многоточий в панели нет: обрезанное название человеку ничего не говорит
  const ellipsis = await page
    .locator(".home__calpanel .rowline__title")
    .evaluateAll(
      (nodes) =>
        nodes.filter(
          (node) => getComputedStyle(node).textOverflow === "ellipsis",
        ).length,
    );
  expect(ellipsis, "названия событий не режутся многоточием").toBe(0);
  await page.close();

  // прогон убирает за собой то, что завёл, и возвращает то, что правил
  for (const id of created) await apiDelete(director, `/api/exam-goals/${id}/`);
  for (const goal of touched)
    await apiPatch(director, `/api/exam-goals/${goal.id}/`, {
      exam_date: goal.exam_date,
      registration_date: goal.registration_date,
    });
  await director.close();
});

// --- Второй ученик и состояние без карусели ---------------------------------

test("второй ученик прогона: та же раскладка, календарь одного размера", async ({
  browser,
}) => {
  // заводим второго ученика тем же путём, что администратор в жизни:
  // список, временный пароль, обязательная смена при первом входе.
  // Карточка с прошлого прогона переживает уборку одноразовых записей,
  // поэтому если она на месте — администратор просто выпускает новый
  // временный пароль: прогон обязан идти и по второму разу
  const admin = await as(browser, "admin");
  await admin.goto("/users");
  const account = async () => {
    const rows = (await (
      await admin.request.get(
        `/api/users/?search=${encodeURIComponent(SECOND)}`,
      )
    ).json()) as { id: number; email: string }[];
    return rows.find((row) => row.email === SECOND);
  };
  const cards = (await (
    await admin.request.get(
      `/api/students/?search=${encodeURIComponent(SECOND)}`,
    )
  ).json()) as { results: { email: string }[] };
  const hasCard = cards.results.some((row) => row.email === SECOND);

  let temporary = "";
  let known = await account();
  // карточка ученика переживает уборку одноразовых записей, а учётная
  // запись — нет: тогда администратор заводит запись почтой, и она
  // связывается с карточкой сама (связь по почте, фаза 26)
  if (!known && hasCard) {
    await apiPost(admin, "/api/users/invite/", {
      emails: [SECOND],
      role: "student",
    });
    known = await account();
  }
  if (known) {
    const issued = await apiPost<{ password: string }>(
      admin,
      `/api/users/${known.id}/temp-password/`,
      {},
    );
    temporary = issued.password;
  } else {
    await admin
      .getByRole("button", { name: "Завести учеников списком" })
      .click();
    const applied = admin.waitForResponse((r) =>
      r.url().includes("/api/enrollment/apply/"),
    );
    await admin
      .locator('input[type="file"]')
      .first()
      .setInputFiles({
        name: "spisok.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(
          `ФИО,почта,класс,группа\n${SECOND_NAME},${SECOND},11,11A\n`,
          "utf8",
        ),
      });
    await expect(admin.getByText("будет заведён")).toBeVisible();
    await admin
      .getByRole("button", { name: /Завести/ })
      .last()
      .click();
    const issued = (await (await applied).json()) as {
      rows: { email: string; password: string }[];
    };
    temporary = issued.rows.find((row) => row.email === SECOND)?.password ?? "";
  }
  expect(temporary, "временный пароль на руках у администратора").toBeTruthy();
  await admin.close();

  const context = await browser.newContext({ viewport: LAPTOP });
  const page = await context.newPage();
  await page.goto("/login");
  await page.getByLabel("Почта").fill(SECOND);
  await page.getByLabel("Пароль").fill(temporary);
  await page.getByRole("button", { name: "Войти" }).click();
  await page.getByLabel("Текущий пароль").fill(temporary);
  await page.getByLabel("Новый пароль", { exact: true }).fill(SECOND_PASSWORD);
  await page.getByLabel("Ещё раз").fill(SECOND_PASSWORD);
  await page.getByRole("button", { name: "Сохранить и продолжить" }).click();
  await expect(page.locator(".pmenu__username")).toBeVisible();

  await page.goto("/dashboard");
  const own = (await (await page.request.get("/api/home/cues/")).json()) as {
    cues: { code: string }[];
  };
  expect(
    own.cues.length,
    "у нового ученика закрывать есть что",
  ).toBeGreaterThan(0);
  const paired = await topLayout(page);
  expect(paired.cal!.x, "календарь слева").toBeLessThan(paired.caro!.x);
  expect(paired.cal!.w).toBeGreaterThan(paired.caro!.w);

  // --- школа закрывает сюжеты: карусели нет, календарь во всю ширину ---
  const director = await as(browser, "director_behavior");
  await director.goto("/home-cues");
  const rules = (await (
    await director.request.get("/api/home-cues/?page_size=100")
  ).json()) as { results: { id: number; is_active: boolean }[] };
  const active = rules.results.filter((row) => row.is_active);
  for (const row of active)
    await apiPatch(director, `/api/home-cues/${row.id}/`, {
      is_active: false,
    });

  await page.reload();
  const alone = await topLayout(page);
  expect(alone.caro, "карусели нет вовсе").toBeNull();
  expect(
    alone.cal!.w / alone.screenWidth,
    "календарь занял всю ширину",
  ).toBeGreaterThan(0.95);
  expect(alone.cal!.w, "календарь стал шире").toBeGreaterThan(paired.cal!.w);
  // главное: он растянулся, а не увеличился — буквы те же самые
  expect(alone.fonts, "размеры текста календаря не изменились").toEqual(
    paired.fonts,
  );
  expect(alone.cal!.h, "высота календаря та же").toBe(paired.cal!.h);

  for (const row of active)
    await apiPatch(director, `/api/home-cues/${row.id}/`, { is_active: true });
  await director.close();
  await page.reload();
  await expect(page.locator(".caro")).toBeVisible();
  await context.close();
});

test("на планшетной ширине блоки друг под другом, календарь первым", async ({
  browser,
}) => {
  const page = await as(browser, "student", TABLET);
  await page.goto("/dashboard");
  const top = await topLayout(page);
  expect(top.cal && top.caro, "оба блока на экране").toBeTruthy();
  expect(top.cal!.y, "календарь выше карусели").toBeLessThan(top.caro!.y);
  expect(top.cal!.x, "оба блока во всю ширину").toBe(top.caro!.x);
  expect(Math.abs(top.cal!.w - top.caro!.w)).toBeLessThanOrEqual(1);
  expect(top.pageOverflow, "экран не уезжает вбок").toBeLessThanOrEqual(0);
  await page.close();
});
