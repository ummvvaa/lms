/**
 * Расходы на модель — экран администратора.
 *
 * Видно, сколько потрачено с начала месяца, кто и на что тратит.
 * При исчерпании лимита операции отключаются, и здесь об этом сказано
 * прямо — чтобы не искать причину по логам.
 *
 * Вид — по макету: период в шапке, четыре показателя, ниже на две трети
 * последние вызовы, справа — на что и кто тратит полосами долей.
 */
import { useState } from 'react'
import { useSpendReport, type SpendReport } from '../api/hooks'
import DataTable from '../components/DataTable'
import { Segmented, ShowAll } from '../components/patterns'
import { Bar, Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../components/ui'
import { t, tn } from '../i18n'
import { formatDateTime } from '../lib/format'
import './spend.css'

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

  // доли полос — от общей суммы; пока всё бесплатно (ноль долларов) — от числа вызовов
  const share = (rows: { cost: number; calls: number }[]) => {
    const cost = rows.reduce((sum, row) => sum + row.cost, 0)
    const calls = rows.reduce((sum, row) => sum + row.calls, 0)
    return (row: { cost: number; calls: number }) => (cost > 0 ? (row.cost / cost) * 100 : calls > 0 ? (row.calls / calls) * 100 : 0)
  }
  const purposeShare = share(data.by_purpose)
  const roleShare = share(data.by_role)

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Расходы на модель')}
        subtitle={data.detail || undefined}
        actions={<Segmented<string> value={String(days)} onChange={(next) => setDays(Number(next))} label={t('Период')} items={[7, 30, 90].map((n) => ({ value: String(n), label: tn(n, '{n} день|{n} дня|{n} дней') }))} />}
      />

      <div className="lay-4">
        <Kpi label={t('Расход за месяц')} value={money(data.spent_this_month)} note={data.limit > 0 ? t('из {limit}', { limit: money(data.limit) }) : t('лимит не задан')} tone={data.available ? 'neutral' : 'bad'} action={data.limit > 0 ? undefined : { label: t('Задать лимит'), to: '/school-settings?section=ai' }} />
        <Kpi label={t('Использовано лимита')} value={data.limit > 0 ? `${data.percent}%` : null} none={t('без лимита')} chip={data.limit > 0 ? { label: data.percent >= 90 ? t('лимит почти исчерпан') : data.percent >= 70 ? t('ближе к лимиту') : t('в пределах лимита'), tone: data.percent >= 90 ? 'bad' : data.percent >= 70 ? 'warn' : 'good' } : undefined} />
        <Kpi label={tn(days, 'Вызовов за {n} день|Вызовов за {n} дня|Вызовов за {n} дней')} value={data.calls || null} none={t('нет')} />
        <Kpi label={t('Неудачных')} value={data.failures || null} none={t('нет')} chip={data.calls > 0 ? (data.failures > 0 ? { label: t('есть сбои'), tone: 'warn' } : { label: t('всё работает'), tone: 'good' }) : undefined} />
      </div>

      <div className="lay-main">
        <DataCard className="card--beam" title={t('Последние вызовы')} count={data.recent.length || undefined} empty={data.calls === 0 && t('модель ещё не вызывали — платить не за что')}>
          <DataTable
            columns={[
              { key: 'when', title: t('Когда'), width: '24%', cell: (row: RecentCall) => <span className="num aispend__nowrap">{formatDateTime(row.created_at)}</span>, sortBy: (row: RecentCall) => row.created_at },
              { key: 'who', title: t('Кто'), width: '20%', cell: (row: RecentCall) => <span><b>{row.actor_name}</b><span className="t-note"> · {row.role_title}</span></span> },
              { key: 'what', title: t('Операция'), width: '18%', cell: (row: RecentCall) => row.purpose_title },
              { key: 'tokens', title: t('Токенов'), width: '13%', align: 'right', cell: (row: RecentCall) => <span className="num">{row.tokens}</span>, sortBy: (row: RecentCall) => row.tokens },
              { key: 'cost', title: t('Стоимость'), width: '14%', align: 'right', cell: (row: RecentCall) => <span className="num">{money(row.cost)}</span>, sortBy: (row: RecentCall) => row.cost },
              { key: 'ok', title: '', width: '11%', cell: (row: RecentCall) => (row.is_ok ? <Chip tone="good" size="sm">{t('успех')}</Chip> : <Chip tone="bad" size="sm">{row.error || t('сбой')}</Chip>) },
            ]}
            rows={data.recent}
            rowKey={(row) => row.id}
            limit={20}
          />
        </DataCard>
        <div className="lay-stack">
          <DataCard title={t('На что')} empty={data.by_purpose.length === 0 && t('вызовов не было')}>
            <div className="aispend__bars">
              <ShowAll>
                {data.by_purpose.map((row: PurposeSpend) => (
                  <div key={row.purpose} className="aispend__bar">
                    <div className="aispend__barhead">
                      <b>{row.purpose_title}</b>
                      <span className="num">{money(row.cost)}</span>
                    </div>
                    <Bar percent={purposeShare(row)} />
                    <span className="t-note num">{t('Вызовов: {calls} · токенов: {tokens}', { calls: row.calls, tokens: row.tokens })}</span>
                  </div>
                ))}
              </ShowAll>
            </div>
          </DataCard>
          <DataCard title={t('Кто тратит')} empty={data.by_role.length === 0 && t('вызовов не было')}>
            <div className="aispend__bars">
              <ShowAll>
                {data.by_role.map((row: RoleSpend) => (
                  <div key={row.role} className="aispend__bar">
                    <div className="aispend__barhead">
                      <b>{row.role_title}</b>
                      <span className="num">{money(row.cost)}</span>
                    </div>
                    <Bar percent={roleShare(row)} />
                    <span className="t-note num">{t('Вызовов: {calls}', { calls: row.calls })}</span>
                  </div>
                ))}
              </ShowAll>
            </div>
          </DataCard>
        </div>
      </div>
    </div>
  )
}
