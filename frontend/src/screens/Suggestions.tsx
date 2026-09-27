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
import DataTable from '../components/DataTable'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead, type Tone } from '../components/ui'
import SuggestionPreview from './SuggestionPreview'
import { t } from '../i18n'
import { Button } from '../components/ui/button'

const STATUS_TONE: Record<string, Tone> = {
  draft: 'neutral',
  pending: 'warn',
  applied: 'good',
  partially_applied: 'warn',
  rejected: 'neutral',
  reverted: 'neutral',
}

type SuggestionRow = NonNullable<ReturnType<typeof useSuggestions>['data']>['results'][number]

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

      {rows.length > 0 && (
        <DataCard title={t('Разборы')} count={rows.length}>
          <DataTable
            columns={[
              { key: 'when', title: t('Когда'), width: '16%', cell: (row: SuggestionRow) => <span className="num">{new Date(row.created_at).toLocaleString('ru', { dateStyle: 'short', timeStyle: 'short' })}</span>, sortBy: (row: SuggestionRow) => row.created_at },
              { key: 'id', title: '№', width: '8%', align: 'right', cell: (row: SuggestionRow) => <span className="num">{row.id}</span>, sortBy: (row: SuggestionRow) => row.id },
              { key: 'what', title: t('Что разобрано'), width: '30%', cell: (row: SuggestionRow) => <b>{row.command_title || row.source_title}</b> },
              { key: 'rows', title: t('Строк'), width: '10%', align: 'right', cell: (row: SuggestionRow) => <span className="num">{row.changes.length}</span>, sortBy: (row: SuggestionRow) => row.changes.length },
              { key: 'status', title: t('Статус'), width: '18%', cell: (row: SuggestionRow) => <Chip tone={STATUS_TONE[row.status] ?? 'neutral'} size="sm">{row.status_title}</Chip>, sortBy: (row: SuggestionRow) => row.status },
              {
                key: 'open',
                title: '',
                width: '18%',
                align: 'right',
                cell: (row: SuggestionRow) => (
                  <Button variant="secondary" size="sm" onClick={() => navigate(openId === row.id ? '/suggestions' : `/suggestions/${row.id}`)}>
                    {openId === row.id ? t('Свернуть') : t('Посмотреть')}
                  </Button>
                ),
              },
            ]}
            rows={rows}
            rowKey={(row) => row.id}
            selected={(row) => row.id === openId}
          />
        </DataCard>
      )}

      {openId !== null && <SuggestionPreview id={openId} />}
    </div>
  )
}
