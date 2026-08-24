/**
 * Импорт из файла: загрузка → сопоставление колонок → предпросмотр → применение.
 * Сопоставлять можно только поля своего домена — список приходит с сервера.
 */
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { useDomainMeta } from '../api/hooks'
import { profileModelOf } from '../api/types'
import ImportHistory from '../components/ImportHistory'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import { t } from '../i18n'

interface PreviewChange {
  model: string
  field: string
  /** человеческое название колонки — приходит с сервера (фаза 17) */
  field_title: string
  old: string
  new: string
  raw: string
}

interface PreviewRow {
  row: number
  student: number
  student_name: string
  changes: PreviewChange[]
}

/** Одна беда в клетке файла: где, что не так и как исправить. */
interface Problem {
  row: number
  column: string
  field: string
  field_title: string
  student_name: string
  value: string
  message: string
  hint: string
}

interface Preview {
  columns: string[]
  total_rows: number
  matched: number
  unmatched: { row: number; value: string }[]
  conflicts: { row: number; field: string; field_title: string; old: string; new: string }[]
  rows: PreviewRow[]
  /** все строки, а не только показанные: применяются они целиком */
  all_rows: PreviewRow[]
  errors: string[]
  problems: Problem[]
  /** сколько строк готовы к применению и сколько требуют правки */
  ready: number
  broken: number
}

/** Строки без ошибок в значениях — только их и применяем. */
function readyRows(preview: Preview): PreviewRow[] {
  const broken = new Set(preview.problems.map((p) => p.row))
  const all = preview.all_rows ?? preview.rows
  return all.filter((row) => !broken.has(row.row) && row.changes.length > 0)
}

export default function ImportScreen() {
  const meta = useDomainMeta()
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [columns, setColumns] = useState<string[]>([])
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState<Preview | null>(null)
  const [applied, setApplied] = useState<string | null>(null)
  const [rejected, setRejected] = useState<{ field?: string; reason: string }[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mine = meta.data?.domains.find((d) => d.is_mine)
  const model = mine ? profileModelOf(mine) : undefined

  async function upload(selected: File) {
    setBusy(true)
    setError(null)
    setPreview(null)
    setApplied(null)
    try {
      const body = new FormData()
      body.append('file', selected)
      const result = await api<Preview>('/import/preview/', { method: 'POST', body })
      setColumns(result.columns)
      setFile(selected)
      // предзаполняем сопоставление по совпадению имён
      const guess: Record<string, string> = {}
      result.columns.forEach((column) => {
        const lower = column.toLowerCase()
        if (lower.includes('email') || lower.includes('почта')) guess[column] = 'student'
        const field = model?.fields.find((f) => f.name === lower || f.title.toLowerCase() === lower)
        if (field && model) guess[column] = `${model.label}.${field.name}`
      })
      setMapping(guess)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось прочитать файл')
    } finally {
      setBusy(false)
    }
  }

  async function buildPreview() {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const body = new FormData()
      body.append('file', file)
      body.append('mapping', JSON.stringify(mapping))
      setPreview(await api<Preview>('/import/preview/', { method: 'POST', body }))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось построить предпросмотр')
    } finally {
      setBusy(false)
    }
  }

  async function apply() {
    if (!preview) return
    setBusy(true)
    try {
      const result = await api<{
        applied: number
        audit_entries: number
        rejected?: { student?: number; field?: string; reason: string }[]
        detail?: string
      }>('/import/apply/', {
        method: 'POST',
        // применяем только те строки, где нет ошибок в значениях: одна
        // кривая клетка не должна отменять весь файл
        // имя файла уходит вместе с данными: без него история загрузок
        // превращается в список одинаковых безымянных строк
        body: JSON.stringify({ rows: readyRows(preview), file_name: file?.name ?? '' }),
      })
      setApplied(
        result.detail ?? `Применено полей: ${result.applied}, записей в журнале: ${result.audit_entries}`,
      )
      // строки с непригодным значением отклоняются поимённо, а не молча теряются
      setRejected(result.rejected ?? [])
      setPreview(null)
      void queryClient.invalidateQueries({ queryKey: ['students'] })
      void queryClient.invalidateQueries({ queryKey: ['imports'] })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось применить')
    } finally {
      setBusy(false)
    }
  }

  if (meta.isLoading) return <Loading />
  if (!mine || !model) {
    return <ScreenHead title={t('Импорт')} subtitle={t('У вашей роли нет домена для импорта.')} />
  }

  return (
    <div>
      <ScreenHead
        title={t('Импорт из файла')}
        subtitle={`XLSX или CSV. Сопоставить можно только поля домена «${mine.title}».`}
      />

      <div className="card card-pad" style={{ marginBottom: 16 }}>
        {/* свой ярлык вместо нативной кнопки: «Choose File / No file chosen»
            остаётся английским при любой локали страницы */}
        <label className="filepick">
          <input
            type="file"
            accept=".csv,.xlsx,.xlsm"
            onChange={(e) => {
              const selected = e.target.files?.[0]
              if (selected) void upload(selected)
            }}
          />
          <span className="btn btn-primary btn-sm">{t('Выбрать файл')}</span>
          <span className="muted filepick__name">{file ? file.name : 'Файл не выбран'}</span>
        </label>
        {busy && <p className="muted">{t('Обрабатываю…')}</p>}
        {error && <ErrorNote error={new Error(error)} />}
        {applied && <p className="chip chip-ok">{applied}</p>}
        {rejected.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <span className="eyebrow">{t('Не приняли')}</span>
            <ul style={{ margin: '8px 0 0', paddingLeft: 18, fontSize: 13 }}>
              {rejected.map((row, i) => (
                <li key={i} style={{ padding: '2px 0' }}>
                  {row.reason}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {columns.length > 0 && (
        <div className="card card-pad" style={{ marginBottom: 16 }}>
          <span className="eyebrow">{t('Сопоставление колонок')}</span>
          <table className="history" style={{ marginTop: 12 }}>
            <tbody>
              {columns.map((column) => (
                <tr key={column}>
                  <td style={{ fontWeight: 650 }}>{column}</td>
                  <td>
                    <select
                      className="input"
                      value={mapping[column] ?? ''}
                      // пока файл читается, таблицу править нельзя: сопоставление
                      // всё равно будет заменено предложением по новому файлу
                      disabled={busy}
                      onChange={(e) => setMapping((prev) => ({ ...prev, [column]: e.target.value }))}
                    >
                      <option value="">{t('— не импортировать —')}</option>
                      <option value="student">{t('Ученик (email)')}</option>
                      {model.fields.map((field) => (
                        <option key={field.name} value={`${model.label}.${field.name}`}>
                          {field.title}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button
            className="btn btn-primary btn-sm"
            style={{ marginTop: 14 }}
            onClick={() => void buildPreview()}
            disabled={busy}
          >
            {t('Показать предпросмотр')}
          </button>
        </div>
      )}

      {preview && (
        <div className="card card-pad">
          <div className="toolbar">
            <span className="chip chip-ok num">Нашлось: {preview.matched}</span>
            {preview.unmatched.length > 0 && (
              <span className="chip chip-warn num">Не найдено: {preview.unmatched.length}</span>
            )}
            {preview.conflicts.length > 0 && (
              <span className="chip chip-risk num">Перезапишется: {preview.conflicts.length}</span>
            )}
            {preview.broken > 0 && (
              <span className="chip chip-warn num">Строк с ошибкой: {preview.broken}</span>
            )}
            <span className="toolbar__spacer" />
            <button
              className="btn btn-primary btn-sm"
              onClick={() => void apply()}
              disabled={busy || readyRows(preview).length === 0}
            >
              {preview.broken > 0 ? `Применить ${readyRows(preview).length} правильных строк` : 'Применить'}
            </button>
          </div>

          {preview.errors.map((message) => (
            <p key={message} className="chip chip-warn imp__error">
              {message}
            </p>
          ))}

          {preview.problems.length > 0 && (
            <div className="imp__problems">
              <span className="eyebrow">{t('Что поправить в файле')}</span>
              <p className="muted imp__problemnote">
                {t(
                  'Эти строки мы не тронем. Остальные можно применить прямо сейчас, а файл поправить и загрузить заново — повторная загрузка тех же значений ничего не изменит.',
                )}
              </p>
              <ul className="imp__problemlist">
                {preview.problems.map((problem) => (
                  <li key={`${problem.row}-${problem.field}`}>
                    <b>Строка {problem.row}</b>, колонка «{problem.column}»
                    {problem.student_name && <span className="muted"> · {problem.student_name}</span>}:{' '}
                    {problem.message}
                    {problem.hint && <span className="muted"> Допустимо {problem.hint}.</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {preview.unmatched.length > 0 && (
            <div className="imp__problems">
              <span className="eyebrow">{t('Учеников не нашли')}</span>
              <p className="muted imp__problemnote">
                {t(
                  'Строка ищет ученика по почте. Если человека нет в базе или почта другая — строка пропускается.',
                )}
              </p>
              <ul className="imp__problemlist">
                {preview.unmatched.slice(0, 20).map((row) => (
                  <li key={row.row}>
                    <b>Строка {row.row}</b>: ученика с почтой «{row.value || 'пусто'}» в базе нет
                  </li>
                ))}
              </ul>
            </div>
          )}

          <table className="history">
            <tbody>
              {preview.rows.map((row) => (
                <tr key={row.row}>
                  <td className="muted">стр. {row.row}</td>
                  <td style={{ fontWeight: 650 }}>{row.student_name}</td>
                  <td className="num">
                    {row.changes.length === 0 && <span className="muted">{t('без изменений')}</span>}
                    {row.changes.map((change) => (
                      <div key={change.field}>
                        {change.field_title}: <span className="muted">{change.old || '—'}</span> →{' '}
                        <b>{change.new}</b>
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {preview.total_rows > preview.rows.length && (
            <p className="muted">
              Показаны первые {preview.rows.length} из {preview.total_rows} строк.
            </p>
          )}
        </div>
      )}

      <ImportHistory />
    </div>
  )
}
