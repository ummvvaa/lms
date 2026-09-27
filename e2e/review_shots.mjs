/**
 * Снимки «после» по замечаниям владельца (docs/prompts/review-fixes.md).
 *
 * Не прогон сценариев: один адрес — один снимок, на базе разработки
 * с посевом `seed_academics`, под учётными записями посева. Ширина 1440;
 * экраны ученика, учителя и куратора — ещё и 390. Файлы ложатся
 * в `docs/ui/review-2026-09-27/after/NN-имя.png`, номер — как у замечания.
 *
 *   cd e2e && SEED_PASSWORD='…' node review_shots.mjs [подстрока имени]
 *
 * Пароль — из окружения, в файлах его нет.
 */
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:5173";
const PASSWORD = process.env.SEED_PASSWORD ?? "";
const OUT = path.resolve("../docs/ui/review-2026-09-27/after");
const ONLY = process.argv[2] ?? "";

if (!PASSWORD) {
  console.error("Нужен SEED_PASSWORD — пароль учётных записей посева");
  process.exit(1);
}

const ACCOUNTS = {
  admin: "admin@fictional.local",
  asem: "asem@fictional.local",
  kymbat: "kymbat@fictional.local",
  saltanat: "saltanat@fictional.local",
  curator: "akbota_seydahmetova@fictional.local",
  teacher: "ayzhan_kasymova@fictional.local",
  student: "kamila.zhumabaeva.1@fictional.local",
};

const LAPTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };

/** Снимок: имя файла, роль, адрес, ширины и что нажать перед съёмкой. */
const SHOTS = [
  { name: "01-assistant-header", role: "asem", path: "/assistant", act: openAssistant },
  { name: "02-sidebar-icons-curator", role: "curator", path: "/dashboard" },
  { name: "02-sidebar-icons-student", role: "student", path: "/dashboard" },
  { name: "02-sidebar-icons-kymbat", role: "kymbat", path: "/dashboard" },
  { name: "02-sidebar-icons-saltanat", role: "saltanat", path: "/dashboard" },
  { name: "02-sidebar-icons-admin", role: "admin", path: "/dashboard" },
  { name: "03-profile", role: "student", path: "/profile", phone: true },
  { name: "03-profile-teacher", role: "teacher", path: "/profile" },
  { name: "04-student-card-tabs", role: "asem", path: "/students/{student}" },
  { name: "05-schedule-kymbat", role: "kymbat", path: "/schedule" },
  { name: "05-schedule-student", role: "student", path: "/schedule", phone: true },
  { name: "05-schedule-curator", role: "curator", path: "/schedule", phone: true },
  { name: "05-schedule-teacher", role: "teacher", path: "/schedule", phone: true },
  { name: "06-cohorts", role: "kymbat", path: "/cohorts" },
  { name: "06-cohorts-split", role: "kymbat", path: "/cohorts", act: clickButton("Разделить группу") },
  { name: "07-teachers", role: "kymbat", path: "/teachers" },
  { name: "08-reports-kymbat", role: "kymbat", path: "/reports" },
  { name: "08-reports-saltanat", role: "saltanat", path: "/reports" },
  { name: "08-reports-curator", role: "curator", path: "/reports", phone: true },
  { name: "08-reports-open", role: "curator", path: "/reports", act: openFirstRow },
  { name: "09-academic-year-bells", role: "kymbat", path: "/academic-year" },
  { name: "10-student-journey", role: "student", path: "/journey", phone: true },
  { name: "11-student-calendar", role: "student", path: "/calendar", phone: true, act: pickCalendarDay },
  { name: "12-student-documents", role: "student", path: "/my-data", phone: true, act: scrollTo("Готовность документов") },
  { name: "13-quiz-gone", role: "student", path: "/quiz" },
  { name: "14-asem-directory", role: "asem", path: "/directory" },
  { name: "14-asem-directory-open", role: "asem", path: "/directory", act: openFirstRow },
  { name: "15-admin-suggestions", role: "admin", path: "/suggestions" },
  { name: "16-admin-digest", role: "admin", path: "/digest" },
  { name: "17-mail-templates-gone", role: "admin", path: "/mail-templates" },
  { name: "18-admin-users", role: "admin", path: "/users" },
  { name: "18-admin-users-groups", role: "admin", path: "/users?tab=groups" },
  { name: "20-curator-attendance", role: "curator", path: "/attendance", phone: true },
  { name: "21-curator-grades", role: "curator", path: "/grades", phone: true },
];

async function login(context, email) {
  const api = context.request;
  await api.get(`${BASE}/api/auth/me/`);
  const csrf = (await context.cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
  const response = await api.post(`${BASE}/api/auth/login/`, {
    data: { email, password: PASSWORD },
    headers: { "X-CSRFToken": csrf },
  });
  if (response.status() !== 200) throw new Error(`вход ${email}: ${response.status()} ${await response.text()}`);
}

async function settle(page) {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(600);
  // заглушки загрузки: ждём, пока уйдут
  await page
    .waitForFunction(() => document.querySelectorAll(".skeleton, [data-loading='true']").length === 0, null, { timeout: 8000 })
    .catch(() => undefined);
  await page.waitForTimeout(300);
}

async function openAssistant(page) {
  await page.getByRole("button", { name: "Открыть помощника" }).click();
  await page.waitForTimeout(400);
  // D48: кнопки шапки помощника отвечают на нажатие
  const panel = page.locator(".aw");
  await page.getByRole("button", { name: "История" }).click();
  await page.waitForTimeout(300);
  const history = await panel.locator(".aw__body").innerText();
  await page.getByRole("button", { name: "Новый" }).click();
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: "Развернуть" }).click();
  await page.waitForTimeout(300);
  const full = await panel.evaluate((el) => el.classList.contains("aw--full"));
  await page.getByRole("button", { name: "Обычный размер" }).click();
  await page.waitForTimeout(300);
  console.log(`  D48: история «${history.slice(0, 40).replace(/\n/g, " ")}», развернуть — ${full ? "да" : "нет"}`);
}

function clickButton(name) {
  return async (page) => {
    await page.getByRole("button", { name, exact: true }).first().click();
    await page.waitForTimeout(1200);
  };
}

async function openFirstRow(page) {
  const row = page.locator("table.tbl tbody tr").first();
  if (!(await row.count())) return;
  await row.click();
  await page.waitForTimeout(800);
}

/** Отчёты за текущий месяц по группе куратора — чтобы список и панель были с данными. */
async function buildReports(context) {
  const api = context.request;
  const csrf = (await context.cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
  const month = new Date().toISOString().slice(0, 7);
  const built = await api.post(`${BASE}/api/acad/reports/build/`, {
    data: { period: month, group: "MIT" },
    headers: { "X-CSRFToken": csrf },
  });
  console.log(`  отчёты MIT за ${month}: ${built.status()}`);
}

async function pickCalendarDay(page) {
  const marked = page.locator(".calcell--full .calcell__marks").first();
  if (await marked.count()) {
    await marked.locator("..").click();
    await page.waitForTimeout(400);
  }
}

function scrollTo(text) {
  return async (page) => {
    const target = page.getByText(text, { exact: true }).first();
    if (await target.count()) await target.scrollIntoViewIfNeeded();
  };
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const contexts = new Map();
  let studentId = null;
  const contextFor = async (role, viewport) => {
    const key = `${role}-${viewport.width}`;
    if (!contexts.has(key)) {
      const context = await browser.newContext({ viewport, locale: "ru-RU", baseURL: BASE, isMobile: viewport.width < 760 });
      await login(context, ACCOUNTS[role]);
      contexts.set(key, context);
    }
    return contexts.get(key);
  };
  {
    const context = await contextFor("asem", LAPTOP);
    const first = await (await context.request.get(`${BASE}/api/students/?page_size=1`)).json();
    studentId = first.results?.[0]?.id ?? null;
    await buildReports(await contextFor("kymbat", LAPTOP));
  }
  for (const shot of SHOTS) {
    if (ONLY && !shot.name.includes(ONLY)) continue;
    const widths = shot.phone ? [LAPTOP, PHONE] : [LAPTOP];
    for (const viewport of widths) {
      const context = await contextFor(shot.role, viewport);
      const page = await context.newPage();
      const url = shot.path.replace("{student}", String(studentId));
      await page.goto(url);
      await settle(page);
      if (shot.act) {
        await shot.act(page);
        await settle(page);
      }
      const file = path.join(OUT, `${shot.name}${viewport.width === 390 ? "-390" : ""}.png`);
      await page.screenshot({ path: file, fullPage: true });
      console.log(`${file} ← ${page.url()}`);
      await page.close();
    }
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
