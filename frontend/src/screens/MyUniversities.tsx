/**
 * «Мои вузы»: по каждой программе — статус соответствия и конкретный разрыв.
 * Формулировки конструктивные, внутренних ярлыков нет (инвариант №7).
 */
import { useState } from 'react'
import { useMyUniversities, useOpenPrograms, useWhatIf, type MatchResult } from '../api/hooks'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import './universities.css'

function StatusChip({ result }: { result: MatchResult }) {
  if (!result.has_requirements) return <span className="chip chip-mute">требования не заведены</span>
  if (result.is_open) return <span className="chip chip-ok">проходите</span>
  return <span className="chip chip-warn">есть разрыв</span>
}

function ProgramCard({ result }: { result: MatchResult }) {
  return (
    <article className="card card-pad">
      <div className="row-between">
        <div>
          <b style={{ fontSize: 15 }}>{result.university_name}</b>
          <p className="muted" style={{ margin: '4px 0 0', fontSize: 12.5 }}>
            {result.country} · {result.program_name}
          </p>
        </div>
        <StatusChip result={result} />
      </div>

      <p className="uni__summary">{result.summary}</p>

      {result.criteria.length > 0 && (
        <table className="uni__criteria">
          <tbody>
            {result.criteria.map((criterion) => (
              <tr key={criterion.code}>
                <td className="muted">{criterion.title}</td>
                <td className="num">
                  {criterion.is_unknown ? <span className="muted">нет данных</span> : criterion.current}
                </td>
                <td className="muted num">нужно {criterion.threshold}</td>
                <td>
                  {criterion.is_met ? (
                    <span className="chip chip-ok">есть</span>
                  ) : (
                    <span className="chip chip-warn num">+{criterion.gap}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </article>
  )
}

export default function MyUniversities() {
  const mine = useMyUniversities()
  const [showAll, setShowAll] = useState(false)
  const all = useOpenPrograms(undefined, true)
  const whatIf = useWhatIf()

  if (mine.isLoading) return <Loading />
  if (mine.error) return <ErrorNote error={mine.error} />

  const results = mine.data ?? []
  const open = results.filter((r) => r.is_open).length

  return (
    <div>
      <ScreenHead
        emoji="⌂"
        title="Мои вузы"
        subtitle={`${results.length} программ в вашем списке, по ${open} вы проходите уже сейчас.`}
      />

      <div className="toolbar">
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => void whatIf.mutate({ ielts_delta: 0.5 })}
          disabled={whatIf.isPending}
        >
          Что даст +0.5 IELTS
        </button>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => void whatIf.mutate({ sat_delta: 100 })}
          disabled={whatIf.isPending}
        >
          Что даст +100 SAT
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => setShowAll(!showAll)}>
          {showAll ? 'Скрыть' : 'Куда я прохожу сейчас'}
        </button>
      </div>

      {whatIf.data && (
        <div className="card card-pad uni__whatif">
          <span className="eyebrow">
            {whatIf.data.ielts_delta ? `+${whatIf.data.ielts_delta} IELTS` : `+${whatIf.data.sat_delta} SAT`}
          </span>
          <p style={{ margin: '10px 0 0' }}>
            Откроется программ: <b className="num">{whatIf.data.open_after - whatIf.data.open_before}</b>{' '}
            (было {whatIf.data.open_before}, станет {whatIf.data.open_after})
          </p>
          {whatIf.data.unlocked.length > 0 && (
            <ul className="uni__unlocked">
              {whatIf.data.unlocked.map((row) => (
                <li key={row.program}>
                  {row.university_name} — {row.program_name}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {showAll && (
        <>
          <h2 className="section">Программы, куда вы проходите по баллам</h2>
          {all.isLoading && <Loading />}
          <div className="grid grid--cards">
            {(all.data ?? []).map((result) => (
              <ProgramCard key={result.program} result={result} />
            ))}
            {all.data?.length === 0 && <p className="muted">Пока ни одна программа не открыта полностью.</p>}
          </div>
        </>
      )}

      <h2 className="section">Ваш список</h2>
      <div className="grid grid--cards">
        {results.map((result) => (
          <ProgramCard key={result.program} result={result} />
        ))}
        {results.length === 0 && (
          <p className="muted">Список вузов ещё не собран — обратитесь к директору по поступлению.</p>
        )}
      </div>
    </div>
  )
}
