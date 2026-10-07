import { useState, type ReactNode } from 'react'
import { t, tk } from '../i18n'
import { useTrack } from '../usage/context'
import { usePhone } from '../phone'
import DataTable, { type Column } from './DataTable'
import Field from './Field'
import { Chip, EmptyNote } from './ui'
import { Button } from './ui/button'
import { filterImportRows, importPage, type ImportStatus } from './importRows'

export interface ImportPreviewRow {
  key: string | number
  number: string | number
  name: string
  search: string
  status: ImportStatus
  detail?: ReactNode
  reason?: ReactNode
  actions?: ReactNode
}
const STATUS = {
  created: { title: tk('Заведётся'), tone: 'good' },
  updated: { title: tk('Обновится'), tone: 'info' },
  skipped: { title: tk('Пропуск'), tone: 'neutral' },
  error: { title: tk('С ошибкой'), tone: 'warn' },
} as const

export function ImportPagination({
  page,
  pages,
  total,
  onChange,
}: {
  page: number
  pages: number
  total: number
  onChange: (page: number) => void
}) {
  return (
    <div className="import-pagination">
      <span className="t-note num">
        {t('Страница {page} из {pages} · строк: {total}', { page, pages, total })}
      </span>
      {pages > 1 && (
        <div className="import-pagination__buttons">
          <Button variant="outline" size="sm" disabled={page === 1} onClick={() => onChange(page - 1)}>
            {t('Назад')}
          </Button>
          <Button variant="outline" size="sm" disabled={page === pages} onClick={() => onChange(page + 1)}>
            {t('Дальше')}
          </Button>
        </div>
      )}
    </div>
  )
}

/** Все строки доступны через поиск, фильтр состояния и страницы по 50. */
export default function ImportPreview({ rows }: { rows: ImportPreviewRow[] }) {
  const phone = usePhone()
  const trackFilter = useTrack('filter.change')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [requestedPage, setPage] = useState(1)
  const filtered = filterImportRows(rows, query, status)
  const page = importPage(filtered, requestedPage)
  const state = (row: ImportPreviewRow) => (
    <Chip size="sm" tone={STATUS[row.status].tone}>
      {t(STATUS[row.status].title)}
    </Chip>
  )
  const notes = (row: ImportPreviewRow) => (
    <div className="import-preview__notes">
      {row.reason && (
        <span className={row.status === 'error' ? 'import-preview__error' : 't-note'}>{row.reason}</span>
      )}
      {row.actions}
    </div>
  )
  const columns: Column<ImportPreviewRow>[] = phone
    ? [
        {
          key: 'name',
          title: t('Запись'),
          width: '100%',
          phone: 'head',
          cell: (row) => (
            <div className="import-preview__head">
              <span>
                <span className="t-note num">{row.number} · </span>
                <b>{row.name}</b>
              </span>
              {state(row)}
            </div>
          ),
        },
        {
          key: 'detail',
          title: '',
          width: '100%',
          cell: (row) => (
            <div className="import-preview__body">
              {row.detail}
              {notes(row)}
            </div>
          ),
        },
      ]
    : [
        {
          key: 'number',
          title: t('Строка'),
          width: '8%',
          cell: (row) => <span className="num">{row.number}</span>,
        },
        { key: 'name', title: t('Запись'), width: '24%', cell: (row) => <b>{row.name}</b> },
        { key: 'detail', title: t('Данные'), width: '36%', cell: (row) => row.detail },
        {
          key: 'status',
          title: t('Что будет'),
          width: '32%',
          cell: (row) => (
            <>
              {state(row)}
              {notes(row)}
            </>
          ),
        },
      ]
  return (
    <div className="import-preview">
      <div className="import-preview__filters">
        <Field
          usageFilter
          name="import-search"
          label={t('Поиск по ФИО или записи')}
          value={query}
          onChange={(value) => {
            setQuery(value)
            setPage(1)
          }}
        />
      </div>
      <div className="import-preview__counts" role="group" aria-label={t('Состояние строки')}>
        <Button
          variant={!status ? 'secondary' : 'outline'}
          size="sm"
          aria-pressed={!status}
          onClick={() => {
            if (status) trackFilter()
            setStatus('')
            setPage(1)
          }}
        >
          {t('Все строки: {n}', { n: rows.length })}
        </Button>
        {Object.entries(STATUS).map(([value, info]) => {
          const count = rows.filter((row) => row.status === value).length
          return (
            <Button
              key={value}
              variant={status === value ? 'secondary' : 'outline'}
              size="sm"
              aria-pressed={status === value}
              onClick={() => {
                if (status !== value) trackFilter()
                setStatus(value)
                setPage(1)
              }}
            >
              {t(info.title)}: <span className="num">{count}</span>
            </Button>
          )
        })}
      </div>
      {page.rows.length ? (
        <DataTable
          fit
          columns={columns}
          rows={page.rows}
          rowKey={(row) => row.key}
          rowClass={(row) => (row.status === 'error' ? 'import-preview__row--error' : undefined)}
        />
      ) : (
        <EmptyNote what={tk('Нет строк по выбранным условиям')} />
      )}
      <ImportPagination page={page.page} pages={page.pages} total={filtered.length} onChange={setPage} />
    </div>
  )
}
