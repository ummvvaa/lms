/**
 * Личная страница: учётная запись, тема и смена пароля.
 *
 * Открывается из меню по аватару. Раскладка по макету: сверху карточка
 * с аватаром, именем и последним входом, ниже две колонки — учётная запись
 * с языком и темой слева, смена пароля справа. Пояснений о правах и
 * подсказок нет — что доступно, видно по меню. У учителя в учётной записи ещё предметы,
 * кабинет и нагрузка; у ученика после пяти шагов — возврат «Моего пути».
 * Язык и тема хранятся в профиле на сервере — те же, что в меню по аватару.
 */
import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router'
import { ApiError } from '../api/client'
import { useTeacherProfile } from '../api/academics'
import { useUpdatePreferences } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import Field from '../components/Field'
import PersonalEmail from '../components/PersonalEmail'
import PasswordRules, { passwordProblem } from '../components/PasswordRules'
import { languagesOf, offeredLanguage, THEMES } from '../components/ProfileMenu'
import { Avatar, Row, Rows, Segmented } from '../components/patterns'
import { Chip, counted, DataCard, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { applyTheme } from '../theme'
import { formatDateTimeLong } from '../lib/format'
import './academics/academics.css'
import './profile-layout.css'

function formatWhen(value: string | null): string {
  if (!value) return t('ещё не входили')
  return formatDateTimeLong(value)
}

/** Язык и тема: те же настройки, что в меню по аватару. */
function SettingsBlock() {
  const { me } = useAuth()
  const prefs = useUpdatePreferences()
  if (!me) return null
  const several = languagesOf(me).length > 1
  const theme = (
    <Segmented
      usageFilter={false}
      value={me.theme}
      onChange={(value) => {
        applyTheme(value)
        prefs.mutate({ theme: value })
      }}
      label={t('Тема')}
      items={THEMES.map((item) => ({ value: item.value, label: t(item.label) }))}
    />
  )
  return (
    <DataCard title={several ? t('Язык и тема') : t('Тема')}>
      {several && (
        <Field.Static label={t('Язык')}>
          <Segmented usageFilter={false} value={offeredLanguage(me)} onChange={(value) => prefs.mutate({ language: value })} label={t('Язык')} items={languagesOf(me).map((item) => ({ value: item.value, label: item.label }))} />
        </Field.Static>
      )}
      {/* при выборе языка у темы своя подпись, иначе её называет заголовок карточки */}
      {several ? <Field.Static label={t('Тема')}>{theme}</Field.Static> : theme}
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
      <Row title={t('Нагрузка')} value={data.hours || null} none={t('уроков нет')} note={counted(data.journals, 'журнал|журнала|журналов')} />
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
          <Field kind="password" name="repeat" label={t('Повторите пароль')} value={repeat} onChange={setRepeat} autoComplete="new-password" required error={mismatch ? t('Пароли не совпадают') : undefined} />
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

export default function Profile() {
  const { me } = useAuth()
  if (!me) return null
  // логин или почта — в главной карточке; вторая из них, если есть обе, — строкой ниже
  const handle = me.login || me.email || ''

  return (
    <div className="lay-screen">
      <ScreenHead title={t('Профиль')} subtitle={`${me.role_title}${me.role === 'student' && me.group ? ` · ${me.group}` : ''}`} />
      <section className="card card-pad card--beam profile__hero">
        <Avatar name={me.full_name || handle} size={72} />
        <div className="profile__who">
          <span className="profile__name">{me.full_name || t('не указано')}</span>
          <span className="t-note profile__line">
            {handle && <span className="profile__handle">{handle}</span>}
            <span className="profile__when">{`${t('Последний вход')}: ${formatWhen(me.last_login)}`}</span>
          </span>
        </div>
      </section>
      <div className="lay-2 profile__cols">
        <div className="lay-stack">
          <DataCard title={t('Учётная запись')}>
            <Rows>
              {me.email && me.login && <Row title={t('Почта')} value={me.email} />}
              <Row title={t('Роль')} value={me.role_title} />
              {me.role === 'student' && <Row title={t('Группа')} value={me.group || null} none={t('не указана')} />}
              {me.role === 'teacher' && <TeacherRows />}
              {/* личная почта — вход и «Забыли пароль» после подтверждения письмом */}
              {me.role === 'student' && <PersonalEmail identities={me.identities} />}
            </Rows>
          </DataCard>
          <SettingsBlock />
        </div>
        <PasswordBlock />
      </div>
    </div>
  )
}
