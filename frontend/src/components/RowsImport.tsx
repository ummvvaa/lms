/**
 * Загрузка строк файлом: контакты родителей, соревнования и им подобное.
 *
 * Отличается от импорта доменных полей тем, что строка файла заводит
 * новую запись, а не правит готовую. Правила общие: сначала предпросмотр —
 * сколько заведётся, что уже есть, где ошибка построчно, — и только
 * потом применение. Отменяется загрузка целиком из истории загрузок.
 */
import { useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { Chip, DataCard, ErrorNote } from './ui'
import { t, tn } from '../i18n'
import { Button } from './ui/button'
import DataTable from './DataTable'
import { Input } from './ui/input'

export interface ImportedRow extends Record<string, unknown> {
  number: number
  status: 'new' | 'exists' | 'error'
  reason: string
}

interface RowsPreview {
  columns: Record<string, string>
  missing_columns: string[]
  total: number
  will_create: number
  already_exist: number
  with_errors: number
  rows: ImportedRow[]
  detail: string
}

export default function RowsImport({
  title,
  note,
  hint,
  previewPath,
  applyPath,
  applyLabel,
  invalidate,
  columns,
}: {
  title: string
  /** одна строка под заголовком */
  note: string
  /** какие колонки распознаются — подробности по наведению */
  hint: string
  previewPath: string
  applyPath: string
  applyLabel: string
  /** какие запросы обновить после применения */
  invalidate: string[][]
  /** что показать в строке предпросмотра */
  columns: { key: string; title: string; cell: (row: ImportedRow) => ReactNode }[]
}) {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<RowsPreview | null>(null)
  const [applied, setApplied] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function upload(selected: File) {
    setBusy(true)
    setError(null)
    setApplied(null)
    setPreview(null)
    try {
      const body = new FormData()
      body.append('file', selected)
      setPreview(await api<RowsPreview>(previewPath, { method: 'POST', body }))
      setFile(selected)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('Не удалось прочитать файл'))
    } finally {
      setBusy(false)
    }
  }

  async function apply() {
    if (!preview) return
    setBusy(true)
    try {
      const result = await api<{ detail: string }>(applyPath, {
        method: 'POST',
        body: JSON.stringify({
          rows: preview.rows.filter((row) => row.status === 'new'),
          file_name: file?.name ?? '',
        }),
      })
      setApplied(result.detail)
      setPreview(null)
      invalidate.forEach((key) => void queryClient.invalidateQueries({ queryKey: key }))
      void queryClient.invalidateQueries({ queryKey: ['imports'] })
    } catch (e) {
      setError(e instanceof Error ? e.message : t('Не удалось применить'))
    } finally {
      setBusy(false)
    }
  }

  const broken = preview?.rows.filter((row) => row.status === 'error') ?? []

  return (
    <>
      <DataCard title={title} note={note} hint={hint}>
        <label className="filepick">
          <Input
            type="file"
            accept=".csv,.xlsx,.xlsm"
            onChange={(event) => {
              const selected = event.target.files?.[0]
              if (selected) void upload(selected)
            }}
          />
          <Button size="sm" nativeButton={false} render={<span />}>
            {t('Выбрать файл')}
          </Button>
          <span className="muted filepick__name">{file ? file.name : t('Файл не выбран')}</span>
        </label>
        {busy && <p className="muted">{t('Обрабатываю…')}</p>}
        {error && <ErrorNote error={new Error(error)} />}
        {applied && (
          <Chip tone="good">
            {applied}
          </Chip>
        )}
      </DataCard>

      {preview && (
        <DataCard title={t('Что будет загружено')} note={preview.detail}>
          <div className="toolbar">
            <Chip tone="good" className="num">
              {t('Заведётся: {n}', { n: preview.will_create })}
            </Chip>
            {preview.already_exist > 0 && (
              <Chip tone="neutral" className="num">
                {t('Уже есть: {n}', { n: preview.already_exist })}
              </Chip>
            )}
            {preview.with_errors > 0 && (
              <Chip tone="warn" className="num">
                {t('С ошибками: {n}', { n: preview.with_errors })}
              </Chip>
            )}
            <span className="toolbar__spacer" />
            <Button size="sm" disabled={busy || preview.will_create === 0} onClick={() => void apply()}>
              {applyLabel}
            </Button>
          </div>

          {preview.missing_columns.length > 0 && (
            <Chip tone="warn">
              {preview.detail}
            </Chip>
          )}

          {broken.length > 0 && (
            <div className="imp__problems">
              <span className="datacard__title">{t('Что поправить в файле')}</span>
              <ul className="imp__problemlist">
                {broken.slice(0, 20).map((row) => (
                  <li key={row.number}>
                    <b>{t('Строка {number}', { number: row.number })}</b>: {row.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <DataTable
            columns={[
              { key: 'n', title: t('Строка'), width: '8%', align: 'right', cell: (row: ImportedRow) => <span className="num">{row.number}</span> },
              ...columns.map((column) => ({ key: column.key, title: column.title, width: `${Math.max(10, Math.floor(76 / Math.max(1, columns.length)))}%`, cell: (row: ImportedRow) => column.cell(row) })),
              {
                key: 'state',
                title: t('Что будет'),
                width: '16%',
                align: 'right',
                cell: (row: ImportedRow) => (
                  <Chip tone={row.status === 'new' ? 'good' : row.status === 'exists' ? 'neutral' : 'warn'} size="sm">
                    {row.status === 'new' ? t('заведётся') : row.status === 'exists' ? t('уже есть') : t('ошибка')}
                  </Chip>
                ),
              },
            ]}
            rows={preview.rows.slice(0, 20)}
            rowKey={(row) => row.number}
          />
          {preview.total > 20 && (
            <p className="muted rows__empty">
              {tn(preview.total, 'Показаны первые 20 из {n} строки — применятся все подходящие.|Показаны первые 20 из {n} строк — применятся все подходящие.|Показаны первые 20 из {n} строк — применятся все подходящие.')}
            </p>
          )}
        </DataCard>
      )}
    </>
  )
}
