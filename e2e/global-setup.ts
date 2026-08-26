/**
 * Перед прогоном: одноразовые записи заведены, сессии всех ролей сохранены.
 *
 * `create_probe_users` сам убирает остатки прошлого прогона, если тот упал
 * посередине: новый всегда начинается с чистых записей и без чужих сессий.
 */
import fs from 'node:fs'
import path from 'node:path'
import { prepareStates } from './helpers/auth-state'
import { createProbeUsers } from './helpers/manage'

export default async function globalSetup() {
  console.log(createProbeUsers())
  fs.rmSync(path.join(__dirname, '.auth'), { recursive: true, force: true })
  await prepareStates(process.env.E2E_BASE_URL ?? 'http://localhost:5173')
}
