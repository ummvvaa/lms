/**
 * Снимки всех экранов под всеми ролями — для проверки глазами.
 *
 * Это не проверка, а инструмент: кадры складываются в `e2e/shots/`,
 * и их смотрит человек. Ищем пустые области без объяснения, обрезанный
 * текст, кнопки без подписи, английские слова, элементы за краем экрана.
 *
 * Запуск: npx playwright test tests/shots.spec.ts
 */
import { test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { statePath } from "../helpers/auth-state";

const DIR = path.join(__dirname, "..", "shots");

/** Экраны каждой роли — те же адреса, что в её навигации. */
const SCREENS: Record<string, string[]> = {
  // кабинеты директоров по макету (24.10.2026): меню каждой роли — как в макете
  director_behavior: [
    "/dashboard",
    "/attendance",
    "/school-reports",
    "/parents",
    "/risks",
    "/table",
    "/profile",
  ],
  director_admission: [
    "/dashboard",
    "/essay-review",
    "/table",
    "/directory",
    "/deadlines",
  ],
  director_exam: [
    "/dashboard",
    "/school-reports",
    "/staff-tasks",
    "/table",
    "/schedule",
    "/exam-results",
    "/mocks",
    "/top30",
    "/exam-kinds",
  ],
  director_talent: [
    "/dashboard",
    "/olympiad-events",
    "/releases",
    "/table",
    "/olympiad-group",
    "/subjects",
    "/tracks",
  ],
  director_sport: ["/dashboard", "/sport-events", "/sport-types", "/table"],
  // «Импорт» — у администратора и Кымбат; «Сюжеты главной» — настройка школы
  admin: [
    "/dashboard",
    "/users",
    "/archive",
    "/table",
    "/import",
    "/home-cues",
    "/spend",
  ],
  // куратор (фаза 60): заглушка кабинета и профиль
  // утренняя отметка с чипом освобождения (24.10.2026)
  curator: ["/dashboard", "/attendance", "/profile"],
  // Все экраны кабинета — фаза 48 переделала вид каждого, и снимков
  // восьми из семнадцати перестало хватать
  // кабинет 11 класса с 07.10.2026 без «Моего пути», плана, стипендий, роадмапа,
  // ресурсов и избранного; «Мои вузы» — вкладка каталога
  student: [
    "/dashboard",
    "/calendar",
    "/my-data",
    // мероприятия школы и свои заявки — у 11 во вкладке «Спорт» портфолио (24.10.2026)
    "/my-data?tab=sport",
    "/selection",
    "/catalog",
    "/catalog?mode=mine",
    "/career",
    "/essays",
    "/prep",
    "/achievements",
    "/profile",
  ],
};

/** Ширины: ноутбук и планшет — интерфейсом пользуются и с того, и с другого. */
const SIZES: { name: string; width: number; height: number }[] = [
  { name: "wide", width: 1440, height: 900 },
  { name: "narrow", width: 820, height: 1180 },
];

/** Темы: тёмная проверяется на каждом экране, а не на одном образцовом. */
const THEMES = ["light", "dark"] as const;

test.describe.configure({ mode: "serial" });

for (const [role, screens] of Object.entries(SCREENS)) {
  for (const size of SIZES) {
    for (const theme of THEMES) {
      const folder = theme === "dark" ? `${size.name}-dark` : size.name;
      test(`снимки ${role} ${size.name} ${theme}`, async ({ browser }) => {
        const context = await browser.newContext({
          storageState: statePath(role),
          viewport: { width: size.width, height: size.height },
        });
        const page = await context.newPage();
        // подсказка первого входа перекрывает экраны — прячем её,
        // для неё есть отдельный кадр
        await page.addInitScript(() =>
          window.localStorage.setItem("first-run-seen", "1"),
        );
        // тема — настройка учётной записи на сервере: ставим её как человек
        // (через профиль) и возвращаем «как в системе» в конце
        await page.goto("/dashboard");
        const csrf = (await context.cookies()).find(
          (c) => c.name === "csrftoken",
        )?.value;
        await page.request.patch("/api/auth/me/preferences/", {
          data: { theme },
          headers: { "X-CSRFToken": csrf ?? "" },
        });
        fs.mkdirSync(path.join(DIR, folder), { recursive: true });

        try {
          for (const screen of screens) {
            await page.goto(screen);
            // предел: экран с медленной ручкой иначе съедает весь тест
            await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => undefined);
            await page.waitForTimeout(400);
            const name = `${role}${screen.replace(/\//g, "_").replace(/[?=]/g, "-")}.png`;
            await page.screenshot({
              path: path.join(DIR, folder, name),
              fullPage: true,
            });
          }
        } finally {
          // возврат темы — всегда, даже если кадр не снялся: тема живёт
          // на сервере, и оставленная тёмной она красила эталоны (фаза 63)
          await page.request
            .patch("/api/auth/me/preferences/", {
              data: { theme: "system" },
              headers: { "X-CSRFToken": csrf ?? "" },
            })
            .catch(() => undefined);
          await context.close();
        }
      });
    }
  }
}

test("снимок первого входа", async ({ browser }) => {
  const context = await browser.newContext({
    storageState: statePath("director_talent"),
  });
  const page = await context.newPage();
  await page.addInitScript(() => window.localStorage.clear());
  await page.goto("/dashboard");
  await page.waitForTimeout(600);
  fs.mkdirSync(path.join(DIR, "wide"), { recursive: true });
  await page.screenshot({
    path: path.join(DIR, "wide", "first-run.png"),
    fullPage: true,
  });
  await context.close();
});
