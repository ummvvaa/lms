/**
 * Личная страница: кто я в системе и мои настройки.
 *
 * Открывается из меню по аватару. Смена пароля живёт здесь же —
 * якорь #password прокручивает к форме. Язык и тема хранятся
 * в профиле на сервере — те же, что в меню по аватару.
 */
import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useJourney, useOnboarding, useUpdatePreferences } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import PasswordRules, { passwordProblem } from '../components/PasswordRules'
import { LANGUAGES, THEMES } from '../components/ProfileMenu'
import { applyTheme } from '../theme'
import { Bar, ScreenHead } from '../components/ui'
import { t } from '../i18n'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'

function formatWhen(value: string | null): string {
  if (!value) return t('ещё не входили')
  return new Date(value).toLocaleString('ru', { dateStyle: 'long', timeStyle: 'short' })
}

/** Язык и тема: те же настройки, что в меню по аватару. */
function SettingsBlock() {
  const { me } = useAuth()
  const prefs = useUpdatePreferences()
  if (!me) return null
  return (
    <div className="card card-pad profile__block">
      <span className="eyebrow">{t('Язык')}</span>
      <div className="segmented">
        {LANGUAGES.map((item) => (
          <button
            key={item.value}
            className={`segmented__option${me.language === item.value ? ' segmented__option--active' : ''}`}
            onClick={() => prefs.mutate({ language: item.value })}
          >
            {item.label}
          </button>
        ))}
      </div>
      <span className="eyebrow">{t('Тема')}</span>
      <div className="segmented">
        {THEMES.map((item) => (
          <button
            key={item.value}
            className={`segmented__option${me.theme === item.value ? ' segmented__option--active' : ''}`}
            onClick={() => {
              applyTheme(item.value)
              prefs.mutate({ theme: item.value })
            }}
          >
            {t(item.label)}
          </button>
        ))}
      </div>
    </div>
  )
}

/** Прогресс заполнения анкеты — только у ученика. */
function StudentProgress() {
  const { data } = useOnboarding()
  if (!data || !data.total) return null
  const percent = Math.round((data.answered / data.total) * 100)
  return (
    <div className="card card-pad profile__block">
      <span className="eyebrow">{t('Заполнение профиля')}</span>
      <p className="muted">
        Анкета: {data.answered} из {data.total} — {percent}%
      </p>
      <Bar percent={percent} />
      {data.answered < data.total && (
        <p className="muted profile__hint">
          {t('Продолжить можно в разделе «Главная» — квиз откроется сам.')}
        </p>
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
      <span className="eyebrow">{t('Смена пароля')}</span>
      <form onSubmit={submit} className="profile__form">
        <label className="login__label" htmlFor="profile-current-password">
          {t('Текущий пароль')}
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
          {t('Новый пароль')}
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
          {t('Ещё раз')}
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
        {mismatch && (
          <Badge variant="warn" className="badge--line">
            {t('Пароли не совпадают')}
          </Badge>
        )}
        {same && (
          <Badge variant="warn" className="badge--line">
            {t('Новый пароль должен отличаться от текущего')}
          </Badge>
        )}

        <Button
          size="sm"
          className="profile__save"
          type="submit"
          disabled={busy || local !== null || mismatch || same || repeat === ''}
        >
          {t('Сменить пароль')}
        </Button>
      </form>
      {done && (
        <Badge variant="ok" className="badge--line">
          {t('Пароль сменён')}
        </Badge>
      )}
      {error && (
        <Badge variant="risk" className="badge--line">
          {error}
        </Badge>
      )}
    </div>
  )
}

/**
 * Возврат раздела «Мой путь» (фаза 49).
 *
 * После пяти пройденных шагов пункт уходит из меню совсем: раздел,
 * в котором больше нечего делать, не должен занимать строку. Но
 * перезаполнить шаг иногда нужно, и вернуть его можно отсюда.
 * Жест, а не факт, — поэтому он живёт в `localStorage`, как «пропущено».
 */
function JourneyPin() {
  const [pinned, setPinned] = useState(localStorage.getItem('journey.pinned') === '1')
  const toggle = () => {
    const next = !pinned
    setPinned(next)
    if (next) localStorage.setItem('journey.pinned', '1')
    else localStorage.removeItem('journey.pinned')
  }
  return (
    <div className="card card-pad profile__block">
      <span className="eyebrow">{t('Мой путь')}</span>
      <p className="muted profile__note">
        {t('Пять шагов пройдены — раздел ушёл из меню. Верните его, если что-то нужно перезаполнить.')}
      </p>
      <Button variant="outline" onClick={toggle}>
        {pinned ? t('Скрыть шаги пути') : t('Показать шаги пути')}
      </Button>
    </div>
  )
}

export default function Profile() {
  const { me } = useAuth()
  const journey = useJourney(me?.role === 'student')
  if (!me) return null

  return (
    <div>
      <ScreenHead title={t('Профиль')} subtitle={t('Ваша учётная запись и настройки.')} />
      <div className="grid grid--two">
        <div className="card card-pad profile__block">
          <span className="eyebrow">{t('Учётная запись')}</span>
          <dl className="profile__facts">
            <dt className="muted">{t('Имя')}</dt>
            <dd>{me.full_name || '—'}</dd>
            <dt className="muted">{t('Почта')}</dt>
            <dd>{me.email}</dd>
            <dt className="muted">{t('Роль')}</dt>
            <dd>{me.role_title}</dd>
            {me.role === 'student' && (
              <>
                <dt className="muted">{t('Группа')}</dt>
                <dd>{me.group || 'не указана'}</dd>
              </>
            )}
            <dt className="muted">{t('Последний вход')}</dt>
            <dd>{formatWhen(me.last_login)}</dd>
          </dl>
        </div>

        <div className="profile__side">
          {me.role === 'student' && <StudentProgress />}
          {me.role === 'student' && journey.data?.complete && <JourneyPin />}
          <SettingsBlock />
          <PasswordBlock />
        </div>
      </div>
    </div>
  )
}
