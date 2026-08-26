/**
 * Фаза 10: каталог вузов, процент соответствия, подбор.
 *
 * Приёмка: ученик с IELTS 6.0 находит программу, видит процент и разрыв
 * «не хватает 0.5 IELTS», добавляет её как target, она появляется в его
 * списке и у Асем на подтверждении. Подбор по стране, которой нет
 * в справочнике, честно говорит, что данных нет.
 */
import { expect, test } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { apiPost, watch } from "../helpers/session";

/** Ученик один на все сценарии: условия теста ставим сами, а не надеемся. */
async function setStudentIelts(
  browser: import("@playwright/test").Browser,
  value: string,
): Promise<void> {
  const context = await browser.newContext({
    storageState: statePath("director_exam"),
  });
  const page = await context.newPage();
  await page.goto("/dashboard");
  const found = await (
    await page.request.get("/api/students/?search=student%40probe.local&page_size=10")
  ).json();
  await apiPost(page, "/api/batch/save/", {
    changes: [
      {
        student: found.results.find((r: { email: string }) => r.email === "student@probe.local")!.id,
        model: "students.ExamProfile",
        field: "ielts_current",
        value,
      },
    ],
  });
  await context.close();
}

/** Освободить место в списке вузов: прошлые прогоны его наполняют. */
async function clearStudentAdditions(
  browser: import("@playwright/test").Browser,
): Promise<void> {
  const context = await browser.newContext({
    storageState: statePath("director_admission"),
  });
  const page = await context.newPage();
  await page.goto("/dashboard");
  const csrf = (await context.cookies()).find(
    (c) => c.name === "csrftoken",
  )!.value;
  const payload = await (
    await page.request.get("/api/student-universities/?page_size=200")
  ).json();
  for (const row of payload.results ?? payload) {
    if (row.added_by === "student") {
      await page.request.delete(`/api/student-universities/${row.id}/`, {
        headers: { "X-CSRFToken": csrf },
      });
    }
  }
  await context.close();
}

/** Слова, которыми проценту называться нельзя (инвариант №11). */
const FORBIDDEN = /шанс|вероятност|прогноз/i;

test.describe("каталог глазами ученика", () => {
  test.use({ storageState: statePath("student") });

  test("карточка показывает процент, разбивку и конкретный разрыв", async ({
    page,
  }) => {
    const diag = watch(page);
    await page.goto("/catalog");
    await expect(page.locator("h1")).toContainText("Каталог вузов");

    const card = page.locator(".match").first();
    await expect(card).toBeVisible();
    await expect(card.locator(".match__value")).toContainText("%");
    await expect(card.locator(".match__caption")).toContainText(
      "соответствие требованиям",
    );
    await expect(card.locator(".match__breakdown")).toBeVisible();
    expect(diag.failed).toEqual([]);
  });

  test("у программы с порогом IELTS выше текущего виден разрыв 0.5 IELTS", async ({
    page,
    browser,
  }) => {
    await setStudentIelts(browser, "6.0");

    const response = await page.request.get("/api/catalog/");
    const { results } = await response.json();

    const withGap = results.find((card: { summary: string }) =>
      card.summary.includes("0.5 IELTS"),
    );
    expect(
      withGap,
      "у ученика с IELTS 6.0 должна найтись программа с порогом 6.5",
    ).toBeTruthy();
    expect(withGap.percent).toBeGreaterThan(0);
    expect(withGap.percent).toBeLessThanOrEqual(100);

    const english = withGap.breakdown.find(
      (p: { code: string }) => p.code === "english",
    );
    expect(english.gap_phrase).toContain("0.5 IELTS");

    await page.goto("/catalog");
    await page
      .locator('[data-slot="input"]')
      .first()
      .fill(withGap.university_name);
    const card = page
      .locator(".match")
      .filter({ hasText: withGap.university_name });
    await expect(card.first()).toBeVisible();
    await expect(card.first()).toContainText("не хватает");
  });

  test("нигде не обещается шанс поступления", async ({ page }) => {
    for (const route of ["/catalog", "/universities"]) {
      await page.goto(route);
      await page.waitForTimeout(700);
      const text = await page.locator("main").innerText();
      expect(
        text,
        `на ${route} проценту дано запрещённое название`,
      ).not.toMatch(FORBIDDEN);
    }
  });

  test("«что откроется, если» пересчитывает список по ползункам", async ({
    page,
  }) => {
    await page.goto("/catalog");
    await page.getByRole("tab", { name: "Что откроется, если" }).click();

    const slider = page.locator('input[type="range"]').first();
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/match/what-if/")),
      slider.fill("1"),
    ]);
    expect(response.status()).toBe(200);

    const payload = await response.json();
    expect(payload.results.length).toBeGreaterThan(0);
    await expect(
      page.locator('[data-slot="badge"][data-variant="ok"]').first(),
    ).toContainText("Проходите полностью");
    // карточки пересчитались: у каждой видно, каким процент был и каким стал
    await expect(page.locator(".match").first()).toContainText("Соответствие");
  });
});

test.describe("подбор словами", () => {
  test.use({ storageState: statePath("student") });

  test("называет только программы справочника", async ({ page }) => {
    const known = await (await page.request.get("/api/catalog/")).json();
    const names: string[] = known.results.map(
      (c: { university_name: string }) => c.university_name,
    );

    const response = await page.request.post("/api/catalog/pick/", {
      data: { text: "хочу в Канаду на Computer Science" },
      headers: {
        "X-CSRFToken": (await page.context().cookies()).find(
          (c) => c.name === "csrftoken",
        )!.value,
      },
    });
    const payload = await response.json();

    expect(payload.picks.length).toBeGreaterThan(0);
    for (const pick of payload.picks) {
      expect(names, `${pick.university_name} нет в справочнике`).toContain(
        pick.university_name,
      );
    }
    expect(JSON.stringify(payload)).not.toMatch(FORBIDDEN);
  });

  test("по стране, которой нет в справочнике, честно говорит об этом", async ({
    page,
  }) => {
    await page.goto("/catalog");
    await page.getByRole("tab", { name: "Подобрать словами" }).click();
    await page.locator("textarea").fill("хочу учиться в Японии");

    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/catalog/pick/")),
      page.getByRole("button", { name: "Подобрать", exact: true }).click(),
    ]);
    expect(response.status()).toBe(200);

    await expect(page.locator(".catalog__note")).toContainText(
      "нет программ по запросу",
    );
    await expect(page.locator(".catalog__note")).toContainText("Япония");
  });
});

test.describe("добавление в свой список", () => {
  test("ученик добавляет target, Асем видит это на подтверждении", async ({
    browser,
  }) => {
    test.setTimeout(120_000);
    await clearStudentAdditions(browser);

    const studentContext = await browser.newContext({
      storageState: statePath("student"),
    });
    const student = await studentContext.newPage();
    await student.goto("/catalog");

    // берём программу, которой ещё нет в списке
    const { results } = await (
      await student.request.get("/api/catalog/")
    ).json();
    const target = results.find((c: { in_my_list: boolean }) => !c.in_my_list);
    expect(target, "нужна программа вне списка ученика").toBeTruthy();

    await student
      .locator('[data-slot="input"]')
      .first()
      .fill(target.university_name);
    const card = student
      .locator(".match")
      .filter({ hasText: target.university_name })
      .first();
    await expect(card).toBeVisible();
    await expect(
      card.getByRole("button", { name: "Добавить к себе" }),
    ).toBeVisible();

    await card.getByRole("button", { name: "Добавить к себе" }).click();
    const [added] = await Promise.all([
      student.waitForResponse((r) => r.url().includes("/api/catalog/add/")),
      card.getByRole("button", { name: /^target/ }).click(),
    ]);
    expect(added.status()).toBe(201);
    await expect(card).toContainText("уже в вашем списке");

    // она видна в «Моих вузах» и помечена как ждущая подтверждения
    await student.goto("/universities");
    await expect(
      student.locator(".match").filter({ hasText: target.university_name }),
    ).toContainText("ждёт подтверждения");

    // Асем видит её отдельным списком и подтверждает
    const directorContext = await browser.newContext({
      storageState: statePath("director_admission"),
    });
    const director = await directorContext.newPage();
    await director.goto("/dashboard");
    const queue = director
      .locator(".card")
      .filter({ hasText: "Ученики добавили себе" });
    await expect(queue).toContainText(target.university_name);

    const [confirmed] = await Promise.all([
      director.waitForResponse((r) =>
        r.url().includes("/api/catalog/pending/"),
      ),
      queue.getByRole("button", { name: "Подтвердить" }).first().click(),
    ]);
    expect(confirmed.status()).toBe(200);

    // после перезагрузки пометка снята — изменение доехало до базы
    await student.reload();
    await expect(
      student.locator(".match").filter({ hasText: target.university_name }),
    ).not.toContainText("ждёт подтверждения");

    // прибираем за собой: иначе следующий прогон не найдёт свободной программы
    const csrf = (await directorContext.cookies()).find(
      (c) => c.name === "csrftoken",
    )!.value;
    const entry = await (
      await director.request.get(
        `/api/student-universities/?program=${target.program}`,
      )
    ).json();
    const mine = (entry.results ?? entry).find(
      (row: { program: number }) => row.program === target.program,
    );
    if (mine) {
      await director.request.delete(`/api/student-universities/${mine.id}/`, {
        headers: { "X-CSRFToken": csrf },
      });
    }

    await studentContext.close();
    await directorContext.close();
  });

  test("добавленное директором ученик снять не может", async ({
    page,
    request,
  }) => {
    const browser = page.context().browser()!;

    // условие ставим сами: директор кладёт программу в список ученика.
    // Полагаться на то, что её туда положил соседний прогон, нельзя
    const directorContext = await browser.newContext({
      storageState: statePath("director_admission"),
    });
    const directorPage = await directorContext.newPage();
    await directorPage.goto("/dashboard");
    const directorCsrf = (await directorContext.cookies()).find(
      (c) => c.name === "csrftoken",
    )!.value;
    const found = await (
      await directorPage.request.get(
        "/api/students/?search=student%40probe.local&page_size=10",
      )
    ).json();
    const studentId = found.results.find((r: { email: string }) => r.email === "student@probe.local")!.id;
    const catalogPrograms = await (
      await directorPage.request.get("/api/programs/?page_size=100")
    ).json();
    const taken = await (
      await directorPage.request.get(
        `/api/student-universities/?student=${studentId}&page_size=100`,
      )
    ).json();
    const usedIds = new Set(
      (taken.results ?? []).map((row: { program: number }) => row.program),
    );
    const free = catalogPrograms.results.find(
      (row: { id: number }) => !usedIds.has(row.id),
    );
    if (free) {
      await directorPage.request.post("/api/student-universities/", {
        data: { student: studentId, program: free.id, tier: "target" },
        headers: { "X-CSRFToken": directorCsrf },
      });
    }
    await directorContext.close();

    const context = await browser.newContext({
      storageState: statePath("student"),
    });
    const student = await context.newPage();
    await student.goto("/universities");

    const { results } = await (
      await student.request.get("/api/catalog/")
    ).json();
    const byDirector = results.find(
      (c: { my_entry: { added_by: string } | null }) =>
        c.my_entry && c.my_entry.added_by === "director",
    );
    expect(byDirector, "нужна запись, добавленная директором").toBeTruthy();

    const csrf = (await context.cookies()).find(
      (c) => c.name === "csrftoken",
    )!.value;
    const denied = await student.request.delete(
      `/api/catalog/remove/${byDirector.my_entry.id}/`,
      {
        headers: { "X-CSRFToken": csrf },
      },
    );
    expect(denied.status()).toBe(403);
    await context.close();
    expect(request).toBeTruthy();
  });
});
