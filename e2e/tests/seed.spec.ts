/**
 * Посев данных для прогона — руками ролей, через тот же API, что и экраны.
 *
 * База стартует пустой (инвариант №8), фикстур с выдуманными учениками
 * в коде нет и не будет. Но проверять экраны на пустой базе бессмысленно:
 * таблица без строк неотличима от сломанной. Поэтому перед прогоном
 * каждый директор делает то, что сделал бы в первый рабочий день:
 * администратор заводит группы и учеников списком, директор
 * по поступлению — стартовый справочник, академический — баллы и пробные,
 * директор талантов — предмет и активности, директор спорта — вид спорта
 * и соревнования, директор школы — посещаемость и задачи.
 *
 * Всё заведённое живёт под доменом `probe.local`: учётные записи учеников
 * уходят уборкой после прогона, карточки остаются данными контура
 * разработки и снимаются `reset_data --all`.
 *
 * Запускается вторым проектом — после сквозного сценария, который базу
 * обнуляет. Повторный запуск на живой базе ничего не дублирует.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { apiPost } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

/** Группы школы — как в прототипе куратора (фаза 60): три группы, один куратор. */
const GROUPS = [
  ["CHICAGO", 11],
  ["TOKYO", 11],
  ["BOSTON", 10],
] as const;

/** Ученики прогона: ФИО без пометок-заглушек, почта под доменом прогона. */
const PUPILS: { name: string; email: string; group: string }[] = [
  { name: "Сейткали Айгерим", email: probeEmail("pupil01"), group: "CHICAGO" },
  { name: "Абдрахманов Данияр", email: probeEmail("pupil02"), group: "CHICAGO" },
  { name: "Ержанова Малика", email: probeEmail("pupil03"), group: "CHICAGO" },
  { name: "Оспанов Тимур", email: probeEmail("pupil04"), group: "CHICAGO" },
  { name: "Сулейменова Дана", email: probeEmail("pupil05"), group: "TOKYO" },
  { name: "Жумабеков Алихан", email: probeEmail("pupil06"), group: "TOKYO" },
  { name: "Нурланова Камила", email: probeEmail("pupil07"), group: "TOKYO" },
  { name: "Кайратов Арсен", email: probeEmail("pupil08"), group: "TOKYO" },
  { name: "Бекова Аружан", email: probeEmail("pupil09"), group: "BOSTON" },
  { name: "Мусин Ерлан", email: probeEmail("pupil10"), group: "BOSTON" },
];

interface Row {
  id: number;
  email: string;
  full_name: string;
  group?: number | null;
}

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  const page = await context.newPage();
  await page.goto("/dashboard");
  return page;
}

async function students(page: Page): Promise<Row[]> {
  const list = await (
    await page.request.get("/api/students/?page_size=500")
  ).json();
  return list.results as Row[];
}

/** Дата «N дней назад» в виде YYYY-MM-DD. */
const daysAgo = (n: number): string =>
  new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 10);

test("администратор: группы и ученики списком", async ({ browser }) => {
  const page = await as(browser, "admin");

  const groups = (
    await (await page.request.get("/api/groups/?page_size=100")).json()
  ).results as { id: number; code: string }[];
  const have = new Set(groups.map((g) => g.code));
  for (const [code, grade] of GROUPS) {
    if (!have.has(code)) await apiPost(page, "/api/groups/", { code, grade });
  }
  const fresh = (
    await (await page.request.get("/api/groups/?page_size=100")).json()
  ).results as { id: number; code: string }[];
  const byCode = new Map(fresh.map((g) => [g.code, g.id]));

  // ученик прогона: учётная запись уже есть, заводим карточку — они
  // свяжутся по почте сами (фаза 16). Группа у него всегда CHICAGO:
  // на посеве эталонов школа другая (11A/11B), и карточка могла остаться
  // от неё — тогда ученик прогона оказывался вне групп куратора
  const mine = await students(page);
  const already = mine.find((row) => row.email === probeEmail("student")) as
    | (Row & { group: number | null })
    | undefined;
  if (!already) {
    await apiPost(page, "/api/students/", {
      last_name: "Прогон",
      first_name: "Айгерим",
      email: probeEmail("student"),
      grade: 11,
      group: byCode.get("CHICAGO"),
      graduation_year: 2027,
    });
  } else if (already.group !== byCode.get("CHICAGO")) {
    const moved = await page.request.patch(`/api/students/${already.id}/`, {
      data: { group: byCode.get("CHICAGO") },
      headers: {
        "X-CSRFToken":
          (await page.context().cookies()).find((c) => c.name === "csrftoken")
            ?.value ?? "",
      },
    });
    expect(moved.ok(), "ученик прогона переезжает в CHICAGO").toBeTruthy();
  }

  // остальные — списком, как из файла: карточка, запись и временный пароль
  const applied = await apiPost<{ created: number; skipped: unknown[] }>(
    page,
    "/api/enrollment/apply/",
    {
      rows: PUPILS.map((p) => ({
        full_name: p.name,
        email: p.email,
        grade: p.group.startsWith("10") ? "10" : "11",
        group: p.group,
      })),
    },
  );
  expect(applied.created + applied.skipped.length).toBe(PUPILS.length);
  const all = await students(page);
  expect(all.length).toBeGreaterThanOrEqual(PUPILS.length + 1);

  // куратор прогона ведёт все три группы (фаза 60): назначение — через API
  // администратора, как это сделал бы владелец на экране «Пользователи».
  // Повторный запуск ничего не дублирует: у кого группа уже есть, тот её и ведёт
  const curators = await (await page.request.get("/api/curators/")).json();
  const me = (
    curators.results as { email: string; groups: { code: string }[] }[]
  ).find((row) => row.email === probeEmail("curator"));
  expect(me).toBeTruthy();
  const users = (await (
    await page.request.get(`/api/users/?search=${probeEmail("curator")}`)
  ).json()) as { id: number; email: string }[];
  const curatorId = users.find((u) => u.email === probeEmail("curator"))!.id;
  const leads = new Set(me!.groups.map((g) => g.code));
  for (const [code] of GROUPS) {
    if (leads.has(code)) continue;
    await apiPost(page, "/api/curator-assignments/", {
      group: byCode.get(code),
      curator: curatorId,
      since: new Date().toISOString().slice(0, 10),
    });
  }
  await page.context().close();
});

test("директор по поступлению: стартовый справочник", async ({ browser }) => {
  const page = await as(browser, "director_admission");
  const stats = await (await page.request.get("/api/catalog/seed/")).json();
  if (!stats.universities) await apiPost(page, "/api/catalog/seed/", {});
  const universities = await (
    await page.request.get("/api/universities/?page_size=1")
  ).json();
  expect(universities.count).toBeGreaterThan(0);
  // цели поступления у учеников — по ним считается соответствие
  const rows = await students(page);
  const changes = rows.slice(0, 8).flatMap((row, i) => [
    {
      student: row.id,
      model: "students.AdmissionProfile",
      field: "target_country",
      value: ["США", "Канада", "Великобритания", "Нидерланды"][i % 4],
    },
    {
      student: row.id,
      model: "students.AdmissionProfile",
      field: "target_major",
      value: ["информатика", "экономика", "медицина", "инженерия"][i % 4],
    },
  ]);
  await apiPost(page, "/api/batch/save/", { changes });
  await page.context().close();
});

/**
 * Двое учеников намеренно остаются без целей и без пробников (фаза 61):
 * иначе корзины «без цели» и «пробника не было больше месяца» в кабинете
 * куратора всегда нули, и проверять на них нечего.
 */
const WITHOUT_DATA = [probeEmail("pupil09"), probeEmail("pupil10")];

test("академический директор: баллы и пробные", async ({ browser }) => {
  const page = await as(browser, "director_exam");
  const rows = (await students(page)).filter(
    (row) => !WITHOUT_DATA.includes(row.email),
  );
  const ielts = [6.0, 6.5, 7.0, 5.5, 7.5, 6.5, 6.0, 8.0, 5.0, 7.0, 6.5];
  const sat = [
    1250, 1380, 1450, 1100, 1520, 1300, 1200, 1480, 1050, 1400, 1350,
  ];
  const gpa = [3.6, 3.9, 4.0, 3.2, 3.8, 3.5, 3.4, 3.9, 3.0, 3.7, 3.6];
  const changes = rows.slice(0, ielts.length).flatMap((row, i) => [
    {
      student: row.id,
      model: "students.ExamProfile",
      field: "ielts_current",
      value: String(ielts[i]),
    },
    {
      student: row.id,
      model: "students.ExamProfile",
      field: "ielts_target",
      value: "7.5",
    },
    {
      student: row.id,
      model: "students.ExamProfile",
      field: "sat_current",
      value: String(sat[i]),
    },
    {
      student: row.id,
      model: "students.ExamProfile",
      field: "sat_target",
      value: "1500",
    },
    {
      student: row.id,
      model: "students.ExamProfile",
      field: "gpa",
      value: String(gpa[i]),
    },
  ]);
  await apiPost(page, "/api/batch/save/", { changes });

  // две волны пробных: по ним рисуется динамика и считаются «упавшие»
  const attempts = rows.slice(0, ielts.length).flatMap((row, i) => [
    {
      student: row.id,
      exam_type: "IELTS",
      attempt_format: "mock",
      date: daysAgo(60),
      total_score: String(Math.max(4, ielts[i] - 0.5)),
    },
    {
      student: row.id,
      exam_type: "IELTS",
      attempt_format: "mock",
      date: daysAgo(20),
      total_score: String(i % 3 === 0 ? ielts[i] - 0.5 : ielts[i]),
    },
  ]);
  await apiPost(page, "/api/attempts/bulk/", { rows: attempts });
  await page.context().close();
});

/** Банк заданий: по три задания на тему, темы — те, что потом станут «слабыми». */
const TOPICS: { exam: string; section: string; topic: string }[] = [
  { exam: "IELTS", section: "listening", topic: "Числа и даты" },
  { exam: "IELTS", section: "listening", topic: "Диалог в быту" },
  { exam: "IELTS", section: "reading", topic: "Поиск деталей" },
  { exam: "IELTS", section: "reading", topic: "Главная мысль абзаца" },
  { exam: "IELTS", section: "writing", topic: "Описание графика" },
  { exam: "IELTS", section: "speaking", topic: "Рассказ о себе" },
  { exam: "SAT", section: "math", topic: "Линейные уравнения" },
  { exam: "SAT", section: "verbal", topic: "Слова в контексте" },
];

test("академический директор: банк заданий и пробный экзамен", async ({
  browser,
}) => {
  const page = await as(browser, "director_exam");
  const bank = await (await page.request.get("/api/prep/bank/")).json();
  if (!bank.total) {
    for (const item of TOPICS) {
      for (let i = 1; i <= 3; i += 1) {
        await apiPost(page, "/api/prep/questions/", {
          exam_type: item.exam,
          section: item.section,
          topic: item.topic,
          text: `${item.topic}: задание ${i}`,
          explanation: `Верный вариант — Б: так устроена тема «${item.topic}»`,
          source: "составлено школой",
          options: [
            { letter: "А", text: "первый вариант", is_correct: false },
            { letter: "Б", text: "второй вариант", is_correct: true },
            { letter: "В", text: "третий вариант", is_correct: false },
            { letter: "Г", text: "четвёртый вариант", is_correct: false },
          ],
        });
      }
    }
  }
  const mocks = await (await page.request.get("/api/prep/mocks/")).json();
  if (
    !mocks.results.some((m: { exam_type: string }) => m.exam_type === "IELTS")
  ) {
    await apiPost(page, "/api/prep/mocks/", {
      title: "Пробный IELTS, короткий",
      exam_type: "IELTS",
      time_limit_minutes: 30,
      description:
        "Четыре секции по три задания — для прогона и первых тренировок",
      sections: [
        { section: "listening", question_count: 3 },
        { section: "reading", question_count: 3 },
        { section: "writing", question_count: 3 },
        { section: "speaking", question_count: 3 },
      ],
    });
  }
  const after = await (await page.request.get("/api/prep/bank/")).json();
  expect(after.total).toBeGreaterThan(0);
  await page.context().close();
});

test("директор талантов: предмет, треки, активности", async ({ browser }) => {
  const page = await as(browser, "director_talent");
  const subjects = (
    await (await page.request.get("/api/subjects/?page_size=100")).json()
  ).results as { id: number; name: string }[];
  if (!subjects.some((s) => s.name === "Математика")) {
    await apiPost(page, "/api/subjects/", { name: "Математика" });
  }
  const rows = await students(page);
  const tracks = ["olympiad", "research", "startup", "leadership"];
  await apiPost(page, "/api/batch/save/", {
    changes: rows.slice(0, 8).map((row, i) => ({
      student: row.id,
      model: "students.TalentProfile",
      field: "main_track",
      value: tracks[i % tracks.length],
    })),
  });
  const existing = await (
    await page.request.get("/api/activities/?page_size=1")
  ).json();
  if (!existing.count) {
    for (const [i, row] of rows.slice(0, 5).entries()) {
      await apiPost(page, "/api/activities/", {
        student: row.id,
        category: tracks[i % tracks.length],
        title: [
          "Олимпиада по математике",
          "Исследование по физике",
          "Школьный стартап",
          "Совет школы",
          "Волонтёрство в приюте",
        ][i],
        date: daysAgo(30 + i * 7),
      });
    }
  }
  await page.context().close();
});

test("директор спорта: вид спорта и соревнования", async ({ browser }) => {
  const page = await as(browser, "director_sport");
  const kinds = (
    await (await page.request.get("/api/sport-types/?page_size=100")).json()
  ).results as { id: number; name: string }[];
  let football = kinds.find((k) => k.name === "Футбол");
  if (!football)
    football = await apiPost(page, "/api/sport-types/", { name: "Футбол" });
  const rows = await students(page);
  const existing = await (
    await page.request.get("/api/competitions/?page_size=1")
  ).json();
  if (!existing.count) {
    for (const [i, row] of rows.slice(0, 4).entries()) {
      await apiPost(page, "/api/competitions/", {
        student: row.id,
        name: "Кубок города по футболу",
        sport_type: football!.id,
        level: "city",
        date: daysAgo(15),
        result: ["1 место", "2 место", "участие", "3 место"][i],
      });
    }
  }
  await page.context().close();
});

test("директор школы: посещаемость, статусы, задачи", async ({ browser }) => {
  const page = await as(browser, "director_behavior");
  const rows = await students(page);
  const attendance = [96, 88, 99, 72, 93, 85, 90, 97, 65, 91, 94];
  const status = [
    "can_execute",
    "can_execute",
    "can_execute",
    "needs_supervision",
    "can_execute",
    "needs_supervision",
    "can_execute",
    "can_execute",
    "critical",
    "can_execute",
    "can_execute",
  ];
  await apiPost(page, "/api/batch/save/", {
    changes: rows.slice(0, attendance.length).flatMap((row, i) => [
      {
        student: row.id,
        model: "students.BehaviorProfile",
        field: "attendance_percent",
        value: String(attendance[i]),
      },
      {
        student: row.id,
        model: "students.BehaviorProfile",
        field: "homework_percent",
        value: String(Math.min(100, attendance[i] + 2)),
      },
      {
        student: row.id,
        model: "students.BehaviorProfile",
        field: "status",
        value: status[i],
      },
    ]),
  });
  const tasks = await (
    await page.request.get("/api/tasks/?page_size=1")
  ).json();
  if (!tasks.count) {
    for (const [i, row] of rows.slice(0, 6).entries()) {
      await apiPost(page, "/api/tasks/", {
        student: row.id,
        title: [
          "Пройти пробный IELTS",
          "Собрать портфолио",
          "Написать черновик эссе",
          "Зарегистрироваться на SAT",
          "Запросить рекомендацию",
          "Заполнить Common App",
        ][i],
        category: "test",
      });
    }
  }
  await page.context().close();
});

/**
 * Данные кабинета куратора (фаза 61).
 *
 * Каждая корзина «кого дёргать» должна быть непустой, иначе проверять
 * на них нечего: числа-нули одинаковы и в исправной системе, и в сломанной.
 *
 * Кто чем занят:
 * — pupil09 и pupil10 остались без целей и пробников (`WITHOUT_DATA`) —
 *   это корзины «без цели» и «пробника не было больше месяца»;
 * — pupil01 получает цель с датой экзамена и отстаёт от неё — «балл далеко
 *   от цели, экзамен ближе 60 дней»;
 * — ученик прогона подаёт два предложения: первое остаётся в очереди
 *   резким скачком, второе куратор отклоняет — «отклонено и не перевнесено».
 *   Оба на одном ученике: корзина смотрит на последнее предложение,
 *   а очередь — на нерешённые.
 */
test("академический директор: цель с датой экзамена", async ({ browser }) => {
  const page = await as(browser, "director_exam");
  const rows = await students(page);
  const target = rows.find((row) => row.email === probeEmail("pupil01"));
  expect(target).toBeTruthy();

  const kinds = (
    await (await page.request.get("/api/exam-kinds/?page_size=50")).json()
  ).results as { id: number; name: string }[];
  const ielts = kinds.find((kind) => kind.name === "IELTS");
  expect(ielts).toBeTruthy();

  const existing = await (
    await page.request.get(`/api/exam-goals/?student=${target!.id}`)
  ).json();
  if (!existing.count) {
    const soon = new Date();
    soon.setDate(soon.getDate() + 30);
    await apiPost(page, "/api/exam-goals/", {
      student: target!.id,
      exam: ielts!.id,
      target_score: "7.5",
      exam_date: soon.toISOString().slice(0, 10),
    });
  }
  // балл заметно ниже цели: 6.0 против 7.5 — корзина «далеко от цели»
  await apiPost(page, "/api/batch/save/", {
    changes: [
      {
        student: target!.id,
        model: "students.ExamProfile",
        field: "ielts_current",
        value: "6.0",
      },
    ],
  });
  await page.context().close();
});

test("ученик и куратор: очередь с резким скачком и отклонение", async ({
  browser,
}) => {
  const student = await as(browser, "student");
  const mine = await (await student.request.get("/api/students/me/")).json();

  const queue = await (
    await student.request.get("/api/suggestions/mine/")
  ).json();
  const already = (queue.results ?? []) as { changes: { field: string }[] }[];

  // резкий скачок: 8.5 против 6.0 в профиле — больше порога школы
  if (!already.some((row) => row.changes.some((c) => c.field === "ielts_current"))) {
    await apiPost(student, "/api/suggestions/propose/", {
      rows: [
        { model: "students.ExamProfile", field: "ielts_current", value: "8.5" },
      ],
    });
  }
  // второе предложение — его куратор отклонит: корзина смотрит на последнее
  let second: number | null = null;
  if (!already.some((row) => row.changes.some((c) => c.field === "sat_current"))) {
    const made = await apiPost<{ suggestions: number[] }>(
      student,
      "/api/suggestions/propose/",
      {
        rows: [
          { model: "students.ExamProfile", field: "sat_current", value: "1590" },
        ],
      },
    );
    second = made.suggestions[0];
  }
  await student.context().close();

  const curator = await as(browser, "curator");
  if (second !== null) {
    await apiPost(curator, `/api/suggestions/${second}/review/`, {
      decision: "decline",
      reason: "Скан сертификата не приложен — пришлите файл",
    });
  }

  // задачи: одна ученику и одна всей группе — экран задач не должен быть пустым
  const tasks = await (
    await curator.request.get("/api/curator/tasks/?filter=all")
  ).json();
  if (!tasks.results.length) {
    const soon = new Date();
    soon.setDate(soon.getDate() + 5);
    await apiPost(curator, "/api/curator/tasks/", {
      student: mine.id,
      title: "Загрузить транскрипт за 10 класс",
      due_date: soon.toISOString().slice(0, 10),
    });
    const late = new Date();
    late.setDate(late.getDate() - 3);
    await apiPost(curator, "/api/curator/tasks/", {
      group: "TOKYO",
      title: "Записаться на пробник IELTS",
      due_date: late.toISOString().slice(0, 10),
    });
  }

  const overview = await (
    await curator.request.get("/api/curator/overview/")
  ).json();
  const buckets = Object.fromEntries(
    (overview.buckets as { code: string; count: number }[]).map((row) => [
      row.code,
      row.count,
    ]),
  );
  // все четыре корзины фазы 61 непустые — иначе проверять на них нечего
  for (const code of ["nogoal", "nomock", "far", "rejected"]) {
    expect(buckets[code], `корзина ${code}`).toBeGreaterThan(0);
  }
  const rows = (await (
    await curator.request.get("/api/suggestions/from-students/")
  ).json()) as { results: { sharp_jump: boolean }[] };
  expect(rows.results.some((row) => row.sharp_jump)).toBeTruthy();
  await curator.context().close();
});
