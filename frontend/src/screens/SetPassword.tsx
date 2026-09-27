/**
 * Установка пароля по ссылке: приглашение и сброс приходят на один экран.
 * Требования показаны заранее — человек не должен угадывать их по отказам.
 */
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Field from '../components/Field'
import PasswordRules, { passwordProblem } from '../components/PasswordRules'
import { Chip } from '../components/ui'
import { t } from '../i18n'
import { Button } from '../components/ui/button'

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
      setError(e instanceof ApiError ? e.message : t('Не удалось установить пароль'))
    } finally {
      setBusy(false)
    }
  }

  if (!token) {
    return (
      <div className="login">
        <div className="card card-pad login__card">
          <h1 className="login__title">{t('Ссылка неполная')}</h1>
          <p className="t-note login__sub">{t('В адресе нет токена. Попросите прислать ссылку заново.')}</p>
          <Button variant="outline" size="sm" onClick={() => navigate('/login')}>
            {t('К входу')}
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="login">
      <div className="card card-pad login__card">
        <span className="t-caps">{t('Пароль')}</span>
        <h1 className="login__title">{t('Придумайте пароль')}</h1>
        <p className="t-note login__sub">{t('Он понадобится при каждом входе.')}</p>

        <form onSubmit={submit} className="login__form">
          <Field kind="password" name="new-password" id="new-password" label={t('Новый пароль')} value={password} onChange={setPassword} autoComplete="new-password" required />
          <Field kind="password" name="repeat-password" id="repeat-password" label={t('Ещё раз')} value={repeat} onChange={setRepeat} autoComplete="new-password" required error={mismatch ? t('Пароли не совпадают') : undefined} />
          <PasswordRules password={password} />
          <Button className="login__ms" type="submit" disabled={busy || local !== null || mismatch || repeat === ''}>
            {t('Сохранить пароль')}
          </Button>
        </form>

        {error && <Chip tone="bad" className="login__hint">{error}</Chip>}
      </div>
    </div>
  )
}
