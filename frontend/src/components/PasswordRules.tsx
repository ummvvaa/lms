import { t, tn } from '../i18n'
/**
 * Требования к паролю, видимые до первой попытки.
 *
 * Полная проверка — на сервере (`accounts.passwords`); здесь только то,
 * что можно сказать сразу, чтобы человек не подбирал пароль по отказам.
 */
const MIN_LENGTH = 10

/** Локальная проверка. `null` — здесь придраться не к чему. */
export function passwordProblem(password: string, email = ''): string | null {
  if (password.length < MIN_LENGTH) return minLengthRule()
  const local = email.split('@')[0]?.trim().toLowerCase()
  const lowered = password.trim().toLowerCase()
  if (email && (lowered === email.trim().toLowerCase() || (local && lowered === local))) {
    return t('Пароль не должен совпадать с почтой')
  }
  return null
}

/** Правило длины одной фразой с числом. */
function minLengthRule(): string {
  return tn(MIN_LENGTH, 'Не короче {n} символа|Не короче {n} символов|Не короче {n} символов')
}

export default function PasswordRules({ password, email = '' }: { password: string; email?: string }) {
  const rules: [string, boolean][] = [
    [minLengthRule(), password.length >= MIN_LENGTH],
    [
      t('Не совпадает с вашей почтой'),
      passwordProblem(password, email) !== t('Пароль не должен совпадать с почтой'),
    ],
    [t('Не из списка самых частых паролей — это проверит сервер'), true],
  ]
  return (
    <ul className="password-rules">
      {rules.map(([text, ok]) => (
        <li key={text} className={ok ? 'password-rules__ok' : 'password-rules__todo'}>
          {ok ? '✓' : '•'} {text}
        </li>
      ))}
    </ul>
  )
}
