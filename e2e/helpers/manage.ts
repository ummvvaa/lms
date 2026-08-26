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

export function manage(args: string[], env: Record<string, string> = {}): string {
  const passEnv = Object.entries(env).flatMap(([name, value]) => ['-e', `${name}=${value}`])
  return execFileSync(
    'docker',
    ['compose', 'exec', '-T', ...passEnv, 'backend', 'python', 'manage.py', ...args],
    { cwd: ROOT, encoding: 'utf8' },
  ).trim()
}

/**
 * Одноразовые записи прогона: семь ролей на `probe.local`.
 * Пароль уходит команде переменной окружения — из `e2e/.env`, других мест нет.
 */
export function createProbeUsers(): string {
  return manage(['create_probe_users'], { PROBE_PASSWORD: process.env.PROBE_PASSWORD ?? '' })
}

/** Убрать записи прогона насовсем — вместе с сессиями. Работает в любом режиме. */
export function purgeProbeUsers(): string {
  return manage(['purge_probe_users'])
}

/** Полная очистка данных — шаг «очистить базу» сквозного сценария. */
export function resetAll(): void {
  manage(['reset_data', '--all', '--confirm', 'УДАЛИТЬ ДАННЫЕ'])
}

/**
 * Убрать учётные записи, заведённые сценарием: он должен начинаться с нуля.
 *
 * Только под доменом прогона: физически удалять настоящие записи нельзя
 * (инвариант №13), а по одному префиксу однажды ушли две архивные записи
 * `journey.*@lms.local`, которые владелец просил оставить в архиве.
 */
export function dropUsers(prefix: string): void {
  manage([
    'shell',
    '-c',
    `from accounts.probe import probe_users; probe_users().filter(email__startswith="${prefix}").delete()`,
  ])
}
