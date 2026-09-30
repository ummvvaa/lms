/**
 * Личная страница: учётная запись, тема и смена пароля.
 *
 * Открывается из меню по аватару. Одна узкая колонка, три карточки
 * (решение владельца, 27.09.2026): пояснений о правах и подсказок нет —
 * что доступно, видно по меню. У учителя в учётной записи ещё предметы,
 * кабинет и нагрузка; у ученика после пяти шагов — возврат «Моего пути».
 * Язык и тема хранятся в профиле на сервере — те же, что в меню по аватару.
 */
import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useTeacherProfile } from '../api/academics'
import { useJourney, useUpdatePreferences } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import Field from '../components/Field'
import PersonalEmail from '../components/PersonalEmail'
import PasswordRules, { passwordProblem } from '../components/PasswordRules'
import { languagesOf, offeredLanguage, THEMES } from '../components/ProfileMenu'
import { Row, Rows, Segmented } from '../components/patterns'
import { Chip, counted, DataCard, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { applyTheme } from '../theme'
import './academics/academics.css'

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
    <DataCard title={t('Тема')}>
      {languagesOf(me).length > 1 && (
        <Field.Static label={t('Язык')}>
          <Segmented value={offeredLanguage(me)} onChange={(value) => prefs.mutate({ language: value })} label={t('Язык')} items={languagesOf(me).map((item) => ({ value: item.value, label: item.label }))} />
        </Field.Static>
      )}
      <Segmented
        value={me.theme}
        onChange={(value) => {
          applyTheme(value)
          prefs.mutate({ theme: value })
        }}
        label={t('Тема')}
        items={THEMES.map((item) => ({ value: item.value, label: t(item.label) }))}
      />
    </DataCard>
  )
}

/** Предметы, кабинет и нагрузка учителя — строками в его учётной записи. */
function TeacherRows() {
  const { data } = useTeacherProfile()
  if (!data) return null
  return (
    <>
      <Row title={t('Предметы')} value={data.teacher.subject_titles || null} none={t('не назначены')} />
      <Row title={t('Кабинет')} value={data.teacher.room || null} none={t('не закреплён')} />
      <Row title={t('Нагрузка')} value={data.hours || null} none={t('уроков нет')} note={counted(data.journals, ['журнал', 'журнала', 'журналов'])} />
    </>
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
    <Row
      title={t('Мой путь')}
      value={pinned ? t('в меню') : t('скрыт из меню')}
      acts={
        <Button variant="outline" size="sm" onClick={toggle}>
          {pinned ? t('Скрыть шаги пути') : t('Показать шаги пути')}
        </Button>
      }
    />
  )
}

export default function Profile() {
  const { me } = useAuth()
  const journey = useJourney(me?.role === 'student' && me.has_admission !== false)
  if (!me) return null

  return (
    <div>
      <ScreenHead title={t('Профиль')} subtitle={`${me.role_title}${me.role === 'student' && me.group ? ` · ${me.group}` : ''}`} />
      <div className="acad__narrow">
        <DataCard title={t('Учётная запись')}>
          <Rows>
            <Row title={t('Имя')} value={me.full_name || null} none={t('не указано')} />
            {me.email && <Row title={t('Почта')} value={me.email} />}
            {me.login && <Row title={t('Логин')} value={me.login} />}
            <Row title={t('Роль')} value={me.role_title} />
            {me.role === 'student' && <Row title={t('Группа')} value={me.group || null} none={t('не указана')} />}
            {me.role === 'teacher' && <TeacherRows />}
            <Row title={t('Последний вход')} value={formatWhen(me.last_login)} />
            {me.role === 'student' && journey.data?.complete && <JourneyPin />}
            {/* личная почта — вход и «Забыли пароль» после подтверждения письмом */}
            {me.role === 'student' && <PersonalEmail identities={me.identities} />}
          </Rows>
        </DataCard>
        <SettingsBlock />
        <PasswordBlock />
      </div>
    </div>
  )
}
