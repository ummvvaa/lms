/**
 * Фиксированный посев под эталоны раскладки (фаза 54).
 *
 * Обычный посев прогонов (`seed.spec.ts`) заводит данные так, как это
 * делал бы человек в первый рабочий день, и от прогона к прогону они
 * разные: даты считаются от «сегодня», а поверх посева сотня проверок
 * пишет своё. Для сравнения раскладки это яд — эталон краснел там, где
 * раскладка не менялась (D29).
 *
 * Здесь школа заводится числами, закреплёнными в коде: те же имена,
 * те же баллы, те же даты, тот же порядок. Данные ставятся через тот же
 * API и руками тех же ролей, что и везде (решение фазы 24 — фикстур
 * с выдуманными учениками в коде проекта нет).
 *
 * Что сюда намеренно не заводится:
 * • вуз в списке ученика — он сам заводит план (фаза 48), а план рисует
 *   «до дедлайна N дн.», и это число меняется каждый день;
 * • цели по экзаменам — они порождают автозадачи со сроком, а срок это
 *   опять обратный отсчёт;
 * • задачи со сроком — по той же причине.
 * Всё, что всё-таки считается от «сегодня», маскируется при сравнении
 * (`baseline.spec.ts`), а не лечится порогом.
 *
 * Идёт своим проектом в самом конце прогона и начинается с обнуления
 * базы: тогда снимок не зависит ни от того, что оставили journey и path,
 * ни от того, что успели натворить четыреста проверок до него, и сам он
 * ничего не портит остальным.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { apiPost } from "../helpers/session";
import { resetAll } from "../helpers/manage";

test.describe.configure({ mode: "serial", timeout: 300_000 });

/** Даты закреплены числами: «сегодня минус N» уехало бы за неделю. */
export const FIXED = {
  /** Дедлайн раунда — далеко впереди, чтобы не выпасть из окна календаря. */
  deadline: "2027-01-15",
  /** Соревнование впереди: по нему в календаре есть ближайшее событие. */
  competition: "2026-11-12",
  /** Активность позади — строка портфолио. */
  activity: "2026-06-10",
  /** Две волны пробных: по ним рисуется динамика. */
  mockFirst: "2026-07-20",
  mockSecond: "2026-08-24",
};

/** Ученики эталона: пятеро, порядок и имена закреплены. */
const PUPILS = [
  { name: "Абдрахманов Данияр", email: probeEmail("base01"), group: "11A" },
  { name: "Ержанова Малика", email: probeEmail("base02"), group: "11A" },
  { name: "Оспанов Тимур", email: probeEmail("base03"), group: "11B" },
  { name: "Сулейменова Дана", email: probeEmail("base04"), group: "11B" },
];

/** Значения профилей — по одному числу на ученика, в том же порядке. */
const IELTS = [6.5, 7.0, 6.0, 7.5, 5.5];
const SAT = [1350, 1450, 1200, 1500, 1120];
const GPA = [3.7, 3.9, 3.4, 4.0, 3.1];
const ATTENDANCE = [94, 98, 86, 99, 74];
const STATUS = [
  "can_execute",
  "can_execute",
  "needs_supervision",
  "can_execute",
  "critical",
];
const COUNTRY = ["США", "Канада", "Великобритания", "Нидерланды", "США"];
const MAJOR = ["информатика", "экономика", "медицина", "инженерия", "право"];

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

/**
 * Ученики в закреплённом порядке: сначала ученик прогона, потом четверо
 * остальных по алфавиту. Порядок ответа API брать нельзя — от него
 * зависит, кому какой балл достанется, а значит и картинка.
 */
async function pupils(page: Page): Promise<Row[]> {
  const listing = await (
    await page.request.get("/api/students/?page_size=500")
  ).json();
  const rows = listing.results as Row[];
  const order = [probeEmail("student"), ...PUPILS.map((p) => p.email)];
  return order
    .map((email) => rows.find((row) => row.email === email))
    .filter((row): row is Row => row !== undefined);
}

test.beforeAll(() => {
  // база обнуляется здесь, а не в globalSetup: проект идёт последним,
  // и всё, что до него, к этому моменту уже отработало
  resetAll();
});

test("администратор: две группы и пятеро учеников", async ({ browser }) => {
  const page = await as(browser, "admin");

  for (const [code, grade] of [
    ["11A", 11],
    ["11B", 11],
  ] as const) {
    await apiPost(page, "/api/groups/", { code, grade });
  }
  const groups = (
    await (await page.request.get("/api/groups/?page_size=100")).json()
  ).results as { id: number; code: string }[];
  const byCode = new Map(groups.map((g) => [g.code, g.id]));

  // ученик прогона: учётная запись живёт с globalSetup, карточка
  // связывается с ней по почте сама (фаза 16)
  await apiPost(page, "/api/students/", {
    last_name: "Прогон",
    first_name: "Айгерим",
    email: probeEmail("student"),
    grade: 11,
    group: byCode.get("11A"),
    graduation_year: 2027,
  });

  const applied = await apiPost<{ created: number; skipped: unknown[] }>(
    page,
    "/api/enrollment/apply/",
    {
      rows: PUPILS.map((p) => ({
        full_name: p.name,
        email: p.email,
        grade: "11",
        group: p.group,
      })),
    },
  );
  expect(applied.created).toBe(PUPILS.length);
  expect((await pupils(page)).length).toBe(PUPILS.length + 1);
  await page.context().close();
});

test("директор по поступлению: один вуз, программа и раунд", async ({
  browser,
}) => {
  const page = await as(browser, "director_admission");

  const university = await apiPost<{ id: number }>(page, "/api/universities/", {
    name: "Университет эталона",
    country: "США",
    city: "Бостон",
    world_rank: 42,
  });
  const program = await apiPost<{ id: number }>(page, "/api/programs/", {
    university: university.id,
    name: "Computer Science",
    level: "bachelor",
  });
  await apiPost(page, "/api/rounds/", {
    program: program.id,
    round_type: "RD",
    deadline: FIXED.deadline,
  });

  const rows = await pupils(page);
  await apiPost(page, "/api/batch/save/", {
    changes: rows.flatMap((row, i) => [
      {
        student: row.id,
        model: "students.AdmissionProfile",
        field: "target_country",
        value: COUNTRY[i],
      },
      {
        student: row.id,
        model: "students.AdmissionProfile",
        field: "target_major",
        value: MAJOR[i],
      },
    ]),
  });
  await page.context().close();
});

test("академический директор: баллы и две волны пробных", async ({
  browser,
}) => {
  const page = await as(browser, "director_exam");
  const rows = await pupils(page);

  await apiPost(page, "/api/batch/save/", {
    changes: rows.flatMap((row, i) => [
      {
        student: row.id,
        model: "students.ExamProfile",
        field: "ielts_current",
        value: String(IELTS[i]),
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
        value: String(SAT[i]),
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
        value: String(GPA[i]),
      },
    ]),
  });

  await apiPost(page, "/api/attempts/bulk/", {
    rows: rows.flatMap((row, i) => [
      {
        student: row.id,
        exam_type: "IELTS",
        attempt_format: "mock",
        date: FIXED.mockFirst,
        total_score: String(IELTS[i] - 0.5),
      },
      {
        student: row.id,
        exam_type: "IELTS",
        attempt_format: "mock",
        date: FIXED.mockSecond,
        total_score: String(IELTS[i]),
      },
    ]),
  });
  await page.context().close();
});

test("директор школы: посещаемость, статусы и задачи без срока", async ({
  browser,
}) => {
  const page = await as(browser, "director_behavior");
  const rows = await pupils(page);

  await apiPost(page, "/api/batch/save/", {
    changes: rows.flatMap((row, i) => [
      {
        student: row.id,
        model: "students.BehaviorProfile",
        field: "attendance_percent",
        value: String(ATTENDANCE[i]),
      },
      {
        student: row.id,
        model: "students.BehaviorProfile",
        field: "homework_percent",
        value: String(Math.min(100, ATTENDANCE[i] + 2)),
      },
      {
        student: row.id,
        model: "students.BehaviorProfile",
        field: "status",
        value: STATUS[i],
      },
    ]),
  });

  // задачи намеренно без срока: со сроком в карточке появляется
  // «N дн.», и число меняется каждый день
  const titles = [
    "Пройти пробный IELTS",
    "Собрать портфолио",
    "Написать черновик эссе",
  ];
  for (const [i, row] of rows.slice(0, 3).entries()) {
    await apiPost(page, "/api/tasks/", {
      student: row.id,
      title: titles[i],
      category: "test",
    });
  }
  await page.context().close();
});

test("директор талантов: предмет и активность", async ({ browser }) => {
  const page = await as(browser, "director_talent");
  const subject = await apiPost<{ id: number }>(page, "/api/subjects/", {
    name: "Математика",
  });
  const rows = await pupils(page);
  await apiPost(page, "/api/batch/save/", {
    changes: rows.map((row, i) => ({
      student: row.id,
      model: "students.TalentProfile",
      field: "main_track",
      value: ["olympiad", "research", "startup", "leadership", "olympiad"][i],
    })),
  });
  await apiPost(page, "/api/activities/", {
    student: rows[0].id,
    category: "olympiad",
    title: "Олимпиада по математике",
    date: FIXED.activity,
  });
  expect(subject.id).toBeGreaterThan(0);
  await page.context().close();
});

test("директор спорта: вид спорта и соревнование впереди", async ({
  browser,
}) => {
  const page = await as(browser, "director_sport");
  const sport = await apiPost<{ id: number }>(page, "/api/sport-types/", {
    name: "Футбол",
  });
  const rows = await pupils(page);
  await apiPost(page, "/api/competitions/", {
    student: rows[0].id,
    name: "Кубок города по футболу",
    sport_type: sport.id,
    level: "city",
    date: FIXED.competition,
    result: "1 место",
  });
  await page.context().close();
});
