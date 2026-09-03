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
  useBulkUsers,
  useCreateUser,
  useInviteLink,
  useInviteUsers,
  useMailStatus,
  useSendTestMail,
  useTempPassword,
  useUpdateUser,
  useUsers,
  type BulkUserAction,
  type InviteLink,
  type IssuedPassword,
  type ManagedUser,
} from '../api/hooks'
import CredentialsBox from '../components/CredentialsBox'
import DeleteButton from '../components/DeleteButton'
import RowMenu, { RowMenuItem, RowMenuSeparator } from '../components/RowMenu'
import EnrollPanel from '../components/EnrollPanel'
import LoginLocks from '../components/LoginLocks'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '../components/ui/sheet'
import StudyGroups from '../components/StudyGroups'
import { counted, ErrorNote, Loading, ScreenHead } from '../components/ui'
import type { Role } from '../api/types'
import { t } from '../i18n'
import { SelectField } from '../components/SelectField'
import { Textarea } from '../components/ui/textarea'
import { Input } from '../components/ui/input'
import { Checkbox } from '../components/ui/checkbox'
import { Switch } from '../components/ui/switch'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'

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
        <Button
          variant="outline"
          size="sm"
          disabled={test.isPending}
          onClick={() =>
            test.mutate(status.data?.from_email ?? '', {
              onSuccess: (answer) => setNote(answer.detail),
              onError: () => setNote(t('Пробное письмо отправить не удалось')),
            })
          }
        >
          {t('Отправить пробное письмо')}
        </Button>
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
  if (!invite.link)
    return (
      <Badge variant="warn" className="badge--line">
        {invite.detail}
      </Badge>
    )

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
          <Button variant="outline" size="sm" onClick={onClose}>
            {t('Скрыть')}
          </Button>
        )}
      </div>
      <p className="muted users__linktext">{invite.detail}</p>
      <div className="toolbar" style={{ marginBottom: 0 }}>
        <Input className="users__linkfield" readOnly value={invite.link} onFocus={(e) => e.target.select()} />
        <Button size="sm" onClick={copy}>
          {copied ? t('Скопировано') : t('Скопировать')}
        </Button>
      </div>
    </div>
  )
}

/**
 * Показанный временный пароль.
 *
 * Открытым текстом он живёт ровно здесь и ровно до перезагрузки: в базе
 * лежит хеш, восстановить пароль нельзя — можно выпустить новый.
 */
function PasswordBox({ issued, onClose }: { issued: IssuedPassword; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="card card-pad users__link">
      <div className="row-between">
        <b>{t('Временный пароль')}</b>
        <Button variant="outline" size="sm" onClick={onClose}>
          {t('Скрыть')}
        </Button>
      </div>
      <p className="muted users__linktext">{issued.detail}</p>
      <div className="toolbar" style={{ marginBottom: 0 }}>
        <Input
          className="users__linkfield"
          readOnly
          value={issued.password}
          onFocus={(e) => e.target.select()}
        />
        <Button
          size="sm"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(issued.password)
              setCopied(true)
            } catch {
              setCopied(false)
            }
          }}
        >
          {copied ? t('Скопировано') : t('Скопировать')}
        </Button>
      </div>
    </div>
  )
}

function UserRow({
  user,
  checked,
  onCheck,
}: {
  user: ManagedUser
  checked: boolean
  onCheck: (on: boolean) => void
}) {
  const update = useUpdateUser()
  const invite = useInviteUsers()
  const link = useInviteLink()
  const temp = useTempPassword()
  const [note, setNote] = useState<string | null>(null)
  const [shown, setShown] = useState<InviteLink | null>(null)
  const [issued, setIssued] = useState<IssuedPassword | null>(null)

  return (
    <tr className={user.is_active ? undefined : 'users__off'}>
      <td className="users__pick">
        <Checkbox checked={checked} aria-label={t('Отметить строку')} onCheckedChange={onCheck} />
      </td>
      {/* на телефоне строка становится карточкой: имя — её заголовок,
          остальные ячейки идут парами «подпись — значение» (фаза 51) */}
      <td data-head="">
        <b>{user.full_name || '—'}</b>
        {user.is_probe && (
          <>
            {' '}
            <Badge variant="mute">{t('прогон')}</Badge>
          </>
        )}
        <div className="muted" style={{ fontSize: 12.5 }}>
          {user.email}
        </div>
      </td>
      <td data-label={t('Роль')}>
        <SelectField
          value={user.role}
          onChange={(e) => update.mutate({ id: user.id, role: e.target.value as Role })}
        >
          {ROLES.map((role) => (
            <option key={role.value} value={role.value}>
              {role.title}
            </option>
          ))}
        </SelectField>
      </td>
      <td data-label={t('Доступ')}>
        <label className="users__check">
          <Checkbox
            checked={user.sees_whole_school}
            onCheckedChange={(on) => update.mutate({ id: user.id, sees_whole_school: on })}
          />
          {t('видит всю школу')}
        </label>
      </td>
      <td data-label={t('Пароль')}>
        {!user.has_password && <Badge variant="warn">{t('пароль не задан')}</Badge>}
        {user.has_password && user.must_change_password && (
          <Badge variant="mute">{t('ждёт смены пароля')}</Badge>
        )}
        {user.has_password && !user.must_change_password && <Badge variant="ok">{t('готов')}</Badge>}
      </td>
      <td className="users__actions">
        {/* одно основное действие на виду: остальное — в меню.
            Семь кнопок в строке превращают таблицу в панель приборов */}
        <Button
          variant="outline"
          size="sm"
          onClick={() => temp.mutate(user.id, { onSuccess: setIssued })}
          disabled={temp.isPending || !user.is_active}
        >
          {t('Выдать пароль')}
        </Button>

        <RowMenu>
          <RowMenuItem
            onClick={() => link.mutate(user.id, { onSuccess: setShown })}
            disabled={!user.is_active}
          >
            {t('Показать ссылку')}
          </RowMenuItem>
          <RowMenuItem
            onClick={() =>
              invite.mutate({ emails: [user.email] }, { onSuccess: () => setNote('Ссылка отправлена') })
            }
            disabled={!user.is_active}
          >
            {t('Выслать письмо заново')}
          </RowMenuItem>
          <RowMenuSeparator />
          <RowMenuItem risk onClick={() => update.mutate({ id: user.id, is_active: !user.is_active })}>
            {user.is_active ? t('Отключить доступ') : t('Включить доступ')}
          </RowMenuItem>
          {user.is_active && (
            <RowMenuItem risk keepOpen>
              <DeleteButton
                model="accounts.User"
                id={user.id}
                path="/users/"
                invalidate={[['users']]}
                onDeleted={setNote}
              />
            </RowMenuItem>
          )}
        </RowMenu>

        {note && <Badge variant="ok">{note}</Badge>}
        {update.isError && <Badge variant="risk">{t('не вышло')}</Badge>}
        {issued && <PasswordBox issued={issued} onClose={() => setIssued(null)} />}
        {shown && <InviteLinkBox invite={shown} onClose={() => setShown(null)} />}
      </td>
    </tr>
  )
}

export default function Users() {
  const [search, setSearch] = useState('')
  // удалённые и отключённые по умолчанию не показываются: они висели
  // серыми строками и мешали работать с живыми
  const [showInactive, setShowInactive] = useState(false)
  const [picked, setPicked] = useState<number[]>([])
  const [issued, setIssued] = useState<{ full_name: string; email: string; password: string }[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [showInvite, setShowInvite] = useState(false)
  const [showEnroll, setShowEnroll] = useState(false)
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
  const bulkAction = useBulkUsers()

  const emails = bulk
    .split(/[\s,;]+/)
    .map((x) => x.trim())
    .filter((x) => x.includes('@'))

  if (users.isLoading) return <Loading kind="table" />
  if (users.error) return <ErrorNote error={users.error} />

  const all = users.data ?? []
  const inactive = all.filter((row) => !row.is_active)
  const rows = showInactive ? all : all.filter((row) => row.is_active)

  const runBulk = (action: BulkUserAction) =>
    bulkAction.mutate(
      { users: picked, action },
      {
        onSuccess: (result) => {
          setNote(result.detail)
          if (result.issued.length) setIssued(result.issued)
          setPicked([])
        },
        onError: (e) => setError(e instanceof Error ? e.message : 'Не получилось'),
      },
    )

  return (
    <div>
      <ScreenHead
        title={t('Пользователи')}
        subtitle={`${counted(rows.length, ['учётная запись', 'учётные записи', 'учётных записей'])}. Пароль человек задаёт себе сам по ссылке.`}
        actions={
          <>
            <Button variant="outline" onClick={() => setShowEnroll(!showEnroll)}>
              {t('Завести учеников списком')}
            </Button>
            <Button variant="outline" onClick={() => setShowInvite(!showInvite)}>
              {t('Массовое приглашение')}
            </Button>
            <Button onClick={() => setShowCreate(!showCreate)}>{t('Завести пользователя')}</Button>
          </>
        }
      />

      <MailWarning />

      <div className="toolbar">
        <Input
          placeholder={t('Поиск по имени или почте')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <label className="users__check">
          <Switch checked={showInactive} onCheckedChange={setShowInactive} />
          {t('Показать неактивных')} ({inactive.length})
        </label>
      </div>

      {note && (
        <Badge variant="ok" className="badge--line">
          {note}
        </Badge>
      )}
      {error && (
        <Badge variant="risk" className="badge--line">
          {error}
        </Badge>
      )}
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
            <Input
              type="email"
              required
              placeholder={t('почта')}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Input placeholder={t('ФИО')} value={fullName} onChange={(e) => setFullName(e.target.value)} />
            <SelectField value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.title}
                </option>
              ))}
            </SelectField>
            <Button size="sm" type="submit" disabled={create.isPending}>
              {t('Завести и пригласить')}
            </Button>
          </div>
          <p className="muted" style={{ fontSize: 12.5, marginBottom: 0 }}>
            {t('Пароль не задаётся здесь: человеку уйдёт ссылка, по которой он придумает свой.')}
          </p>
        </form>
      )}

      {showInvite && (
        <div className="card card-pad users__form">
          <span className="eyebrow">{t('Массовое приглашение')}</span>
          <Textarea
            className="assistant__input"
            rows={6}
            value={bulk}
            onChange={(e) => setBulk(e.target.value)}
            placeholder={'Почты через запятую или с новой строки:\nasel@school.kz\ndamir@school.kz'}
          />
          <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
            <Badge variant="mute" className="num">
              распознано адресов: {emails.length}
            </Badge>
            <SelectField value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.title}
                </option>
              ))}
            </SelectField>
            <span className="toolbar__spacer" />
            <Button
              size="sm"
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
            </Button>
          </div>
        </div>
      )}

      {/* Заведение учеников списком — в выезжающей панели, а не в потоке:
          встроенная форма с предпросмотром файла сжимала список
          пользователей под собой на пол-экрана (то же правило, что
          и для форм создания в фазе 31) */}
      <Sheet open={showEnroll} onOpenChange={setShowEnroll}>
        <SheetContent className="users__sheet sm:max-w-[720px]">
          <SheetHeader>
            <SheetTitle>{t('Завести учеников списком')}</SheetTitle>
          </SheetHeader>
          <div className="users__sheetbody">
            <EnrollPanel onDone={(text) => setNote(text)} onIssued={setIssued} />
          </div>
        </SheetContent>
      </Sheet>

      {issued.length > 0 && <CredentialsBox rows={issued} onClose={() => setIssued([])} />}

      {picked.length > 0 && (
        <div className="card card-pad users__bulk">
          <b>
            {t('Отмечено:')} {picked.length}
          </b>
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <Button
              variant="outline"
              size="sm"
              disabled={bulkAction.isPending}
              onClick={() => runBulk('invite')}
            >
              {t('Выслать письма')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={bulkAction.isPending}
              onClick={() => runBulk('temp_password')}
            >
              {t('Выпустить новые пароли')}
            </Button>
            <span className="toolbar__spacer" />
            <Button
              variant="outline"
              size="sm"
              className="users__danger"
              disabled={bulkAction.isPending}
              onClick={() => runBulk('deactivate')}
            >
              {t('Отключить доступ')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setPicked([])}>
              {t('Снять отметки')}
            </Button>
          </div>
        </div>
      )}

      {/* таблица прокручивается внутри своей карточки: на планшете она
          шире экрана, и без этого вбок уезжала вся страница */}
      <div className="card card-pad">
        <div className="tblwrap">
          <table className="tbl users__table">
            <colgroup>
              <col style={{ width: '44px' }} />
              <col style={{ width: '30%' }} />
              <col style={{ width: '18%' }} />
              <col style={{ width: '12%' }} />
              <col style={{ width: '14%' }} />
              <col style={{ width: '160px' }} />
            </colgroup>
            <thead>
              <tr>
                <th className="users__pick">
                  <Checkbox
                    aria-label={t('Отметить все строки')}
                    checked={picked.length > 0 && picked.length === rows.length}
                    onCheckedChange={(on) => setPicked(on ? rows.map((row) => row.id) : [])}
                  />
                </th>
                <th>{t('Человек')}</th>
                <th>{t('Роль')}</th>
                <th>{t('Доступ')}</th>
                <th>{t('Пароль')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((user) => (
                <UserRow
                  key={user.id}
                  user={user}
                  checked={picked.includes(user.id)}
                  onCheck={(on) =>
                    setPicked((current) =>
                      on ? [...current, user.id] : current.filter((id) => id !== user.id),
                    )
                  }
                />
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && <p className="muted">{t('Никого не нашлось.')}</p>}
      </div>

      <StudyGroups />

      {/* кто заперт после неудачных попыток входа и кнопка снять (фаза 36) */}
      <LoginLocks />
    </div>
  )
}
