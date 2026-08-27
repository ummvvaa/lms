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
import { DataCard, ErrorNote } from './ui'
import { t } from '../i18n'
import { Button } from './ui/button'
import { Badge } from './ui/badge'

interface Result {
  created: number
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
      setError(e instanceof Error ? e.message : 'Не удалось прочитать файл')
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
      setApplied(`Заведено заданий: ${result.created}`)
      void queryClient.invalidateQueries({ queryKey: ['questions'] })
      void queryClient.invalidateQueries({ queryKey: ['bank'] })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось применить')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <DataCard
        title={t('Файл с заданиями')}
        note={t('CSV, одна строка — одно задание')}
        hint={t(
          'Колонки: exam_type, section, topic, difficulty, text, A, B, C, D, correct, explanation, source. Обязательны exam_type, section, topic, text и correct; вариантов ответа минимум два.',
        )}
      >
        <label className="filepick">
          <input
            type="file"
            accept=".csv,.txt"
            onChange={(event) => {
              const selected = event.target.files?.[0]
              if (selected) void open(selected)
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
          <Badge variant="ok" className="badge--line">
            {applied}
          </Badge>
        )}
      </DataCard>

      {preview && (
        <DataCard title={t('Что будет загружено')} note={t('Пробный прогон: в базу пока ничего не записано')}>
          <div className="toolbar">
            <Badge variant="ok" className="num">
              Заведётся: {preview.created}
            </Badge>
            {preview.skipped.length > 0 && (
              <Badge variant="warn" className="num">
                Пропущено: {preview.skipped.length}
              </Badge>
            )}
            <span className="toolbar__spacer" />
            <Button size="sm" disabled={busy || preview.created === 0} onClick={() => void apply()}>
              {t('Завести задания')}
            </Button>
          </div>
          {preview.skipped.length > 0 && (
            <div className="imp__problems">
              <span className="datacard__title">{t('Что поправить в файле')}</span>
              <ul className="imp__problemlist">
                {preview.skipped.slice(0, 20).map((row) => (
                  <li key={row.row}>
                    <b>Строка {row.row}</b>: {row.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </DataCard>
      )}
    </>
  )
}
