/**
 * Учётные записи для браузерных проверок.
 *
 * Ходим под одноразовыми записями `*@probe.local`: их заводит
 * `manage.py create_probe_users` перед прогоном и убирает насовсем
 * `purge_probe_users` после. Разработческие `*@dev.local` прогон
 * не трогает: они отключены владельцем и включаться не должны.
 */
export interface RoleAccount {
  key: string
  email: string
  password: string
  title: string
}

/** Домен одноразовых записей — тот же, что в `accounts/probe.py`. */
export const PROBE_DOMAIN = 'probe.local'

/**
 * Один пароль на семь записей — из `PROBE_PASSWORD` в `e2e/.env`.
 * Значения по умолчанию нет намеренно: файла с паролем у проекта
 * не должно быть даже в тестах.
 */
export function probePassword(): string {
  const value = process.env.PROBE_PASSWORD
  if (!value) {
    throw new Error(
      'Не задана переменная PROBE_PASSWORD. Задайте её в e2e/.env: ' +
        'это пароль одноразовых записей прогона, команда create_probe_users получает его оттуда же.',
    )
  }
  return value
}

const account = (key: string, local: string, title: string): RoleAccount => ({
  key,
  email: `${local}@${PROBE_DOMAIN}`,
  password: probePassword(),
  title,
})

export const ACCOUNTS: RoleAccount[] = [
  account('student', 'student', 'Ученик'),
  account('director_behavior', 'behavior', 'Директор школы — профиль и дисциплина'),
  account('director_admission', 'admission', 'Директор по поступлению'),
  account('director_exam', 'exam', 'Академический директор'),
  account('director_talent', 'talent', 'Директор талантов'),
  account('director_sport', 'sport', 'Директор спорта'),
  account('admin', 'admin', 'Администратор'),
]

export const byKey = (key: string): RoleAccount => {
  const found = ACCOUNTS.find((a) => a.key === key)
  if (!found) throw new Error(`Нет учётной записи для роли ${key}`)
  return found
}

/** Почта, которую сценарий заводит сам: тот же домен, та же уборка. */
export const probeEmail = (local: string): string => `${local}@${PROBE_DOMAIN}`
