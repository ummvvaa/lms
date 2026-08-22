/** Дайджест на сегодня: что изменилось в вашем домене и что ждёт решения. */
import { useNavigate } from 'react-router-dom'
import { useDigest } from '../api/hooks'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'

const SOURCE_TITLE: Record<string, string> = {
  manual: 'руками',
  import: 'импорт',
  ai: 'ИИ',
  sync: 'сверка',
  student_onboarding: 'анкета ученика',
}

export default function Digest() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDigest()
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  if (!data.domain) {
    return <ScreenHead emoji="📰" title="Дайджест" subtitle="У вашей роли нет домена." />
  }

  return (
    <div>
      <ScreenHead
        emoji="📰"
        title="Дайджест на сегодня"
        subtitle={`Домен «${data.domain_title}»: изменений за сутки — ${data.changes}.`}
      />

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
              <span className="person__name">
                Предложение #{row.id} · {row.command || row.source_type}
              </span>
              <span className="chip chip-warn num">строк: {row.n}</span>
            </button>
          ))}
        </div>
      )}

      <div className="grid grid--two">
        <div className="card card-pad">
          <span className="eyebrow">Что правили чаще всего</span>
          {data.by_field.length === 0 && <p className="muted">За сутки изменений не было.</p>}
          {data.by_field.map((row) => (
            <div key={row.field_name} className="row-between" style={{ padding: '6px 0', fontSize: 13 }}>
              <span>{row.field_name}</span>
              <b className="num">{row.n}</b>
            </div>
          ))}
        </div>

        <div className="card card-pad">
          <span className="eyebrow">Откуда пришли изменения</span>
          {Object.entries(data.sources).map(([source, n]) => (
            <div key={source} className="row-between" style={{ padding: '6px 0', fontSize: 13 }}>
              <span>{SOURCE_TITLE[source] ?? source}</span>
              <b className="num">{n}</b>
            </div>
          ))}
          {Object.keys(data.sources).length === 0 && <p className="muted">Пусто.</p>}
        </div>
      </div>

      <h2 className="section">Последние изменения</h2>
      <div className="card card-pad">
        <table className="history">
          <tbody>
            {data.recent.map((row, i) => (
              <tr key={i}>
                <td className="muted history__when">{new Date(row.created_at).toLocaleString('ru')}</td>
                <td className="history__field">{row.field_name}</td>
                <td className="num">
                  <span className="muted">{row.old_value || '—'}</span> → <b>{row.new_value || '—'}</b>
                </td>
                <td>
                  <span className="chip chip-mute">{SOURCE_TITLE[row.source] ?? row.source}</span>
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
