/** Дайджест на сегодня: сводка словами и то, что ждёт решения.
 *
 * Текст сводки приходит с сервера готовым — здесь он только показывается.
 * Собирать фразы из имён полей на фронте нельзя (фаза 17).
 */
import { useNavigate } from 'react-router-dom'
import { useDigest } from '../api/hooks'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'

export default function Digest() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDigest()
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  if (!data.domain) {
    return <ScreenHead title="Дайджест" subtitle={data.headline} />
  }

  return (
    <div>
      <ScreenHead title="Дайджест на сегодня" subtitle={data.headline} />

      <div className="card card-pad" style={{ marginBottom: 16 }}>
        <span className="eyebrow">Коротко</span>
        <ul className="digest">
          {data.lines.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      </div>

      {data.pending.length > 0 && (
        <div className="card card-pad" style={{ marginBottom: 16, borderColor: 'var(--brand)' }}>
          <span className="eyebrow">Ждёт вашего решения</span>
          {data.pending.map((row) => (
            <button
              key={row.id}
              className="person"
              style={{ width: '100%' }}
              onClick={() => navigate(`/suggestions/${row.id}`)}
            >
              <span className="person__name">{row.title}</span>
              <span className="chip chip-warn num">{row.text}</span>
            </button>
          ))}
        </div>
      )}

      <h2 className="section">Последние изменения</h2>
      <div className="card card-pad">
        <table className="history">
          <tbody>
            {data.recent.map((row, i) => (
              <tr key={i}>
                <td className="muted history__when">{new Date(row.created_at).toLocaleString('ru')}</td>
                <td className="history__field">{row.field_title}</td>
                <td className="num">
                  <span className="muted">{row.old_display || '—'}</span> → <b>{row.new_display || '—'}</b>
                </td>
                <td>
                  <span className="chip chip-mute">{row.source_title}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.recent.length === 0 && <p className="muted">Пока ничего не менялось.</p>}
      </div>
    </div>
  )
}
