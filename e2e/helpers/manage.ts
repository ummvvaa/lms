/**
 * Management-команды контура из браузерных сценариев.
 *
 * Нужны там, где шаг сценария и в жизни делается из терминала: очистка
 * базы, выдача одноразовой ссылки. Заводить ради этого ручки в API нельзя —
 * лишняя дверь в системе опаснее неудобства в тестах.
 */
import { execFileSync } from 'node:child_process'
import path from 'node:path'

const ROOT = path.join(__dirname, '..', '..')

export function manage(args: string[]): string {
  return execFileSync('docker', ['compose', 'exec', '-T', 'backend', 'python', 'manage.py', ...args], {
    cwd: ROOT,
    encoding: 'utf8',
  }).trim()
}

/** Полная очистка данных — шаг «очистить базу» сквозного сценария. */
export function resetAll(): void {
  manage(['reset_data', '--all', '--confirm', 'УДАЛИТЬ ДАННЫЕ'])
}

/** Убрать учётные записи, заведённые сценарием: он должен начинаться с нуля. */
export function dropUsers(prefix: string): void {
  manage([
    'shell',
    '-c',
    `from accounts.models import User; User.objects.filter(email__startswith="${prefix}").delete()`,
  ])
}
