/**
 * Личная страница: кто я в системе и мои настройки.
 *
 * Открывается из меню по аватару. Поля строками слева, справа настройки,
 * заполнение анкеты у ученика и смена пароля (якорь #password).
 * Язык и тема хранятся в профиле на сервере — те же, что в меню по аватару.
 */
import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useCuratorProfile, useJourney, useOnboarding, useUpdatePreferences } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import Field from '../components/Field'
import PasswordRules, { passwordProblem } from '../components/PasswordRules'
import { LANGUAGES, offeredLanguage, THEMES } from '../components/ProfileMenu'
import Progress from '../components/Progress'
import { Row, Rows, Segmented } from '../components/patterns'
import { Chip, DataCard, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { applyTheme } from '../theme'
import TeacherProfile from './academics/TeacherProfile'
import { NoteCard } from './academics/shared'

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
    <DataCard title={t('Настройки')}>
      {LANGUAGES.length > 1 && (
        <Field.Static label={t('Язык')}>
          <Segmented value={offeredLanguage(me.language)} onChange={(value) => prefs.mutate({ language: value })} label={t('Язык')} items={LANGUAGES.map((item) => ({ value: item.value, label: item.label }))} />
        </Field.Static>
      )}
      <Field.Static label={t('Тема')}>
        <Segmented
          value={me.theme}
          onChange={(value) => {
            applyTheme(value)
            prefs.mutate({ theme: value })
          }}
          label={t('Тема')}
          items={THEMES.map((item) => ({ value: item.value, label: t(item.label) }))}
        />
      </Field.Static>
    </DataCard>
  )
}

/** Прогресс заполнения анкеты — только у ученика. */
function StudentProgress() {
  const { data } = useOnboarding()
  if (!data || !data.total) return null
  const percent = Math.round((data.answered / data.total) * 100)
  return (
    <DataCard title={t('Заполнение профиля')} note={`${t('Анкета')}: ${data.answered} ${t('из')} ${data.total}`}>
      <Progress percent={percent} />
      {data.answered < data.total && <p className="t-note">{t('Продолжить можно в разделе «Главная» — квиз откроется сам.')}</p>}
    </DataCard>
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
      setError(e instanceof ApiError ? e.message : t('Не удалось сменить пароль'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div id="password" ref={block}>
      <DataCard title={t('Смена пароля')}>
        <form onSubmit={submit} className="acad__stack">
          <Field kind="password" name="current" label={t('Текущий пароль')} value={current} onChange={setCurrent} autoComplete="current-password" required />
          <Field kind="password" name="next" label={t('Новый пароль')} value={next} onChange={setNext} autoComplete="new-password" required error={same ? t('Новый пароль должен отличаться от текущего') : undefined} />
          <Field kind="password" name="repeat" label={t('Ещё раз')} value={repeat} onChange={setRepeat} autoComplete="new-password" required error={mismatch ? t('Пароли не совпадают') : undefined} />
          <PasswordRules password={next} email={me?.email ?? ''} />
          <div className="acad__actions">
            <Button size="sm" type="submit" disabled={busy || local !== null || mismatch || same || repeat === ''}>
              {t('Сменить пароль')}
            </Button>
            {done && <Chip tone="good">{t('Пароль сменён')}</Chip>}
            {error && <Chip tone="bad">{error}</Chip>}
          </div>
        </form>
      </DataCard>
    </div>
  )
}

/** Возврат раздела «Мой путь»: после пяти шагов пункт уходит из меню. */
function JourneyPin() {
  const [pinned, setPinned] = useState(localStorage.getItem('journey.pinned') === '1')
  const toggle = () => {
    const next = !pinned
    setPinned(next)
    if (next) localStorage.setItem('journey.pinned', '1')
    else localStorage.removeItem('journey.pinned')
  }
  return (
    <DataCard title={t('Мой путь')} note={t('Пять шагов пройдены — раздел ушёл из меню')}>
      <div className="acad__actions">
        <Button variant="outline" size="sm" onClick={toggle}>
          {pinned ? t('Скрыть шаги пути') : t('Показать шаги пути')}
        </Button>
      </div>
    </DataCard>
  )
}

/** Что куратору доступно: группы, что он подтверждает и что читает — с сервера. */
function CuratorFacts() {
  const { data } = useCuratorProfile()
  if (!data) return null
  return (
    <DataCard title={t('Что вам доступно')} note={t('Набор доменов, которые подтверждает куратор, задаёт школа')}>
      <Rows>
        <Row title={t('Группы')} value={data.groups.map((group) => group.code).join(', ') || null} none={t('не назначены')} />
        <Row title={t('Подтверждаете')} value={data.confirms.join(', ') || null} none={t('нет')} />
        <Row title={t('Читаете')} value={data.reads.join(', ') || null} none={t('нет')} />
      </Rows>
    </DataCard>
  )
}

export default function Profile() {
  const { me } = useAuth()
  const journey = useJourney(me?.role === 'student')
  if (!me) return null

  return (
    <div>
      <ScreenHead title={t('Профиль')} subtitle={`${me.role_title}${me.role === 'student' && me.group ? ` · ${me.group}` : ''}`} />
      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard title={t('Учётная запись')}>
            <Rows>
              <Row title={t('Имя')} value={me.full_name || null} none={t('не указано')} />
              <Row title={t('Почта')} value={me.email} />
              <Row title={t('Роль')} value={me.role_title} />
              {me.role === 'student' && <Row title={t('Группа')} value={me.group || null} none={t('не указана')} />}
              <Row title={t('Последний вход')} value={formatWhen(me.last_login)} />
            </Rows>
          </DataCard>
          {me.role === 'curator' && <CuratorFacts />}
          {me.role === 'teacher' && <TeacherProfile />}
          <PasswordBlock />
        </div>
        <div className="acad__stack">
          {me.role === 'student' && <StudentProgress />}
          {me.role === 'student' && journey.data?.complete && <JourneyPin />}
          <SettingsBlock />
          <NoteCard title={t('Личная почта')}>{me.identities.some((identity) => identity.provider === 'email_link') ? t('Личная почта привязана — доступ сохранится и после выпуска.') : t('Школьный аккаунт после выпуска отключат. Личную почту можно привязать на главной.')}</NoteCard>
        </div>
      </div>
    </div>
  )
}
