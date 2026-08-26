/** Конфигурация браузерных проверок: контур поднимается через docker compose. */
import { defineConfig, devices } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

// Пароли учётных записей — из e2e/.env (в git не попадает). Своего .env-загрузчика
// у Playwright нет, а тащить зависимость ради семи строк незачем.
for (const line of fs.existsSync(path.join(__dirname, '.env'))
  ? fs.readFileSync(path.join(__dirname, '.env'), 'utf8').split('\n')
  : []) {
  const match = line.match(/^([A-Z0-9_]+)=(.*)$/)
  if (match && !process.env[match[1]]) process.env[match[1]] = match[2]
}

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:5173'

export default defineConfig({
  testDir: './tests',
  globalSetup: './global-setup.ts',
  globalTeardown: './global-teardown.ts',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'report' }]],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'ru-RU',
  },
  // Порядок важен и выполняется одним воркером: сквозной сценарий обнуляет базу,
  // посев наполняет её тем, что заводил бы человек, остальное ходит по данным.
  // Зависимостей между проектами нет намеренно: упавший сквозной сценарий
  // не должен отменять сотню остальных проверок
  projects: [
    { name: 'journey', testMatch: /journey\.spec\.ts/, use: { ...devices['Desktop Chrome'] } },
    { name: 'seed', testMatch: /seed\.spec\.ts/, use: { ...devices['Desktop Chrome'] } },
    {
      name: 'chromium',
      testIgnore: [/journey\.spec\.ts/, /seed\.spec\.ts/],
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
