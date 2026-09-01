/** Роадмап: два представления — таймлайн по месяцам и доска по статусам. */
import { useMemo, useState } from 'react'
import { useMyTasks, useTaskStatus, type Task, type TaskStatus } from '../api/hooks'
import Empty from '../components/Empty'
import { counted, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../components/ui'
import './roadmap.css'
import { t } from '../i18n'
import { NativeSelect } from '../components/ui/native-select'
import { Badge } from '../components/ui/badge'
import { type BadgeVariant } from '../components/ui/badge'

const STATUSES: { code: TaskStatus; title: string }[] = [
  { code: 'todo', title: 'Сделать' },
  { code: 'in_progress', title: 'В работе' },
  { code: 'review', title: 'На проверке' },
  { code: 'done', title: 'Готово' },
]

const PRIORITY_TONE: Record<string, BadgeVariant> = { high: 'risk', medium: 'warn', low: 'mute' }
const CATEGORY_TONE: Record<string, BadgeVariant> = {
  test: 'teal',
  essay: 'brand',
  documents: 'mute',
  university: 'indigo',
  portfolio: 'ok',
  finance: 'mute',
}
const CATEGORY_TITLE: Record<string, string> = {
  test: 'Тест',
  essay: 'Эссе',
  documents: 'Документы',
  university: 'Вузы',
  portfolio: 'Портфолио',
  finance: 'Финансы',
}
const MONTHS = [
  'Январь',
  'Февраль',
  'Март',
  'Апрель',
  'Май',
  'Июнь',
  'Июль',
  'Август',
  'Сентябрь',
  'Октябрь',
  'Ноябрь',
  'Декабрь',
]

function TaskCard({ task, onMove }: { task: Task; onMove: (status: TaskStatus) => void }) {
  return (
    <article className="card card-pad task">
      <div className="task__tags">
        <Badge variant={CATEGORY_TONE[task.category] ?? 'mute'}>
          {CATEGORY_TITLE[task.category] ?? task.category}
        </Badge>
        <Badge variant={PRIORITY_TONE[task.priority]}>
          {task.priority === 'high' ? 'высокий' : task.priority === 'medium' ? 'средний' : 'низкий'}
        </Badge>
        {task.from_deadline && <Badge variant="mute">{t('дедлайн вуза')}</Badge>}
        {/* задача плана помечена вузом: в общем роадмапе их несколько,
            и без пометки непонятно, к какой заявке относится задача */}
        {task.plan_university && <Badge variant="indigo">{task.plan_university}</Badge>}
      </div>
      <h3 className="task__title">{task.title}</h3>
      {task.due_date_effective && (
        <p className="muted task__due">до {new Date(task.due_date_effective).toLocaleDateString('ru')}</p>
      )}
      <NativeSelect
        className="task__status"
        value={task.status}
        onChange={(e) => onMove(e.target.value as TaskStatus)}
      >
        {STATUSES.map((s) => (
          <option key={s.code} value={s.code}>
            {s.title}
          </option>
        ))}
      </NativeSelect>
    </article>
  )
}

export default function Roadmap() {
  const { data, isLoading, error } = useMyTasks()
  const move = useTaskStatus()
  const [view, setView] = useState<'timeline' | 'board'>('timeline')

  const byMonth = useMemo(() => {
    const map = new Map<string, Task[]>()
    ;(data ?? []).forEach((task) => {
      const due = task.due_date_effective
      const key = due ? `${new Date(due).getFullYear()}-${new Date(due).getMonth()}` : 'later'
      map.set(key, [...(map.get(key) ?? []), task])
    })
    return [...map.entries()].sort(([a], [b]) =>
      a === 'later' ? 1 : b === 'later' ? -1 : a.localeCompare(b),
    )
  }, [data])

  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />

  const tasks = data ?? []
  const done = tasks.filter((t) => t.status === 'done').length

  return (
    <div>
      <ScreenHead
        title={t('Роадмап')}
        subtitle={
          tasks.length === 0
            ? 'План собирается из ваших вузов и их дедлайнов.'
            : `Сделано ${done} из ${counted(tasks.length, ['задачи', 'задач', 'задач'])}.`
        }
      />

      <ScreenTabs
        value={view}
        onChange={setView}
        items={[
          { value: 'timeline', label: t('Таймлайн') },
          { value: 'board', label: t('Доска') },
        ]}
      />

      {tasks.length === 0 && (
        <Empty
          icon="checklist"
          title={t('План пока пуст')}
          what={t('План соберётся сам, как только появятся вузы.')}
          hint={t('Задачи растут из дедлайнов ваших программ, а ещё их ставят директора.')}
          action={t('Выбрать вузы')}
          to="/catalog"
        />
      )}

      {view === 'timeline' &&
        byMonth.map(([key, list]) => {
          const [year, month] = key.split('-')
          const label = key === 'later' ? 'Без срока' : `${MONTHS[Number(month)]} ${year}`
          return (
            <section key={key} className="timeline__month">
              <div className="timeline__head">
                <h2 className="timeline__label">{label}</h2>
                <Badge variant="mute" className="num">
                  {list.length}
                </Badge>
              </div>
              <div className="grid grid--cards">
                {list.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    onMove={(status) => move.mutate({ id: task.id, status })}
                  />
                ))}
              </div>
            </section>
          )
        })}

      {view === 'board' && (
        <div className="board">
          {STATUSES.map((column) => {
            const list = tasks.filter((t) => t.status === column.code)
            return (
              <div key={column.code} className="board__column">
                <div className="board__head">
                  <b>{column.title}</b>
                  <Badge variant="mute" className="num">
                    {list.length}
                  </Badge>
                </div>
                {list.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    onMove={(status) => move.mutate({ id: task.id, status })}
                  />
                ))}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
