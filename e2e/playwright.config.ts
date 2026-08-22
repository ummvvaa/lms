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
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
