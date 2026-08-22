/** Экран входа: школьный аккаунт Microsoft и вторая дверь для выпускников. */
import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { isEntraConfigured } from '../auth/msal'

export default function Login() {
  const { loginWithMicrosoft, loginWithPassword, requestLink } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onMicrosoft() {
    setError(null)
    setBusy(true)
    try {
      await loginWithMicrosoft()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось войти')
    } finally {
      setBusy(false)
    }
  }

  async function onPassword(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await loginWithPassword(email, password)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось войти')
    } finally {
      setBusy(false)
    }
  }

  async function onLink(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await requestLink(email)
      setNote('Если такая почта известна системе, ссылка отправлена')
    } catch {
      setError('Не удалось отправить ссылку')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <div className="card card-pad login__card">
        <span className="eyebrow">◆ Вход</span>
        <h1 className="login__title">Платформа поступления</h1>
        <p className="muted login__sub">Школьный аккаунт — основной способ входа.</p>

        <button
          className="btn btn-primary login__ms"
          onClick={onMicrosoft}
          disabled={busy || !isEntraConfigured}
        >
          Войти через Microsoft
        </button>
        {!isEntraConfigured && (
          <p className="muted login__hint">
            Вход через Microsoft ещё не настроен — воспользуйтесь ссылкой на почту.
          </p>
        )}

        {import.meta.env.DEV && (
          <>
            <div className="login__sep">
              <span>ручная проверка</span>
            </div>
            <form onSubmit={onPassword} className="login__form">
              <label className="login__label" htmlFor="email">
                Тестовая почта
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="test@example.kz"
                className="login__input"
              />
              <label className="login__label" htmlFor="password">
                Пароль
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="login__input"
              />
              <button className="btn btn-ghost" type="submit" disabled={busy}>
                Войти с тестовым аккаунтом
              </button>
            </form>
          </>
        )}

        <div className="login__sep">
          <span>или для выпускников</span>
        </div>

        <form onSubmit={onLink} className="login__form">
          <label className="login__label" htmlFor="link-email">
            Личная почта
          </label>
          <input
            id="link-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@gmail.com"
            className="login__input"
          />
          <button className="btn btn-ghost" type="submit" disabled={busy}>
            Прислать ссылку для входа
          </button>
        </form>

        {note && <p className="login__note chip chip-ok">{note}</p>}
        {error && <p className="login__note chip chip-risk">{error}</p>}
      </div>
    </div>
  )
}
