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
        setNote('Если такая почта известна системе, ссылка отправлена. Она действует час.')
      } else {
        await requestLink(email)
        setNote('Если такая почта известна системе, ссылка отправлена.')
      }
    } catch (e) {
      setError(message(e, mode === 'password' ? 'Не удалось войти' : 'Не удалось отправить ссылку'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <div className="card card-pad login__card">
        <img className="login__logo" src={LOGO.login} alt="" />
        <span className="eyebrow">Вход</span>
        <h1 className="login__title">{SCHOOL_NAME}</h1>
        <p className="muted login__sub">
          {mode === 'password' && 'Почта и пароль, выданные школой.'}
          {mode === 'reset' && 'Пришлём ссылку на смену пароля. Она действует час.'}
          {mode === 'link' && 'Для выпускников: вход по ссылке на личную почту.'}
        </p>

        <form onSubmit={submit} className="login__form">
          <label className="login__label" htmlFor="email">
            Почта
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
                Пароль
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

          <button className="btn btn-primary login__ms" type="submit" disabled={busy}>
            {mode === 'password' ? 'Войти' : 'Прислать ссылку'}
          </button>
        </form>

        {note && <p className="chip chip-ok login__hint">{note}</p>}
        {error && <p className="chip chip-risk login__hint">{error}</p>}

        <div className="login__sep">
          <span>ещё</span>
        </div>

        <div className="login__modes">
          {mode !== 'password' && (
            <button className="btn btn-ghost btn-sm" onClick={() => setMode('password')}>
              Войти по паролю
            </button>
          )}
          {mode !== 'reset' && (
            <button className="btn btn-ghost btn-sm" onClick={() => setMode('reset')}>
              Забыли пароль?
            </button>
          )}
          {mode !== 'link' && (
            <button className="btn btn-ghost btn-sm" onClick={() => setMode('link')}>
              Я выпускник, у меня нет пароля
            </button>
          )}
        </div>

        <p className="muted login__hint">
          Учётные записи заводит администратор школы — самостоятельной регистрации нет.
        </p>
      </div>
    </div>
  )
}
