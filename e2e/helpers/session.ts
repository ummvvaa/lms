/**
 * Вход в интерфейс и сбор диагностики.
 *
 * Кнопка считается рабочей только если по клику ушёл сетевой запрос,
 * ответ пришёл со статусом 2xx и в консоли не появилось ошибок —
 * поэтому слушатели вешаются до первой навигации.
 */
import type { ConsoleMessage, Page, Request, Response } from '@playwright/test'
import type { RoleAccount } from './roles'

export interface NetCall {
  method: string
  url: string
  status: number
}

export interface Diagnostics {
  consoleErrors: string[]
  pageErrors: string[]
  calls: NetCall[]
  failed: NetCall[]
  /** Запросы к /api/, ушедшие после отметки. */
  since(mark: number): NetCall[]
  mark(): number
  reset(): void
}

/** Шум, не относящийся к приложению: расширения, favicon, HMR Vite. */
function isNoise(text: string): boolean {
  return (
    text.includes('favicon') ||
    text.includes('[vite]') ||
    text.includes('Download the React DevTools') ||
    text.includes('ERR_NETWORK_CHANGED')
  )
}

export function watch(page: Page): Diagnostics {
  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  const calls: NetCall[] = []
  const failed: NetCall[] = []

  page.on('console', (message: ConsoleMessage) => {
    if (message.type() !== 'error' && message.type() !== 'warning') return
    const text = message.text()
    if (isNoise(text)) return
    if (message.type() === 'error') consoleErrors.push(text)
  })

  page.on('pageerror', (error: Error) => {
    pageErrors.push(error.message)
  })

  page.on('response', (response: Response) => {
    const url = response.url()
    if (!url.includes('/api/')) return
    const call: NetCall = { method: response.request().method(), url, status: response.status() }
    calls.push(call)
    if (response.status() >= 400) failed.push(call)
  })

  page.on('requestfailed', (request: Request) => {
    const url = request.url()
    if (!url.includes('/api/')) return
    failed.push({ method: request.method(), url, status: 0 })
  })

  return {
    consoleErrors,
    pageErrors,
    calls,
    failed,
    mark: () => calls.length,
    since: (mark: number) => calls.slice(mark),
    reset() {
      consoleErrors.length = 0
      pageErrors.length = 0
      calls.length = 0
      failed.length = 0
    },
  }
}

/** Вход через форму на /login — именно так, как это делает человек. */
export async function login(page: Page, account: RoleAccount): Promise<void> {
  await page.goto('/login')
  await page.getByLabel(/почта|email/i).first().fill(account.email)
  await page.getByLabel(/пароль/i).first().fill(account.password)
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/auth/') && r.request().method() === 'POST'),
    page.getByRole('button', { name: /войти/i }).first().click(),
  ])
  await page.waitForURL(/\/(dashboard|onboarding)/, { timeout: 15_000 })
}

/** Быстрый вход запросом — когда проверяется не форма, а экран за ней. */
export async function loginByApi(page: Page, account: RoleAccount): Promise<void> {
  await page.goto('/login')
  const response = await page.request.post('/api/auth/local/', {
    data: { email: account.email, password: account.password },
  })
  if (!response.ok()) throw new Error(`Вход ${account.email}: HTTP ${response.status()}`)
}
