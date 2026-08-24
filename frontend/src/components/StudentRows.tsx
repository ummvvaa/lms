/**
 * Дочерние строки ученика на его карточке: вузы, попытки, активности,
 * соревнования, задачи и эссе.
 *
 * Здесь же их и убирают. Кнопку удаления видит только тот, чей это домен:
 * право приходит с сервера вместе с расчётом последствий (инвариант №1).
 */
import { useState, type ReactNode } from 'react'
import { useAddActivity, useDirectoryEntries, useStudentRows } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import DeleteButton from './DeleteButton'
import { ErrorNote, Loading } from './ui'
import { t } from '../i18n'

/** Кто вправе убирать строки этой таблицы. Совпадает с реестром доменов. */
const OWNER: Record<string, string[]> = {
  'universities.StudentUniversity': ['director_admission'],
  'students.ExamAttempt': ['director_exam'],
  'students.Activity': ['director_talent'],
  'students.Competition': ['director_sport'],
  'roadmap.Task': [
    'director_behavior',
    'director_admission',
    'director_exam',
    'director_talent',
    'director_sport',
  ],
  'roadmap.Essay': [
    'director_behavior',
    'director_admission',
    'director_exam',
    'director_talent',
    'director_sport',
  ],
}

const TIER_TITLE: Record<string, string> = { reach: 'reach', target: 'target', safety: 'safety' }

/** Статусы по-русски: в интерфейсе не должно быть внутренних кодов. */
const TASK_STATUS: Record<string, string> = {
  todo: 'сделать',
  in_progress: 'в работе',
  review: 'на проверке',
  done: 'готово',
}

const ESSAY_STATUS: Record<string, string> = {
  draft: 'черновик',
  review: 'на проверке',
  revision: 'на доработке',
  done: 'готово',
}

function Section({
  title,
  model,
  path,
  role,
  rows,
  empty,
  footer,
}: {
  title: string
  model: string
  path: string
  role: string
  rows: { id: number; label: string; note?: string }[]
  empty: string
  /** действие под списком — например, заведение строки */
  footer?: ReactNode
}) {
  const canDelete = (OWNER[model] ?? []).includes(role)
  return (
    <section className="card card-pad rows">
      <div className="row-between rows__head">
        <span className="eyebrow">{title}</span>
        <span className="chip chip-mute num">{rows.length}</span>
      </div>
      {rows.length === 0 && <p className="muted rows__empty">{empty}</p>}
      <ul className="rows__list">
        {rows.map((row) => (
          <li key={row.id} className="rows__item">
            <div>
              <span className="rows__label">{row.label}</span>
              {row.note && <span className="muted rows__note"> · {row.note}</span>}
            </div>
            {canDelete && (
              <DeleteButton
                model={model}
                id={row.id}
                path={path}
                invalidate={[['student-rows'], ['students'], ['match']]}
              />
            )}
          </li>
        ))}
      </ul>
      {footer}
      {!canDelete && rows.length > 0 && (
        <p className="muted rows__empty">{t('Эти строки ведёт другой директор')}</p>
      )}
    </section>
  )
}

/** Категории активности — те же, что в модели. */
const ACTIVITY_CATEGORY: { value: string; title: string }[] = [
  { value: 'olympiad', title: 'Олимпиада' },
  { value: 'project', title: 'Проект' },
  { value: 'research', title: 'Исследование' },
  { value: 'startup', title: 'Стартап' },
  { value: 'leadership', title: 'Лидерство' },
  { value: 'volunteering', title: 'Волонтёрство' },
  { value: 'competition', title: 'Конкурс' },
  { value: 'award', title: 'Награда' },
]

/** Заведение активности: предмет выбирается из справочника Армана. */
function AddActivity({ studentId }: { studentId: number }) {
  const subjects = useDirectoryEntries('subjects')
  const add = useAddActivity(studentId)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ category: 'olympiad', title: '', subject: '', date: '' })
  const [problem, setProblem] = useState<string | null>(null)

  const options = (subjects.data?.results ?? []).filter((row) => row.is_active)

  if (!open) {
    return (
      <button className="btn btn-ghost btn-sm rows__add" onClick={() => setOpen(true)}>
        {t('+ Добавить активность')}
      </button>
    )
  }

  return (
    <div className="rows__form">
      <select
        className="input"
        aria-label={t('Категория активности')}
        value={form.category}
        onChange={(event) => setForm({ ...form, category: event.target.value })}
      >
        {ACTIVITY_CATEGORY.map((item) => (
          <option key={item.value} value={item.value}>
            {item.title}
          </option>
        ))}
      </select>
      <select
        className="input"
        aria-label={t('Предмет олимпиады')}
        value={form.subject}
        onChange={(event) => setForm({ ...form, subject: event.target.value })}
      >
        <option value="">{t('без предмета')}</option>
        {options.map((row) => (
          <option key={row.id} value={row.id}>
            {row.name}
          </option>
        ))}
      </select>
      <input
        className="input"
        aria-label={t('Название активности')}
        placeholder={t('Название')}
        value={form.title}
        onChange={(event) => setForm({ ...form, title: event.target.value })}
      />
      <input
        className="input"
        type="date"
        aria-label={t('Дата активности')}
        value={form.date}
        onChange={(event) => setForm({ ...form, date: event.target.value })}
      />
      <button
        className="btn btn-primary btn-sm"
        disabled={add.isPending}
        onClick={() => {
          if (!form.title.trim()) {
            setProblem('Без названия активность не найти в списке')
            return
          }
          add.mutate(
            {
              category: form.category,
              title: form.title.trim(),
              subject: form.subject ? Number(form.subject) : null,
              date: form.date || null,
            },
            {
              onSuccess: () => {
                setForm({ category: 'olympiad', title: '', subject: '', date: '' })
                setProblem(null)
                setOpen(false)
              },
              onError: (error) => setProblem(String((error as Error).message)),
            },
          )
        }}
      >
        {t('Добавить')}
      </button>
      <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
        {t('Отмена')}
      </button>
      {problem && <p className="chip chip-risk">{problem}</p>}
      {options.length === 0 && (
        <p className="muted">
          {t('Предметов в справочнике пока нет — их заводит директор талантов в разделе «Предметы».')}
        </p>
      )}
    </div>
  )
}

export default function StudentRows({ studentId }: { studentId: number }) {
  const { me } = useAuth()
  const data = useStudentRows(studentId)
  const role = me?.role ?? ''

  if (data.isLoading) return <Loading />
  if (data.isError) return <ErrorNote error={data.error} />
  if (!data.data) return null
  const bundle = data.data

  return (
    <div className="grid grid--two">
      <Section
        title={t('Вузы в списке')}
        model="universities.StudentUniversity"
        path="/student-universities/"
        role={role}
        empty={t('Программ в списке пока нет')}
        rows={bundle.universities.map((row) => ({
          id: row.id,
          label: `${row.university_name} — ${row.program_name}`,
          note: `${TIER_TITLE[row.tier] ?? row.tier}${row.added_by === 'student' ? ' · добавил ученик' : ''}`,
        }))}
      />
      <Section
        title={t('Попытки экзаменов')}
        model="students.ExamAttempt"
        path="/attempts/"
        role={role}
        empty={t('Попыток пока нет')}
        rows={bundle.attempts.map((row) => ({
          id: row.id,
          label: `${row.exam_type} ${row.total_score ?? '—'}`,
          note: `${new Date(row.date).toLocaleDateString('ru')} · ${row.attempt_format === 'mock' ? 'мок' : 'официальный'}`,
        }))}
      />
      <Section
        title={t('Активности')}
        model="students.Activity"
        path="/activities/"
        role={role}
        empty={t('Активностей пока нет')}
        rows={bundle.activities.map((row) => ({
          id: row.id,
          label: row.title,
          note: [row.subject_name, row.is_confirmed ? 'подтверждена' : 'ждёт подтверждения']
            .filter(Boolean)
            .join(' · '),
        }))}
        footer={role === 'director_talent' ? <AddActivity studentId={studentId} /> : undefined}
      />
      <Section
        title={t('Соревнования')}
        model="students.Competition"
        path="/competitions/"
        role={role}
        empty={t('Соревнований пока нет')}
        rows={bundle.competitions.map((row) => ({
          id: row.id,
          label: row.name,
          note: row.result || undefined,
        }))}
      />
      <Section
        title={t('Задачи')}
        model="roadmap.Task"
        path="/tasks/"
        role={role}
        empty={t('Задач пока нет')}
        rows={bundle.tasks.map((row) => ({
          id: row.id,
          label: row.title,
          note: TASK_STATUS[row.status] ?? row.status,
        }))}
      />
      <Section
        title={t('Эссе')}
        model="roadmap.Essay"
        path="/essays/"
        role={role}
        empty={t('Эссе пока нет')}
        rows={bundle.essays.map((row) => ({
          id: row.id,
          label: row.title,
          note: ESSAY_STATUS[row.status] ?? row.status,
        }))}
      />
    </div>
  )
}
