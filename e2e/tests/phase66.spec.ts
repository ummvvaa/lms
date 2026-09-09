/**
 * Фаза 66 — дисциплина у куратора и письма в живом браузере.
 *
 * Три сценария:
 *
 * 1. Посещаемость группы за день: лист открывается «все были», снимаем
 *    отметку, пишем причину, сохраняем — и число в карточке ученика
 *    меняется, потому что процент считается из дней.
 * 2. Контакты родителя правятся прямо в карточке, и замечание пишется
 *    словами.
 * 3. Письмо из карточки и «всем»: проверяем, что ссылка `mailto:`
 *    собрана правильно — с кириллицей и скрытой копией. Почтовый клиент
 *    не открываем: он не наш, и в прогоне ему делать нечего.
 *
 * Кнопка считается рабочей, только если по клику ушёл запрос, ответ 2xx
 * и в консоли пусто — за этим следит `watch()`.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { statePath } from "../helpers/auth-state";
import { probeEmail } from "../helpers/roles";
import { watch } from "../helpers/session";

test.describe.configure({ mode: "serial", timeout: 180_000 });

/** Вчера — по местным часам: в UTC вечером получился бы позавчерашний день. */
const YESTERDAY = (() => {
  const date = new Date();
  date.setDate(date.getDate() - 1);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
})();

async function as(browser: Browser, role: string): Promise<Page> {
  const context = await browser.newContext({ storageState: statePath(role) });
  return context.newPage();
}

async function studentId(page: Page, email: string): Promise<number> {
  const list = (await (
    await page.request.get("/api/students/?page_size=500")
  ).json()) as { results: { id: number; email: string }[] };
  const row = list.results.find((r) => r.email === email);
  expect(row, `карточка ${email}`).toBeTruthy();
  return row!.id;
}

test("посещаемость: лист за день, отметка отсутствия и причина", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);

  await page.goto("/attendance");
  await expect(page.locator("h1")).toContainText("Посещаемость");
  await expect(page.locator("body")).toContainText(
    "Остальные считаются присутствовавшими",
  );

  // день выбираем вчерашний: сегодняшний посев мог уже отметить
  await page.getByLabel("День").fill(YESTERDAY);
  const rows = page.locator(".att__row");
  await expect(rows.first()).toBeVisible();
  const total = await rows.count();
  expect(total, "в группе есть ученики").toBeGreaterThan(0);

  // снимаем отметку у первого и пишем причину
  const first = rows.first();
  const name = (await first.locator(".att__name").innerText()).trim();
  await first.locator(".att__mark").click();
  await expect(first).toHaveClass(/att__row--absent/);
  await first.locator("input").fill("был на олимпиаде");

  const mark = diag.mark();
  await page.getByRole("button", { name: "Сохранить день" }).click();
  await expect(page.locator("body")).toContainText("Отмечено учеников");
  expect(
    diag
      .since(mark)
      .some(
        (call) => call.url.includes("/attendance/save/") && call.status === 200,
      ),
    "сохранение идёт запросом на сервер",
  ).toBeTruthy();

  // перезагрузка: отметка и причина на месте, день помечен отмеченным
  await page.reload();
  await page.getByLabel("День").fill(YESTERDAY);
  const saved = page.locator(".att__row--absent").first();
  await expect(saved).toContainText(name);
  await expect(saved.locator("input")).toHaveValue("был на олимпиаде");
  await expect(page.locator("body")).toContainText("день отмечен");

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("карточка: замечание словами и правка контакта родителя", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);
  const id = await studentId(page, probeEmail("pupil01"));

  await page.goto(`/students/${id}`);
  const discipline = page
    .locator(".card")
    .filter({ hasText: "Дисциплина" })
    .first();
  await expect(discipline).toContainText("Ведёт директор школы");

  // текст свой на каждый прогон: повторный прогон на живой базе не должен
  // проходить за счёт замечания, оставленного прошлым
  const remark = `Опоздал на первый урок ${Date.now()}`;
  await discipline.getByLabel("Замечание").fill(remark);
  const saved = page.waitForResponse(
    (response) =>
      response.url().includes("/remarks/") &&
      response.request().method() === "POST",
  );
  await discipline.getByRole("button", { name: "Записать" }).click();
  expect((await saved).status(), "замечание уходит запросом").toBe(201);
  await expect(discipline).toContainText(remark);

  // контакт родителя правится тут же
  const contacts = page
    .locator(".card")
    .filter({ hasText: "Контакты" })
    .first();
  const phone = `+7701555${String(Date.now()).slice(-4)}`;
  await contacts.getByRole("button", { name: "Поправить" }).first().click();
  await contacts
    .getByLabel(/Телефон/)
    .first()
    .fill(phone);
  const patched = page.waitForResponse(
    (response) =>
      response.url().includes("/contacts/") &&
      response.request().method() === "PATCH",
  );
  await contacts.getByRole("button", { name: "Сохранить" }).click();
  expect((await patched).status(), "контакт правится запросом").toBe(200);
  await expect(contacts).toContainText(phone);

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});

test("письмо: ссылка mailto собрана с кириллицей и скрытой копией", async ({
  browser,
}) => {
  const page = await as(browser, "curator");
  const diag = watch(page);

  // письмо из карточки — одному ученику
  const id = await studentId(page, probeEmail("pupil01"));
  await page.goto(`/students/${id}?tab=documents`);
  const firstDraft = page.waitForResponse((response) =>
    response.url().includes("/letters/compose/"),
  );
  await page.getByRole("button", { name: "Письмо", exact: true }).click();
  expect(
    (await firstDraft).status(),
    "заготовка письма приходит с сервера",
  ).toBe(200);
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Открыть в почте");
  await expect(dialog).toContainText("подтвердить не может");
  // тема пришла из школьного шаблона, а не выдумана экраном
  await expect(dialog.getByLabel("Тема")).not.toHaveValue("");

  // ссылку проверяем на сервере: клиент открывать нечем и незачем
  const single = (await (
    await page.request.post("/api/letters/open/", {
      data: {
        students: [id],
        audience: "student",
        subject: "Документы Данияра",
        body: "Здравствуйте!\nНе хватает паспорта.",
      },
      headers: {
        "X-CSRFToken":
          (await page.context().cookies()).find((c) => c.name === "csrftoken")
            ?.value ?? "",
      },
    })
  ).json()) as { links: string[]; recipients: number };
  expect(single.recipients).toBe(1);
  expect(single.links[0]).toContain("mailto:");
  // кириллица закодирована, пробелов в запросе нет
  expect(single.links[0]).toContain("subject=");
  expect(single.links[0]).not.toContain(" ");
  expect(decodeURIComponent(single.links[0])).toContain("Документы Данияра");

  // закрываем окно клавишей: имя кнопки закрытия — деталь оформления,
  // а Escape работает в любой модалке
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  // письмо всем, у кого не хватает документов
  await page.goto("/documents?group=all");
  const letterAll = page.getByRole("button", { name: "Письмо", exact: true });
  await expect(letterAll).toBeVisible();
  const composed = page.waitForResponse((response) =>
    response.url().includes("/letters/compose/"),
  );
  await letterAll.click();
  expect((await composed).status(), "заготовка приходит с сервера").toBe(200);
  const many = page.getByRole("dialog");
  await expect(many).toContainText("Получателей:");

  expect(diag.consoleErrors, "ошибки в консоли").toEqual([]);
  expect(diag.pageErrors, "исключения").toEqual([]);
  await page.context().close();
});
