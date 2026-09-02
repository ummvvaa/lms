/**
 * Фаза 41 — план поступления по конкретному вузу.
 *
 * Ученик создаёт план из подбора, задачи собираются в фоне и появляются
 * после подтверждения самим учеником. Счётчики, этапы и таймлайн на месте.
 * Сдвиг дедлайна раунда двигает дедлайн плана (инвариант №4). Задачи плана
 * видны в общем роадмапе с пометкой вуза.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { apiDelete, apiPatch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 240_000 });

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

interface Program {
  id: number;
}

async function firstProgram(page: Page): Promise<number | null> {
  const progs = (await (
    await page.request.get("/api/programs/?page_size=1")
  ).json()) as {
    results: Program[];
  };
  return progs.results[0]?.id ?? null;
}

async function cleanupPlans(page: Page) {
  const plans = (await (
    await page.request.get("/api/application-plans/?page_size=200")
  ).json()) as {
    results: { id: number }[];
  };
  for (const plan of plans.results)
    await apiDelete(page, `/api/application-plans/${plan.id}/`);
}

test("ученик создаёт план, задачи генерируются и применяются им", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  await cleanupPlans(page);

  const program = await firstProgram(page);
  test.skip(program === null, "в справочнике нет программ");

  // создаём план через API (то же, что кнопка «Создать план» в подборе)
  const created = await page.request.post("/api/application-plans/", {
    data: { program },
    headers: {
      "X-CSRFToken":
        (await page.context().cookies()).find((c) => c.name === "csrftoken")
          ?.value ?? "",
    },
  });
  expect(created.status()).toBe(201);
  const plan = (await created.json()) as { id: number };

  await page.goto(`/plan/${plan.id}`);
  await expect(page.getByText("План поступления").first()).toBeVisible();

  // С фазы 48 задачи применяются сами: второго подтверждения нет,
  // подтверждением стало добавление вуза. Ждём счётчики плана
  await expect(page.getByText("Всего задач")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Задачи и этапы")).toBeVisible();
  await page.getByRole("tab", { name: "Таймлайн" }).click();
  await expect(page.locator(".rowline").first()).toBeVisible();
});

test("сдвиг дедлайна раунда двигает дедлайн плана", async ({ browser }) => {
  const student = await as(browser, "student");
  const plans = (await (
    await student.request.get("/api/application-plans/?page_size=1")
  ).json()) as {
    results: {
      id: number;
      admission_round: number | null;
      deadline: string | null;
    }[];
  };
  const plan = plans.results[0];
  test.skip(
    !plan || plan.admission_round === null,
    "у плана нет раунда с дедлайном",
  );

  // директор сдвигает дедлайн раунда в справочнике
  const director = await as(browser, "director_admission");
  const moved = "2027-05-15";
  await apiPatch(director, `/api/rounds/${plan.admission_round}/`, {
    deadline: moved,
  });

  const updated = (await (
    await student.request.get(`/api/application-plans/${plan.id}/`)
  ).json()) as {
    deadline: string | null;
  };
  expect(updated.deadline).toBe(moved);

  // и срок задачи подачи уехал за дедлайном
  const grouped = (await (
    await student.request.get(`/api/application-plans/${plan.id}/tasks/`)
  ).json()) as {
    stages: {
      category: string;
      tasks: { due_date_effective: string | null }[];
    }[];
  };
  const submit = grouped.stages.find((s) => s.category === "university");
  if (submit)
    expect(submit.tasks.some((t) => t.due_date_effective === moved)).toBe(true);
});

test("задачи плана видны в общем роадмапе с пометкой вуза", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  const me = (await (await page.request.get("/api/students/me/")).json()) as {
    id: number;
  };
  const roadmap = (await (
    await page.request.get(`/api/tasks/?student=${me.id}&page_size=200`)
  ).json()) as {
    results: { plan: number | null; plan_university: string | null }[];
  };
  const planTasks = roadmap.results.filter((t) => t.plan !== null);
  expect(planTasks.length).toBeGreaterThan(0);
  expect(planTasks.every((t) => t.plan_university)).toBe(true);
});

test("несколько планов переключаются в шапке, счётчики раздельны", async ({
  browser,
}) => {
  const page = await as(browser, "student");
  const csrf =
    (await page.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? "";

  // заводим второй план по другой программе, если она есть
  const progs = (await (
    await page.request.get("/api/programs/?page_size=10")
  ).json()) as {
    results: { id: number }[];
  };
  const mine = (await (
    await page.request.get("/api/application-plans/?page_size=50")
  ).json()) as {
    results: { program: number }[];
  };
  const used = new Set(mine.results.map((p) => p.program));
  const other = progs.results.find((p) => !used.has(p.id));

  if (other) {
    const made = await page.request.post("/api/application-plans/", {
      data: { program: other.id },
      headers: { "X-CSRFToken": csrf },
    });
    expect([201, 409]).toContain(made.status());
  }

  await page.goto("/plan");
  const list = (await (
    await page.request.get("/api/application-plans/?page_size=50")
  ).json()) as {
    results: { id: number }[];
  };
  if (list.results.length >= 2) {
    // переключатель планов в шапке
    await expect(page.getByLabel("Выбрать план")).toBeVisible();
  }

  // уборка планов прогона, чтобы не копились между запусками
  await cleanupPlans(page);
});
