/**
 * Заведение карточки ученика. Только администратор.
 *
 * Доменных полей здесь нет: их вносят директора у себя. Пять пустых
 * профилей создаются на сервере сразу, иначе карточка открывается
 * наполовину, а таблица рисует пустые ячейки.
 */
import { useState } from 'react'
import { useCreateStudent, useStudyGroups } from '../api/hooks'
import { ErrorNote } from './ui'

const THIS_YEAR = new Date().getFullYear()

export default function AddStudent({ onCreated }: { onCreated?: (id: number) => void }) {
  const [open, setOpen] = useState(false)
  const [lastName, setLastName] = useState('')
  const [firstName, setFirstName] = useState('')
  const [email, setEmail] = useState('')
  const [grade, setGrade] = useState(11)
  const [group, setGroup] = useState('')
  const [year, setYear] = useState(THIS_YEAR + 1)
  const [error, setError] = useState<string | null>(null)

  const groups = useStudyGroups()
  const create = useCreateStudent()

  if (!open) {
    return (
      <button className="btn btn-primary btn-sm" onClick={() => setOpen(true)}>
        Завести ученика
      </button>
    )
  }

  const ready = lastName.trim() && firstName.trim() && email.includes('@')

  return (
    <div className="card card-pad addst">
      <span className="eyebrow">Новый ученик</span>
      <div className="addst__grid">
        <label className="addst__field">
          Фамилия
          <input className="input" value={lastName} onChange={(e) => setLastName(e.target.value)} autoFocus />
        </label>
        <label className="addst__field">
          Имя
          <input className="input" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
        </label>
        <label className="addst__field">
          Почта
          <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="addst__field">
          Класс
          <input
            className="input num"
            type="number"
            min={1}
            max={12}
            value={grade}
            onChange={(e) => setGrade(Number(e.target.value))}
          />
        </label>
        <label className="addst__field">
          Группа
          <select className="input" value={group} onChange={(e) => setGroup(e.target.value)}>
            <option value="">— без группы —</option>
            {(groups.data?.results ?? []).map((row) => (
              <option key={row.id} value={row.id}>
                {row.code}
              </option>
            ))}
          </select>
        </label>
        <label className="addst__field">
          Год выпуска
          <input
            className="input num"
            type="number"
            min={THIS_YEAR}
            max={THIS_YEAR + 8}
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
          />
        </label>
      </div>

      {error && <ErrorNote error={new Error(error)} />}

      <div className="addst__actions">
        <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
          Отмена
        </button>
        <button
          className="btn btn-primary btn-sm"
          disabled={!ready || create.isPending}
          onClick={() => {
            setError(null)
            create.mutate(
              {
                last_name: lastName.trim(),
                first_name: firstName.trim(),
                email: email.trim().toLowerCase(),
                grade,
                group: group ? Number(group) : null,
                graduation_year: year,
              },
              {
                onSuccess: (created) => {
                  setOpen(false)
                  setLastName('')
                  setFirstName('')
                  setEmail('')
                  onCreated?.(created.id)
                },
                onError: (e) => setError(e instanceof Error ? e.message : 'Не удалось завести'),
              },
            )
          }}
        >
          {create.isPending ? 'Заводим…' : 'Завести'}
        </button>
      </div>
    </div>
  )
}
