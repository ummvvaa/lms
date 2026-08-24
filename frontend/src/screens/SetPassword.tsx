/**
 * Установка пароля по ссылке: приглашение и сброс приходят на один экран.
 * Требования показаны заранее — человек не должен угадывать их по отказам.
 */
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import PasswordRules, { passwordProblem } from '../components/PasswordRules'
import { t } from '../i18n'

export default function SetPassword() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { setPasswordByToken } = useAuth()
  const token = params.get('token') ?? ''

  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const local = passwordProblem(password)
  const mismatch = repeat !== '' && repeat !== password

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await setPasswordByToken(token, password)
      navigate('/dashboard', { replace: true })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не удалось установить пароль')
    } finally {
      setBusy(false)
    }
  }

  if (!token) {
    return (
      <div className="login">
        <div className="card card-pad login__card">
          <h1 className="login__title">{t('Ссылка неполная')}</h1>
          <p className="muted login__sub">{t('В адресе нет токена. Попросите прислать ссылку заново.')}</p>
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/login')}>
            {t('К входу')}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="login">
      <div className="card card-pad login__card">
        <span className="eyebrow">{t('Пароль')}</span>
        <h1 className="login__title">{t('Придумайте пароль')}</h1>
        <p className="muted login__sub">{t('Он понадобится при каждом входе.')}</p>

        <form onSubmit={submit} className="login__form">
          <label className="login__label" htmlFor="new-password">
            {t('Новый пароль')}
          </label>
          <input
            id="new-password"
            type="password"
            required
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="login__input"
          />
          <label className="login__label" htmlFor="repeat-password">
            {t('Ещё раз')}
          </label>
          <input
            id="repeat-password"
            type="password"
            required
            autoComplete="new-password"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
            className="login__input"
          />

          <PasswordRules password={password} />
          {mismatch && <p className="chip chip-warn login__hint">{t('Пароли не совпадают')}</p>}

          <button
            className="btn btn-primary login__ms"
            type="submit"
            disabled={busy || local !== null || mismatch || repeat === ''}
          >
            {t('Сохранить пароль')}
          </button>
        </form>

        {error && <p className="chip chip-risk login__hint">{error}</p>}
      </div>
    </div>
  )
}
