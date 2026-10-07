import { useState } from 'react'
import DataTable from '../components/DataTable'
import ExportButton from '../components/ExportPreview'
import Field from '../components/Field'
import { Segmented, StatRow } from '../components/patterns'
import { DataCard, EmptyNote, ErrorNote, Kpi, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t, tk } from '../i18n'
import { formatDateTime } from '../lib/format'
import { useTrack } from '../usage/context'
import { usageParams, useUsageSummary } from '../usage/queries'
import { useUsageRegistry } from '../usage/UsageProvider'
import type { UsageDimension, UsageFilters, UsageSummary } from '../usage/types'
import './usage.css'

const DIMENSIONS: { value: UsageDimension; label: string; column: string }[] = [
  { value: 'action', label: tk('По действиям'), column: tk('Действие') },
  { value: 'user', label: tk('По пользователям'), column: tk('Пользователь') },
  { value: 'role', label: tk('По ролям'), column: tk('Роль') },
  { value: 'day', label: tk('По дням'), column: tk('День') },
]
type SummaryRow = UsageSummary['results'][number]

export default function Usage() {
  const registry = useUsageRegistry()
  const [filters, setFilters] = useState<UsageFilters>({ by: 'action' })
  const [page, setPage] = useState(1)
  const summary = useUsageSummary(filters, page, Boolean(registry.data?.can_read))
  const trackFilter = useTrack('filter.change')
  const data = summary.data
  const change = (patch: Partial<UsageFilters>) => {
    setFilters((current) => ({ ...current, ...patch }))
    setPage(1)
  }
  const reset = () => {
    if ([filters.from, filters.to, filters.role, filters.action, filters.screen, filters.user].some(Boolean))
      trackFilter()
    setFilters({ by: filters.by })
    setPage(1)
  }
  const dimension = DIMENSIONS.find((item) => item.value === filters.by)!
  const period = { from: filters.from || data?.period.from || '', to: filters.to || data?.period.to || '' }
  const exportQuery = usageParams({ ...filters, ...period }).toString()
  const totalPages = Math.max(1, Math.ceil((data?.count ?? 0) / 50))

  return (
    <div className="usage-screen">
      <ScreenHead
        title={t('Использование')}
        subtitle={t('Действия в системе за выбранный период. Даты и время — по Алматы.')}
        actions={
          <ExportButton
            path={`/usage/export/?${exportQuery}`}
            fallback="usage.xlsx"
            title={tk('Использование')}
            label={tk('Скачать XLSX')}
            disabled={!data || summary.isFetching}
          />
        }
      />
      <DataCard title={t('Период и фильтры')}>
        <div className="usage-screen__filters">
          <Field
            usageFilter
            kind="date"
            name="usage-from"
            label={t('с')}
            value={period.from}
            onChange={(value) => change({ from: value, to: period.to })}
          />
          <Field
            usageFilter
            kind="date"
            name="usage-to"
            label={t('по')}
            value={period.to}
            onChange={(value) => change({ from: period.from, to: value })}
          />
          <Field
            usageFilter
            kind="select"
            name="usage-role"
            label={t('Роль')}
            value={filters.role ?? ''}
            onChange={(value) => change({ role: value })}
            options={[
              { value: '', title: t('Все роли') },
              ...(registry.data?.roles ?? []).map((role) => ({ value: role.key, title: role.title })),
            ]}
          />
          <Field
            usageFilter
            kind="select"
            name="usage-action"
            label={t('Действие')}
            value={filters.action ?? ''}
            onChange={(value) => change({ action: value })}
            options={[
              { value: '', title: t('Все действия') },
              ...(registry.data?.actions ?? []).map((action) => ({ value: action.key, title: action.title })),
            ]}
          />
          <Field
            usageFilter
            kind="select"
            name="usage-screen"
            label={t('Экран')}
            value={filters.screen ?? ''}
            onChange={(value) => change({ screen: value })}
            options={[
              { value: '', title: t('Все экраны') },
              ...(registry.data?.screens ?? []).map((screen) => ({ value: screen.key, title: screen.title })),
            ]}
          />
          <div className="usage-screen__reset">
            <Button variant="ghost" size="sm" onClick={reset}>
              {t('Сбросить фильтры')}
            </Button>
          </div>
        </div>
      </DataCard>
      {registry.isError && <ErrorNote error={registry.error} />}
      {summary.isError && <ErrorNote error={summary.error} />}
      {(registry.isLoading || summary.isLoading) && <Loading kind="table" />}
      {data && (
        <>
          <StatRow>
            <Kpi label={t('Активных пользователей')} value={data.cards.active_users} />
            <Kpi label={t('Действий')} value={data.cards.actions} />
            <Kpi
              label={t('Самое частое действие')}
              value={data.cards.most_frequent?.count ?? null}
              note={data.cards.most_frequent?.title}
              none={t('Действий нет')}
            />
            <Kpi
              label={t('Ни разу не входили')}
              value={data.cards.never_logged_in}
              note={t('Сейчас, среди активных учётных записей')}
            />
          </StatRow>
          <DataCard title={t('Сводка')} count={data.count}>
            <Segmented
              label={t('Разрез сводки')}
              value={filters.by}
              onChange={(by) => change({ by })}
              items={DIMENSIONS.map((item) => ({ value: item.value, label: t(item.label) }))}
            />
            <div className="usage-screen__table">
              {data.results.length === 0 ? (
                <EmptyNote what={tk('За выбранный период действий нет')} />
              ) : (
                <DataTable
                  fit
                  columns={[
                    {
                      key: 'title',
                      title: t(dimension.column),
                      width: '40%',
                      phone: 'head',
                      cell: (row: SummaryRow) => <b>{row.title}</b>,
                    },
                    {
                      key: 'count',
                      title: t('Действий'),
                      width: '16%',
                      align: 'right',
                      cell: (row: SummaryRow) => <span className="num">{row.count}</span>,
                    },
                    {
                      key: 'users',
                      title: t('Пользователей'),
                      width: '18%',
                      align: 'right',
                      cell: (row: SummaryRow) => <span className="num">{row.users}</span>,
                    },
                    {
                      key: 'last',
                      title: t('Последнее действие'),
                      width: '26%',
                      cell: (row: SummaryRow) => (
                        <span className="num">{row.last_at ? formatDateTime(row.last_at) : t('нет')}</span>
                      ),
                    },
                  ]}
                  rows={data.results}
                  rowKey={(row) => row.key}
                />
              )}
            </div>
            {data.count > 50 && (
              <div className="usage-screen__pages">
                <span className="t-note num">
                  {t('Страница {page} из {pages}', { page, pages: totalPages })}
                </span>
                <div className="usage-screen__page-buttons">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!data.previous}
                    onClick={() => setPage((current) => current - 1)}
                  >
                    {t('Назад')}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!data.next}
                    onClick={() => setPage((current) => current + 1)}
                  >
                    {t('Дальше')}
                  </Button>
                </div>
              </div>
            )}
          </DataCard>
        </>
      )}
    </div>
  )
}
