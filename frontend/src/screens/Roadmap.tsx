/**
 * Роадмап: задачи строками по месяцам, справа фильтр и сводка; доска
 * по статусам — второй вид того же списка.
 */
import { useMemo, useState } from 'react'
import { useMyTasks, useTaskStatus, type Task, type TaskStatus } from '../api/hooks'
import Field from '../components/Field'
import { Row, Rows, Segmented, StatRow } from '../components/patterns'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { NoteCard } from './academics/shared'
import './roadmap.css'

const STATUSES: { code: TaskStatus; title: string }[] = [
  { code: 'todo', title: 'Сделать' },
  { code: 'in_progress', title: 'В работе' },
  { code: 'review', title: 'На проверке' },
  { code: 'done', title: 'Готово' },
]

const PRIORITY_TONE: Record<string, Tone> = { high: 'bad', medium: 'warn', low: 'neutral' }
const PRIORITY_TITLE: Record<string, string> = { high: 'важно', medium: 'обычное', low: 'не срочно' }
const CATEGORY_TITLE: Record<string, string> = {
  test: 'Тест',
  essay: 'Эссе',
  documents: 'Документы',
  university: 'Вузы',
  portfolio: 'Портфолио',
  finance: 'Финансы',
}
const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

function TaskLine({ task, onMove }: { task: Task; onMove: (status: TaskStatus) => void }) {
  return (
    <Row
      icon="checklist"
      tone={task.status === 'done' ? 'good' : PRIORITY_TONE[task.priority] ?? 'neutral'}
      title={task.title}
      note={[t(CATEGORY_TITLE[task.category] ?? task.category), t(PRIORITY_TITLE[task.priority] ?? task.priority), task.plan_university ?? '', task.from_deadline ? t('дедлайн вуза') : '', task.due_date_effective ? `${t('до')} ${new Date(task.due_date_effective).toLocaleDateString('ru')}` : ''].filter(Boolean).join(' · ')}
      muted={task.status === 'done'}
      acts={<Field kind="select" name={`status-${task.id}`} label={t('Статус')} value={task.status} onChange={(value) => onMove(value as TaskStatus)} options={STATUSES.map((s) => ({ value: s.code, title: t(s.title) }))} className="task__status" />}
    />
  )
}

export default function Roadmap() {
  const { data, isLoading, error } = useMyTasks()
  const move = useTaskStatus()
  const [view, setView] = useState<'timeline' | 'board'>('timeline')
  const [category, setCategory] = useState('')
  const [hideDone, setHideDone] = useState(false)

  const tasks = useMemo(() => (data ?? []).filter((task) => (!category || task.category === category) && (!hideDone || task.status !== 'done')), [data, category, hideDone])
  const byMonth = useMemo(() => {
    const map = new Map<string, Task[]>()
    tasks.forEach((task) => {
      const due = task.due_date_effective
      const key = due ? `${new Date(due).getFullYear()}-${new Date(due).getMonth()}` : 'later'
      map.set(key, [...(map.get(key) ?? []), task])
    })
    return [...map.entries()].sort(([a], [b]) => (a === 'later' ? 1 : b === 'later' ? -1 : a.localeCompare(b)))
  }, [tasks])

  if (isLoading) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />

  const all = data ?? []
  const done = all.filter((task) => task.status === 'done').length
  const overdue = all.filter((task) => task.status !== 'done' && task.due_date_effective && task.due_date_effective < new Date().toISOString().slice(0, 10)).length
  const categories = [...new Set(all.map((task) => task.category))]

  return (
    <div>
      <ScreenHead title={t('Роадмап')} subtitle={all.length === 0 ? t('План собирается из ваших вузов и их дедлайнов') : `${t('Сделано')} ${done} ${t('из')} ${counted(all.length, ['задачи', 'задач', 'задач'])}`} />
      <StatRow>
        <Kpi label={t('Открытых')} value={all.length - done || null} none={t('нет')} />
        <Kpi label={t('Просрочено')} value={overdue || null} none={t('нет')} tone={overdue ? 'bad' : undefined} />
        <Kpi label={t('На проверке')} value={all.filter((task) => task.status === 'review').length || null} none={t('нет')} />
        <Kpi label={t('Сделано')} value={done || null} none={t('нет')} tone={done ? 'good' : undefined} />
      </StatRow>
      <div className="acad__toolbar">
        <Segmented
          value={view}
          onChange={setView}
          label={t('Вид')}
          items={[
            { value: 'timeline', label: t('Таймлайн') },
            { value: 'board', label: t('Доска') },
          ]}
        />
        <Button variant={hideDone ? 'default' : 'outline'} size="sm" onClick={() => setHideDone(!hideDone)}>
          {hideDone ? t('Показать сделанные') : t('Скрыть сделанные')}
        </Button>
      </div>

      {view === 'timeline' && (
        <div className="acad__cols">
          <div className="acad__stack">
            {all.length === 0 && <DataCard title={t('План пока пуст')} empty={t('план соберётся сам, как только появятся вузы; задачи растут из дедлайнов ваших программ, а ещё их ставят директора')} />}
            {byMonth.map(([key, list]) => {
              const [year, month] = key.split('-')
              const label = key === 'later' ? t('Без срока') : `${t(MONTHS[Number(month)])} ${year}`
              return (
                <DataCard key={key} title={label} count={list.length}>
                  <Rows>
                    {list.map((task) => (
                      <TaskLine key={task.id} task={task} onMove={(status) => move.mutate({ id: task.id, status })} />
                    ))}
                  </Rows>
                </DataCard>
              )
            })}
          </div>
          <div className="acad__stack">
            <DataCard title={t('Категория')}>
              <div className="acad__chips">
                <Button variant={category === '' ? 'default' : 'outline'} size="sm" onClick={() => setCategory('')}>
                  {t('Все')}
                </Button>
                {categories.map((code) => (
                  <Button key={code} variant={category === code ? 'default' : 'outline'} size="sm" onClick={() => setCategory(code)}>
                    {t(CATEGORY_TITLE[code] ?? code)}
                  </Button>
                ))}
              </div>
            </DataCard>
            <NoteCard title={t('Откуда задачи')}>{t('Из дедлайнов ваших вузов, из плана по каждой программе и от директоров. Выполненную задачу закрываете вы; на проверку уходит то, что подтверждает школа.')}</NoteCard>
          </div>
        </div>
      )}

      {view === 'board' && (
        <div className="board">
          {STATUSES.map((column) => {
            const list = tasks.filter((task) => task.status === column.code)
            return (
              <DataCard key={column.code} title={t(column.title)} count={list.length} empty={list.length === 0 && t('пусто')}>
                <Rows>
                  {list.map((task) => (
                    <Row
                      key={task.id}
                      title={task.title}
                      note={task.due_date_effective ? `${t('до')} ${new Date(task.due_date_effective).toLocaleDateString('ru')}` : undefined}
                      right={<Chip tone={PRIORITY_TONE[task.priority] ?? 'neutral'} size="sm">{t(PRIORITY_TITLE[task.priority] ?? task.priority)}</Chip>}
                    />
                  ))}
                </Rows>
              </DataCard>
            )
          })}
        </div>
      )}
    </div>
  )
}
