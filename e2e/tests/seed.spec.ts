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

/** Ученики прогона: ФИО без пометок-заглушек, почта под доменом прогона. */
const PUPILS: { name: string; email: string; group: string }[] = [
  { name: "Сейткали Айгерим", email: probeEmail("pupil01"), group: "11A" },
  { name: "Абдрахманов Данияр", email: probeEmail("pupil02"), group: "11A" },
  { name: "Ержанова Малика", email: probeEmail("pupil03"), group: "11A" },
  { name: "Оспанов Тимур", email: probeEmail("pupil04"), group: "11A" },
  { name: "Сулейменова Дана", email: probeEmail("pupil05"), group: "11B" },
  { name: "Жумабеков Алихан", email: probeEmail("pupil06"), group: "11B" },
  { name: "Нурланова Камила", email: probeEmail("pupil07"), group: "11B" },
  { name: "Кайратов Арсен", email: probeEmail("pupil08"), group: "11B" },
  { name: "Бекова Аружан", email: probeEmail("pupil09"), group: "10A" },
  { name: "Мусин Ерлан", email: probeEmail("pupil10"), group: "10A" },
];

interface Row {
  id: number;
  email: string;
  full_name: string;
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
  for (const [code, grade] of [
    ["11A", 11],
    ["11B", 11],
    ["10A", 10],
  ] as const) {
    if (!have.has(code)) await apiPost(page, "/api/groups/", { code, grade });
  }
  const fresh = (
    await (await page.request.get("/api/groups/?page_size=100")).json()
  ).results as { id: number; code: string }[];
  const byCode = new Map(fresh.map((g) => [g.code, g.id]));

  // ученик прогона: учётная запись уже есть, заводим карточку — они
  // свяжутся по почте сами (фаза 16)
  const mine = await students(page);
  if (!mine.some((row) => row.email === probeEmail("student"))) {
    await apiPost(page, "/api/students/", {
      last_name: "Прогон",
      first_name: "Айгерим",
      email: probeEmail("student"),
      grade: 11,
      group: byCode.get("11A"),
      graduation_year: 2027,
    });
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

test("академический директор: баллы и пробные", async ({ browser }) => {
  const page = await as(browser, "director_exam");
  const rows = await students(page);
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
