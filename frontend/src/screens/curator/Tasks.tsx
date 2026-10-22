/**
 * Задачи ученикам — экран куратора (фаза 61).
 *
 * Задача живёт той же сущностью, что и остальные задачи ученика
 * (`roadmap.Task`): она попадает ему в календарь, в панель «Сегодня»
 * и на доску, и закрыть её он может сам. Здесь — фильтры и действия
 * куратора: закрыть, отменить, вернуть.
 */
import { Link, useSearchParams } from 'react-router'
import { useCuratorOverview, useCuratorTaskStatus, useCuratorTasks } from '../../api/hooks'
import RowMenu, { RowMenuItem } from '../../components/RowMenu'
import { Segmented, ShowAll } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import GroupSwitch from './GroupSwitch'
import TaskDialog from './TaskDialog'
import { useGroup } from './state'
import './curator.css'
import './curator-layout.css'
import { formatDate } from '../../lib/format'

const FILTERS: { code: string; label: string }[] = [
  { code: 'open', label: tk('Открытые') },
  { code: 'late', label: tk('Просроченные') },
  { code: 'done', label: tk('Сделанные') },
  { code: 'cancelled', label: tk('Отменённые') },
  { code: 'all', label: tk('Все') },
]

export default function CuratorTasks() {
  const [group, setGroup] = useGroup()
  const [params, setParams] = useSearchParams()
  const filter = params.get('filter') ?? 'open'

  const overview = useCuratorOverview(group)
  const { data, isLoading, error } = useCuratorTasks(group, filter)
  const move = useCuratorTaskStatus()

  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />

  const setFilter = (code: string) => {
    const updated = new URLSearchParams(params)
    updated.set('filter', code)
    setParams(updated, { replace: true })
  }

  const rows = data?.results ?? []

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Задачи ученикам')}
        subtitle={t('Что поставили вы и что пришло от школы')}
        actions={
          <TaskDialog groups={overview.data?.groups ?? []} defaultGroup={group} label={t('Новая задача')} />
        }
      />
      <GroupSwitch groups={overview.data?.groups ?? []} value={group} onChange={setGroup} />

      <div className="filters">
        <Segmented
          value={filter}
          onChange={setFilter}
          label={t('Какие задачи')}
          items={FILTERS.map((item) => ({
            value: item.code,
            label: (
              <>
                {t(item.label)}
                <span className="tabs__n num">{data?.counts[item.code] ?? 0}</span>
              </>
            ),
          }))}
        />
      </div>

      <DataCard
        className={rows.length ? 'card--beam' : undefined}
        title={t(FILTERS.find((item) => item.code === filter)?.label ?? 'Задачи')}
        count={rows.length || undefined}
        empty={rows.length === 0 && t('с таким фильтром ничего нет')}
      >
        <div className="ctasks">
          <ShowAll limit={20}>
            {rows.map((task) => {
              const closed = task.status === 'done' || task.status === 'cancelled'
              return (
                <div key={task.id} className="ctasks__row">
                  <span className="ctasks__what">
                    <b>{task.title}</b>
                    <span className="t-note">{task.origin_title}</span>
                  </span>
                  <Link className="ctasks__who" to={`/students/${task.student}?tab=tasks`}>
                    {`${task.student_name} · ${task.group}`}
                  </Link>
                  <Chip tone={task.is_overdue ? 'bad' : closed ? 'neutral' : 'warn'} size="sm">
                    {task.status === 'done'
                      ? t('сделано')
                      : task.status === 'cancelled'
                        ? t('отменена')
                        : task.is_overdue
                          ? t('просрочена')
                          : task.due_date
                            ? t('до {date}', { date: formatDate(task.due_date) })
                            : t('без срока')}
                  </Chip>
                  {/* на виду одно действие: «Сделано» у открытой, «Вернуть» у закрытой; отмена — в «…» */}
                  <span className="ctasks__acts">
                    {closed ? (
                      <Button variant="ghost" size="sm" onClick={() => move.mutate({ id: task.id, status: 'todo' })}>
                        {t('Вернуть')}
                      </Button>
                    ) : (
                      <>
                        <Button variant="outline" size="sm" onClick={() => move.mutate({ id: task.id, status: 'done' })}>
                          {t('Сделано')}
                        </Button>
                        <RowMenu>
                          <RowMenuItem onClick={() => move.mutate({ id: task.id, status: 'cancelled' })}>{t('Отменить')}</RowMenuItem>
                        </RowMenu>
                      </>
                    )}
                  </span>
                </div>
              )
            })}
          </ShowAll>
        </div>
      </DataCard>
    </div>
  )
}
