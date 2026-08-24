/** Роадмап: два представления — таймлайн по месяцам и доска по статусам. */
import { useMemo, useState } from 'react'
import { useMyTasks, useTaskStatus, type Task, type TaskStatus } from '../api/hooks'
import Empty from '../components/Empty'
import { counted, ErrorNote, Loading, ScreenHead } from '../components/ui'
import './roadmap.css'

const STATUSES: { code: TaskStatus; title: string }[] = [
  { code: 'todo', title: 'Сделать' },
  { code: 'in_progress', title: 'В работе' },
  { code: 'review', title: 'На проверке' },
  { code: 'done', title: 'Готово' },
]

const PRIORITY_TONE: Record<string, string> = { high: 'chip-risk', medium: 'chip-warn', low: 'chip-mute' }
const CATEGORY_TONE: Record<string, string> = {
  test: 'chip-teal',
  essay: 'chip-brand',
  documents: 'chip-mute',
  university: 'chip-indigo',
  portfolio: 'chip-ok',
  finance: 'chip-mute',
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
        <span className={`chip ${CATEGORY_TONE[task.category] ?? 'chip-mute'}`}>
          {CATEGORY_TITLE[task.category] ?? task.category}
        </span>
        <span className={`chip ${PRIORITY_TONE[task.priority]}`}>
          {task.priority === 'high' ? 'высокий' : task.priority === 'medium' ? 'средний' : 'низкий'}
        </span>
        {task.from_deadline && <span className="chip chip-mute">дедлайн вуза</span>}
      </div>
      <h3 className="task__title">{task.title}</h3>
      {task.due_date_effective && (
        <p className="muted task__due">до {new Date(task.due_date_effective).toLocaleDateString('ru')}</p>
      )}
      <select
        className="input task__status"
        value={task.status}
        onChange={(e) => onMove(e.target.value as TaskStatus)}
      >
        {STATUSES.map((s) => (
          <option key={s.code} value={s.code}>
            {s.title}
          </option>
        ))}
      </select>
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
        title="Роадмап"
        subtitle={
          tasks.length === 0
            ? 'План собирается из ваших вузов и их дедлайнов.'
            : `Сделано ${done} из ${counted(tasks.length, ['задачи', 'задач', 'задач'])}.`
        }
      />

      <div className="toolbar">
        <button
          className={`tab${view === 'timeline' ? ' tab--active' : ''}`}
          onClick={() => setView('timeline')}
        >
          Таймлайн
        </button>
        <button className={`tab${view === 'board' ? ' tab--active' : ''}`} onClick={() => setView('board')}>
          Доска
        </button>
      </div>

      {tasks.length === 0 && (
        <Empty
          title="План пока пуст"
          what="Задачи собираются из выбранных вами вузов и их дедлайнов, а ещё их ставят директора. Выберите первые вузы — и план появится сам."
          action="Выбрать вузы"
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
                <span className="chip chip-mute num">{list.length}</span>
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
                  <span className="chip chip-mute num">{list.length}</span>
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
