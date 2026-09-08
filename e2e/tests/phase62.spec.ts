/**
 * Фаза 62 — документы, заметки и связь с владельцами доменов в живом браузере.
 *
 * Экран «Документы» с матрицей и пятью числами, предпросмотр с решением,
 * отклонение с причиной и то, что видит ученик, «напомнить всем»,
 * заметки (ученик не видит), звонок родителям, передача строки Кымбат
 * и её очередь, журнал, уведомления куратора.
 *
 * Кнопка считается рабочей, только если по клику ушёл запрос, ответ 2xx
 * и в консоли пусто — за этим следит `watch()`.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { apiPost, watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

const PDF = Buffer.from(
  "%PDF-1.4\n%probe\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n",
);
const stamp = Date.now();
const NOTE = `Заметка прогона ${stamp}: мама просила звонить после шести`;
const CALL = `Звонок прогона ${stamp}: договорились о сертификате`;
const HANDOVER = `Передача прогона ${stamp}: балл расходится с сертификатом`;

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

/** Ученик прогона загружает документ чек-листа — как форма на «Мои данные». */
async function upload(student: Page, docType: string): Promise<number> {
  const csrf =
    (await student.context().cookies()).find((c) => c.name === "csrftoken")
      ?.value ?? "";
  const response = await student.request.post("/api/documents/", {
    multipart: {
      doc_type: docType,
      file: {
        name: `${docType}.pdf`,
        mimeType: "application/pdf",
        buffer: PDF,
      },
    },
    headers: { "X-CSRFToken": csrf },
  });
  expect(response.status(), await response.text()).toBe(201);
  return ((await response.json()) as { id: number }).id;
}

/** Предложение ученика с резким скачком — строка домена «Экзамены» для передачи. */
async function proposeJump(browser: Browser): Promise<number> {
  const student = await as(browser, "student");
  const me = await (await student.request.get("/api/students/me/")).json();
  const current = Number(me.exam?.ielts_current ?? 6);
  const value = current + 2 <= 9 ? current + 2 : current - 2;
  const made = await apiPost<{ suggestions: number[] }>(
    student,
    "/api/suggestions/propose/",
    {
      rows: [
        {
          model: "students.ExamProfile",
          field: "ielts_current",
          value: String(value),
        },
      ],
    },
  );
  await student.context().close();
  return made.suggestions[0];
}

let studentId = 0;
let studentName = "";

test.beforeAll(async ({ browser }) => {
  const student = await as(browser, "student");
  const me = await (await student.request.get("/api/students/me/")).json();
  studentId = me.id;
  studentName = me.full_name;
  await student.context().close();
});

test("экран «Документы»: пять чисел, фильтры, матрица, выгрузка", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/documents?group=all");

  await expect(page.locator("h1")).toContainText("Документы");
  // пять чисел «собрано / всего» — по числу типов чек-листа
  await expect(page.locator(".statrow .stat")).toHaveCount(5);
  await expect(page.locator(".statrow .stat").first()).toContainText("/");

  const rows = page.locator("table.cdocs tbody tr");
  await expect(rows.first()).toBeVisible();
  const all = await rows.count();
  expect(all).toBeGreaterThan(3);
  // у каждого ученика пять ячеек-кнопок
  await expect(rows.first().locator("button.cdocs__cell")).toHaveCount(5);
  // в посеве есть и полный набор, и незакрытые — оба вида ячеек на экране
  await expect(
    page.locator("button.cdocs__cell--confirmed").first(),
  ).toBeVisible();
  await expect(page.locator("button.cdocs__cell--none").first()).toBeVisible();
  await expect(
    page.locator("button.cdocs__cell--expiring").first(),
  ).toBeVisible();

  // фильтр «Истекает срок» сужает и попадает в адрес. Пока ответ не пришёл,
  // на экране прежний список (`placeholderData`) — ждём сам ответ
  await Promise.all([
    page.waitForResponse((r) => r.url().includes("f=expiring")),
    page.getByRole("button", { name: /^Истекает срок/ }).click(),
  ]);
  await expect(page).toHaveURL(/f=expiring/);
  await expect.poll(async () => rows.count()).toBeLessThan(all);
  const expiring = await rows.count();
  expect(expiring).toBeGreaterThan(0);
  await expect(
    page.locator("button.cdocs__cell--expiring").first(),
  ).toBeVisible();

  await Promise.all([
    page.waitForResponse((r) => r.url().includes("f=missing")),
    page.getByRole("button", { name: /^Не собраны/ }).click(),
  ]);
  await expect(page).toHaveURL(/f=missing/);
  await expect.poll(async () => rows.count()).toBeLessThan(all);
  expect(await rows.count()).toBeGreaterThan(0);

  // выгрузка — настоящий файл
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Выгрузить" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);

  expect(diag.failed).toEqual([]);
  expect(diag.consoleErrors).toEqual([]);
  expect(diag.pageErrors).toEqual([]);
  await page.context().close();
});

test("предпросмотр: подтвердить документ из матрицы", async ({ browser }) => {
  const student = await as(browser, "student");
  await upload(student, "transcript");
  await student.context().close();

  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/documents?group=all");

  const cell = page.getByRole("button", {
    name: `${studentName}, Транскрипт: ждёт проверки`,
  });
  await expect(cell).toBeVisible();
  await cell.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Транскрипт");
  await expect(dialog).toContainText("только после входа");
  // файл открывается внутри окна — сам запрос за ним должен быть 200
  await expect(dialog.locator("iframe.cdoc__pdf")).toBeVisible();

  const mark = diag.mark();
  await dialog
    .getByRole("button", { name: "Подтвердить", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(
    diag
      .since(mark)
      .some((c) => c.url.includes("/review/") && c.status === 200),
  ).toBeTruthy();
  await expect(
    page.getByRole("button", {
      name: `${studentName}, Транскрипт: подтверждён`,
    }),
  ).toBeVisible();

  expect(diag.consoleErrors).toEqual([]);
  await page.context().close();
});

test("отклонение с причиной: ученик видит причину, но не проверившего", async ({
  browser,
}) => {
  const student = await as(browser, "student");
  await upload(student, "recommendation");

  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/documents?group=all");
  await page
    .getByRole("button", {
      name: `${studentName}, Рекомендательное письмо: ждёт проверки`,
    })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Отклонить", exact: true }).click();
  // без причины не уходит
  await expect(
    dialog.getByRole("button", { name: "Отклонить с причиной" }),
  ).toBeDisabled();
  await dialog.getByRole("button", { name: "Скан нечёткий" }).click();
  await expect(dialog.getByLabel("Причина отклонения")).toHaveValue(
    "Скан нечёткий",
  );
  const mark = diag.mark();
  await dialog.getByRole("button", { name: "Отклонить с причиной" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(
    diag
      .since(mark)
      .some((c) => c.url.includes("/review/") && c.status === 200),
  ).toBeTruthy();
  await expect(
    page.getByRole("button", {
      name: `${studentName}, Рекомендательное письмо: отклонён`,
    }),
  ).toBeVisible();
  await page.context().close();

  // ученик: статус и причина на «Мои данные», имени куратора нет
  await student.goto("/my-data");
  await student.getByRole("tab", { name: "Документы" }).click();
  const body = student.locator("body");
  await expect(body).toContainText("Скан нечёткий");
  await expect(body).toContainText("загрузите заново");
  await expect(body).not.toContainText("Асель");
  await expect(body).not.toContainText("curator@probe.local");

  // перезагрузка после отклонения: тип снова ждёт проверки, история остаётся
  const before = (
    (await (await student.request.get("/api/documents/")).json()) as {
      results: unknown[];
    }
  ).results.length;
  await upload(student, "recommendation");
  const after = (
    (await (await student.request.get("/api/documents/")).json()) as {
      results: { id: number; doc_type: string; status: string }[];
    }
  ).results;
  expect(after.length).toBe(before + 1);
  // последний по типу — снова «ждёт проверки», отклонённый остался историей
  const recs = after
    .filter((r) => r.doc_type === "recommendation")
    .sort((a, b) => a.id - b.id);
  expect(recs.at(-1)?.status).toBe("pending");
  expect(recs.some((r) => r.status === "rejected")).toBeTruthy();
  await student.context().close();

  // куратору пришло уведомление о перезагрузке
  const again = await as(browser, "curator");
  const bell = (await (
    await again.request.get("/api/notifications/")
  ).json()) as { rows: { text: string }[] };
  expect(
    bell.rows.some((row) => row.text.includes("перезагрузил документ")),
  ).toBeTruthy();
  await again.context().close();
});

test("напомнить всем: задача каждому со списком его недостающих", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/documents?group=BOSTON");
  await expect(page.locator("table.cdocs tbody tr").first()).toBeVisible();

  await page
    .getByRole("button", { name: "Напомнить всем, у кого не хватает" })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Учеников без полного набора:");
  const countText = await dialog.locator("b.num").innerText();
  const count = Number(countText);
  expect(count).toBeGreaterThan(0);

  const mark = diag.mark();
  await dialog.getByRole("button", { name: /^Отправить/ }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const call = diag
    .since(mark)
    .find((c) => c.url.includes("/documents/remind/"));
  expect(call?.status).toBe(200);

  await page.goto("/tasks?group=BOSTON&filter=open");
  const made = page.locator(".rowline", { hasText: "Загрузить:" });
  await expect(made.first()).toBeVisible();
  expect(await made.count()).toBeGreaterThanOrEqual(count);
  expect(diag.consoleErrors).toEqual([]);
  await page.context().close();
});

test("карточка: вкладка «Документы» и напоминание одному", async ({
  browser,
}) => {
  // свой отклонённый документ — чтобы причина на вкладке не зависела от посева
  const student = await as(browser, "student");
  await upload(student, "attestat");
  await student.context().close();
  const page = await as(browser, "curator");
  const matrix = (await (
    await page.request.get("/api/curator/documents/?group=all")
  ).json()) as {
    results: {
      id: number;
      cells: { code: string; suggestion: number | null }[];
    }[];
  };
  const attestat = matrix.results
    .find((r) => r.id === studentId)
    ?.cells.find((c) => c.code === "attestat");
  expect(attestat?.suggestion, "строка очереди у аттестата").toBeTruthy();
  await apiPost(page, `/api/suggestions/${attestat!.suggestion}/review/`, {
    decision: "decline",
    reason: "Не тот документ",
  });

  const diag = watch(page);
  await page.goto(`/students/${studentId}?tab=documents`);

  await expect(page.locator("body")).toContainText("Напомнить о недостающих");
  // пять строк — по типу, с подписью состояния
  const rows = page.locator(".datacard .rowline");
  await expect(rows).toHaveCount(5);
  await expect(page.locator("body")).toContainText("Причина: Не тот документ");

  const mark = diag.mark();
  await page.getByRole("button", { name: "Напомнить о недостающих" }).click();
  await expect
    .poll(
      () =>
        diag.since(mark).find((c) => c.url.includes("/documents/remind/"))
          ?.status ?? 0,
    )
    .toBe(200);

  // число «Документы» на обзоре ведёт на вкладку
  await page.getByRole("tab", { name: "Обзор" }).click();
  await page.locator(".stat", { hasText: "Документы" }).click();
  await expect(page).toHaveURL(/tab=documents/);
  expect(diag.consoleErrors).toEqual([]);
  await page.context().close();
});

test("заметки: куратор пишет, Кымбат читает, ученик не видит", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto(`/students/${studentId}?tab=notes`);
  await expect(page.locator("body")).toContainText("ученик не видит");

  await page.getByLabel("Новая заметка").fill(NOTE);
  const mark = diag.mark();
  await page.getByRole("button", { name: "Сохранить заметку" }).click();
  await expect(page.locator(".rowline", { hasText: NOTE })).toBeVisible();
  expect(
    diag.since(mark).some((c) => c.url.includes("/notes/") && c.status === 201),
  ).toBeTruthy();
  await page.context().close();

  // Кымбат видит заметку в карточке ученика, только читает
  const kymbat = await as(browser, "director_exam");
  await kymbat.goto(`/students/${studentId}`);
  await expect(kymbat.locator("body")).toContainText(NOTE);
  await expect(
    kymbat.getByRole("button", { name: "Сохранить заметку" }),
  ).toHaveCount(0);
  await kymbat.context().close();

  // Асем — нет: список ролей на сервере
  const asem = await as(browser, "director_admission");
  await asem.goto(`/students/${studentId}`);
  await expect(asem.locator("h1")).toBeVisible();
  await expect(asem.locator("body")).not.toContainText(NOTE);
  await asem.context().close();

  // ученик — никогда: ни на экранах, ни в API
  const student = await as(browser, "student");
  for (const path of ["/dashboard", "/my-data", "/roadmap"]) {
    await student.goto(path);
    await expect(student.locator("h1").first()).toBeVisible();
    await expect(student.locator("body")).not.toContainText("Заметка прогона");
  }
  expect((await student.request.get("/api/notes/")).status()).toBe(403);
  expect(
    (await student.request.get(`/api/notes/?student=${studentId}`)).status(),
  ).toBe(403);
  await student.context().close();
});

test("звонок родителям: телефон с владельцем, итог уходит в заметки и журнал", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto(`/students/${studentId}`);

  await page.getByRole("button", { name: "Родителям" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Контакт ведёт");
  await expect(dialog).toContainText("Салтанат");
  await dialog.getByPlaceholder("Коротко").fill(CALL);
  const mark = diag.mark();
  await dialog.getByRole("button", { name: "Сохранить итог звонка" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(
    diag.since(mark).some((c) => c.url.includes("/call/") && c.status === 200),
  ).toBeTruthy();

  await page.getByRole("tab", { name: "Заметки" }).click();
  await expect(
    page.locator(".rowline", { hasText: `Звонок родителям: ${CALL}` }),
  ).toBeVisible();

  await page.goto("/journal?group=all");
  await expect(page.locator("body")).toContainText("Звонок родителям");
  expect(diag.consoleErrors).toEqual([]);
  await page.context().close();
});

test("передача Кымбат: строка уходит к владельцу, ответ возвращается уведомлением", async ({
  browser,
}) => {
  const suggestion = await proposeJump(browser);

  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/queue?group=all");
  const row = page.locator(`[data-suggestion="${suggestion}"]`);
  await expect(row).toBeVisible();
  // у строки экзамена кнопка подписана владельцем домена
  await row.getByRole("button", { name: "Передать Кымбат" }).click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("button", { name: "Передать", exact: true }),
  ).toBeDisabled();
  await dialog.getByPlaceholder("Что смущает").fill(HANDOVER);
  const mark = diag.mark();
  await dialog.getByRole("button", { name: "Передать", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(
    diag
      .since(mark)
      .some((c) => c.url.includes("/escalate/") && c.status === 200),
  ).toBeTruthy();

  // строка ушла из очереди в блок внизу — с именем адресата
  await expect(
    page.locator(`.squeue__row[data-suggestion="${suggestion}"]`),
  ).toHaveCount(0);
  const handed = page.locator(".cescalated");
  await expect(handed).toContainText("Передано владельцу");
  await expect(handed).toContainText("у Кымбат");
  await expect(handed).toContainText(HANDOVER);

  // вернуть себе — и передать снова: до решения владельца строка своя
  await handed.getByRole("button", { name: "Вернуть себе" }).click();
  await expect(
    page.locator(`.squeue__row[data-suggestion="${suggestion}"]`),
  ).toBeVisible();
  await apiPost(page, `/api/suggestions/${suggestion}/escalate/`, {
    comment: HANDOVER,
  });
  await page.context().close();

  // Кымбат: строка сверху её очереди, с именем куратора и его словами
  const kymbat = await as(browser, "director_exam");
  const kdiag = watch(kymbat);
  await kymbat.goto("/suggestions");
  const queue = kymbat.locator("#student-queue");
  const first = queue.locator(".squeue__row").first();
  await expect(first).toHaveAttribute("data-suggestion", String(suggestion));
  await expect(first).toContainText("от куратора Асель");
  await expect(first).toContainText(HANDOVER);
  const kmark = kdiag.mark();
  await first.getByRole("button", { name: "Подтвердить", exact: true }).click();
  await expect(queue.locator(`[data-suggestion="${suggestion}"]`)).toHaveCount(
    0,
  );
  expect(
    kdiag
      .since(kmark)
      .some((c) => c.url.includes("/review/") && c.status === 200),
  ).toBeTruthy();
  await kymbat.context().close();

  // куратор: уведомление в колокольчике ведёт к ученику
  const back = await as(browser, "curator");
  await back.goto("/dashboard");
  await back.locator(".notif__button").click();
  const notice = back
    .locator(".notif__row", { hasText: "ответ на переданное" })
    .first();
  await expect(notice).toBeVisible();
  await notice.click();
  await expect(back).toHaveURL(/\/students\/\d+/);
  await back.context().close();
});

test("очередь: вкладка «Документы» и строка документа с файлом", async ({
  browser,
}) => {
  const student = await as(browser, "student");
  const docId = await upload(student, "exam_certificate");
  await student.context().close();

  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/queue?group=all");
  await page.getByRole("button", { name: /^Документы/ }).click();
  const row = page
    .locator(".squeue__row", { hasText: "exam_certificate" })
    .first();
  await expect(row).toBeVisible();
  await expect(row).toContainText("Сертификат экзамена");
  // «Поправить» у документа нет, есть файл и «Передать Асем»
  await expect(row.getByRole("button", { name: "Поправить" })).toHaveCount(0);
  await expect(
    row.getByRole("button", { name: "Передать Асем" }),
  ).toBeVisible();
  await row.getByRole("button", { name: "Открыть файл" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Сертификат экзамена");
  const mark = diag.mark();
  await dialog
    .getByRole("button", { name: "Подтвердить", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(
    diag
      .since(mark)
      .some((c) => c.url.includes("/review/") && c.status === 200),
  ).toBeTruthy();
  // файл открылся из окна — запрос за ним прошёл
  expect(
    diag.calls.some(
      (c) => c.url.includes(`/documents/${docId}/file/`) && c.status === 200,
    ),
  ).toBeTruthy();

  // снять подтверждение — документ снова в очереди
  await page.goto(`/students/${studentId}?tab=documents`);
  await page
    .locator(".rowline", { hasText: "Сертификат экзамена" })
    .getByRole("button", { name: "Открыть" })
    .click();
  const again = page.getByRole("dialog");
  const rmark = diag.mark();
  await again.getByRole("button", { name: "Снять подтверждение" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(
    diag
      .since(rmark)
      .some((c) => c.url.includes("/revoke/") && c.status === 200),
  ).toBeTruthy();
  await expect(
    page.locator(".rowline", { hasText: "Сертификат экзамена" }),
  ).toContainText("ждёт проверки");
  expect(diag.consoleErrors).toEqual([]);
  await page.context().close();
});

test("журнал: только чтение, по группе, выгрузка", async ({ browser }) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  await page.goto("/journal?group=all");
  await expect(page.locator("h1")).toContainText("Журнал");
  const rows = page.locator("table.tbl tbody tr");
  await expect(rows.first()).toBeVisible();
  await expect(page.locator("body")).toContainText("Передано владельцу домена");
  // ни одной кнопки правки в таблице — журнал не редактируется
  await expect(page.locator("table.tbl button")).toHaveCount(0);

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Выгрузить" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);

  // «Прочитать все» в колокольчике — один запрос, точка гаснет
  await page.locator(".notif__button").click();
  const mark = diag.mark();
  await page.locator(".notif__all").click();
  await expect
    .poll(() =>
      diag
        .since(mark)
        .some(
          (c) => c.url.includes("/notifications/read/") && c.status === 200,
        ),
    )
    .toBeTruthy();
  expect(diag.consoleErrors).toEqual([]);
  await page.context().close();
});
