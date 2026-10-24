/**
 * «Задачи сотрудникам» — академический директор (макет ETasks, 24.10.2026).
 *
 * Задачу ставят учителю, куратору или директору: текст и срок. Исполнитель
 * видит её у себя на главной и отмечает «Выполнено»; здесь её принимают
 * или возвращают с причиной. Открытой — «Напомнить» уведомлением.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import {
  useSetStaffTask,
  useStaffPeople,
  useStaffTaskAction,
  useStaffTasks,
  type StaffTask,
} from '../../api/directors'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import RowMenu, { RowMenuItem } from '../../components/RowMenu'
import { Segmented, ShowAll } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk, tn } from '../../i18n'
import { formatDate, formatDayMonth } from '../../lib/format'
import { todayLine } from './parts'
import './directors.css'

type Filter = 'open' | 'late' | 'done' | 'all'
type Who = 'all' | 'teacher' | 'curator' | 'director'

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'open', label: tk('Открытые') },
  { value: 'late', label: tk('Просроченные') },
  { value: 'done', label: tk('Выполнено') },
  { value: 'all', label: tk('Все') },
]

const WHO: { value: Who; label: string }[] = [
  { value: 'all', label: tk('Все') },
  { value: 'teacher', label: tk('Учителя') },
  { value: 'curator', label: tk('Кураторы') },
  { value: 'director', label: tk('Директора') },
]

const isOpen = (task: StaffTask) => task.status === 'open' || task.status === 'returned'
const matches = (filter: Filter, task: StaffTask) =>
  filter === 'all' ||
  (filter === 'open' && (isOpen(task) || task.status === 'done')) ||
  (filter === 'late' && task.late) ||
  (filter === 'done' && task.status === 'accepted')
const whoOf = (task: StaffTask): Who =>
  task.assignee.role === 'teacher' ? 'teacher' : task.assignee.role === 'curator' ? 'curator' : 'director'

function stateOf(task: StaffTask): { label: string; tone: Tone } {
  if (task.status === 'accepted') return { label: t('принято'), tone: 'good' }
  if (task.status === 'done') return { label: t('ждёт приёмки'), tone: 'info' }
  if (task.late) return { label: tn(task.days_late, 'просрочено {n} день|просрочено {n} дня|просрочено {n} дней'), tone: 'bad' }
  if (task.status === 'returned') return { label: t('возвращена'), tone: 'warn' }
  return { label: t('в работе'), tone: 'neutral' }
}

export default function StaffTasks() {
  const { data, isLoading, error } = useStaffTasks()
  const action = useStaffTaskAction()
  const [filter, setFilter] = useState<Filter>('open')
  const [who, setWho] = useState<Who>('all')
  const [creating, setCreating] = useState(false)
  const [returning, setReturning] = useState<StaffTask | null>(null)

  if (isLoading && !data) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const rows = data.rows.filter((task) => matches(filter, task) && (who === 'all' || whoOf(task) === who))
  const open = data.rows.filter(isOpen)
  const byPerson = Object.values(
    open.reduce<Record<number, { name: string; role: string; n: number; late: number }>>((acc, task) => {
      const row = (acc[task.assignee.id] ??= { name: task.assignee.name, role: task.assignee.role_title, n: 0, late: 0 })
      row.n += 1
      if (task.late) row.late += 1
      return acc
    }, {}),
  ).sort((a, b) => b.n - a.n)

  const remind = (task: StaffTask) =>
    action.mutate({ id: task.id, action: 'remind' }, { onSuccess: () => toast.success(t('Напоминание отправлено — {name}', { name: task.assignee.name })) })

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Задачи сотрудникам')}
        subtitle={todayLine(t('учителя, кураторы и директора'))}
        actions={<Button onClick={() => setCreating(true)}>{t('Новая задача')}</Button>}
      />
      <div className="filters">
        <Segmented
          value={filter}
          onChange={setFilter}
          label={t('Какие задачи')}
          items={FILTERS.map((item) => ({
            value: item.value,
            label: (
              <>
                {t(item.label)}
                <span className="tabs__n num">{data.rows.filter((task) => matches(item.value, task)).length}</span>
              </>
            ),
          }))}
        />
        <Segmented value={who} onChange={setWho} label={t('Кому')} items={WHO.map((item) => ({ value: item.value, label: t(item.label) }))} />
      </div>
      <div className="lay-main lay-main--even">
        <DataCard
          className={rows.length ? 'card--beam' : undefined}
          title={t(FILTERS.find((item) => item.value === filter)?.label ?? '')}
          count={rows.length || undefined}
          empty={rows.length === 0 && t('с таким фильтром задач нет')}
        >
          <div className="dir__rows">
            <ShowAll limit={8}>
              {rows.map((task) => {
                const state = stateOf(task)
                return (
                  <div key={task.id} className="dir__row">
                    <span className="dir__what">
                      <b>{task.title}</b>
                      <span className="t-note">
                        {`${task.assignee.name} · ${task.assignee.role_title} · ${t('до {date}', { date: formatDayMonth(task.due) })}`}
                      </span>
                    </span>
                    <Chip tone={state.tone} size="sm">
                      {state.label}
                    </Chip>
                    <span className="dir__acts">
                      {task.status === 'done' ? (
                        <>
                          <Button variant="outline" size="sm" disabled={action.isPending} onClick={() => action.mutate({ id: task.id, action: 'accept' }, { onSuccess: () => toast.success(t('Задача принята — {name}', { name: task.assignee.name })) })}>
                            {t('Принять')}
                          </Button>
                          <RowMenu>
                            <RowMenuItem onClick={() => setReturning(task)}>{t('Вернуть')}</RowMenuItem>
                          </RowMenu>
                        </>
                      ) : isOpen(task) ? (
                        <Button variant="ghost" size="sm" disabled={action.isPending} onClick={() => remind(task)}>
                          {t('Напомнить')}
                        </Button>
                      ) : null}
                    </span>
                  </div>
                )
              })}
            </ShowAll>
          </div>
        </DataCard>
        <div className="lay-stack">
          <DataCard title={t('Открыто по сотрудникам')} count={open.length || undefined} empty={byPerson.length === 0 && t('открытых задач нет')}>
            <div className="dir__lines">
              {byPerson.slice(0, 5).map((row) => (
                <div key={row.name} className="dir__line">
                  <span>
                    {row.name}
                    <span className="t-note">{` · ${row.role}`}</span>
                  </span>
                  <b className="num">{row.late ? t('{n} · просрочено {late}', { n: row.n, late: row.late }) : row.n}</b>
                </div>
              ))}
            </div>
            {byPerson.length > 5 && <span className="t-note">{t('ещё {n}', { n: byPerson.length - 5 })}</span>}
          </DataCard>
          <DataCard title={t('За месяц')}>
            <div className="dir__lines">
              <div className="dir__line">
                <span>{t('Поставлено')}</span>
                <b className="num">{data.month.set}</b>
              </div>
              <div className="dir__line">
                <span>{t('Принято')}</span>
                <b className="num">{data.month.accepted}</b>
              </div>
              <div className="dir__line">
                <span>{t('Вернули на доработку')}</span>
                <b className="num">{data.month.returned}</b>
              </div>
            </div>
          </DataCard>
        </div>
      </div>
      {creating && <StaffTaskDialog onClose={() => setCreating(false)} />}
      {returning && <ReturnDialog task={returning} onClose={() => setReturning(null)} />}
    </div>
  )
}

function ReturnDialog({ task, onClose }: { task: StaffTask; onClose: () => void }) {
  const action = useStaffTaskAction()
  const [note, setNote] = useState('')
  return (
    <Modal title={t('Вернуть на доработку')} note={`${task.title} · ${task.assignee.name}`} onClose={onClose}>
      <Field kind="textarea" name="return-note" label={t('Что доделать')} value={note} onChange={setNote} rows={3} autoFocus />
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={!note.trim() || action.isPending}
          onClick={() =>
            action.mutate(
              { id: task.id, action: 'return', note },
              { onSuccess: () => { toast.success(t('Задача возвращена на доработку — {name}', { name: task.assignee.name })); onClose() } },
            )
          }
        >
          {t('Вернуть')}
        </Button>
      </div>
    </Modal>
  )
}

/** Новая задача сотруднику: кому, что, срок. Из «Отчётов» открывается сразу на учителя. */
export function StaffTaskDialog({ assignee, onClose }: { assignee?: { id: number; name: string }; onClose: () => void }) {
  const people = useStaffPeople()
  const save = useSetStaffTask()
  const [who, setWho] = useState(assignee ? String(assignee.id) : '')
  const [title, setTitle] = useState('')
  const week = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10)
  const [due, setDue] = useState(week)
  const options = (people.data?.rows ?? []).map((row) => ({ value: String(row.id), title: `${row.name} · ${row.role_title}` }))
  return (
    <Modal title={t('Новая задача')} note={assignee?.name} onClose={onClose}>
      <div className="dir__form">
        <Field className="dir__wide" kind="select" name="assignee" label={t('Кому')} value={who} onChange={setWho} options={options} placeholder={t('Выберите сотрудника')} />
        <Field className="dir__wide" kind="textarea" name="title" label={t('Задача')} value={title} onChange={setTitle} rows={3} />
        <Field kind="date" name="due" label={t('Срок')} value={due} onChange={setDue} hint={t('до {date}', { date: due ? formatDate(due) : '' })} />
      </div>
      {save.error && <ErrorNote error={save.error} />}
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={!who || !title.trim() || !due || save.isPending}
          onClick={() =>
            save.mutate(
              { assignee: Number(who), title, due },
              { onSuccess: (task) => { toast.success(t('Задача поставлена — {name}', { name: task.assignee.name })); onClose() } },
            )
          }
        >
          {t('Поставить')}
        </Button>
      </div>
    </Modal>
  )
}
