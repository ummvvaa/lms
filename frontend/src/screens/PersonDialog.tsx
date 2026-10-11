/**
 * Один человек на «Пользователях»: заведение и правка по роли.
 *
 * Роль выбирается первой, под неё появляются поля именно этой роли
 * (решение владельца, 11.10.2026): ученику — фамилия, имя, отчество, группа,
 * школьная и личная почта, телефон; учителю — предметы и кабинет; куратору —
 * группы; директору — домен по роли. Сохранение заводит и учётную запись,
 * и запись роли одной транзакцией на сервере (`accounts.people`).
 *
 * ФИО ученика живёт в карточке, учётная запись повторяет его; «Таблица»
 * и карточка ученика на это окно ссылаются, а не правят сами.
 * Окно одно на заведение и правку: второе место для тех же полей
 * разошлось бы с первым в первый же месяц.
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { useAcadMeta } from '../api/academics'
import {
  useCreateUser,
  usePerson,
  useStudyGroups,
  useUpdateUser,
  type InviteLink,
  type IssuedPassword,
  type ManagedUser,
  type PersonWrite,
} from '../api/hooks'
import type { Role } from '../api/types'
import Field from '../components/Field'
import Modal from '../components/Modal'
import { InviteUserDialog, LastUserMail, UserMailHistory } from '../components/UserMail'
import { Chip, ErrorNote, Loading } from '../components/ui'
import { Button } from '../components/ui/button'
import { t, tk } from '../i18n'
import { formatDate, formatDateTime } from '../lib/format'

export const ROLES: { value: Role; title: string; short: string }[] = [
  { value: 'student', title: tk('Ученик'), short: tk('Ученик') },
  { value: 'teacher', title: tk('Учитель'), short: tk('Учитель') },
  { value: 'curator', title: tk('Куратор'), short: tk('Куратор') },
  { value: 'director_behavior', title: tk('Директор школы — профиль и дисциплина'), short: tk('Профиль и дисциплина') },
  { value: 'director_admission', title: tk('Директор по поступлению'), short: tk('Поступление') },
  { value: 'director_exam', title: tk('Академический директор'), short: tk('Экзамены') },
  { value: 'director_talent', title: tk('Директор талантов'), short: tk('Таланты') },
  { value: 'director_sport', title: tk('Директор спорта'), short: tk('Спорт') },
  { value: 'admin', title: tk('Администратор'), short: tk('Администратор') },
]

const isRole = (value: string): value is Role => ROLES.some((role) => role.value === value)

/** Что показать после заведения: пароль один раз или ссылку на пароль. */
export interface PersonCreated {
  invite?: InviteLink
  password?: IssuedPassword
}

interface Form {
  role: Role
  last_name: string
  first_name: string
  middle_name: string
  full_name: string
  handle: string
  email: string
  personal_email: string
  phone: string
  group: string
  subjects: number[]
  room: string
  groups: number[]
}

const EMPTY: Form = {
  role: 'student',
  last_name: '',
  first_name: '',
  middle_name: '',
  full_name: '',
  handle: '',
  email: '',
  personal_email: '',
  phone: '',
  group: '',
  subjects: [],
  room: '',
  groups: [],
}

export default function PersonDialog({
  user: given,
  userId,
  initialRole,
  onClose,
  onCreated,
}: {
  /** правка — есть строка; заведение — нет */
  user?: ManagedUser
  /** правка по номеру учётной записи, когда строки под рукой нет (переход из карточки ученика) */
  userId?: number
  initialRole?: Role
  onClose: () => void
  onCreated?: (made: PersonCreated) => void
}) {
  const editing = given !== undefined || userId !== undefined
  const person = usePerson(given?.id ?? userId ?? null)
  const user: ManagedUser | undefined = given ?? person.data
  const groups = useStudyGroups()
  const meta = useAcadMeta()
  const create = useCreateUser()
  const update = useUpdateUser()
  const [form, setForm] = useState<Form>({ ...EMPTY, role: initialRole ?? 'student' })
  const [loaded, setLoaded] = useState(false)
  const [moved, setMoved] = useState<string | null>(null)
  const [mailing, setMailing] = useState(false)
  const detail = person.data

  useEffect(() => {
    if (!detail || loaded) return
    setForm({
      role: detail.role,
      last_name: detail.student?.last_name ?? '',
      first_name: detail.student?.first_name ?? '',
      middle_name: detail.student?.middle_name ?? '',
      full_name: detail.full_name,
      handle: detail.email ?? detail.login ?? '',
      email: detail.student?.email ?? detail.email ?? '',
      personal_email: detail.personal_email,
      phone: detail.phone,
      group: detail.student?.group ? String(detail.student.group) : '',
      subjects: detail.teacher?.subjects ?? [],
      room: detail.teacher?.room ?? '',
      groups: detail.curator?.groups.map((g) => g.id) ?? [],
    })
    setLoaded(true)
  }, [detail, loaded])

  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((prev) => ({ ...prev, [key]: value }))
  const student = form.role === 'student'
  const roleChanged = editing && detail !== undefined && form.role !== detail.role
  const pending = create.isPending || update.isPending
  const error = create.error ?? update.error

  const groupRows = (groups.data?.results ?? []).filter((row) => row.is_active)
  const chosenGroup = groupRows.find((row) => String(row.id) === form.group)
  // предметы LMS первыми: учителю LMS их назначают чаще всего
  const subjects = [...(meta.data?.subjects ?? [])].sort(
    (a, b) => Number(b.in_lms) - Number(a.in_lms) || a.title.localeCompare(b.title),
  )
  const roleRow = ROLES.find((row) => row.value === form.role)

  const body = (): PersonWrite => {
    if (student) {
      return {
        role: form.role,
        last_name: form.last_name.trim(),
        first_name: form.first_name.trim(),
        middle_name: form.middle_name.trim(),
        group: form.group ? Number(form.group) : null,
        email: form.email.trim(),
        personal_email: form.personal_email.trim(),
        phone: form.phone.trim(),
      }
    }
    const common: PersonWrite = {
      role: form.role,
      full_name: form.full_name.trim(),
      handle: form.handle.trim(),
      personal_email: form.personal_email.trim(),
      phone: form.phone.trim(),
    }
    if (form.role === 'teacher') return { ...common, subjects: form.subjects, room: form.room.trim() }
    if (form.role === 'curator') return { ...common, groups: form.groups }
    return common
  }

  const ready = student
    ? Boolean(form.last_name.trim() && form.first_name.trim() && form.group)
    : Boolean(form.full_name.trim())

  const save = () => {
    if (!editing || !user) {
      create.mutate(body(), {
        onSuccess: (made) => {
          toast.success(t('Заведён {name}', { name: made.full_name || made.email || made.login || '' }))
          onCreated?.({ invite: made.invite, password: made.password })
          onClose()
        },
      })
      return
    }
    update.mutate(
      { id: user.id, ...body() },
      {
        onSuccess: (data) => {
          if (data.login_changed) {
            setMoved(data.login_changed.detail)
            return
          }
          toast.success(t('Сохранено'))
          onClose()
        },
      },
    )
  }

  if (mailing && user) return <InviteUserDialog user={{ ...user, email: form.handle.trim() }} onClose={onClose} />

  const title = editing ? t('Изменить: {name}', { name: user?.full_name || user?.email || user?.login || '' }) : t('Завести пользователя')
  const note = editing
    ? undefined
    : t('Пароль здесь не задаётся: ученик и сотрудник без почты получат временный пароль, сотрудник с почтой — ссылку.')

  return (
    <Modal title={title} note={note} onClose={onClose}>
      <div className="pform">
        {editing && user && (
          <div className="pform__state">
            <span className="t-note">{user.password_state_title}</span>
            <LastUserMail user={user} />
            <span className="t-note">
              {user.last_login ? t('Последний вход: {date}', { date: formatDateTime(user.last_login) }) : t('Не входил ни разу')}
            </span>
          </div>
        )}

        {editing && !detail && <Loading />}

        <Field
          kind="select"
          name="role"
          label={t('Роль')}
          value={form.role}
          disabled={editing && (detail?.role === 'student' || !detail)}
          onChange={(value) => isRole(value) && set('role', value)}
          options={ROLES.map((row) => ({ value: row.value, title: t(row.title) }))}
          hint={editing && detail?.role === 'student' ? detail.role_change_note : undefined}
        />
        {roleChanged && detail && (
          <Chip tone="warn" size="sm" className="pform__note">
            {t('Смена роли: {note}', { note: detail.role_change_note })}
          </Chip>
        )}

        {student ? (
          <>
            <Field.Row>
              <Field kind="text" name="last_name" label={t('Фамилия')} value={form.last_name} onChange={(v) => set('last_name', v)} required autoFocus={!editing} />
              <Field kind="text" name="first_name" label={t('Имя')} value={form.first_name} onChange={(v) => set('first_name', v)} required />
              <Field kind="text" name="middle_name" label={t('Отчество')} value={form.middle_name} onChange={(v) => set('middle_name', v)} />
            </Field.Row>
            <Field
              kind="select"
              name="group"
              label={t('Учебная группа')}
              value={form.group}
              required
              placeholder={t('выберите группу')}
              onChange={(v) => set('group', v)}
              options={groupRows.map((row) => ({ value: String(row.id), title: `${row.code} · ${row.parallel}` }))}
              hint={
                chosenGroup
                  ? t('Параллель {parallel}; год выпуска считается от группы', { parallel: chosenGroup.parallel })
                  : t('Параллель и год выпуска — от группы; группы заводят на вкладке «Учебные группы»')
              }
            />
            <Field
              kind="text"
              name="email"
              label={t('Школьная почта')}
              value={form.email}
              onChange={(v) => set('email', v)}
              placeholder="imya_familiya@bhs.kz"
              hint={
                editing && detail?.login
                  ? t('Нет почты — вход по логину {login}', { login: detail.login })
                  : form.email.trim()
                    ? undefined
                    : t('Нет почты — вход по логину «имя.фамилия», он выдастся сам')
              }
            />
            <Field.Row>
              <Field
                kind="text"
                name="personal_email"
                label={t('Личная почта')}
                value={form.personal_email}
                onChange={(v) => set('personal_email', v)}
                hint={
                  detail?.personal_email && detail.personal_email === form.personal_email.trim()
                    ? detail.personal_email_confirmed
                      ? t('подтверждена')
                      : t('не подтверждена — ждём письма')
                    : t('заработает после письма с подтверждением ученику')
                }
              />
              <Field kind="text" name="phone" label={t('Телефон')} value={form.phone} onChange={(v) => set('phone', v)} placeholder="+7 701 000 00 00" />
            </Field.Row>
          </>
        ) : (
          <>
            <Field kind="text" name="full_name" label={t('Фамилия и имя')} value={form.full_name} onChange={(v) => set('full_name', v)} required autoFocus={!editing} />
            <Field.Row>
              <Field
                kind="text"
                name="handle"
                label={t('Почта или логин')}
                value={form.handle}
                onChange={(v) => set('handle', v)}
                placeholder="imya_familiya@bhs.kz"
                hint={
                  editing && user && form.handle.trim().toLowerCase() !== (user.email ?? user.login ?? '').toLowerCase()
                    ? t('Почта — это логин: после сохранения человек будет входить по новой почте.')
                    : t('Пусто — логин «имя.фамилия» выдастся сам')
                }
              />
              <Field kind="text" name="phone" label={t('Телефон')} value={form.phone} onChange={(v) => set('phone', v)} placeholder="+7 701 000 00 00" />
            </Field.Row>
            <Field
              kind="text"
              name="personal_email"
              label={t('Личная почта')}
              value={form.personal_email}
              onChange={(v) => set('personal_email', v)}
              hint={
                detail?.personal_email && detail.personal_email === form.personal_email.trim()
                  ? detail.personal_email_confirmed
                    ? t('подтверждена')
                    : t('не подтверждена — ждём письма')
                  : t('заработает после письма с подтверждением')
              }
            />
          </>
        )}

        {form.role === 'teacher' && (
          <>
            <span className="t-caps">{t('Предметы')}</span>
            {/* выбранные — чипами со снятием, добавление — списком: рамка с галочками
                на двадцать предметов не читалась (решение владельца, 09.10.2026) */}
            <div className="tdrawer__chips">
              {form.subjects.length === 0 && <span className="t-note">{t('предметы не назначены')}</span>}
              {subjects
                .filter((s) => form.subjects.includes(s.id))
                .map((s) => (
                  <Button key={s.id} variant="secondary" size="sm" aria-label={t('Снять предмет {subject}', { subject: s.title })} onClick={() => set('subjects', form.subjects.filter((id) => id !== s.id))}>
                    {s.title} ×
                  </Button>
                ))}
            </div>
            <Field.Row>
              <Field
                kind="select"
                name="add-subject"
                label={t('Добавить предмет')}
                value=""
                placeholder={t('выберите предмет')}
                onChange={(value) => value && set('subjects', [...form.subjects, Number(value)])}
                options={subjects
                  .filter((s) => !form.subjects.includes(s.id))
                  .map((s) => ({ value: String(s.id), title: s.in_lms ? s.title : t('{subject} — только расписание', { subject: s.title }) }))}
              />
              <Field kind="text" name="room" label={t('Кабинет')} value={form.room} onChange={(v) => set('room', v)} placeholder={t('например, 305')} />
            </Field.Row>
            {detail?.teacher && (
              <p className="t-note pform__note">
                {detail.teacher.weekly_hours
                  ? t('Ведёт уроки: {n} в неделю по расписанию', { n: detail.teacher.weekly_hours })
                  : t('Уроков в расписании пока нет — журналы появятся с расписанием')}
              </p>
            )}
          </>
        )}

        {form.role === 'curator' && (
          <>
            <span className="t-caps">{t('Группы')}</span>
            <div className="tdrawer__chips">
              {form.groups.length === 0 && <span className="t-note">{t('группы не назначены')}</span>}
              {groupRows
                .filter((row) => form.groups.includes(row.id))
                .map((row) => (
                  <Button key={row.id} variant="secondary" size="sm" aria-label={t('Снять группу {group}', { group: row.code })} onClick={() => set('groups', form.groups.filter((id) => id !== row.id))}>
                    {row.code} ×
                  </Button>
                ))}
            </div>
            <Field
              kind="select"
              name="add-group"
              label={t('Добавить группу')}
              value=""
              placeholder={t('выберите группу')}
              onChange={(value) => value && set('groups', [...form.groups, Number(value)])}
              options={groupRows
                .filter((row) => !form.groups.includes(row.id))
                .map((row) => ({
                  value: String(row.id),
                  title: row.curator_user ? t('{group} — ведёт {name}', { group: row.code, name: row.curator_user.full_name }) : row.code,
                }))}
              hint={
                editing
                  ? t('Добавленная группа — с сегодняшнего дня, снятая закрывается сегодняшним днём; история — на вкладке «Учебные группы»')
                  : t('Назначение действует с сегодняшнего дня; у группы бывает один куратор')
              }
            />
            {detail?.curator && detail.curator.groups.length > 0 && (
              <p className="t-note pform__note">
                {detail.curator.groups.map((g) => t('{group} с {date}', { group: g.code, date: formatDate(g.since) })).join(' · ')}
              </p>
            )}
          </>
        )}

        {form.role.startsWith('director_') && roleRow && (
          <p className="t-note pform__note">{t('Домен по роли: {domain}', { domain: detail?.domain_title || t(roleRow.short) })}</p>
        )}

        {error && <ErrorNote error={error} />}

        {moved ? (
          <>
            <p className="pform__done">{moved}</p>
            <div className="acad__actions">
              <Button size="sm" onClick={() => setMailing(true)}>
                {t('Выслать письмо заново')}
              </Button>
              <Button variant="outline" size="sm" onClick={onClose}>
                {t('Закрыть')}
              </Button>
            </div>
          </>
        ) : (
          <div className="acad__actions">
            <Button size="sm" disabled={!ready || pending || (editing && !detail)} onClick={save}>
              {editing ? t('Сохранить') : t('Завести')}
            </Button>
            <Button variant="outline" size="sm" onClick={onClose}>
              {t('Отмена')}
            </Button>
          </div>
        )}

        {editing && user && <UserMailHistory id={user.id} />}
      </div>
    </Modal>
  )
}
