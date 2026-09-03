/**
 * Загрузка требований вузов файлом — у администратора, за домен «Поступление».
 *
 * До фазы 35 у этой загрузки не было экрана вовсе: пустой справочник вёл
 * на общий импорт, который требований не понимал. Порядок тот же, что
 * у остальных загрузок: файл → сопоставление колонок → предпросмотр
 * (пробный прогон на сервере, ничего не пишется) → применение. Ключ
 * строки — пара «вуз + программа», повторная загрузка ничего не дублирует.
 */
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { DataCard, ErrorNote } from './ui'
import { t } from '../i18n'
import { SelectField } from './SelectField'
import { Button } from './ui/button'
import { Badge } from './ui/badge'

interface Opened {
  columns: string[]
  total_rows: number
  /** поля требований: ключ → подпись из реестра */
  targets: Record<string, string>
}

interface Report {
  created: number
  updated: number
  unchanged: number
  errors: string[]
  rows: { row: number; program: string; state: string }[]
}

export default function RequirementsImport() {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [opened, setOpened] = useState<Opened | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [report, setReport] = useState<Report | null>(null)
  const [applied, setApplied] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function send(selected: File, extra: Record<string, string> = {}) {
    const body = new FormData()
    body.append('file', selected)
    Object.entries(extra).forEach(([key, value]) => body.append(key, value))
    return api<Opened & Report>('/requirements/import/', { method: 'POST', body })
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
      // колонку с тем же названием, что у поля, подставляем сразу —
      // остальное человек назначает сам
      const guess: Record<string, string> = {}
      result.columns.forEach((column) => {
        const hit = Object.entries(result.targets).find(
          ([, title]) => title.toLowerCase() === column.trim().toLowerCase(),
        )
        if (hit) guess[column] = hit[0]
      })
      setMapping(guess)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось прочитать файл')
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
      if (dryRun) setReport(result)
      else {
        setReport(null)
        setApplied(
          `Заведено требований: ${result.created}, обновлено: ${result.updated}, без изменений: ${result.unchanged}`,
        )
        void queryClient.invalidateQueries({ queryKey: ['directory'] })
        void queryClient.invalidateQueries({ queryKey: ['imports'] })
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось применить')
    } finally {
      setBusy(false)
    }
  }

  const ready = Boolean(
    mapping && Object.values(mapping).includes('university') && Object.values(mapping).includes('program'),
  )

  return (
    <>
      <DataCard
        title={t('Файл с требованиями вузов')}
        note={t('XLSX или CSV, ключ строки — вуз и программа')}
        hint={t(
          'Колонки сопоставляются с полями требований: вуз, программа, уровень, пороги IELTS/TOEFL/SAT/ACT/GPA, предметы, портфолио, примечания, ссылка. Обязательны вуз и программа. Записи придут с плашкой «не подтверждено» — снимет её директор по поступлению, сверив с сайтом.',
        )}
      >
        <label className="filepick">
          <input
            type="file"
            accept=".csv,.xlsx,.xlsm"
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

      {opened && (
        <DataCard title={t('Сопоставление колонок')} note={`Строк в файле: ${opened.total_rows}`}>
          <table className="history">
            <tbody>
              {opened.columns.map((column) => (
                <tr key={column}>
                  <td style={{ fontWeight: 650 }}>{column}</td>
                  <td>
                    <SelectField
                      value={mapping[column] ?? ''}
                      disabled={busy}
                      aria-label={column}
                      onChange={(event) => setMapping((prev) => ({ ...prev, [column]: event.target.value }))}
                    >
                      <option value="">{t('— не импортировать —')}</option>
                      {Object.entries(opened.targets).map(([key, title]) => (
                        <option key={key} value={key}>
                          {title}
                        </option>
                      ))}
                    </SelectField>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!ready && (
            <p className="muted imp__hint">
              {t('Назначьте колонки «Название вуза» и «Название программы».')}
            </p>
          )}
          <Button
            size="sm"
            style={{ marginTop: 12 }}
            disabled={busy || !ready}
            onClick={() => void run(true)}
          >
            {t('Показать предпросмотр')}
          </Button>
        </DataCard>
      )}

      {report && (
        <DataCard title={t('Что будет загружено')} note={t('Пробный прогон: в базу пока ничего не записано')}>
          <div className="toolbar">
            <Badge variant="ok" className="num">
              Заведётся: {report.created}
            </Badge>
            <Badge variant="mute" className="num">
              Обновится: {report.updated}
            </Badge>
            <Badge variant="mute" className="num">
              Без изменений: {report.unchanged}
            </Badge>
            {report.errors.length > 0 && (
              <Badge variant="warn" className="num">
                С ошибками: {report.errors.length}
              </Badge>
            )}
            <span className="toolbar__spacer" />
            <Button
              size="sm"
              disabled={busy || report.created + report.updated === 0}
              onClick={() => void run(false)}
            >
              {t('Применить')}
            </Button>
          </div>
          {report.errors.length > 0 && (
            <div className="imp__problems">
              <span className="datacard__title">{t('Что поправить в файле')}</span>
              <ul className="imp__problemlist">
                {report.errors.slice(0, 20).map((message, index) => (
                  <li key={index}>{message}</li>
                ))}
              </ul>
            </div>
          )}
          <table className="history">
            <tbody>
              {report.rows.map((row) => (
                <tr key={row.row}>
                  <td className="muted">стр. {row.row}</td>
                  <td style={{ fontWeight: 650 }}>{row.program}</td>
                  <td className="muted">{row.state}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataCard>
      )}
    </>
  )
}
