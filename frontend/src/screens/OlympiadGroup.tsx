/**
 * Отбор в олимпиадную группу — экран директора талантов.
 *
 * Отметка открывает ученику раздел материалов, снятие — закрывает.
 * Правка идёт через журнал изменений, как любое доменное поле.
 */
import { useState } from 'react'
import { useOlympiadGroup, usePickForGroup } from '../api/hooks'
import Empty from '../components/Empty'
import { counted, ErrorNote, Loading, ScreenHead } from '../components/ui'
import './materials.css'

export default function OlympiadGroup() {
  const [query, setQuery] = useState('')
  const [grade, setGrade] = useState('')
  const [onlyMembers, setOnlyMembers] = useState(false)
  const [flash, setFlash] = useState<string | null>(null)

  const list = useOlympiadGroup({ q: query, grade, member: onlyMembers ? 'true' : undefined })
  const pick = usePickForGroup()

  if (list.isLoading) return <Loading />
  if (list.isError) return <ErrorNote error={list.error} />

  const rows = list.data?.students ?? []

  return (
    <div>
      <ScreenHead
        emoji="🏅"
        title="Олимпиадная группа"
        subtitle="Отмеченным открыт раздел материалов: они выкладывают разборы и видят чужие. Остальные его не видят вовсе."
      />

      <p className="chip chip-mute mat__flash">{list.data?.detail}</p>
      {flash && <p className="chip chip-ok mat__flash">{flash}</p>}

      <div className="card card-pad mat__filters">
        <input
          className="input"
          placeholder="Фамилия или имя"
          aria-label="Поиск ученика"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <select
          className="input"
          aria-label="Класс"
          value={grade}
          onChange={(event) => setGrade(event.target.value)}
        >
          <option value="">все классы</option>
          {[9, 10, 11, 12].map((n) => (
            <option key={n} value={n}>
              {n} класс
            </option>
          ))}
        </select>
        <label className="mat__check">
          <input type="checkbox" checked={onlyMembers} onChange={(e) => setOnlyMembers(e.target.checked)} />
          только те, кто в группе
        </label>
      </div>

      {rows.length === 0 ? (
        <Empty
          emoji="🏅"
          title="Никого не нашлось"
          what="Снимите фильтры или заведите учеников — карточки заводит администратор."
          action="Снять фильтры"
          onAction={() => {
            setQuery('')
            setGrade('')
            setOnlyMembers(false)
          }}
        />
      ) : (
        <div className="card card-pad">
          <table className="history dir__table">
            <thead>
              <tr>
                <th>Ученик</th>
                <th>Класс</th>
                <th>Группа</th>
                <th>Материалов</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td style={{ fontWeight: 650 }}>{row.full_name}</td>
                  <td className="muted num">{row.grade}</td>
                  <td className="muted">{row.group || '—'}</td>
                  <td className="num">
                    {row.materials === 0 ? (
                      <span className="muted">нет</span>
                    ) : (
                      counted(row.materials, ['материал', 'материала', 'материалов'])
                    )}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      className={`btn btn-sm ${row.in_group ? 'btn-primary' : 'btn-ghost'}`}
                      disabled={pick.isPending}
                      onClick={() =>
                        pick.mutate(
                          { student: row.id, member: !row.in_group },
                          { onSuccess: (answer) => setFlash(answer.detail) },
                        )
                      }
                    >
                      {row.in_group ? '✓ В группе' : 'Отметить'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
