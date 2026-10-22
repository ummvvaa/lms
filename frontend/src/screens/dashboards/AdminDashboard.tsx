/**
 * Кабинет администратора (фаза 49).
 *
 * Очереди подтверждений здесь нет: ему нечего подтверждать, доменных
 * данных он не ведёт. Вместо неё — «Требует ваших действий» с рабочими
 * кнопками прямо в строках: выслать приглашение, выпустить пароль,
 * снять блокировку входа.
 */
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useBulkUsers, useCabinet, useInviteUsers, useUnlockLogin, type CabinetStat } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import DataTable from '../../components/DataTable'
import { Avatar, LIST_LIMIT, Row, Rows } from '../../components/patterns'
import { usePhone } from '../../phone'
import { Chip, DataCard, EmptyNote, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk, tn } from '../../i18n'
import './cabinet.css'
import { useAcademicsCard } from '../academics/AcademicsBlock'

interface AdminCabinet {
  title: string
  owner: string
  stats: CabinetStat[]
  registry: {
    id: number
    student: string
    parallel: number
    group: string
    email: string
    status: { code: string; title: string }
  }[]
  actions: {
    code: string
    title: string
    note: string
    action: string
    count: number
    emails?: string[]
    users?: number[]
    scope?: string
    value?: string
  }[]
  uploads: {
    id: number
    file_name: string
    domain_code: string
    kind: string
    rows_created: number
    rows_updated: number
    status: string
    created_at: string
  }[]
}

type RegistryRow = AdminCabinet['registry'][number]

/** Сколько учеников реестра на дашборде: таблица кончается вровень с правой колонкой. */
const REGISTRY_ROWS = 14

const STATUS_TONE: Record<string, Tone> = {
  ok: 'good',
  never: 'warn',
  temporary: 'bad',
  no_account: 'neutral',
}

const DOMAIN_TITLE: Record<string, string> = {
  behavior: tk('Профиль и дисциплина'),
  admission: tk('Поступление'),
  exam: tk('Экзамены'),
  talent: tk('Таланты'),
  sport: tk('Спорт'),
}

export default function AdminDashboard() {
  // блок «Учёба»: то же, что у Кымбат — расписание, не отмечено, отчёты
  const academics = useAcademicsCard()
  const navigate = useNavigate()
  const phone = usePhone()
  const { data, isLoading, error, refetch } = useCabinet()
  const schoolIsEmpty = useSchoolIsEmpty()
  const invite = useInviteUsers()
  const bulk = useBulkUsers()
  const unlock = useUnlockLogin()

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Администрирование')}
        hint={t('Здесь появится реестр школы')}
        what={t('Кто учится, в какой группе и с какой почтой.')}
        detail={t('Заведите группы и учеников списком.')}
        guide
      />
    )

  const cabinet = data as unknown as AdminCabinet

  const run = (row: AdminCabinet['actions'][number]) => {
    if (row.code === 'invite' && row.emails)
      invite.mutate(
        { emails: row.emails, role: 'student' },
        {
          onSuccess: (result) => {
            toast.success(t('Приглашений отправлено: {n}', { n: result.invited }))
            void refetch()
          },
          onError: (problem) => toast.error(problem.message),
        },
      )
    if (row.code === 'password' && row.users)
      bulk.mutate(
        { users: row.users, action: 'temp_password' },
        {
          onSuccess: (result) => {
            toast.success(result.detail)
            void refetch()
          },
          onError: (problem) => toast.error(problem.message),
        },
      )
    if (row.code === 'lock' && row.value)
      unlock.mutate(
        { scope: (row.scope as 'account' | 'address') ?? 'address', value: row.value },
        {
          onSuccess: (result) => {
            toast.success(result.detail)
            void refetch()
          },
          onError: (problem) => toast.error(problem.message),
        },
      )
  }

  // показатель ведёт туда, где с ним работают; состояние — чипом под числом
  const STAT_LINK: Record<string, string> = {
    students: '/table',
    never: '/users?never_logged_in=true',
    spend: '/spend',
    locks: '/users',
  }
  const statChip = (stat: AdminCabinet['stats'][number]): { label: string; tone: Tone } | undefined => {
    const value = Number(stat.value ?? 0)
    if (stat.code === 'never') return value > 0 ? { label: t('выдать пароли'), tone: 'warn' } : { label: t('все вошли'), tone: 'good' }
    if (stat.code === 'locks') return value > 0 ? { label: t('снять блокировку'), tone: 'bad' } : { label: t('всё спокойно'), tone: 'good' }
    return undefined
  }

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t(cabinet.title)}
        subtitle={t(cabinet.owner)}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => navigate('/users')}>
              {t('Пользователи')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => navigate('/import')}>
              {t('Импорт файлом')}
            </Button>
            <Button size="sm" onClick={() => navigate('/table')}>
              {t('Завести учеников')}
            </Button>
          </>
        }
      />

      <GettingStarted />
      <div className="lay-4">
        {cabinet.stats.map((stat) => (
          <Kpi
            key={stat.code}
            label={t(stat.label)}
            value={stat.value}
            note={stat.note ? t(stat.note) : undefined}
            chip={statChip(stat)}
            to={STAT_LINK[stat.code]}
          />
        ))}
      </div>

      <div className="lay-main">
        <DataCard
          title={t('Реестр школы')}
          right={
            <Button variant="link" size="sm" onClick={() => navigate('/table')}>
              {t('Открыть таблицу')}
            </Button>
          }
        >
          {cabinet.registry.length === 0 && (
            <EmptyNote what={tk('учеников пока нет')} who={tk('заводит администратор списком')} />
          )}
          {cabinet.registry.length > 0 && (
            <DataTable
              columns={[
                {
                  key: 'student',
                  title: t('Ученик'),
                  width: '32%',
                  phone: 'head',
                  cell: (row: RegistryRow) => (
                    <span className="personcell">
                      <Avatar name={row.student} />
                      <b>{row.student}</b>
                    </span>
                  ),
                  sortBy: (row: RegistryRow) => row.student,
                },
                { key: 'group', title: t('Группа'), width: '18%', cell: (row: RegistryRow) => (row.group ? <span className="cabinet__nowrap">{row.group}</span> : <span className="t-note">{t('без группы')}</span>), sortBy: (row: RegistryRow) => row.group },
                { key: 'email', title: t('Почта'), width: '30%', cell: (row: RegistryRow) => <span className="t-note cabinet__ellipsis" title={row.email}>{row.email}</span> },
                { key: 'status', title: t('Статус'), width: '20%', cell: (row: RegistryRow) => <Chip tone={STATUS_TONE[row.status.code] ?? 'neutral'} size="sm">{t(row.status.title)}</Chip>, sortBy: (row: RegistryRow) => row.status.code },
              ]}
              rows={cabinet.registry.slice(0, phone ? LIST_LIMIT : REGISTRY_ROWS)}
              rowKey={(row) => row.id}
            />
          )}
        </DataCard>

        <div className="lay-stack cabinet__first">
          {/* главная карточка экрана — с бегущим светом по рамке */}
          <DataCard className="card--beam" title={t('Требует ваших действий')} count={cabinet.actions.length}>
            {cabinet.actions.length === 0 && <EmptyNote what={tk('ничего не требует вмешательства')} />}
            {cabinet.actions.map((row, index) => (
              <div key={`${row.code}-${index}`} className="cabinet__row">
                <span className="cabinet__rowtext">
                  <b>{t(row.title)}</b>
                  <span className="muted">{row.note}</span>
                </span>
                <Button size="sm" disabled={invite.isPending || bulk.isPending || unlock.isPending} onClick={() => run(row)}>
                  {t(row.action)}
                </Button>
              </div>
            ))}
          </DataCard>

          {academics?.node}

          <DataCard
            title={t('Последние загрузки')}
            right={
              cabinet.uploads.length > 0 ? (
                <Button variant="link" size="sm" onClick={() => navigate('/import')}>
                  {t('Все')}
                </Button>
              ) : undefined
            }
          >
            {cabinet.uploads.length === 0 && <EmptyNote what={tk('загрузок пока не было')} />}
            <div className="cabinet__oneline">
              <Rows>
                {cabinet.uploads.map((row) => (
                  <Row
                    key={row.id}
                    title={row.file_name || t('Без имени файла')}
                    note={tn(
                      row.rows_created + row.rows_updated,
                      'за домен «{domain}» · {n} строка|за домен «{domain}» · {n} строки|за домен «{domain}» · {n} строк',
                      { domain: t(DOMAIN_TITLE[row.domain_code] ?? row.domain_code) },
                    )}
                    right={
                      <Chip tone={row.status === 'applied' ? 'good' : 'neutral'} size="sm">
                        {row.status === 'applied' ? t('Применена') : t('Отменена')}
                      </Chip>
                    }
                  />
                ))}
              </Rows>
            </div>
          </DataCard>
        </div>
      </div>
    </div>
  )
}
