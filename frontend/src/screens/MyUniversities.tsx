/**
 * «Мои вузы»: список ученика с соответствием требованиям и конкретным разрывом.
 *
 * Процент — соответствие заведённым требованиям, не шанс поступления
 * (инвариант №11). Внутренних ярлыков здесь нет (инвариант №7).
 */
import { useNavigate } from 'react-router-dom'
import { useMyUniversities, useRemoveFromMyList, useCatalog } from '../api/hooks'
import MatchCard from '../components/MatchCard'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import './universities.css'

export default function MyUniversities() {
  const navigate = useNavigate()
  const mine = useMyUniversities()
  // карточки каталога знают, что у ученика уже в списке и что он может убрать
  const catalog = useCatalog({})
  const remove = useRemoveFromMyList()

  if (mine.isLoading) return <Loading />
  if (mine.error) return <ErrorNote error={mine.error} />

  const byProgram = new Map((catalog.data?.results ?? []).map((card) => [card.program, card]))
  const results = mine.data ?? []
  const open = results.filter((r) => r.is_open).length
  const waiting = results.filter((r) => {
    const card = byProgram.get(r.program)
    return card?.my_entry && !card.my_entry.is_confirmed
  }).length

  return (
    <div>
      <ScreenHead
        emoji="⌂"
        title="Мои вузы"
        subtitle={`${results.length} программ в вашем списке, по ${open} вы проходите уже сейчас.`}
      />

      <div className="toolbar">
        <button className="btn btn-primary btn-sm" onClick={() => navigate('/catalog')}>
          Найти ещё в каталоге
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/catalog?mode=whatif')}>
          Что откроется, если
        </button>
        {waiting > 0 && <span className="chip chip-warn num">ждут подтверждения директора: {waiting}</span>}
      </div>

      <div className="grid grid--cards">
        {results.map((result) => {
          const card = byProgram.get(result.program)
          const entry = card?.my_entry ?? null
          return (
            <MatchCard
              key={result.program}
              card={{
                ...result,
                university: card?.university ?? 0,
                level: card?.level ?? 'low',
                rounds: card?.rounds ?? [],
                in_my_list: true,
                my_entry: entry,
              }}
              actions={
                entry?.can_remove ? (
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => remove.mutate(entry.id)}
                    disabled={remove.isPending}
                  >
                    Убрать из списка
                  </button>
                ) : (
                  <span className="muted uni__note">Эту программу ведёт директор по поступлению</span>
                )
              }
            />
          )
        })}
        {results.length === 0 && (
          <p className="muted">
            Список пока пуст. Загляните в каталог — там видно, куда вы проходите уже сейчас.
          </p>
        )}
      </div>
    </div>
  )
}
