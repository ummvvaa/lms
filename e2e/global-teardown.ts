/**
 * После прогона — уборка: записи `*@probe.local` удаляются насовсем,
 * вместе с сессиями и всем, что прогон завёл под этим доменом.
 *
 * Playwright вызывает teardown и при упавших тестах, и при Ctrl+C. На случай
 * жёсткого обрыва процесса та же уборка продублирована в `run.sh`.
 */
import fs from 'node:fs'
import path from 'node:path'
import { purgeProbeUsers } from './helpers/manage'

export default async function globalTeardown() {
  console.log(purgeProbeUsers())
  fs.rmSync(path.join(__dirname, '.auth'), { recursive: true, force: true })
}
