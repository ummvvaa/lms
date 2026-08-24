/**
 * Управление учётными записями. Только роль `admin`.
 *
 * Пароля здесь нет нигде: человек ставит его себе сам по ссылке-приглашению,
 * администратор его не знает и не может подсмотреть.
 *
 * «Удалить» отключает доступ и кладёт запись в архив: физически удалять
 * пользователя нельзя — на нём висит журнал правок (инвариант №13).
 */
import { useState } from 'react'
import {
  useCreateUser,
  useInviteLink,
  useInviteUsers,
  useMailStatus,
  useSendTestMail,
  useUpdateUser,
  useUsers,
  type InviteLink,
  type ManagedUser,
} from '../api/hooks'
import DeleteButton from '../components/DeleteButton'
import StudyGroups from '../components/StudyGroups'
import { counted, ErrorNote, Loading, ScreenHead } from '../components/ui'
import type { Role } from '../api/types'
import { t } from '../i18n'

const ROLES: { value: Role; title: string }[] = [
  { value: 'student', title: 'Ученик' },
  { value: 'director_behavior', title: 'Директор школы — профиль и дисциплина' },
  { value: 'director_admission', title: 'Директор по поступлению' },
  { value: 'director_exam', title: 'Академический директор' },
  { value: 'director_talent', title: 'Директор талантов' },
  { value: 'director_sport', title: 'Директор спорта' },
  { value: 'admin', title: 'Администратор' },
]

/**
 * Предупреждение о неработающей почте.
 *
 * Приглашать людей, не зная, что письма никуда не уходят, — худший
 * из возможных порядков: человек не войдёт, а администратор узнает
 * об этом от него же, через день.
 */
function MailWarning() {
  const status = useMailStatus()
  const test = useSendTestMail()
  const [note, setNote] = useState<string | null>(null)
  if (!status.data?.warning) return null

  return (
    <div className="card card-pad users__mail">
      <b>{t('Письма не уходят')}</b>
      <p className="muted users__mailtext">{status.data.warning}</p>
      <div className="toolbar" style={{ marginBottom: 0 }}>
        <button
          className="btn btn-ghost btn-sm"
          disabled={test.isPending}
          onClick={() =>
            test.mutate(status.data?.from_email ?? '', {
              onSuccess: (answer) => setNote(answer.detail),
              onError: () => setNote(t('Пробное письмо отправить не удалось')),
            })
          }
        >
          {t('Отправить пробное письмо')}
        </button>
        {note && <span className="muted">{note}</span>}
      </div>
    </div>
  )
}

/**
 * Ссылка-приглашение на экране.
 *
 * Показывается только по нажатию и только администратору: до первой
 * установки пароля ссылка равна паролю, и в общем списке ей не место —
 * оттуда она уедет в скриншот и в журнал прокси.
 */
function InviteLinkBox({ invite, onClose }: { invite: InviteLink; onClose?: () => void }) {
  const [copied, setCopied] = useState(false)
  if (!invite.link) return <p className="chip chip-warn">{invite.detail}</p>

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(invite.link)
      setCopied(true)
    } catch {
      // буфер может быть закрыт настройками браузера — ссылка и так видна
      setCopied(false)
    }
  }

  return (
    <div className="card card-pad users__link">
      <div className="row-between">
        <b>{t('Ссылка на установку пароля')}</b>
        {onClose && (
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            {t('Скрыть')}
          </button>
        )}
      </div>
      <p className="muted users__linktext">{invite.detail}</p>
      <div className="toolbar" style={{ marginBottom: 0 }}>
        <input
          className="input users__linkfield"
          readOnly
          value={invite.link}
          onFocus={(e) => e.target.select()}
        />
        <button className="btn btn-primary btn-sm" onClick={copy}>
          {copied ? t('Скопировано') : t('Скопировать')}
        </button>
      </div>
    </div>
  )
}

function UserRow({ user }: { user: ManagedUser }) {
  const update = useUpdateUser()
  const invite = useInviteUsers()
  const link = useInviteLink()
  const [note, setNote] = useState<string | null>(null)
  const [shown, setShown] = useState<InviteLink | null>(null)

  return (
    <tr className={user.is_active ? undefined : 'users__off'}>
      <td>
        <b>{user.full_name || '—'}</b>
        <div className="muted" style={{ fontSize: 12.5 }}>
          {user.email}
        </div>
      </td>
      <td>
        <select
          className="input"
          value={user.role}
          onChange={(e) => update.mutate({ id: user.id, role: e.target.value as Role })}
        >
          {ROLES.map((role) => (
            <option key={role.value} value={role.value}>
              {role.title}
            </option>
          ))}
        </select>
      </td>
      <td>
        <label className="users__check">
          <input
            type="checkbox"
            checked={user.sees_whole_school}
            onChange={(e) => update.mutate({ id: user.id, sees_whole_school: e.target.checked })}
          />
          {t('видит всю школу')}
        </label>
      </td>
      <td>
        {!user.has_password && <span className="chip chip-warn">{t('пароль не задан')}</span>}
        {user.has_password && user.must_change_password && (
          <span className="chip chip-mute">{t('ждёт смены пароля')}</span>
        )}
        {user.has_password && !user.must_change_password && (
          <span className="chip chip-ok">{t('готов')}</span>
        )}
      </td>
      <td className="users__actions">
        <button
          className="btn btn-ghost btn-sm"
          onClick={() =>
            invite.mutate({ emails: [user.email] }, { onSuccess: () => setNote('Ссылка отправлена') })
          }
          disabled={invite.isPending || !user.is_active}
        >
          {t('Выслать ссылку')}
        </button>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => link.mutate(user.id, { onSuccess: setShown })}
          disabled={link.isPending || !user.is_active}
          title={t('Показать ссылку, чтобы передать её лично')}
        >
          {t('Показать ссылку')}
        </button>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => update.mutate({ id: user.id, is_active: !user.is_active })}
          disabled={update.isPending}
        >
          {user.is_active ? 'Отключить' : 'Включить'}
        </button>
        {user.is_active && (
          <DeleteButton
            model="accounts.User"
            id={user.id}
            path="/users/"
            invalidate={[['users']]}
            onDeleted={setNote}
          />
        )}
        {note && <span className="chip chip-ok">{note}</span>}
        {update.isError && <span className="chip chip-risk">{t('не вышло')}</span>}
        {shown && <InviteLinkBox invite={shown} onClose={() => setShown(null)} />}
      </td>
    </tr>
  )
}

export default function Users() {
  const [search, setSearch] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [showInvite, setShowInvite] = useState(false)
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [role, setRole] = useState<Role>('student')
  const [bulk, setBulk] = useState('')
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [fresh, setFresh] = useState<InviteLink | null>(null)

  const users = useUsers(search)
  const create = useCreateUser()
  const invite = useInviteUsers()

  const emails = bulk
    .split(/[\s,;]+/)
    .map((x) => x.trim())
    .filter((x) => x.includes('@'))

  if (users.isLoading) return <Loading />
  if (users.error) return <ErrorNote error={users.error} />

  const rows = users.data ?? []

  return (
    <div>
      <ScreenHead
        title={t('Пользователи')}
        subtitle={`${counted(rows.length, ['учётная запись', 'учётные записи', 'учётных записей'])}. Пароль человек задаёт себе сам по ссылке.`}
      />

      <MailWarning />

      <div className="toolbar">
        <input
          className="input"
          placeholder={t('Поиск по имени или почте')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span className="toolbar__spacer" />
        <button className="btn btn-ghost btn-sm" onClick={() => setShowInvite(!showInvite)}>
          {t('Массовое приглашение')}
        </button>
        <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(!showCreate)}>
          {t('Завести пользователя')}
        </button>
      </div>

      {note && <p className="chip chip-ok">{note}</p>}
      {error && <p className="chip chip-risk">{error}</p>}
      {fresh && <InviteLinkBox invite={fresh} onClose={() => setFresh(null)} />}

      {showCreate && (
        <form
          className="card card-pad users__form"
          onSubmit={(e) => {
            e.preventDefault()
            setError(null)
            create.mutate(
              { email, full_name: fullName, role },
              {
                onSuccess: (created) => {
                  setNote(`Заведён ${email}`)
                  // ссылку показываем сразу: письмо могло уйти в журнал,
                  // и без неё человеку нечем задать себе пароль
                  setFresh(created.invite ?? null)
                  setEmail('')
                  setFullName('')
                  setShowCreate(false)
                },
                onError: (e) => setError(e instanceof Error ? e.message : 'Не удалось завести'),
              },
            )
          }}
        >
          <span className="eyebrow">{t('Новая учётная запись')}</span>
          <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
            <input
              className="input"
              type="email"
              required
              placeholder={t('почта')}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <input
              className="input"
              placeholder={t('ФИО')}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
            <select className="input" value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.title}
                </option>
              ))}
            </select>
            <button className="btn btn-primary btn-sm" type="submit" disabled={create.isPending}>
              {t('Завести и пригласить')}
            </button>
          </div>
          <p className="muted" style={{ fontSize: 12.5, marginBottom: 0 }}>
            {t('Пароль не задаётся здесь: человеку уйдёт ссылка, по которой он придумает свой.')}
          </p>
        </form>
      )}

      {showInvite && (
        <div className="card card-pad users__form">
          <span className="eyebrow">{t('Массовое приглашение')}</span>
          <textarea
            className="assistant__input"
            rows={6}
            value={bulk}
            onChange={(e) => setBulk(e.target.value)}
            placeholder={'Почты через запятую или с новой строки:\nasel@school.kz\ndamir@school.kz'}
          />
          <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
            <span className="chip chip-mute num">распознано адресов: {emails.length}</span>
            <select className="input" value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.title}
                </option>
              ))}
            </select>
            <span className="toolbar__spacer" />
            <button
              className="btn btn-primary btn-sm"
              disabled={emails.length === 0 || invite.isPending}
              onClick={() =>
                invite.mutate(
                  { emails, role },
                  {
                    onSuccess: (result) => {
                      setNote(
                        `Заведено новых: ${result.created}, ссылок отправлено: ${result.invited}` +
                          (result.skipped.length ? `, пропущено: ${result.skipped.length}` : ''),
                      )
                      setBulk('')
                      setShowInvite(false)
                    },
                    onError: (e) => setError(e instanceof Error ? e.message : 'Не удалось пригласить'),
                  },
                )
              }
            >
              {t('Разослать приглашения')}
            </button>
          </div>
        </div>
      )}

      {/* таблица прокручивается внутри своей карточки: на планшете она
          шире экрана, и без этого вбок уезжала вся страница */}
      <div className="card card-pad users__wrap">
        <table className="history users__table">
          <thead>
            <tr>
              <th>{t('Человек')}</th>
              <th>{t('Роль')}</th>
              <th>{t('Доступ')}</th>
              <th>{t('Пароль')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((user) => (
              <UserRow key={user.id} user={user} />
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="muted">{t('Никого не нашлось.')}</p>}
      </div>

      <StudyGroups />
    </div>
  )
}
