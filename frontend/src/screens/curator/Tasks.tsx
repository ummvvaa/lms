/**
 * Задачи ученикам — экран куратора (фаза 61).
 *
 * Задача живёт той же сущностью, что и остальные задачи ученика
 * (`roadmap.Task`): она попадает ему в календарь, в панель «Сегодня»
 * и на доску, и закрыть её он может сам. Здесь — фильтры и действия
 * куратора: закрыть, отменить, вернуть.
 */
import { useSearchParams } from 'react-router-dom'
import { useCuratorOverview, useCuratorTaskStatus, useCuratorTasks } from '../../api/hooks'
import { Rows } from '../../components/patterns'
import { ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import { TaskLine } from './Card'
import GroupSwitch from './GroupSwitch'
import TaskDialog from './TaskDialog'
import { useGroup } from './state'
import './curator.css'

const FILTERS: { code: string; label: string }[] = [
  { code: 'open', label: 'Открытые' },
  { code: 'late', label: 'Просроченные' },
  { code: 'done', label: 'Сделанные' },
  { code: 'cancelled', label: 'Отменённые' },
  { code: 'all', label: 'Все' },
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
    <div>
      <ScreenHead
        title={t('Задачи ученикам')}
        subtitle={t('Ученик видит задачу в календаре и на своей доске. Закрыть её может он сам или вы.')}
        actions={<TaskDialog groups={overview.data?.groups ?? []} defaultGroup={group} label={t('Новая задача')} />}
      />
      <GroupSwitch groups={overview.data?.groups ?? []} value={group} onChange={setGroup} />

      <div className="cfilters">
        {FILTERS.map((item) => (
          <button
            key={item.code}
            type="button"
            className={`cchip${filter === item.code ? ' cchip--on' : ''}`}
            onClick={() => setFilter(item.code)}
          >
            {t(item.label)} <span className="cchip__note">{data?.counts[item.code] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="card card-pad">
        {rows.length === 0 && <p className="muted">{t('С таким фильтром ничего нет')}</p>}
        <Rows>
          {rows.map((task) => (
            <TaskLine key={task.id} task={task} onStatus={(status) => move.mutate({ id: task.id, status })} />
          ))}
        </Rows>
      </div>
    </div>
  )
}
