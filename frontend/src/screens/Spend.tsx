/**
 * Расходы на модель — экран администратора.
 *
 * Видно, сколько потрачено с начала месяца, кто и на что тратит.
 * При исчерпании лимита операции отключаются, и здесь об этом сказано
 * прямо — чтобы не искать причину по логам.
 */
import { useState } from 'react'
import { useSpendReport, type SpendReport } from '../api/hooks'
import DataTable from '../components/DataTable'
import { Segmented, StatRow } from '../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../components/ui'
import { t, tn } from '../i18n'
import { formatDateTime } from '../lib/format'
import './academics/academics.css'

type RecentCall = SpendReport['recent'][number]
type RoleSpend = SpendReport['by_role'][number]
type PurposeSpend = SpendReport['by_purpose'][number]

const money = (value: number) => `$${value.toFixed(2)}`

export default function Spend() {
  const [days, setDays] = useState(30)
  const report = useSpendReport(days)

  if (report.isLoading) return <Loading kind="table" />
  if (report.isError) return <ErrorNote error={report.error} />
  if (!report.data) return null

  const data = report.data

  return (
    <div>
      <ScreenHead
        title={t('Расходы на модель')}
      />

      <StatRow>
        <Kpi label={t('Расход за месяц')} value={money(data.spent_this_month)} note={data.limit > 0 ? t('из {limit}', { limit: money(data.limit) }) : t('лимит не задан')} tone={data.available ? 'neutral' : 'bad'} action={data.limit > 0 ? undefined : { label: t('Задать лимит'), to: '/school-settings?section=ai' }} />
        <Kpi label={t('Использовано лимита')} value={data.limit > 0 ? `${data.percent}%` : null} none={t('без лимита')} tone={data.percent >= 90 ? 'bad' : data.percent >= 70 ? 'warn' : 'good'} />
        <Kpi label={tn(days, 'Вызовов за {n} день|Вызовов за {n} дня|Вызовов за {n} дней')} value={data.calls || null} none={t('нет')} />
        <Kpi label={t('Неудачных')} value={data.failures || null} none={t('нет')} tone={data.failures > 0 ? 'warn' : 'neutral'} />
      </StatRow>

      <div className="acad__toolbar">
        <Segmented<string> value={String(days)} onChange={(next) => setDays(Number(next))} label={t('Период')} items={[7, 30, 90].map((n) => ({ value: String(n), label: tn(n, '{n} день|{n} дня|{n} дней') }))} />
        <span className="t-note">{data.detail}</span>
      </div>

      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard title={t('Последние вызовы')} count={data.recent.length || undefined} empty={data.calls === 0 && t('модель ещё не вызывали — платить не за что')}>
            <DataTable
              columns={[
                { key: 'when', title: t('Когда'), width: '16%', cell: (row: RecentCall) => <span className="num">{formatDateTime(row.created_at)}</span>, sortBy: (row: RecentCall) => row.created_at },
                { key: 'who', title: t('Кто'), width: '22%', cell: (row: RecentCall) => <><b>{row.actor_name}</b><span className="t-note"> · {row.role_title}</span></> },
                { key: 'what', title: t('Операция'), width: '22%', cell: (row: RecentCall) => row.purpose_title },
                { key: 'tokens', title: t('Токенов'), width: '12%', align: 'right', cell: (row: RecentCall) => <span className="num">{row.tokens}</span>, sortBy: (row: RecentCall) => row.tokens },
                { key: 'cost', title: t('Стоимость'), width: '12%', align: 'right', cell: (row: RecentCall) => <span className="num">{money(row.cost)}</span>, sortBy: (row: RecentCall) => row.cost },
                { key: 'ok', title: '', width: '16%', cell: (row: RecentCall) => (row.is_ok ? <Chip tone="good" size="sm">{t('успех')}</Chip> : <Chip tone="bad" size="sm">{row.error || t('сбой')}</Chip>) },
              ]}
              rows={data.recent}
              rowKey={(row) => row.id}
              limit={20}
            />
          </DataCard>
        </div>
        <div className="acad__stack">
          <DataCard title={t('Кто тратит')} empty={data.by_role.length === 0 && t('вызовов не было')}>
            <DataTable
              columns={[
                { key: 'role', title: t('Роль'), width: '50%', cell: (row: RoleSpend) => row.role_title },
                { key: 'calls', title: t('Вызовов'), width: '20%', align: 'right', cell: (row: RoleSpend) => <span className="num">{row.calls}</span>, sortBy: (row: RoleSpend) => row.calls },
                { key: 'cost', title: t('Стоимость'), width: '30%', align: 'right', cell: (row: RoleSpend) => <span className="num">{money(row.cost)}</span>, sortBy: (row: RoleSpend) => row.cost },
              ]}
              rows={data.by_role}
              rowKey={(row) => row.role}
            />
          </DataCard>
          <DataCard title={t('На что')} empty={data.by_purpose.length === 0 && t('вызовов не было')}>
            <DataTable
              columns={[
                { key: 'purpose', title: t('Операция'), width: '40%', cell: (row: PurposeSpend) => row.purpose_title },
                { key: 'calls', title: t('Вызовов'), width: '18%', align: 'right', cell: (row: PurposeSpend) => <span className="num">{row.calls}</span>, sortBy: (row: PurposeSpend) => row.calls },
                { key: 'tokens', title: t('Токенов'), width: '20%', align: 'right', cell: (row: PurposeSpend) => <span className="num">{row.tokens}</span>, sortBy: (row: PurposeSpend) => row.tokens },
                { key: 'cost', title: t('Стоимость'), width: '22%', align: 'right', cell: (row: PurposeSpend) => <span className="num">{money(row.cost)}</span>, sortBy: (row: PurposeSpend) => row.cost },
              ]}
              rows={data.by_purpose}
              rowKey={(row) => row.purpose}
            />
          </DataCard>
        </div>
      </div>
    </div>
  )
}
