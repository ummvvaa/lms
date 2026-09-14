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
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
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
import Modal from '../components/Modal'
import DeleteButton from '../components/DeleteButton'
import RowMenu, { RowMenuCheck, RowMenuItem, RowMenuSeparator } from '../components/RowMenu'
import Notice from '../components/Notice'
import { usePhone } from '../phone'
import EditUserDialog from './EditUserDialog'
import HandoutDialog from '../components/HandoutDialog'
import EnrollPanel from '../components/EnrollPanel'
import LoginLocks from '../components/LoginLocks'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '../components/ui/sheet'
import StudyGroups, { Curators } from '../components/StudyGroups'
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
import PhoneFold from '../components/PhoneFold'

/** Тон бейджа состояния: тревожное — то, из-за чего человек не войдёт. */
const STATE_TONE: Record<string, 'warn' | 'mute' | 'ok' | 'risk'> = {
  no_password: 'warn',
  waiting: 'mute',
  expired: 'risk',
  ready: 'ok',
}

/** Роли списка. `short` — короткая форма для строки на телефоне (фаза 75):
 *  «Директор по поступлению» в узкую ячейку не помещается, а обрезать
 *  подпись нельзя; полная форма остаётся в листе выбора. */
const ROLES: { value: Role; title: string; short: string }[] = [
  { value: 'student', title: 'Ученик', short: 'Ученик' },
  { value: 'director_behavior', title: 'Директор школы — профиль и дисциплина', short: 'Профиль и дисциплина' },
  { value: 'director_admission', title: 'Директор по поступлению', short: 'Поступление' },
  { value: 'director_exam', title: 'Академический директор', short: 'Экзамены' },
  { value: 'director_talent', title: 'Директор талантов', short: 'Таланты' },
  { value: 'director_sport', title: 'Директор спорта', short: 'Спорт' },
  { value: 'curator', title: 'Куратор', short: 'Куратор' },
  { value: 'admin', title: 'Администратор', short: 'Администратор' },
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

  // одна строка на виду, подробности с именами переменных и путём
  // к документации — по «подробнее» (фаза 75). Заголовок строки и текст
  // сервера начинаются одними словами — второй раз они не показываются
  const title = t('Отправка писем не настроена')
  const detail = status.data.warning.startsWith(`${title}:`)
    ? status.data.warning.slice(title.length + 1).trim().replace(/^./u, (c) => c.toUpperCase())
    : status.data.warning
  return (
    <Notice tone="warn" className="users__mail" summary={title}>
      <b>{title}</b>
      <p className="muted users__mailtext">{detail}</p>
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
    </Notice>
  )
}

/**
 * Ссылка-приглашение на экране.
 *
 * Показывается только по нажатию и только администратору: до первой
 * установки пароля ссылка равна паролю, и в общем списке ей не место —
 * оттуда она уедет в скриншот и в журнал прокси.
 */
function InviteLinkBox({
  invite,
  onClose,
  /** в строке таблицы — окном поверх экрана (фаза 69): карточка внутри
      ячейки обрезалась краем таблицы и растила строку под собой */
  asModal = false,
}: {
  invite: InviteLink
  onClose?: () => void
  asModal?: boolean
}) {
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

  const body = (
    <>
      <p className="muted users__linktext">{invite.detail}</p>
      <div className="toolbar" style={{ marginBottom: 0 }}>
        <Input className="users__linkfield" readOnly value={invite.link} onFocus={(e) => e.target.select()} />
        <Button size="sm" onClick={copy}>
          {copied ? t('Скопировано') : t('Скопировать')}
        </Button>
      </div>
    </>
  )

  if (asModal)
    return (
      <Modal title={t('Ссылка на установку пароля')} onClose={() => onClose?.()}>
        {body}
      </Modal>
    )

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
      {body}
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
    <Modal title={t('Временный пароль')} onClose={onClose}>
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
    </Modal>
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
  const phone = usePhone()
  const update = useUpdateUser()
  const invite = useInviteUsers()
  const link = useInviteLink()
  const temp = useTempPassword()
  const [shown, setShown] = useState<InviteLink | null>(null)
  const [issued, setIssued] = useState<IssuedPassword | null>(null)
  const [editing, setEditing] = useState(false)

  const setRole = (role: Role) =>
    update.mutate({ id: user.id, role }, { onError: (error) => toast.error(error.message) })
  const setWholeSchool = (on: boolean) =>
    update.mutate({ id: user.id, sees_whole_school: on }, { onError: (error) => toast.error(error.message) })
  const issuePassword = () => temp.mutate(user.id, { onSuccess: setIssued })

  const roleSelect = (
    <SelectField
      className={phone ? 'users__role' : undefined}
      aria-label={t('Роль')}
      value={user.role}
      onChange={(e) => setRole(e.target.value as Role)}
    >
      {ROLES.map((role) => (
        <option key={role.value} value={role.value} data-short={role.short}>
          {role.title}
        </option>
      ))}
    </SelectField>
  )

  const state = (
    <Badge variant={STATE_TONE[user.password_state] ?? 'mute'}>{user.password_state_title}</Badge>
  )

  const menu = (
    <RowMenu>
      {/* на телефоне «Выдать пароль» тоже в меню (фаза 75): строка
          в две линии, и кнопке в ней места нет */}
      {phone && (
        <RowMenuItem onClick={issuePassword} disabled={temp.isPending || !user.is_active}>
          {t('Выдать пароль')}
        </RowMenuItem>
      )}
      {/* правка ФИО и почты (фаза 67): до неё опечатку в имени
          исправить было нечем */}
      <RowMenuItem onClick={() => setEditing(true)}>{t('Изменить')}</RowMenuItem>
      <RowMenuItem onClick={() => link.mutate(user.id, { onSuccess: setShown })} disabled={!user.is_active}>
        {t('Показать ссылку')}
      </RowMenuItem>
      <RowMenuItem
        onClick={() =>
          invite.mutate(
            { emails: [user.email] },
            {
              onSuccess: () => toast.success(t('Ссылка отправлена')),
              onError: (error) => toast.error(error.message),
            },
          )
        }
        disabled={!user.is_active}
      >
        {t('Выслать письмо заново')}
      </RowMenuItem>
      {phone && (
        <RowMenuCheck checked={user.sees_whole_school} onChange={setWholeSchool}>
          {t('Видит всю школу')}
        </RowMenuCheck>
      )}
      <RowMenuSeparator />
      <RowMenuItem
        risk
        onClick={() =>
          update.mutate(
            { id: user.id, is_active: !user.is_active },
            {
              onSuccess: () => toast.success(user.is_active ? t('Доступ отключён') : t('Доступ включён')),
              onError: (error) => toast.error(error.message),
            },
          )
        }
      >
        {user.is_active ? t('Отключить доступ') : t('Включить доступ')}
      </RowMenuItem>
      {user.is_active && (
        <RowMenuItem risk keepOpen>
          <DeleteButton
            model="accounts.User"
            id={user.id}
            path="/users/"
            invalidate={[['users']]}
            inMenu
            onDeleted={(detail) => toast.success(detail)}
          />
        </RowMenuItem>
      )}
    </RowMenu>
  )

  // в ячейке не остаётся ничего (фаза 69): плашки уезжали под
  // соседнюю строку и меняли её высоту. Короткие сообщения уходят
  // тостом внизу экрана, а пароль и ссылку — их надо скопировать —
  // показывает окно поверх таблицы
  const dialogs = (
    <>
      {issued && <PasswordBox issued={issued} onClose={() => setIssued(null)} />}
      {shown && <InviteLinkBox invite={shown} asModal onClose={() => setShown(null)} />}
      {editing && <EditUserDialog user={user} onClose={() => setEditing(false)} />}
    </>
  )

  // Телефон (фаза 75): строка-карточка в две линии — имя и почта, роль
  // и состояние пароля; всё остальное в меню. Двести человек в карточках
  // по шесть строк было не пролистать
  if (phone)
    return (
      <tr className={user.is_active ? undefined : 'users__off'}>
        <td className="users__pick">
          <Checkbox checked={checked} aria-label={t('Отметить строку')} onCheckedChange={onCheck} />
        </td>
        <td className="users__actions">
          {menu}
          {dialogs}
        </td>
        <td data-head="" className="users__line">
          <b className="users__name">{user.full_name || '—'}</b>
          <span className="muted users__email">{user.email}</span>
        </td>
        <td className="users__line users__line--second">
          {roleSelect}
          <span className="users__marks">
            {user.is_probe && <Badge variant="mute">{t('прогон')}</Badge>}
            {state}
          </span>
        </td>
      </tr>
    )

  return (
    <tr className={user.is_active ? undefined : 'users__off'}>
      <td className="users__pick">
        <Checkbox checked={checked} aria-label={t('Отметить строку')} onCheckedChange={onCheck} />
      </td>
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
      <td data-label={t('Роль')}>{roleSelect}</td>
      <td data-label={t('Доступ')}>
        <label className="users__check">
          <Checkbox checked={user.sees_whole_school} onCheckedChange={(on) => setWholeSchool(Boolean(on))} />
          {t('видит всю школу')}
        </label>
      </td>
      <td className="users__state" data-label={t('Пароль')}>
        {/* состояние приходит с сервера (фаза 69): чип, счётчик и строка
            обязаны говорить одно и то же, а склеивать его на экране
            значило бы завести второй источник правды */}
        {state}
      </td>
      <td className="users__actions">
        {/* одно основное действие на виду: остальное — в меню.
            Семь кнопок в строке превращают таблицу в панель приборов */}
        <Button
          variant="outline"
          size="sm"
          onClick={issuePassword}
          disabled={temp.isPending || !user.is_active}
        >
          {t('Выдать пароль')}
        </Button>
        {menu}
        {dialogs}
      </td>
    </tr>
  )
}

export default function Users() {
  // фильтры живут в адресе (фаза 69): в день раздачи паролей человек
  // уходит в карточку и возвращается — набор, по которому он работал,
  // должен вернуться вместе с ним
  const [params, setParams] = useSearchParams()
  const search = params.get('search') ?? ''
  const state = params.get('state') ?? ''
  const roleFilter = params.get('role') ?? ''
  const groupFilter = params.get('group') ?? ''
  const setFilter = (name: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(name, value)
    else next.delete(name)
    setParams(next, { replace: true })
    setPicked([])
  }
  const setSearch = (value: string) => setFilter('search', value)
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
  const [error, setError] = useState<string | null>(null)
  const [showHandout, setShowHandout] = useState(false)

  const [fresh, setFresh] = useState<InviteLink | null>(null)

  // переключатель уезжает на сервер вместе с остальными фильтрами:
  // счётчик чипа обязан сходиться с числом строк под ним, а он считается
  // там же, где выбираются строки (фаза 69)
  const filters = {
    search,
    state,
    role: roleFilter,
    group: groupFilter,
    is_active: showInactive ? '' : 'true',
  }
  const users = useUsers(filters)
  const create = useCreateUser()
  const invite = useInviteUsers()
  const bulkAction = useBulkUsers()

  const emails = bulk
    .split(/[\s,;]+/)
    .map((x) => x.trim())
    .filter((x) => x.includes('@'))

  if (users.isLoading) return <Loading kind="table" />
  if (users.error) return <ErrorNote error={users.error} />

  const page = users.data
  const rows = page?.results ?? []
  const inactive = page?.counts.inactive ?? 0

  const runBulk = (action: BulkUserAction) =>
    bulkAction.mutate(
      { users: picked, action },
      {
        onSuccess: (result) => {
          toast.success(result.detail)
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
            {/* раздача паролей списком (фаза 69): по отмеченным строкам
                или по текущему фильтру — окно говорит, по чему именно */}
            <Button variant="outline" onClick={() => setShowHandout(true)}>
              {t('Выдать пароли')}
            </Button>
            <Button variant="outline" onClick={() => setShowInvite(!showInvite)}>
              {t('Массовое приглашение')}
            </Button>
            <Button onClick={() => setShowCreate(!showCreate)}>{t('Завести пользователя')}</Button>
          </>
        }
      />

      <MailWarning />

      <PhoneFold active={Boolean(search || roleFilter || groupFilter)}>
      <div className="toolbar">
        <Input
          placeholder={t('Поиск по имени или почте')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <SelectField
          aria-label={t('Роль')}
          value={roleFilter}
          onChange={(e) => setFilter('role', e.target.value)}
        >
          <option value="">{t('Все роли')}</option>
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.title}
            </option>
          ))}
        </SelectField>
        <SelectField
          aria-label={t('Группа')}
          value={groupFilter}
          onChange={(e) => setFilter('group', e.target.value)}
        >
          <option value="">{t('Все группы')}</option>
          {(page?.groups ?? []).map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </SelectField>
        <label className="users__check">
          <Switch checked={showInactive} onCheckedChange={setShowInactive} />
          {t('Показать неактивных')} ({inactive})
        </label>
      </div>
      </PhoneFold>

      {/* чипы по состоянию пароля со счётчиками: в день раздачи человек
          работает именно ими — «кому ещё не выдали» и «у кого сгорело» */}
      <div className="users__chips">
        <button
          type="button"
          className={`cchip${state === '' ? ' cchip--on' : ''}`}
          onClick={() => setFilter('state', '')}
        >
          {t('Все')} <b className="num">{page?.counts.all ?? 0}</b>
        </button>
        {(page?.states ?? []).map((mode) => (
          <button
            key={mode.code}
            type="button"
            className={`cchip${state === mode.code ? ' cchip--on' : ''}`}
            onClick={() => setFilter('state', mode.code)}
          >
            {mode.title} <b className="num">{page?.counts[mode.code] ?? 0}</b>
          </button>
        ))}
      </div>

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
                  toast.success(`${t('Заведён')} ${email}`)
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
                      toast.success(
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
            <EnrollPanel onDone={(text) => toast.success(text)} onIssued={setIssued} />
          </div>
        </SheetContent>
      </Sheet>

      {issued.length > 0 && <CredentialsBox rows={issued} onClose={() => setIssued([])} />}

      {showHandout && (
        <HandoutDialog filters={filters} picked={picked} onClose={() => setShowHandout(false)} />
      )}

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
              {/* состояние пароля — числом, а не долей: у таблицы
                  `table-layout: fixed`, и самая длинная подпись «Ждёт смены
                  пароля» на доле в 14 % обрезалась многоточием (фаза 69) */}
              <col style={{ width: '176px' }} />
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
      <Curators />

      {/* кто заперт после неудачных попыток входа и кнопка снять (фаза 36) */}
      <LoginLocks />
    </div>
  )
}
