/**
 * Список предложений своего домена.
 *
 * Раньше предложение можно было открыть только сразу после разбора: закрыл
 * вкладку — потерял. Здесь оно живёт до решения человека.
 */
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { useSuggestions } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import Empty from '../components/Empty'
import StudentQueue from '../components/StudentQueue'
import DataTable from '../components/DataTable'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead, type Tone } from '../components/ui'
import { namesLine, Segmented } from '../components/patterns'
import SuggestionPreview from './SuggestionPreview'
import { t, tn } from '../i18n'
import { Button } from '../components/ui/button'
import { formatDateTime } from '../lib/format'

const STATUS_TONE: Record<string, Tone> = {
  draft: 'neutral',
  pending: 'warn',
  applied: 'good',
  partially_applied: 'warn',
  rejected: 'neutral',
  reverted: 'neutral',
}

type SuggestionRow = NonNullable<ReturnType<typeof useSuggestions>['data']>['results'][number]

/** Фильтр списка по решению: ждут, применены, отклонены или отменены, все. */
type Decision = 'wait' | 'applied' | 'rejected' | 'all'

const DECISION_OF: Record<SuggestionRow['status'], Exclude<Decision, 'all'>> = {
  draft: 'wait',
  pending: 'wait',
  applied: 'applied',
  partially_applied: 'applied',
  rejected: 'rejected',
  reverted: 'rejected',
}

/** Кого касается разбор: ученики из его строк, без повторов, одной строкой. */
function whoOf(row: SuggestionRow): string {
  const names = [...new Set(row.changes.map((change) => change.student_name).filter((name): name is string => Boolean(name)))]
  return names.length ? namesLine(names) : t('нет')
}

export default function Suggestions() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { me } = useAuth()
  const { data, isLoading, error } = useSuggestions()
  // по умолчанию — все: открытый по ссылке разбор не должен прятаться за фильтром
  const [decision, setDecision] = useState<Decision>('all')

  if (isLoading) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />

  const rows = data?.results ?? []
  const openId = id ? Number(id) : null
  const pending = rows.filter((row) => row.status === 'pending' || row.status === 'draft').length
  const countOf = (value: Decision) => rows.filter((row) => value === 'all' || DECISION_OF[row.status] === value).length
  const shown = rows.filter((row) => decision === 'all' || DECISION_OF[row.status] === decision)
  const decisions: { value: Decision; label: string }[] = [
    { value: 'wait', label: t('Ждут решения') },
    { value: 'applied', label: t('Применены') },
    { value: 'rejected', label: t('Отклонены') },
    { value: 'all', label: t('Все') },
  ]

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Предложения')}
        subtitle={
          pending > 0
            ? tn(
                pending,
                '{n} ждёт вашего решения. Ничего не применяется само.|{n} ждут вашего решения. Ничего не применяется само.|{n} ждут вашего решения. Ничего не применяется само.',
              )
            : t('Ничего не ждёт решения.')
        }
      />

      {/* очередь того, что внесли ученики, — отдельным блоком сверху:
          это решения, которые ждут именно владельца домена (фаза 37).
          У администратора здесь только разборы (решение владельца, 27.09.2026) */}
      {me?.role !== 'admin' && <StudentQueue />}

      {rows.length === 0 && (
        <Empty
          icon="bulb"
          title={t('Предложений пока нет')}
          what={t('Здесь ждут разборы: что изменится в данных, строка за строкой.')}
          hint={t('Ничего не применяется само: вы смотрите строки и решаете по каждой.')}
        />
      )}

      {rows.length > 0 && (
        <div className="filters">
          <Segmented
            label={t('Статус')}
            value={decision}
            onChange={setDecision}
            items={decisions.map((item) => ({
              value: item.value,
              label: (
                <>
                  {item.label}
                  <span className="tabs__n num">{countOf(item.value)}</span>
                </>
              ),
            }))}
          />
        </div>
      )}

      {rows.length > 0 && (
        <DataCard title={t('Разборы')} count={shown.length} empty={shown.length === 0 && t('По этим фильтрам ничего нет')}>
          <DataTable
            columns={[
              { key: 'when', title: t('Когда'), width: '14%', cell: (row: SuggestionRow) => <span className="num whitespace-nowrap">{formatDateTime(row.created_at)}</span>, sortBy: (row: SuggestionRow) => row.created_at },
              { key: 'id', title: '№', width: '7%', align: 'right', cell: (row: SuggestionRow) => <span className="num t-note">{row.id}</span>, sortBy: (row: SuggestionRow) => row.id },
              { key: 'what', title: t('Источник'), width: '25%', cell: (row: SuggestionRow) => <b>{row.command_title || row.source_title}</b> },
              { key: 'who', title: t('Кого затронет'), width: '22%', cell: (row: SuggestionRow) => whoOf(row) },
              { key: 'rows', title: t('Строк'), width: '8%', align: 'right', cell: (row: SuggestionRow) => <span className="num">{row.changes.length}</span>, sortBy: (row: SuggestionRow) => row.changes.length },
              { key: 'status', title: t('Статус'), width: '12%', cell: (row: SuggestionRow) => <Chip tone={STATUS_TONE[row.status] ?? 'neutral'} size="sm">{row.status_title}</Chip>, sortBy: (row: SuggestionRow) => row.status },
              {
                key: 'open',
                title: '',
                width: '12%',
                align: 'right',
                cell: (row: SuggestionRow) => (
                  <Button variant="secondary" size="sm" onClick={() => navigate(openId === row.id ? '/suggestions' : `/suggestions/${row.id}`)}>
                    {openId === row.id ? t('Свернуть') : t('Посмотреть')}
                  </Button>
                ),
              },
            ]}
            rows={shown}
            rowKey={(row) => row.id}
            selected={(row) => row.id === openId}
          />
        </DataCard>
      )}

      {openId !== null && <SuggestionPreview id={openId} />}
    </div>
  )
}
