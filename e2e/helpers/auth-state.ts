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
const LOGIN_PATH = '/api/auth/login/'

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
  const response = await context.post(LOGIN_PATH, {
    data: { email: account.email, password: account.password },
  })
  if (!response.ok()) {
    throw new Error(`Не удалось войти под ${account.email}: HTTP ${response.status()}`)
  }
  await context.storageState({ path: statePath(account.key) })
  await context.dispose()
}
