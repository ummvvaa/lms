/**
 * Импорт из файла: загрузка → сопоставление колонок → предпросмотр → применение.
 * Сопоставлять можно только поля своего домена — список приходит с сервера.
 */
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { useDomainMeta } from '../api/hooks'
import { profileModelOf } from '../api/types'
import ContactsImport from '../components/ContactsImport'
import Empty from '../components/Empty'
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

/** Разбор файла: что распознано, что пропущено и что подозрительно. */
interface Reading {
  columns: {
    title: string
    index: number
    target: string
    field_title: string
    skip_reason: string
    foreign_domain: string
  }[]
  mapping: Record<string, string>
  total_rows: number
  matched: number
  unmatched: string[]
  unmatched_count: number
  warnings: { kind: string; column: string; rows: number[]; count: number; text: string }[]
  text: string
  offline: boolean
  note: string
}

interface Preview {
  columns: string[]
  reading?: Reading
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
  const [reading, setReading] = useState<Reading | null>(null)
  const [applied, setApplied] = useState<string | null>(null)
  const [rejected, setRejected] = useState<{ field?: string; reason: string }[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // директор школы грузит два разных файла: доменные поля учеников
  // и контакты родителей. Разные сущности — разные экраны загрузки
  const [what, setWhat] = useState<'fields' | 'contacts'>('fields')

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
      setReading(result.reading ?? null)
      // сопоставление приходит с сервера как предложение: его считают
      // правила, а модель уточняет. Любую колонку человек переназначит сам
      setMapping(result.reading?.mapping ?? {})
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
      const result = await api<Preview>('/import/preview/', { method: 'POST', body })
      setPreview(result)
      // объяснение пересобирается под изменённое сопоставление:
      // текст обязан говорить о том, что человек выбрал сейчас
      if (result.reading) setReading(result.reading)
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
    // у администратора домена нет, но ученики списком заводятся у него:
    // экран без объяснения и без кнопки читается как поломка
    return (
      <div>
        <ScreenHead title={t('Импорт')} subtitle={t('Загружать нечего: домена у вашей роли нет.')} />
        <Empty
          title={t('Импорт ведут директора')}
          what={t('Ученики списком заводятся на экране «Пользователи».')}
          action={t('Открыть пользователей')}
          to="/users"
        />
      </div>
    )
  }

  const contactsOwner = mine.code === 'behavior'

  return (
    <div>
      <ScreenHead
        title={t('Импорт из файла')}
        subtitle={`Домен «${mine.title}» — чужие колонки не примутся.`}
      />

      {contactsOwner && (
        <div className="toolbar">
          <button
            className={`tab${what === 'fields' ? ' tab--active' : ''}`}
            onClick={() => setWhat('fields')}
          >
            {t('Данные учеников')}
          </button>
          <button
            className={`tab${what === 'contacts' ? ' tab--active' : ''}`}
            onClick={() => setWhat('contacts')}
          >
            {t('Контакты родителей')}
          </button>
        </div>
      )}

      {contactsOwner && what === 'contacts' && (
        <>
          <ContactsImport />
          <ImportHistory />
        </>
      )}

      {!(contactsOwner && what === 'contacts') && (
        <>
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

          {reading && (
            <div className="card card-pad imp__reading">
              <span className="eyebrow">{t('Что будет загружено')}</span>
              <p className="imp__readingtext">{reading.text}</p>
              {reading.offline && reading.note && <p className="muted imp__hint">{reading.note}</p>}
              {reading.warnings.length > 0 && (
                <ul className="imp__warnings">
                  {reading.warnings.map((warning, index) => (
                    <li key={index}>{warning.text}</li>
                  ))}
                </ul>
              )}
              <p className="muted imp__hint">
                {t(
                  'Сопоставление ниже — предложение. Переназначьте любую колонку: ничего не применится, пока вы не подтвердите.',
                )}
              </p>
            </div>
          )}

          {columns.length > 0 && (
            <div className="card card-pad" style={{ marginBottom: 16 }}>
              <span className="eyebrow">{t('Сопоставление колонок')}</span>
              <table className="history" style={{ marginTop: 12 }}>
                <tbody>
                  {columns.map((column) => {
                    const info = reading?.columns.find((row) => row.title === column)
                    return (
                      <tr key={column}>
                        <td style={{ fontWeight: 650 }}>
                          {column}
                          {info?.skip_reason === 'foreign_domain' && (
                            <div className="muted imp__hint">
                              {t('поле ведёт домен')} «{info.foreign_domain}»
                            </div>
                          )}
                          {info?.skip_reason === 'unknown' && (
                            <div className="muted imp__hint">{t('колонка не распознана')}</div>
                          )}
                        </td>
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
                    )
                  })}
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
                  {preview.broken > 0
                    ? `Применить ${readyRows(preview).length} правильных строк`
                    : 'Применить'}
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
        </>
      )}
    </div>
  )
}
