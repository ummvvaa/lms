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
  director_behavior: [
    "/dashboard",
    "/table",
    "/import",
    "/assistant",
    "/suggestions",
    "/digest",
    "/task-templates",
    "/groups",
    "/contacts",
    "/risks",
    // справочники фазы 49: из них живут карусель ученика и список обзвона
    "/home-cues",
    "/call-rules",
    "/overview",
    "/profile",
  ],
  director_admission: [
    "/dashboard",
    "/directory",
    "/table",
    "/import",
    "/suggestions",
    "/deadlines",
  ],
  director_exam: [
    "/dashboard",
    "/table",
    "/import",
    "/digest",
    "/top30",
    "/mocks",
  ],
  director_talent: [
    "/dashboard",
    "/table",
    "/subjects",
    "/tracks",
    "/materials",
    "/olympiad-group",
  ],
  director_sport: ["/dashboard", "/table", "/sport-types", "/competitions"],
  admin: ["/dashboard", "/users", "/archive", "/table", "/spend"],
  // Все экраны кабинета — фаза 48 переделала вид каждого, и снимков
  // восьми из семнадцати перестало хватать
  student: [
    "/dashboard",
    "/journey",
    "/calendar",
    "/my-data",
    "/selection",
    "/catalog",
    "/favorites",
    "/universities",
    "/plan",
    "/scholarships",
    "/career",
    "/essays",
    "/prep",
    "/roadmap",
    "/quiz",
    "/achievements",
    "/resources",
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

        for (const screen of screens) {
          await page.goto(screen);
          await page.waitForLoadState("networkidle").catch(() => undefined);
          await page.waitForTimeout(400);
          const name = `${role}${screen.replace(/\//g, "_")}.png`;
          await page.screenshot({
            path: path.join(DIR, folder, name),
            fullPage: true,
          });
        }
        // возврат темы — уборка, а не проверка: обрыв соединения здесь не повод ронять кадры
        await page.request
          .patch("/api/auth/me/preferences/", {
            data: { theme: "system" },
            headers: { "X-CSRFToken": csrf ?? "" },
          })
          .catch(() => undefined);
        await context.close();
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
