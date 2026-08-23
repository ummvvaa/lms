/**
 * Дочерние строки ученика на его карточке: вузы, попытки, активности,
 * соревнования, задачи и эссе.
 *
 * Здесь же их и убирают. Кнопку удаления видит только тот, чей это домен:
 * право приходит с сервера вместе с расчётом последствий (инвариант №1).
 */
import { useStudentRows } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import DeleteButton from './DeleteButton'
import { ErrorNote, Loading } from './ui'

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

function Section({
  title,
  emoji,
  model,
  path,
  role,
  rows,
  empty,
}: {
  title: string
  emoji: string
  model: string
  path: string
  role: string
  rows: { id: number; label: string; note?: string }[]
  empty: string
}) {
  const canDelete = (OWNER[model] ?? []).includes(role)
  return (
    <section className="card card-pad rows">
      <div className="row-between rows__head">
        <span className="eyebrow">
          {emoji} {title}
        </span>
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
      {!canDelete && rows.length > 0 && <p className="muted rows__empty">Эти строки ведёт другой директор</p>}
    </section>
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
        title="Вузы в списке"
        emoji="🎓"
        model="universities.StudentUniversity"
        path="/student-universities/"
        role={role}
        empty="Программ в списке пока нет"
        rows={bundle.universities.map((row) => ({
          id: row.id,
          label: `${row.university_name} — ${row.program_name}`,
          note: `${TIER_TITLE[row.tier] ?? row.tier}${row.added_by === 'student' ? ' · добавил ученик' : ''}`,
        }))}
      />
      <Section
        title="Попытки экзаменов"
        emoji="🎯"
        model="students.ExamAttempt"
        path="/attempts/"
        role={role}
        empty="Попыток пока нет"
        rows={bundle.attempts.map((row) => ({
          id: row.id,
          label: `${row.exam_type} ${row.total_score ?? '—'}`,
          note: `${new Date(row.date).toLocaleDateString('ru')} · ${row.attempt_format === 'mock' ? 'мок' : 'официальный'}`,
        }))}
      />
      <Section
        title="Активности"
        emoji="🏆"
        model="students.Activity"
        path="/activities/"
        role={role}
        empty="Активностей пока нет"
        rows={bundle.activities.map((row) => ({
          id: row.id,
          label: row.title,
          note: row.is_confirmed ? 'подтверждена' : 'ждёт подтверждения',
        }))}
      />
      <Section
        title="Соревнования"
        emoji="⚽️"
        model="students.Competition"
        path="/competitions/"
        role={role}
        empty="Соревнований пока нет"
        rows={bundle.competitions.map((row) => ({
          id: row.id,
          label: row.name,
          note: row.result || undefined,
        }))}
      />
      <Section
        title="Задачи"
        emoji="▤"
        model="roadmap.Task"
        path="/tasks/"
        role={role}
        empty="Задач пока нет"
        rows={bundle.tasks.map((row) => ({ id: row.id, label: row.title, note: row.status }))}
      />
      <Section
        title="Эссе"
        emoji="✎"
        model="roadmap.Essay"
        path="/essays/"
        role={role}
        empty="Эссе пока нет"
        rows={bundle.essays.map((row) => ({ id: row.id, label: row.title, note: row.status }))}
      />
    </div>
  )
}
