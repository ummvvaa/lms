/**
 * Сессии ролей сохраняются один раз и переиспользуются: вход занимает
 * время, а проверять надо экраны, а не форму логина (её проверяет
 * отдельный сценарий).
 */
import fs from 'node:fs'
import path from 'node:path'
import { request } from '@playwright/test'
import { ACCOUNTS, type RoleAccount } from './roles'

const DIR = path.join(__dirname, '..', '.auth')
const LOGIN_PATHS = ['/api/auth/login/', '/api/auth/local/']

export const statePath = (key: string) => path.join(DIR, `${key}.json`)

/** Логинится под всеми ролями и раскладывает cookie по файлам. */
export async function prepareStates(baseURL: string): Promise<void> {
  fs.mkdirSync(DIR, { recursive: true })
  for (const account of ACCOUNTS) {
    await saveState(baseURL, account)
  }
}

async function saveState(baseURL: string, account: RoleAccount): Promise<void> {
  const context = await request.newContext({ baseURL })
  let ok = false
  for (const loginPath of LOGIN_PATHS) {
    const response = await context.post(loginPath, {
      data: { email: account.email, password: account.password },
    })
    if (response.ok()) {
      ok = true
      break
    }
  }
  if (!ok) throw new Error(`Не удалось войти под ${account.email}`)
  await context.storageState({ path: statePath(account.key) })
  await context.dispose()
}
