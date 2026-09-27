/**
 * Обязательная смена пароля при первом входе.
 *
 * Экран не обойти: пока `must_change_password` стоит, сервер отвечает 403
 * на любой другой запрос к API — проверка не только в интерфейсе.
 */
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import Field from '../components/Field'
import PasswordRules, { passwordProblem } from '../components/PasswordRules'
import { Chip } from '../components/ui'
import { t } from '../i18n'
import { Button } from '../components/ui/button'

export default function ChangePassword() {
  const { me, changePassword, logout } = useAuth()
  const queryClient = useQueryClient()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const local = passwordProblem(next, me?.email ?? '')
  const mismatch = repeat !== '' && repeat !== next
  const same = next !== '' && next === current

  /**
   * Дождаться, пока в воздухе не останется ни одного запроса: ответ на смену
   * пароля обязан установить cookie последним (D1).
   */
  async function settle(): Promise<void> {
    for (let i = 0; i < 50 && queryClient.isFetching() > 0; i += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 100))
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await settle()
      await changePassword(current, next)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t('Не удалось сменить пароль'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <div className="card card-pad login__card">
        <span className="t-caps">{t('Первый вход')}</span>
        <h1 className="login__title">{t('Смените пароль')}</h1>
        <p className="t-note login__sub">{t('Пароль, который вам выдали, знает ещё кто-то. Придумайте свой — дальше он и будет рабочим.')}</p>

        <form onSubmit={submit} className="login__form">
          <Field kind="password" name="current-password" id="current-password" label={t('Текущий пароль')} value={current} onChange={setCurrent} autoComplete="current-password" required />
          <Field kind="password" name="next-password" id="next-password" label={t('Новый пароль')} value={next} onChange={setNext} autoComplete="new-password" required error={same ? t('Новый пароль должен отличаться от текущего') : undefined} />
          <Field kind="password" name="repeat-new-password" id="repeat-new-password" label={t('Ещё раз')} value={repeat} onChange={setRepeat} autoComplete="new-password" required error={mismatch ? t('Пароли не совпадают') : undefined} />
          <PasswordRules password={next} email={me?.email ?? ''} />
          <Button className="login__ms" type="submit" disabled={busy || local !== null || mismatch || same || repeat === ''}>
            {t('Сохранить и продолжить')}
          </Button>
        </form>

        {error && <Chip tone="bad" className="login__hint">{error}</Chip>}

        <Button variant="outline" size="sm" className="login__hint" onClick={() => void logout()}>
          {t('Выйти')}
        </Button>
      </div>
    </div>
  )
}
