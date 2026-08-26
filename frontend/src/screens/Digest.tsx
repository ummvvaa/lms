/** Дайджест на сегодня: сводка словами и то, что ждёт решения.
 *
 * Текст сводки приходит с сервера готовым — здесь он только показывается.
 * Собирать фразы из имён полей на фронте нельзя (фаза 17).
 */
import { useNavigate } from 'react-router-dom'
import { useDigest } from '../api/hooks'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import { t } from '../i18n'
import { Badge } from '../components/ui/badge'

export default function Digest() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDigest()
  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  if (!data.domain) {
    return <ScreenHead title={t('Дайджест')} subtitle={data.headline} />
  }

  return (
    <div>
      <ScreenHead title={t('Дайджест на сегодня')} subtitle={data.headline} />

      <div className="card card-pad" style={{ marginBottom: 16 }}>
        <span className="eyebrow">{t('Что изменилось со вчера')}</span>
        <ul className="digest">
          {data.lines.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      </div>

      {data.pending.length > 0 && (
        <div className="card card-pad" style={{ marginBottom: 16, borderColor: 'var(--brand)' }}>
          <span className="eyebrow">{t('Ждёт вашего решения')}</span>
          {data.pending.map((row) => (
            <button
              key={row.id}
              className="person"
              style={{ width: '100%' }}
              onClick={() => navigate(`/suggestions/${row.id}`)}
            >
              <span className="person__name">{row.title}</span>
              <Badge variant="warn" className="num">
                {row.text}
              </Badge>
            </button>
          ))}
        </div>
      )}

      <h2 className="section">{t('Последние изменения')}</h2>
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
                  <Badge variant="mute">{row.source_title}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.recent.length === 0 && <p className="muted">{t('Пока ничего не менялось.')}</p>}
      </div>
    </div>
  )
}
