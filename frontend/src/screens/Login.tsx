/**
 * Вход по почте и паролю.
 *
 * Регистрации самому себе нет: учётную запись заводит администратор.
 * Вторая дверь — одноразовая ссылка: для выпускников, у которых пароля нет,
 * и для тех, кто его забыл.
 */
import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import { LOGO, SCHOOL_NAME } from '../branding'
import { t } from '../i18n'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'

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
        setNote(t('Если такая почта известна системе, ссылка отправлена. Она действует час.'))
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
        {/* логотип и название — одной строкой: плашка «Вход» над ними
            ничего не добавляла, экран входа и так один */}
        <div className="login__brand">
          <img className="login__logo" src={LOGO.login} alt="" />
          <h1 className="login__title">{SCHOOL_NAME}</h1>
        </div>
        <p className="muted login__sub">
          {mode === 'password' && t('Почта и пароль, выданные школой.')}
          {mode === 'reset' && t('Пришлём ссылку на смену пароля. Она действует час.')}
          {mode === 'link' && t('Для выпускников: вход по ссылке на личную почту.')}
        </p>

        <form onSubmit={submit} className="login__form">
          <label className="login__label" htmlFor="email">
            {t('Почта')}
          </label>
          <input
            id="email"
            name="email"
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="ivanova@school.kz"
            className="login__input"
          />

          {mode === 'password' && (
            <>
              <label className="login__label" htmlFor="password">
                {t('Пароль')}
              </label>
              <input
                id="password"
                name="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="login__input"
              />
            </>
          )}

          <Button className="login__ms" type="submit" disabled={busy}>
            {mode === 'password' ? t('Войти') : t('Прислать ссылку')}
          </Button>
        </form>

        {note && (
          <Badge variant="ok" className="badge--line login__hint">
            {note}
          </Badge>
        )}
        {error && (
          <Badge variant="risk" className="badge--line login__hint">
            {error}
          </Badge>
        )}

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

        <p className="muted login__hint">
          {t('Учётные записи заводит администратор школы — самостоятельной регистрации нет.')}
        </p>
      </div>
    </div>
  )
}
