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
import { t } from '../i18n'
import { Button } from './ui/button'
import ImportPreview from './ImportRowsPreview'
import ImportFile from './ImportFile'
import WizardSteps from './WizardSteps'

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
    setError(null)
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

  const step = applied ? 3 : preview ? 2 : 1
  return (
    <div className="import-flow">
      <WizardSteps stackedOnPhone steps={[t('Файл'), t('Проверка строк'), t('Готово')]} current={step} />
      <DataCard
        title={applied ? t('Готово') : preview ? t('Проверка строк') : title}
        note={file?.name || note}
        right={<Chip size="sm">{t('Шаг {step} из {total}', { step, total: 3 })}</Chip>}
      >
        {error && <ErrorNote error={new Error(error)} />}
        {busy && <p className="muted">{t('Обрабатываю…')}</p>}
        {!preview && !applied && (
          <>
            <p className="import-flow__hint">{hint}</p>
            <ImportFile file={file} disabled={busy} onSelect={(selected) => void upload(selected)} />
          </>
        )}
        {preview && (
          <>
            <p className="import-flow__hint">{preview.detail}</p>
            <ImportPreview
              rows={preview.rows.map((row) => ({
                key: row.number,
                number: row.number,
                name: String(
                  row.student_name ||
                    row.full_name ||
                    row.name ||
                    row.student_email ||
                    t('Строка {number}', { number: row.number }),
                ),
                search: Object.values(row)
                  .filter((value) => typeof value === 'string')
                  .join(' '),
                status: row.status === 'new' ? 'created' : row.status === 'exists' ? 'skipped' : 'error',
                detail: (
                  <div className="import-preview__values">
                    {columns.map((column) => (
                      <span key={column.key}>
                        <span className="t-note">{column.title}: </span>
                        {column.cell(row)}
                      </span>
                    ))}
                  </div>
                ),
                reason: row.reason,
              }))}
            />
            <div className="import-flow__actions">
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => {
                  setPreview(null)
                  setError(null)
                }}
              >
                {t('Назад')}
              </Button>
              <Button disabled={busy || preview.will_create === 0} onClick={() => void apply()}>
                {applyLabel}
              </Button>
            </div>
          </>
        )}
        {applied && (
          <>
            <Chip tone="good" className="badge--sentence">
              {applied}
            </Chip>
            <div className="import-flow__actions">
              <Button
                variant="outline"
                onClick={() => {
                  setApplied(null)
                  setFile(null)
                  setError(null)
                }}
              >
                {t('Загрузить ещё файл')}
              </Button>
            </div>
          </>
        )}
      </DataCard>
    </div>
  )
}
