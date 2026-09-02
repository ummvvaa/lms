/**
 * Снимки экранов, которых коснулась фаза 35, на двух ширинах.
 *
 * Узкий набор по заданию: импорт администратора (с выбранным доменом),
 * история загрузок и таблица директора, помощник с выбором домена,
 * соревнования и контакты без кнопки загрузки. Полный набор всех экранов
 * снимает `shots.spec.ts`.
 */
import { test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { statePath } from "../helpers/auth-state";

const DIR = path.join(__dirname, "..", "shots", "phase35");

const SHOTS: {
  role: string;
  screen: string;
  name: string;
  prepare?: (page: Page) => Promise<void>;
}[] = [
  {
    role: "admin",
    screen: "/import",
    name: "admin_import_exam",
    prepare: async (page) => {
      await page.getByLabel("Домен", { exact: true }).selectOption("exam");
      await page.waitForTimeout(300);
    },
  },
  {
    role: "admin",
    screen: "/import",
    name: "admin_import_admission_rows",
    prepare: async (page) => {
      await page.getByLabel("Домен", { exact: true }).selectOption("admission");
      await page.getByRole("tab", { name: "Требования вузов" }).click();
      await page.waitForTimeout(300);
    },
  },
  {
    role: "admin",
    screen: "/assistant?panel=paste_as_is",
    name: "admin_assistant_paste",
  },
  { role: "director_exam", screen: "/import", name: "exam_uploads" },
  { role: "director_exam", screen: "/table", name: "exam_table" },
  {
    role: "director_exam",
    screen: "/assistant?panel=paste_as_is",
    name: "exam_assistant_paste",
  },
  {
    role: "director_sport",
    screen: "/competitions",
    name: "sport_competitions",
  },
  { role: "director_behavior", screen: "/contacts", name: "behavior_contacts" },
];

const SIZES = [
  { name: "wide", width: 1440, height: 900 },
  { name: "narrow", width: 820, height: 1180 },
];

test.describe.configure({ mode: "serial" });

for (const size of SIZES) {
  test(`снимки фазы 35 · ${size.name}`, async ({ browser }) => {
    fs.mkdirSync(path.join(DIR, size.name), { recursive: true });
    for (const shot of SHOTS) {
      const context = await browser.newContext({
        storageState: statePath(shot.role),
        viewport: { width: size.width, height: size.height },
      });
      const page = await context.newPage();
      await page.addInitScript(() =>
        window.localStorage.setItem("first-run-seen", "1"),
      );
      await page.goto(shot.screen);
      await page.waitForLoadState("networkidle").catch(() => undefined);
      await page.waitForTimeout(400);
      if (shot.prepare) await shot.prepare(page);
      await page.screenshot({
        path: path.join(DIR, size.name, `${shot.name}.png`),
        fullPage: true,
      });
      await context.close();
    }
  });
}
