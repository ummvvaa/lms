/**
 * Управление учётными записями. Только роль `admin`.
 *
 * Главный экран дня раздачи паролей: слева фильтры, состояния паролей
 * сегментами со счётчиками и таблица людей; справа — группы, кураторы
 * и блокировки входа. Пароля здесь нет нигде: человек ставит его себе
 * сам по ссылке-приглашению, администратор его не знает и не может
 * подсмотреть; выданный временный пароль показывается один раз.
 *
 * «Удалить» отключает доступ и кладёт запись в архив: физически удалять
 * пользователя нельзя — на нём висит журнал правок (инвариант №13).
 * Роль «Учитель» заводится и фильтруется здесь же, как остальные роли;
 * предметы и кабинет учителя — на экране «Учителя».
 */
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  useBulkUsers,
  useCreateUser,
  useInviteLink,
  useInviteUsers,
  useTempPassword,
  useUpdateUser,
  useUsers,
  type BulkUserAction,
  type InviteLink,
  type IssuedPassword,
  type ManagedUser,
} from '../api/hooks'
import CredentialsBox, { type Credential } from '../components/CredentialsBox'
import DataTable, { type Column } from '../components/DataTable'
import DeleteButton from '../components/DeleteButton'
import EditDrawer from '../components/EditDrawer'
import EnrollPanel from '../components/EnrollPanel'
import { ExportPreview } from '../components/ExportPreview'
import Field from '../components/Field'
import HandoutDialog from '../components/HandoutDialog'
import LoginLocks from '../components/LoginLocks'
import Modal from '../components/Modal'
import { Segmented } from '../components/patterns'
import PhoneFold from '../components/PhoneFold'
import RowMenu, { RowMenuItem, RowMenuSeparator } from '../components/RowMenu'
import { SelectField } from '../components/SelectField'
import StudyGroups, { Curators } from '../components/StudyGroups'
import { Chip, counted, DataCard, ErrorNote, Loading, ScreenHead, ScreenTabs, type Tone } from '../components/ui'
import { Button } from '../components/ui/button'
import { Checkbox } from '../components/ui/checkbox'
import { Input } from '../components/ui/input'
import type { Role } from '../api/types'
import { t } from '../i18n'
import { PARALLELS } from '../lib/parallels'
import { usePhone } from '../phone'
import EditUserDialog from './EditUserDialog'
import './academics/academics.css'

/** Тон чипа состояния: тревожное — то, из-за чего человек не войдёт. */
const STATE_TONE: Record<string, Tone> = {
  no_password: 'warn',
  waiting: 'neutral',
  expired: 'bad',
  ready: 'good',
}

/** Роли списка. `short` — короткая форма для строки на телефоне:
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
  { value: 'teacher', title: 'Учитель', short: 'Учитель' },
  { value: 'admin', title: 'Администратор', short: 'Администратор' },
]

/** Параллели в фильтре: только учеников — у сотрудника параллели нет. */
const PARALLEL_FILTER = [{ value: '', title: t('Все параллели') }, ...PARALLELS.map((value) => ({ value: String(value), title: String(value) }))]

/**
 * Ссылка-приглашение окном поверх экрана.
 *
 * Показывается только по нажатию и только администратору: до первой
 * установки пароля ссылка равна паролю, и в общем списке ей не место —
 * оттуда она уедет в скриншот и в журнал прокси.
 */
function InviteLinkBox({ invite, onClose }: { invite: InviteLink; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
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
    <Modal title={t('Ссылка на установку пароля')} onClose={onClose}>
      {!invite.link && (
        <Chip tone="warn" size="sm">
          {invite.detail}
        </Chip>
      )}
      {invite.link && (
        <>
          <p className="t-note">{invite.detail}</p>
          <div className="acad__actions">
            <Input className="users__linkfield" readOnly value={invite.link} onFocus={(e) => e.target.select()} />
            <Button size="sm" onClick={copy}>
              {copied ? t('Скопировано') : t('Скопировать')}
            </Button>
          </div>
        </>
      )}
    </Modal>
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
      <p className="t-note">{issued.detail}</p>
      <div className="acad__actions">
        <Input className="users__linkfield" readOnly value={issued.password} onFocus={(e) => e.target.select()} />
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

/** Роль — списком в клетке; на телефоне короткая форма. */
function RolePick({ user }: { user: ManagedUser }) {
  const phone = usePhone()
  const update = useUpdateUser()
  return (
    <SelectField
      className={phone ? 'users__role' : undefined}
      aria-label={`${t('Роль')}: ${user.full_name || user.email}`}
      value={user.role}
      onChange={(e) => update.mutate({ id: user.id, role: e.target.value as Role }, { onError: (error) => toast.error(error.message) })}
    >
      {ROLES.map((role) => (
        <option key={role.value} value={role.value} data-short={role.short}>
          {role.title}
        </option>
      ))}
    </SelectField>
  )
}

/** Одно основное действие на виду, остальное — в меню строки. */
function UserActions({ user }: { user: ManagedUser }) {
  const update = useUpdateUser()
  const invite = useInviteUsers()
  const link = useInviteLink()
  const temp = useTempPassword()
  const [shown, setShown] = useState<InviteLink | null>(null)
  const [issued, setIssued] = useState<IssuedPassword | null>(null)
  const [editing, setEditing] = useState(false)
  const fail = (error: Error) => toast.error(error.message)
  return (
    <span className="acad__inline">
      <Button variant="secondary" size="sm" disabled={temp.isPending || !user.is_active} onClick={() => temp.mutate(user.id, { onSuccess: setIssued, onError: fail })}>
        {t('Выдать пароль')}
      </Button>
      <RowMenu>
        <RowMenuItem onClick={() => setEditing(true)}>{t('Изменить')}</RowMenuItem>
        <RowMenuItem onClick={() => link.mutate(user.id, { onSuccess: setShown, onError: fail })} disabled={!user.is_active}>
          {t('Показать ссылку')}
        </RowMenuItem>
        {/* письмо — только тем, у кого есть почта; у 8–10 ссылку показывают на экране */}
        {user.email && (
          <RowMenuItem onClick={() => invite.mutate({ emails: [user.email ?? ''] }, { onSuccess: () => toast.success(t('Ссылка отправлена')), onError: fail })} disabled={!user.is_active}>
            {t('Выслать письмо заново')}
          </RowMenuItem>
        )}
        <RowMenuItem onClick={() => update.mutate({ id: user.id, sees_whole_school: !user.sees_whole_school }, { onError: fail })}>
          {user.sees_whole_school ? t('Не видит всю школу') : t('Видит всю школу')}
        </RowMenuItem>
        <RowMenuSeparator />
        <RowMenuItem
          risk
          onClick={() =>
            update.mutate(
              { id: user.id, is_active: !user.is_active },
              { onSuccess: () => toast.success(user.is_active ? t('Доступ отключён') : t('Доступ включён')), onError: fail },
            )
          }
        >
          {user.is_active ? t('Отключить доступ') : t('Включить доступ')}
        </RowMenuItem>
        {user.is_active && (
          <RowMenuItem risk keepOpen>
            <DeleteButton model="accounts.User" id={user.id} path="/users/" invalidate={[['users']]} inMenu onDeleted={(detail) => toast.success(detail)} />
          </RowMenuItem>
        )}
      </RowMenu>
      {issued && <PasswordBox issued={issued} onClose={() => setIssued(null)} />}
      {shown && <InviteLinkBox invite={shown} onClose={() => setShown(null)} />}
      {editing && <EditUserDialog user={user} onClose={() => setEditing(false)} />}
    </span>
  )
}

export default function Users() {
  // фильтры живут в адресе: в день раздачи паролей человек уходит
  // в карточку и возвращается — набор, по которому он работал,
  // должен вернуться вместе с ним
  const [params, setParams] = useSearchParams()
  const search = params.get('search') ?? ''
  const state = params.get('state') ?? ''
  const roleFilter = params.get('role') ?? ''
  const groupFilter = params.get('group') ?? ''
  const parallelFilter = params.get('parallel') ?? ''
  // учебные группы — своей вкладкой, не колонкой справа (решение владельца, 27.09.2026)
  const tab: 'accounts' | 'groups' = params.get('tab') === 'groups' ? 'groups' : 'accounts'
  const setFilter = (name: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(name, value)
    else next.delete(name)
    setParams(next, { replace: true })
    setPicked([])
  }
  // удалённые и отключённые по умолчанию не показываются: они висели
  // серыми строками и мешали работать с живыми
  const [showInactive, setShowInactive] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [picked, setPicked] = useState<number[]>([])
  const [issued, setIssued] = useState<Credential[]>([])
  const [panel, setPanel] = useState<'create' | 'invite' | 'enroll' | null>(null)
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [role, setRole] = useState<Role>('student')
  const [bulk, setBulk] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [showHandout, setShowHandout] = useState(false)
  const [fresh, setFresh] = useState<InviteLink | null>(null)

  // переключатель уезжает на сервер вместе с остальными фильтрами:
  // счётчик сегмента обязан сходиться с числом строк под ним, а он
  // считается там же, где выбираются строки
  const filters = {
    search,
    state,
    role: roleFilter,
    group: groupFilter,
    parallel: parallelFilter,
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
        onError: (e) => setError(e instanceof Error ? e.message : t('Не получилось')),
      },
    )

  const columns: Column<ManagedUser>[] = [
    {
      key: 'pick',
      title: '',
      width: '5%',
      cell: (user) => (
        <Checkbox
          checked={picked.includes(user.id)}
          aria-label={`${t('Отметить строку')}: ${user.full_name || user.email}`}
          onCheckedChange={(on) => setPicked((current) => (on ? [...current, user.id] : current.filter((id) => id !== user.id)))}
        />
      ),
    },
    {
      key: 'person',
      title: t('Человек'),
      width: '30%',
      cell: (user) => (
        <>
          <b>{user.full_name || t('без имени')}</b>
          {user.is_probe && (
            <Chip size="sm">
              {t('прогон')}
            </Chip>
          )}
          <span className="t-note"> · {user.email || user.login}</span>
          {!user.is_active && (
            <Chip size="sm">
              {t('доступ отключён')}
            </Chip>
          )}
        </>
      ),
      sortBy: (user) => (user.full_name || user.email || user.login || '').toLowerCase(),
    },
    { key: 'role', title: t('Роль'), width: '19%', cell: (user) => <RolePick user={user} />, sortBy: (user) => user.role },
    {
      key: 'access',
      title: t('Доступ'),
      width: '10%',
      cell: (user) => (user.sees_whole_school ? <Chip tone="info" size="sm">{t('вся школа')}</Chip> : <span className="t-note">{t('свои')}</span>),
      sortBy: (user) => (user.sees_whole_school ? 0 : 1),
    },
    {
      // состояние приходит с сервера: чип, счётчик и строка обязаны говорить
      // одно и то же, а склеивать его на экране значило бы завести второй источник правды
      key: 'password',
      title: t('Пароль'),
      width: '16%',
      cell: (user) => (
        <Chip tone={STATE_TONE[user.password_state] ?? 'neutral'} size="sm">
          {user.password_state_title}
        </Chip>
      ),
      sortBy: (user) => user.password_state,
    },
    { key: 'acts', title: '', width: '20%', align: 'right', cell: (user) => <UserActions user={user} /> },
  ]

  const closePanel = () => setPanel(null)

  return (
    <div>
      <ScreenHead
        title={t('Пользователи')}
        subtitle={counted(rows.length, ['учётная запись', 'учётные записи', 'учётных записей'])}
        actions={
          <>
            <Button onClick={() => setPanel('create')}>{t('Завести пользователя')}</Button>
            {/* одно главное действие, остальное — в «Ещё» (решение владельца, 27.09.2026):
                ученики списком, раздача паролей по отмеченным или по фильтру,
                массовое приглашение, выгрузка по текущему фильтру */}
            <RowMenu>
              <RowMenuItem onClick={() => setPanel('enroll')}>{t('Завести учеников списком')}</RowMenuItem>
              <RowMenuItem onClick={() => setShowHandout(true)}>{t('Выдать пароли')}</RowMenuItem>
              <RowMenuItem onClick={() => setPanel('invite')}>{t('Массовое приглашение')}</RowMenuItem>
              <RowMenuItem onClick={() => setExporting(true)}>{t('Выгрузить')}</RowMenuItem>
            </RowMenu>
          </>
        }
      />

      <ScreenTabs<'accounts' | 'groups'>
        value={tab}
        onChange={(next) => setFilter('tab', next === 'accounts' ? '' : next)}
        items={[
          { value: 'accounts', label: t('Учётные записи') },
          { value: 'groups', label: t('Учебные группы') },
        ]}
      />

      {tab === 'groups' && (
        <div className="acad__cols acad__cols--even">
          <div className="acad__stack">
            <StudyGroups />
          </div>
          <div className="acad__stack">
            <Curators />
          </div>
        </div>
      )}

      {tab === 'accounts' && (
        <div className="acad__stack">
          <PhoneFold active={Boolean(search || roleFilter || groupFilter || parallelFilter)}>
            <div className="acad__toolbar">
              <Field name="search" label={t('Поиск')} value={search} placeholder={t('Поиск по имени или почте')} onChange={(value) => setFilter('search', value)} />
              <Field kind="select" name="role" label={t('Роль')} value={roleFilter} onChange={(value) => setFilter('role', value)} options={[{ value: '', title: t('Все роли') }, ...ROLES.map((r) => ({ value: r.value, title: r.title }))]} />
              <Field kind="select" name="group" label={t('Группа')} value={groupFilter} onChange={(value) => setFilter('group', value)} options={[{ value: '', title: t('Все группы') }, ...(page?.groups ?? []).map((code) => ({ value: code, title: code }))]} />
              <Field kind="select" name="parallel" label={t('Параллель')} value={parallelFilter} onChange={(value) => setFilter('parallel', value)} options={PARALLEL_FILTER} />
              <Field kind="checkbox" name="inactive" label={`${t('Показать неактивных')} (${inactive})`} checked={showInactive} onChange={setShowInactive} />
            </div>
          </PhoneFold>

          {/* состояния пароля со счётчиками: в день раздачи человек работает
              именно ими — «кому ещё не выдали» и «у кого сгорело» */}
          <div className="acad__toolbar">
            <Segmented<string>
              value={state}
              onChange={(next) => setFilter('state', next)}
              label={t('Состояние пароля')}
              items={[{ value: '', label: `${t('Все')} ${page?.counts.all ?? 0}` }, ...(page?.states ?? []).map((mode) => ({ value: mode.code, label: `${mode.title} ${page?.counts[mode.code] ?? 0}` }))]}
            />
          </div>

          {error && (
            <Chip tone="bad" size="sm">
              {error}
            </Chip>
          )}

          {picked.length > 0 && (
            <DataCard title={`${t('Отмечено:')} ${picked.length}`}>
              <div className="acad__actions">
                <Button variant="outline" size="sm" disabled={bulkAction.isPending} onClick={() => runBulk('invite')}>
                  {t('Выслать письма')}
                </Button>
                <Button variant="outline" size="sm" disabled={bulkAction.isPending} onClick={() => runBulk('temp_password')}>
                  {t('Выпустить новые пароли')}
                </Button>
                <Button variant="outline" size="sm" className="users__danger" disabled={bulkAction.isPending} onClick={() => runBulk('deactivate')}>
                  {t('Отключить доступ')}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setPicked([])}>
                  {t('Снять отметки')}
                </Button>
              </div>
            </DataCard>
          )}

          <DataCard
            title={t('Учётные записи')}
            count={rows.length || undefined}
            empty={rows.length === 0 && t('никого не нашлось — снимите фильтры или заведите пользователя')}
            right={
              rows.length > 0 ? (
                <Button variant="link" size="sm" onClick={() => setPicked(picked.length === rows.length ? [] : rows.map((row) => row.id))}>
                  {picked.length === rows.length ? t('Снять все') : t('Отметить все')}
                </Button>
              ) : undefined
            }
          >
            <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} selected={(row) => picked.includes(row.id)} minWidth="960px" />
          </DataCard>
          {/* кто заперт после неудачных попыток входа и кнопка снять */}
          <LoginLocks />
        </div>
      )}

      <EditDrawer open={panel === 'create'} onClose={closePanel} title={t('Новая учётная запись')} sub={t('Пароль не задаётся здесь: человеку уйдёт ссылка, по которой он придумает свой.')}>
        <form
          className="acad__form"
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
                  closePanel()
                },
                onError: (e) => setError(e instanceof Error ? e.message : t('Не удалось завести')),
              },
            )
          }}
        >
          <Field kind="email" name="email" label={t('Почта')} value={email} required onChange={setEmail} />
          <Field name="full_name" label={t('ФИО')} value={fullName} onChange={setFullName} />
          <Field kind="select" name="role" label={t('Роль')} value={role} onChange={(value) => setRole(value as Role)} options={ROLES.map((r) => ({ value: r.value, title: r.title }))} />
          <div className="acad__actions">
            <Button type="submit" disabled={create.isPending}>
              {t('Завести и пригласить')}
            </Button>
            <Button variant="outline" type="button" onClick={closePanel}>
              {t('Отмена')}
            </Button>
          </div>
        </form>
      </EditDrawer>

      <EditDrawer open={panel === 'invite'} onClose={closePanel} title={t('Массовое приглашение')} sub={`${t('Распознано адресов')}: ${emails.length}`}>
        <div className="acad__form">
          <Field kind="textarea" name="emails" label={t('Почты через запятую или с новой строки')} rows={8} value={bulk} placeholder={'asel@school.kz\ndamir@school.kz'} onChange={setBulk} />
          <Field kind="select" name="invite_role" label={t('Роль')} value={role} onChange={(value) => setRole(value as Role)} options={ROLES.map((r) => ({ value: r.value, title: r.title }))} />
          <div className="acad__actions">
            <Button
              disabled={emails.length === 0 || invite.isPending}
              onClick={() =>
                invite.mutate(
                  { emails, role },
                  {
                    onSuccess: (result) => {
                      toast.success(`${t('Заведено новых')}: ${result.created}, ${t('ссылок отправлено')}: ${result.invited}${result.skipped.length ? `, ${t('пропущено')}: ${result.skipped.length}` : ''}`)
                      setBulk('')
                      closePanel()
                    },
                    onError: (e) => setError(e instanceof Error ? e.message : t('Не удалось пригласить')),
                  },
                )
              }
            >
              {t('Разослать приглашения')}
            </Button>
            <Button variant="outline" onClick={closePanel}>
              {t('Отмена')}
            </Button>
          </div>
        </div>
      </EditDrawer>

      {/* заведение учеников списком — в панели, а не в потоке: встроенная
          форма с предпросмотром файла сжимала список под собой на пол-экрана */}
      <EditDrawer open={panel === 'enroll'} onClose={closePanel} title={t('Завести учеников списком')} className="drawer--wide">
        <EnrollPanel onDone={(text) => toast.success(text)} onIssued={setIssued} />
      </EditDrawer>

      {fresh && <InviteLinkBox invite={fresh} onClose={() => setFresh(null)} />}
      {issued.length > 0 && <CredentialsBox rows={issued} onClose={() => setIssued([])} />}
      {showHandout && <HandoutDialog filters={filters} picked={picked} onClose={() => setShowHandout(false)} />}
      {exporting && (
        <ExportPreview
          path={`/users/export/?${new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== '')).toString()}`}
          fallback="polzovateli.xlsx"
          title={t('Выгрузка пользователей')}
          onClose={() => setExporting(false)}
        />
      )}
    </div>
  )
}
