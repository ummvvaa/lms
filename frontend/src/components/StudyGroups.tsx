/**
 * Учебные группы: завести и убрать. Реестр школы, ведёт администратор.
 *
 * Группа с учениками не удаляется молча: сервер считает, сколько их,
 * и говорит об этом в диалоге.
 */
import { useState } from 'react'
import { useCreateStudyGroup, useStudyGroups } from '../api/hooks'
import DeleteButton from './DeleteButton'
import { ErrorNote, Loading } from './ui'

export default function StudyGroups() {
  const [code, setCode] = useState('')
  const [grade, setGrade] = useState(11)
  const [curator, setCurator] = useState('')
  const [error, setError] = useState<string | null>(null)

  const list = useStudyGroups()
  const create = useCreateStudyGroup()
  const rows = list.data?.results ?? []

  return (
    <section className="card card-pad groups">
      <span className="eyebrow">▤ Учебные группы</span>

      <div className="groups__form">
        <input
          className="input"
          placeholder="Код, например 11A"
          value={code}
          aria-label="Код группы"
          onChange={(event) => setCode(event.target.value)}
        />
        <input
          className="input num"
          type="number"
          min={1}
          max={12}
          value={grade}
          aria-label="Класс группы"
          onChange={(event) => setGrade(Number(event.target.value))}
        />
        <input
          className="input"
          placeholder="Куратор"
          value={curator}
          aria-label="Куратор группы"
          onChange={(event) => setCurator(event.target.value)}
        />
        <button
          className="btn btn-primary btn-sm"
          disabled={!code.trim() || create.isPending}
          onClick={() => {
            setError(null)
            create.mutate(
              { code: code.trim(), grade, curator: curator.trim() },
              {
                onSuccess: () => {
                  setCode('')
                  setCurator('')
                },
                onError: (e) => setError(e instanceof Error ? e.message : 'Не удалось завести группу'),
              },
            )
          }}
        >
          Завести группу
        </button>
      </div>

      {error && <ErrorNote error={new Error(error)} />}
      {list.isLoading && <Loading />}

      {!list.isLoading && rows.length === 0 && (
        <p className="muted rows__empty">
          Групп пока нет. Заведите первую — по ней потом раскладываются ученики и считаются дашборды.
        </p>
      )}

      <ul className="rows__list">
        {rows.map((row) => (
          <li key={row.id} className="rows__item">
            <div>
              <span className="rows__label">{row.code}</span>
              <span className="muted rows__note">
                {' '}
                · {row.grade} класс · учеников {row.students_count}
                {row.curator && ` · куратор ${row.curator}`}
              </span>
            </div>
            <DeleteButton
              model="students.StudyGroup"
              id={row.id}
              path="/groups/"
              invalidate={[['groups'], ['students']]}
            />
          </li>
        ))}
      </ul>
    </section>
  )
}
