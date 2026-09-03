/**
 * Список предложений своего домена.
 *
 * Раньше предложение можно было открыть только сразу после разбора: закрыл
 * вкладку — потерял. Здесь оно живёт до решения человека.
 */
import { useNavigate, useParams } from 'react-router-dom'
import { useSuggestions } from '../api/hooks'
import Empty from '../components/Empty'
import StudentQueue from '../components/StudentQueue'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import SuggestionPreview from './SuggestionPreview'
import { t } from '../i18n'
import { Button } from '../components/ui/button'
import { Badge } from '../components/ui/badge'
import { type BadgeVariant } from '../components/ui/badge'

const STATUS_TONE: Record<string, BadgeVariant> = {
  draft: 'mute',
  pending: 'warn',
  applied: 'ok',
  partially_applied: 'warn',
  rejected: 'mute',
  reverted: 'mute',
}

export default function Suggestions() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data, isLoading, error } = useSuggestions()

  if (isLoading) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />

  const rows = data?.results ?? []
  const openId = id ? Number(id) : null
  const pending = rows.filter((row) => row.status === 'pending' || row.status === 'draft').length

  return (
    <div>
      <ScreenHead
        title={t('Предложения')}
        subtitle={
          pending > 0
            ? `${pending} ждут вашего решения. Ничего не применяется само.`
            : 'Ничего не ждёт решения.'
        }
      />

      {/* очередь того, что внесли ученики, — отдельным блоком сверху:
          это решения, которые ждут именно владельца домена (фаза 37) */}
      <StudentQueue />

      {rows.length === 0 && (
        <Empty
          icon="bulb"
          title={t('Предложений пока нет')}
          what={t('Здесь ждут разборы помощника — из письма, файла или скриншота.')}
          hint={t('Ничего не применяется само: вы смотрите строки и решаете по каждой.')}
          action={t('Открыть помощника')}
          to="/assistant"
        />
      )}

      <div className="card card-pad" hidden={rows.length === 0}>
        <table className="history">
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="muted history__when">{new Date(row.created_at).toLocaleString('ru')}</td>
                <td style={{ fontWeight: 650 }}>#{row.id}</td>
                {/* на телефоне строка становится карточкой: что разобрано —
                    её заголовок (фаза 51) */}
                <td data-head="">{row.command_title || row.source_title}</td>
                <td className="num">строк: {row.changes.length}</td>
                <td>
                  <Badge variant={STATUS_TONE[row.status] ?? 'mute'}>{row.status_title}</Badge>
                </td>
                <td>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate(openId === row.id ? '/suggestions' : `/suggestions/${row.id}`)}
                  >
                    {openId === row.id ? 'Свернуть' : 'Посмотреть'}
                  </Button>
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
