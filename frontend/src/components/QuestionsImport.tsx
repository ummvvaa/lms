/**
 * Загрузка банка заданий файлом — у администратора, за домен «Экзамены».
 *
 * Формат простой: одна строка — одно задание, колонки с фиксированными
 * названиями. Сначала пробный прогон: сколько заведётся и какие строки
 * пропущены и почему; потом применение. Экрана у этой загрузки до фазы 35
 * не было — только запрос к API.
 */
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { Chip, DataCard, ErrorNote } from './ui'
import { t } from '../i18n'
import { Button } from './ui/button'
import ImportFile from './ImportFile'
import ImportPreview from './ImportRowsPreview'
import WizardSteps from './WizardSteps'
import type { ImportStatus } from './importRows'

interface Result {
  created: number
  rows: {
    row: number
    exam_type: string
    section: string
    topic: string
    text: string
    status: ImportStatus
    reason: string
  }[]
  skipped: { row: number; reason: string }[]
}

export default function QuestionsImport() {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Result | null>(null)
  const [applied, setApplied] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function send(selected: File, dryRun: boolean) {
    const body = new FormData()
    body.append('file', selected)
    if (dryRun) body.append('dry_run', '1')
    return api<Result>('/prep/questions/import/', { method: 'POST', body })
  }

  async function open(selected: File) {
    setBusy(true)
    setError(null)
    setApplied(null)
    setPreview(null)
    try {
      setPreview(await send(selected, true))
      setFile(selected)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('Не удалось прочитать файл'))
    } finally {
      setBusy(false)
    }
  }

  async function apply() {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const result = await send(file, false)
      setPreview(null)
      setApplied(t('Заведено заданий: {n}', { n: result.created }))
      void queryClient.invalidateQueries({ queryKey: ['questions'] })
      void queryClient.invalidateQueries({ queryKey: ['bank'] })
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
        title={applied ? t('Готово') : preview ? t('Проверка строк') : t('Файл с заданиями')}
        note={file?.name || t('CSV, одна строка — одно задание')}
        right={<Chip size="sm">{t('Шаг {step} из {total}', { step, total: 3 })}</Chip>}
      >
        {error && <ErrorNote error={new Error(error)} />}
        {busy && <p className="muted">{t('Обрабатываю…')}</p>}
        {!preview && !applied && (
          <>
            <p className="import-flow__hint">
              {t(
                'Колонки: exam_type, section, topic, difficulty, text, A, B, C, D, correct, explanation, source. Обязательны exam_type, section, topic, text и correct; вариантов ответа минимум два.',
              )}
            </p>
            <ImportFile
              file={file}
              accept=".csv,.txt"
              disabled={busy}
              onSelect={(selected) => void open(selected)}
            />
          </>
        )}
        {preview && (
          <>
            <p className="import-flow__hint">{t('Пробный прогон: в базу пока ничего не записано')}</p>
            <ImportPreview
              rows={preview.rows.map((row) => ({
                key: row.row,
                number: row.row,
                name: row.text || row.topic || t('Строка {n}', { n: row.row }),
                search: [row.text, row.exam_type, row.section, row.topic].join(' '),
                status: row.status,
                detail: [row.exam_type, row.section, row.topic].filter(Boolean).join(' · '),
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
              <Button disabled={busy || preview.created === 0} onClick={() => void apply()}>
                {t('Завести задания')}
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
