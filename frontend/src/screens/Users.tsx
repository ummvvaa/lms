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
import { useCreateUser, useInviteUsers, useUpdateUser, useUsers, type ManagedUser } from '../api/hooks'
import DeleteButton from '../components/DeleteButton'
import StudyGroups from '../components/StudyGroups'
import { counted, ErrorNote, Loading, ScreenHead } from '../components/ui'
import type { Role } from '../api/types'

const ROLES: { value: Role; title: string }[] = [
  { value: 'student', title: 'Ученик' },
  { value: 'director_behavior', title: 'Директор школы — профиль и дисциплина' },
  { value: 'director_admission', title: 'Директор по поступлению' },
  { value: 'director_exam', title: 'Академический директор' },
  { value: 'director_talent', title: 'Директор талантов' },
  { value: 'director_sport', title: 'Директор спорта' },
  { value: 'admin', title: 'Администратор' },
]

function UserRow({ user }: { user: ManagedUser }) {
  const update = useUpdateUser()
  const invite = useInviteUsers()
  const [note, setNote] = useState<string | null>(null)

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
          видит всю школу
        </label>
      </td>
      <td>
        {!user.has_password && <span className="chip chip-warn">пароль не задан</span>}
        {user.has_password && user.must_change_password && (
          <span className="chip chip-mute">ждёт смены пароля</span>
        )}
        {user.has_password && !user.must_change_password && <span className="chip chip-ok">готов</span>}
      </td>
      <td className="users__actions">
        <button
          className="btn btn-ghost btn-sm"
          onClick={() =>
            invite.mutate({ emails: [user.email] }, { onSuccess: () => setNote('Ссылка отправлена') })
          }
          disabled={invite.isPending || !user.is_active}
        >
          Выслать ссылку
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
        {update.isError && <span className="chip chip-risk">не вышло</span>}
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
        title="Пользователи"
        subtitle={`${counted(rows.length, ['учётная запись', 'учётные записи', 'учётных записей'])}. Пароль человек задаёт себе сам по ссылке.`}
      />

      <div className="toolbar">
        <input
          className="input"
          placeholder="Поиск по имени или почте"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span className="toolbar__spacer" />
        <button className="btn btn-ghost btn-sm" onClick={() => setShowInvite(!showInvite)}>
          Массовое приглашение
        </button>
        <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(!showCreate)}>
          Завести пользователя
        </button>
      </div>

      {note && <p className="chip chip-ok">{note}</p>}
      {error && <p className="chip chip-risk">{error}</p>}

      {showCreate && (
        <form
          className="card card-pad users__form"
          onSubmit={(e) => {
            e.preventDefault()
            setError(null)
            create.mutate(
              { email, full_name: fullName, role },
              {
                onSuccess: () => {
                  setNote(`Заведён ${email}, ссылка на установку пароля отправлена`)
                  setEmail('')
                  setFullName('')
                  setShowCreate(false)
                },
                onError: (e) => setError(e instanceof Error ? e.message : 'Не удалось завести'),
              },
            )
          }}
        >
          <span className="eyebrow">Новая учётная запись</span>
          <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
            <input
              className="input"
              type="email"
              required
              placeholder="почта"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <input
              className="input"
              placeholder="ФИО"
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
              Завести и пригласить
            </button>
          </div>
          <p className="muted" style={{ fontSize: 12.5, marginBottom: 0 }}>
            Пароль не задаётся здесь: человеку уйдёт ссылка, по которой он придумает свой.
          </p>
        </form>
      )}

      {showInvite && (
        <div className="card card-pad users__form">
          <span className="eyebrow">Массовое приглашение</span>
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
              Разослать приглашения
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
              <th>Человек</th>
              <th>Роль</th>
              <th>Доступ</th>
              <th>Пароль</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((user) => (
              <UserRow key={user.id} user={user} />
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="muted">Никого не нашлось.</p>}
      </div>

      <StudyGroups />
    </div>
  )
}
