/**
 * Обязательная смена пароля при первом входе.
 *
 * Экран не обойти: пока `must_change_password` стоит, сервер отвечает 403
 * на любой другой запрос к API — проверка не только в интерфейсе.
 */
import { useState } from 'react'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import PasswordRules, { passwordProblem } from '../components/PasswordRules'

export default function ChangePassword() {
  const { me, changePassword, logout } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const local = passwordProblem(next, me?.email ?? '')
  const mismatch = repeat !== '' && repeat !== next
  const same = next !== '' && next === current

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await changePassword(current, next)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не удалось сменить пароль')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <div className="card card-pad login__card">
        <span className="eyebrow">Первый вход</span>
        <h1 className="login__title">Смените пароль</h1>
        <p className="muted login__sub">
          Пароль, который вам выдали, знает ещё кто-то. Придумайте свой — дальше он и будет рабочим.
        </p>

        <form onSubmit={submit} className="login__form">
          <label className="login__label" htmlFor="current-password">
            Текущий пароль
          </label>
          <input
            id="current-password"
            type="password"
            required
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            className="login__input"
          />
          <label className="login__label" htmlFor="next-password">
            Новый пароль
          </label>
          <input
            id="next-password"
            type="password"
            required
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            className="login__input"
          />
          <label className="login__label" htmlFor="repeat-new-password">
            Ещё раз
          </label>
          <input
            id="repeat-new-password"
            type="password"
            required
            autoComplete="new-password"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
            className="login__input"
          />

          <PasswordRules password={next} email={me?.email ?? ''} />
          {mismatch && <p className="chip chip-warn login__hint">Пароли не совпадают</p>}
          {same && <p className="chip chip-warn login__hint">Новый пароль должен отличаться от текущего</p>}

          <button
            className="btn btn-primary login__ms"
            type="submit"
            disabled={busy || local !== null || mismatch || same || repeat === ''}
          >
            Сохранить и продолжить
          </button>
        </form>

        {error && <p className="chip chip-risk login__hint">{error}</p>}

        <button className="btn btn-ghost btn-sm login__hint" onClick={() => void logout()}>
          Выйти
        </button>
      </div>
    </div>
  )
}
