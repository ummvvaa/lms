/**
 * Список предложений своего домена.
 *
 * Раньше предложение можно было открыть только сразу после разбора: закрыл
 * вкладку — потерял. Здесь оно живёт до решения человека.
 */
import { useNavigate, useParams } from 'react-router-dom'
import { useSuggestions } from '../api/hooks'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import SuggestionPreview from './SuggestionPreview'

const STATUS_TITLE: Record<string, string> = {
  draft: 'черновик',
  pending: 'ждёт решения',
  applied: 'применено',
  partially_applied: 'применено частично',
  rejected: 'отклонено',
  reverted: 'откачено',
}

const STATUS_TONE: Record<string, string> = {
  draft: 'chip-mute',
  pending: 'chip-warn',
  applied: 'chip-ok',
  partially_applied: 'chip-warn',
  rejected: 'chip-mute',
  reverted: 'chip-mute',
}

const SOURCE_TITLE: Record<string, string> = {
  paste: 'вставка текста',
  file: 'файл',
  manual: 'руками',
  sync: 'фоновая сверка',
}

export default function Suggestions() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data, isLoading, error } = useSuggestions()

  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />

  const rows = data?.results ?? []
  const openId = id ? Number(id) : null
  const pending = rows.filter((row) => row.status === 'pending' || row.status === 'draft').length

  return (
    <div>
      <ScreenHead
        emoji="👁"
        title="Предложения"
        subtitle={
          pending > 0
            ? `${pending} ждут вашего решения. Ничего не применяется само.`
            : 'Ничего не ждёт решения.'
        }
      />

      {rows.length === 0 && (
        <p className="muted">
          Пока пусто. Предложения появляются после разбора текста или файла в «Помощнике».
        </p>
      )}

      <div className="card card-pad">
        <table className="history">
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="muted history__when">{new Date(row.created_at).toLocaleString('ru')}</td>
                <td style={{ fontWeight: 650 }}>#{row.id}</td>
                <td>{SOURCE_TITLE[row.source_type] ?? row.source_type}</td>
                <td className="num">строк: {row.changes.length}</td>
                <td>
                  <span className={`chip ${STATUS_TONE[row.status] ?? 'chip-mute'}`}>
                    {STATUS_TITLE[row.status] ?? row.status}
                  </span>
                </td>
                <td>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => navigate(openId === row.id ? '/suggestions' : `/suggestions/${row.id}`)}
                  >
                    {openId === row.id ? 'Свернуть' : 'Посмотреть'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {openId !== null && <SuggestionPreview id={openId} />}
    </div>
  )
}
