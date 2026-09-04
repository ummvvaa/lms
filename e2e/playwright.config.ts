/** Конфигурация браузерных проверок: контур поднимается через docker compose. */
import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// Пароли учётных записей — из e2e/.env (в git не попадает). Своего .env-загрузчика
// у Playwright нет, а тащить зависимость ради семи строк незачем.
for (const line of fs.existsSync(path.join(__dirname, ".env"))
  ? fs.readFileSync(path.join(__dirname, ".env"), "utf8").split("\n")
  : []) {
  const match = line.match(/^([A-Z0-9_]+)=(.*)$/);
  if (match && !process.env[match[1]]) process.env[match[1]] = match[2];
}

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

export default defineConfig({
  testDir: "./tests",
  globalSetup: "./global-setup.ts",
  globalTeardown: "./global-teardown.ts",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "report" }]],
  // Эталоны сравнения раскладки лежат рядом с остальными кадрами, в `shots/`:
  // каталог снимков в git не идёт, и картинки не попадают в историю
  snapshotPathTemplate: "shots/baseline/{arg}{ext}",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "ru-RU",
  },
  // Порядок важен и выполняется одним воркером: сквозной сценарий обнуляет базу,
  // посев наполняет её тем, что заводил бы человек, остальное ходит по данным.
  // Зависимостей между проектами нет намеренно: упавший сквозной сценарий
  // не должен отменять сотню остальных проверок
  projects: [
    {
      name: "journey",
      testMatch: /journey\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    // сквозной путь ученика (фаза 47) тоже начинается с чистой базы,
    // поэтому идёт своим проектом до посева, а не вперемешку с остальными
    {
      name: "path",
      testMatch: /phase47\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "seed",
      testMatch: /seed\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "chromium",
      testIgnore: [
        /journey\.spec\.ts/,
        /phase47\.spec\.ts/,
        /seed\.spec\.ts/,
        /seed-baseline\.spec\.ts/,
        /baseline\.spec\.ts/,
      ],
      use: { ...devices["Desktop Chrome"] },
    },
    // Эталоны раскладки идут последними и двумя проектами: сначала посев,
    // потом снимки. Последними — потому что посев начинается с обнуления
    // базы: так снимок не зависит от четырёхсот проверок, отработавших
    // раньше, и сам их не задевает своими учениками (D29, фаза 54).
    // Порядок между файлами внутри одного проекта не гарантирован,
    // поэтому посев и съёмка разведены по проектам, а не по describe
    {
      name: "baseline-seed",
      testMatch: /seed-baseline\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "baseline",
      testMatch: /tests\/baseline\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
