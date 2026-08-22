/**
 * Токен одноразовой ссылки в контуре разработки.
 *
 * Почтового сервера здесь нет, а служебную ручку в API заводить нельзя:
 * лишней двери в аутентификации быть не должно. Поэтому спрашиваем
 * management-команду, которая сама работает только при DEBUG.
 */
import { execFileSync } from 'node:child_process'
import path from 'node:path'

const ROOT = path.join(__dirname, '..', '..')

function manage(args: string[]): string {
  return execFileSync('docker', ['compose', 'exec', '-T', 'backend', 'python', 'manage.py', ...args], {
    cwd: ROOT,
    encoding: 'utf8',
  }).trim()
}

/** Токен последней действующей ссылки для этой почты. */
export function lastLinkToken(email: string): string {
  const token = manage(['dev_link', '--email', email])
  if (!token) throw new Error(`Для ${email} не нашлось действующей ссылки`)
  return token
}

/** Пометить, что человеку нужно сменить пароль — как при выдаче временного. */
export function requirePasswordChange(email: string): void {
  manage(['dev_link', '--email', email, '--require-password-change'])
}
