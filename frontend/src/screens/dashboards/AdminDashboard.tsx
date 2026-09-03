/**
 * Кабинет администратора (фаза 49).
 *
 * Очереди подтверждений здесь нет: ему нечего подтверждать, доменных
 * данных он не ведёт. Вместо неё — «Требует ваших действий» с рабочими
 * кнопками прямо в строках: выслать приглашение, выпустить пароль,
 * снять блокировку входа.
 */
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useBulkUsers, useCabinet, useInviteUsers, useUnlockLogin } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import { Row, Rows } from '../../components/patterns'
import { DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Badge, type BadgeVariant } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { CabinetColumns, CabinetStats } from './cabinet'

interface AdminCabinet {
  title: string
  owner: string
  stats: Parameters<typeof CabinetStats>[0]['stats']
  registry: {
    id: number
    student: string
    grade: number
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

const STATUS_TONE: Record<string, BadgeVariant> = {
  ok: 'ok',
  never: 'warn',
  temporary: 'risk',
  no_account: 'mute',
}

const DOMAIN_TITLE: Record<string, string> = {
  behavior: 'Профиль и дисциплина',
  admission: 'Поступление',
  exam: 'Экзамены',
  talent: 'Таланты',
  sport: 'Спорт',
}

export default function AdminDashboard() {
  const navigate = useNavigate()
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
        what={t('Кто учится, в каком классе и с какой почтой.')}
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
            toast.success(`${t('Приглашений отправлено')}: ${result.invited}`)
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

  return (
    <div>
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
      <CabinetStats stats={cabinet.stats} />

      <CabinetColumns
        main={
          <DataCard
            title={t('Реестр школы')}
            note={t('Кто учится, где и с какой почтой. Доменные данные ведут директора.')}
            accent="brand"
            right={
              <Button variant="outline" size="sm" onClick={() => navigate('/table')}>
                {t('Открыть таблицу')}
              </Button>
            }
          >
            {cabinet.registry.length === 0 && <p className="muted rows__empty">{t('Учеников пока нет')}</p>}
            {cabinet.registry.length > 0 && (
              <table className="cabinet__table">
                <thead>
                  <tr>
                    <th>{t('Ученик')}</th>
                    <th>{t('Класс')}</th>
                    <th>{t('Группа')}</th>
                    <th>{t('Почта')}</th>
                    <th>{t('Статус')}</th>
                  </tr>
                </thead>
                <tbody>
                  {cabinet.registry.slice(0, 12).map((row) => (
                    // на телефоне строка разворачивается в карточку:
                    // имя заголовком, остальное парами (фаза 51)
                    <tr key={row.id}>
                      <td data-head="">
                        <b>{row.student}</b>
                      </td>
                      <td className="num" data-label={t('Класс')}>
                        {row.grade}
                      </td>
                      <td data-label={t('Группа')}>{row.group || '—'}</td>
                      <td data-label={t('Почта')}>{row.email}</td>
                      <td data-label={t('Статус')}>
                        <Badge variant={STATUS_TONE[row.status.code] ?? 'mute'}>{t(row.status.title)}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </DataCard>
        }
        aside={
          <>
            <DataCard
              title={t('Требует ваших действий')}
              note={t('Кнопка в строке делает то, что написано')}
              accent="warn"
              count={cabinet.actions.length}
            >
              {cabinet.actions.length === 0 && (
                <p className="muted rows__empty">{t('Ничего не требует вмешательства')}</p>
              )}
              {cabinet.actions.map((row, index) => (
                <div key={`${row.code}-${index}`} className="cabinet__row">
                  <span className="cabinet__rowtext">
                    <b>{t(row.title)}</b>
                    <span className="muted">{row.note}</span>
                  </span>
                  <Button
                    size="sm"
                    disabled={invite.isPending || bulk.isPending || unlock.isPending}
                    onClick={() => run(row)}
                  >
                    {t(row.action)}
                  </Button>
                </div>
              ))}
            </DataCard>

            <DataCard
              title={t('Последние загрузки')}
              note={t('Файлы, которые вы залили за домен')}
              accent="indigo"
            >
              {cabinet.uploads.length === 0 && (
                <p className="muted rows__empty">{t('Загрузок пока не было')}</p>
              )}
              <Rows>
                {cabinet.uploads.map((row) => (
                  <Row
                    key={row.id}
                    title={row.file_name || t('Без имени файла')}
                    note={`${t('за домен')} «${t(DOMAIN_TITLE[row.domain_code] ?? row.domain_code)}» · ${
                      row.rows_created + row.rows_updated
                    } ${t('строк')}`}
                    right={
                      <Badge variant={row.status === 'applied' ? 'ok' : 'mute'}>
                        {row.status === 'applied' ? t('Применена') : t('Отменена')}
                      </Badge>
                    }
                    onOpen={() => navigate('/import')}
                    openLabel={t('Открыть историю')}
                  />
                ))}
              </Rows>
            </DataCard>
          </>
        }
      />
    </div>
  )
}
