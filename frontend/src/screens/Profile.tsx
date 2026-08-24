/**
 * Личная страница: кто я в системе и мои настройки.
 *
 * Открывается из меню по аватару. Смена пароля живёт здесь же —
 * якорь #password прокручивает к форме. Настройки языка и темы
 * появятся в фазе 24 вместе с самой возможностью.
 */
import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useOnboarding } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import PasswordRules, { passwordProblem } from '../components/PasswordRules'
import { Bar, ScreenHead } from '../components/ui'

function formatWhen(value: string | null): string {
  if (!value) return 'ещё не входили'
  return new Date(value).toLocaleString('ru', { dateStyle: 'long', timeStyle: 'short' })
}

/** Прогресс заполнения анкеты — только у ученика. */
function StudentProgress() {
  const { data } = useOnboarding()
  if (!data || !data.total) return null
  const percent = Math.round((data.answered / data.total) * 100)
  return (
    <div className="card card-pad profile__block">
      <span className="eyebrow">Заполнение профиля</span>
      <p className="muted">
        Анкета: {data.answered} из {data.total} — {percent}%
      </p>
      <Bar percent={percent} />
      {data.answered < data.total && (
        <p className="muted profile__hint">Продолжить можно в разделе «Главная» — квиз откроется сам.</p>
      )}
    </div>
  )
}

function PasswordBlock() {
  const { me, changePassword } = useAuth()
  const location = useLocation()
  const block = useRef<HTMLDivElement>(null)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (location.hash === '#password') block.current?.scrollIntoView({ behavior: 'smooth' })
  }, [location.hash])

  const local = passwordProblem(next, me?.email ?? '')
  const mismatch = repeat !== '' && repeat !== next
  const same = next !== '' && next === current

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setDone(false)
    setBusy(true)
    try {
      await changePassword(current, next)
      setCurrent('')
      setNext('')
      setRepeat('')
      setDone(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не удалось сменить пароль')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card card-pad profile__block" id="password" ref={block}>
      <span className="eyebrow">Смена пароля</span>
      <form onSubmit={submit} className="profile__form">
        <label className="login__label" htmlFor="profile-current-password">
          Текущий пароль
        </label>
        <input
          id="profile-current-password"
          type="password"
          required
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          className="login__input"
        />
        <label className="login__label" htmlFor="profile-next-password">
          Новый пароль
        </label>
        <input
          id="profile-next-password"
          type="password"
          required
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          className="login__input"
        />
        <label className="login__label" htmlFor="profile-repeat-password">
          Ещё раз
        </label>
        <input
          id="profile-repeat-password"
          type="password"
          required
          autoComplete="new-password"
          value={repeat}
          onChange={(e) => setRepeat(e.target.value)}
          className="login__input"
        />

        <PasswordRules password={next} email={me?.email ?? ''} />
        {mismatch && <p className="chip chip-warn">Пароли не совпадают</p>}
        {same && <p className="chip chip-warn">Новый пароль должен отличаться от текущего</p>}

        <button
          className="btn btn-primary btn-sm profile__save"
          type="submit"
          disabled={busy || local !== null || mismatch || same || repeat === ''}
        >
          Сменить пароль
        </button>
      </form>
      {done && <p className="chip chip-ok">Пароль сменён</p>}
      {error && <p className="chip chip-risk">{error}</p>}
    </div>
  )
}

export default function Profile() {
  const { me } = useAuth()
  if (!me) return null

  return (
    <div>
      <ScreenHead title="Профиль" subtitle="Ваша учётная запись и настройки." />
      <div className="grid grid--two">
        <div className="card card-pad profile__block">
          <span className="eyebrow">Учётная запись</span>
          <dl className="profile__facts">
            <dt className="muted">Имя</dt>
            <dd>{me.full_name || '—'}</dd>
            <dt className="muted">Почта</dt>
            <dd>{me.email}</dd>
            <dt className="muted">Роль</dt>
            <dd>{me.role_title}</dd>
            {me.role === 'student' && (
              <>
                <dt className="muted">Группа</dt>
                <dd>{me.group || 'не указана'}</dd>
              </>
            )}
            <dt className="muted">Последний вход</dt>
            <dd>{formatWhen(me.last_login)}</dd>
          </dl>
        </div>

        <div className="profile__side">
          {me.role === 'student' && <StudentProgress />}
          <PasswordBlock />
        </div>
      </div>
    </div>
  )
}
