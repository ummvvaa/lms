/**
 * Вход по почте или логину и паролю.
 *
 * У 8–10 почты школы нет — они входят логином «имя.фамилия». Ссылку на
 * пароль им выдаёт куратор на экране; «Забыли пароль» работает, только
 * если к учётной записи привязана и подтверждена личная почта.
 *
 * Регистрации самому себе нет: учётную запись заводит администратор.
 * Вторая дверь — одноразовая ссылка: для выпускников, у которых пароля нет,
 * и для тех, кто его забыл.
 */
import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import { LOGO, SCHOOL_NAME } from '../branding'
import Field from '../components/Field'
import { Chip } from '../components/ui'
import { t } from '../i18n'
import { Button } from '../components/ui/button'

type Mode = 'password' | 'reset' | 'link'

function message(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : fallback
}

export default function Login() {
  const { login, requestPasswordReset, requestLink } = useAuth()
  const [mode, setMode] = useState<Mode>('password')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setNote(null)
    setBusy(true)
    try {
      if (mode === 'password') {
        await login(email, password)
      } else if (mode === 'reset') {
        await requestPasswordReset(email)
        setNote(t('Если такая почта известна системе, ссылка отправлена. Срок её действия указан в письме.'))
      } else {
        await requestLink(email)
        setNote(t('Если такая почта известна системе, ссылка отправлена.'))
      }
    } catch (e) {
      setError(message(e, mode === 'password' ? t('Не удалось войти') : t('Не удалось отправить ссылку')))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <div className="card card-pad login__card">
        <div className="login__brand">
          <img className="login__logo" src={LOGO.login} alt="" />
          <h1 className="login__title">{SCHOOL_NAME}</h1>
        </div>
        <p className="t-note login__sub">
          {mode === 'password' && t('Почта или логин и пароль, выданные школой.')}
          {mode === 'reset' && t('Пришлём ссылку на смену пароля. Срок её действия указан в письме.')}
          {mode === 'reset' && ` ${t('Нет почты — попросите куратора выдать ссылку на пароль.')}`}
          {mode === 'link' && t('Для выпускников: вход по ссылке на личную почту.')}
        </p>

        <form onSubmit={submit} className="login__form">
          {mode === 'password' ? (
            <Field name="email" id="email" label={t('Почта или логин')} value={email} onChange={setEmail} placeholder="ivanova@school.kz" autoComplete="username" required />
          ) : (
            <Field kind="email" name="email" id="email" label={t('Почта')} value={email} onChange={setEmail} placeholder="ivanova@school.kz" autoComplete="username" required />
          )}
          {mode === 'password' && <Field kind="password" name="password" id="password" label={t('Пароль')} value={password} onChange={setPassword} autoComplete="current-password" required />}
          <Button className="login__ms" type="submit" disabled={busy}>
            {mode === 'password' ? t('Войти') : t('Прислать ссылку')}
          </Button>
        </form>

        {note && <Chip tone="good" className="login__hint">{note}</Chip>}
        {error && <Chip tone="bad" className="login__hint">{error}</Chip>}

        <div className="login__sep">
          <span>{t('ещё')}</span>
        </div>

        <div className="login__modes">
          {mode !== 'password' && (
            <Button variant="outline" size="sm" onClick={() => setMode('password')}>
              {t('Войти по паролю')}
            </Button>
          )}
          {mode !== 'reset' && (
            <Button variant="outline" size="sm" onClick={() => setMode('reset')}>
              {t('Забыли пароль?')}
            </Button>
          )}
          {mode !== 'link' && (
            <Button variant="outline" size="sm" onClick={() => setMode('link')}>
              {t('Я выпускник, у меня нет пароля')}
            </Button>
          )}
        </div>

        <p className="t-note login__hint">{t('Учётные записи заводит администратор школы — самостоятельной регистрации нет.')}</p>
      </div>
    </div>
  )
}
