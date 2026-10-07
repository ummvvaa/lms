import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { t } from '../i18n'
import { Chip, DataCard, ErrorNote } from './ui'
import { Button } from './ui/button'
import { SelectField } from './SelectField'
import DataTable from './DataTable'
import ImportFile from './ImportFile'
import ImportPreview from './ImportRowsPreview'
import WizardSteps from './WizardSteps'
import type { ImportStatus } from './importRows'

interface Opened {
  columns: string[]
  total_rows: number
  targets: Record<string, string>
}
interface Report {
  created: number
  updated: number
  unchanged: number
  errors: string[]
  rows: {
    row: number
    program?: string
    name?: string
    state: string
    status: ImportStatus
    reason: string
  }[]
}
interface Props {
  path: string
  title: string
  note: string
  hint: string
  missing: string
  required: string[]
  invalidate: string[][]
  resultText: (report: Report) => string
}

/** Два справочника используют одинаковые шаги; применение отправляет исходный файл и соответствия. */
export default function MappedImport({
  path,
  title,
  note,
  hint,
  missing,
  required,
  invalidate,
  resultText,
}: Props) {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [opened, setOpened] = useState<Opened | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [report, setReport] = useState<Report | null>(null)
  const [applied, setApplied] = useState<string | null>(null)
  const [step, setStep] = useState(1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function send(selected: File, extra: Record<string, string> = {}) {
    const body = new FormData()
    body.append('file', selected)
    Object.entries(extra).forEach(([key, value]) => body.append(key, value))
    return api<Opened & Report>(path, { method: 'POST', body })
  }
  async function open(selected: File) {
    setBusy(true)
    setError(null)
    setReport(null)
    setApplied(null)
    try {
      const result = await send(selected)
      setFile(selected)
      setOpened(result)
      const guess: Record<string, string> = {}
      result.columns.forEach((column) => {
        const hit = Object.entries(result.targets).find(
          ([, label]) => label.toLowerCase() === column.trim().toLowerCase(),
        )
        if (hit) guess[column] = hit[0]
      })
      setMapping(guess)
      setStep(2)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('Не удалось прочитать файл'))
    } finally {
      setBusy(false)
    }
  }
  async function run(dryRun: boolean) {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const result = await send(file, { mapping: JSON.stringify(mapping), dry_run: dryRun ? '1' : '' })
      if (dryRun) {
        setReport(result)
        setStep(3)
      } else {
        setReport(null)
        setApplied(resultText(result))
        setStep(4)
        invalidate.forEach((key) => void queryClient.invalidateQueries({ queryKey: key }))
        void queryClient.invalidateQueries({ queryKey: ['imports'] })
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t('Не удалось применить'))
    } finally {
      setBusy(false)
    }
  }
  const ready = required.every((key) => Object.values(mapping).includes(key))
  const steps = [t('Файл'), t('Сопоставление колонок'), t('Проверка строк'), t('Готово')]
  return (
    <div className="import-flow">
      <WizardSteps stackedOnPhone steps={steps} current={step} />
      <DataCard
        title={step === 1 ? title : steps[step - 1]}
        note={file?.name || note}
        right={<Chip size="sm">{t('Шаг {step} из {total}', { step, total: 4 })}</Chip>}
      >
        {error && <ErrorNote error={new Error(error)} />}
        {busy && <p className="muted">{t('Обрабатываю…')}</p>}
        {step === 1 && (
          <>
            <p className="import-flow__hint">{hint}</p>
            <ImportFile file={file} disabled={busy} onSelect={(selected) => void open(selected)} />
          </>
        )}
        {step === 2 && opened && (
          <>
            <p className="import-flow__hint num">
              {t('Строк в файле: {total}', { total: opened.total_rows })}
            </p>
            <DataTable
              fit
              columns={[
                {
                  key: 'column',
                  title: t('Колонка в файле'),
                  width: '40%',
                  cell: (column: string) => <b>{column}</b>,
                },
                {
                  key: 'target',
                  title: t('Поле'),
                  width: '60%',
                  cell: (column: string) => (
                    <SelectField
                      value={mapping[column] ?? ''}
                      disabled={busy}
                      aria-label={column}
                      onChange={(event) => setMapping((prev) => ({ ...prev, [column]: event.target.value }))}
                    >
                      <option value="">{t('— не импортировать —')}</option>
                      {Object.entries(opened.targets).map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </SelectField>
                  ),
                },
              ]}
              rows={opened.columns}
              rowKey={(column) => column}
            />
            {!ready && <p className="import-flow__hint">{missing}</p>}
            <div className="import-flow__actions">
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => {
                  setStep(1)
                  setError(null)
                }}
              >
                {t('Назад')}
              </Button>
              <Button disabled={busy || !ready} onClick={() => void run(true)}>
                {t('Показать предпросмотр')}
              </Button>
            </div>
          </>
        )}
        {step === 3 && report && (
          <>
            <p className="import-flow__hint">{t('Пробный прогон: в базу пока ничего не записано')}</p>
            <ImportPreview
              rows={report.rows.map((row) => ({
                key: row.row,
                number: row.row,
                name: row.program || row.name || t('Строка {n}', { n: row.row }),
                search: [row.program, row.name].filter(Boolean).join(' '),
                status: row.status,
                detail: row.state,
                reason: row.reason,
              }))}
            />
            <div className="import-flow__actions">
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => {
                  setStep(2)
                  setReport(null)
                  setError(null)
                }}
              >
                {t('Назад')}
              </Button>
              <Button
                disabled={busy || report.created + report.updated === 0}
                onClick={() => void run(false)}
              >
                {t('Применить')}
              </Button>
            </div>
          </>
        )}
        {step === 4 && applied && (
          <>
            <Chip tone="good" className="badge--sentence">
              {applied}
            </Chip>
            <div className="import-flow__actions">
              <Button
                variant="outline"
                onClick={() => {
                  setStep(1)
                  setFile(null)
                  setOpened(null)
                  setApplied(null)
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
