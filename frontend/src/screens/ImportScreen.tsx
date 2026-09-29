/**
 * Загрузка файлов — у администратора, по всем пяти доменам (фаза 35).
 *
 * Единственное место в системе, где пересекается граница доменов.
 * Порядок осознанный: сначала выбрать домен — чьи данные в файле, —
 * потом файл. Сопоставление колонок ограничено полями выбранного домена,
 * чужие для него колонки сервер не примет. Каждая правка в журнале
 * помечена «администратор за домен «…»».
 *
 * Директор на том же адресе видит историю загрузок по своему домену —
 * что залил администратор и что можно отменить — и подсказку, что данные
 * вносятся руками или вставкой текста. Файл выбрать ему негде.
 */
import { useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { useDomainMeta } from '../api/hooks'
import { profileModelOf, type Domain } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import RowsImport, { type ImportedRow } from '../components/RowsImport'
import RequirementsImport from '../components/RequirementsImport'
import QuestionsImport from '../components/QuestionsImport'
import ScholarshipsImport from '../components/ScholarshipsImport'
import ImportWizard from '../components/ImportWizard'
import ImportHistory from '../components/ImportHistory'
import DataTable from '../components/DataTable'
import ManualEntryNote from '../components/ManualEntryNote'
import { Chip, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../components/ui'
import { t } from '../i18n'
import { SelectField } from '../components/SelectField'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'

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

/** Загрузка полей учеников одного домена: файл → сопоставление → предпросмотр → применение. */
function FieldsImport({ domain }: { domain: Domain }) {
  const queryClient = useQueryClient()
  const model = profileModelOf(domain)
  const [file, setFile] = useState<File | null>(null)
  const [columns, setColumns] = useState<string[]>([])
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState<Preview | null>(null)
  const [reading, setReading] = useState<Reading | null>(null)
  const [applied, setApplied] = useState<string | null>(null)
  const [rejected, setRejected] = useState<{ field?: string; reason: string }[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function upload(selected: File) {
    setBusy(true)
    setError(null)
    setPreview(null)
    setApplied(null)
    try {
      const body = new FormData()
      body.append('file', selected)
      // домен уходит с каждым запросом: сервер отсекает чужие колонки сам
      body.append('domain', domain.code)
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
      body.append('domain', domain.code)
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
        body: JSON.stringify({ rows: readyRows(preview), file_name: file?.name ?? '', domain: domain.code }),
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

  if (!model) return null

  return (
    <>
      <div className="card card-pad mb-4">
        {/* свой ярлык вместо нативной кнопки: «Choose File / No file chosen»
            остаётся английским при любой локали страницы */}
        <label className="filepick">
          <Input
            type="file"
            accept=".csv,.xlsx,.xlsm"
            onChange={(e) => {
              const selected = e.target.files?.[0]
              if (selected) void upload(selected)
            }}
          />
          <Button size="sm" nativeButton={false} render={<span />}>
            {t('Выбрать файл')}
          </Button>
          <span className="muted filepick__name">{file ? file.name : 'Файл не выбран'}</span>
        </label>
        {busy && <p className="muted">{t('Обрабатываю…')}</p>}
        {error && <ErrorNote error={new Error(error)} />}
        {applied && (
          <Chip tone="good">
            {applied}
          </Chip>
        )}
        {rejected.length > 0 && (
          <div className="mt-3">
            <span className="eyebrow">{t('Не приняли')}</span>
            <ul className="bullets">
              {rejected.map((row, i) => (
                <li key={i}>{row.reason}</li>
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
        <div className="card card-pad mb-4">
          <span className="eyebrow">{t('Сопоставление колонок')}</span>
          <DataTable
            columns={[
              {
                key: 'column',
                title: t('Колонка в файле'),
                width: '40%',
                cell: (column: string) => {
                  const info = reading?.columns.find((row) => row.title === column)
                  return (
                    <>
                      <b>{column}</b>
                      {info?.skip_reason === 'foreign_domain' && (
                        <span className="t-note">
                          {' '}
                          · {t('поле ведёт домен')} «{info.foreign_domain}»
                        </span>
                      )}
                      {info?.skip_reason === 'unknown' && <span className="t-note"> · {t('колонка не распознана')}</span>}
                    </>
                  )
                },
              },
              {
                key: 'target',
                title: t('Поле'),
                width: '60%',
                cell: (column: string) => (
                  <SelectField
                    value={mapping[column] ?? ''}
                    // пока файл читается, таблицу править нельзя: сопоставление
                    // всё равно будет заменено предложением по новому файлу
                    disabled={busy}
                    aria-label={column}
                    onChange={(e) => setMapping((prev) => ({ ...prev, [column]: e.target.value }))}
                  >
                    <option value="">{t('— не импортировать —')}</option>
                    <option value="student">{t('Ученик (почта или логин)')}</option>
                    {model.fields.map((field) => (
                      <option key={field.name} value={`${model.label}.${field.name}`}>
                        {field.title}
                      </option>
                    ))}
                  </SelectField>
                ),
              },
            ]}
            rows={columns}
            rowKey={(column) => column}
          />
          <Button size="sm"className="mt-3.5" onClick={() => void buildPreview()} disabled={busy}>
            {t('Показать предпросмотр')}
          </Button>
        </div>
      )}

      {preview && (
        <div className="card card-pad">
          <div className="toolbar">
            <Chip tone="good" className="num">
              Нашлось: {preview.matched}
            </Chip>
            {preview.unmatched.length > 0 && (
              <Chip tone="warn" className="num">
                Не найдено: {preview.unmatched.length}
              </Chip>
            )}
            {preview.conflicts.length > 0 && (
              <Chip tone="bad" className="num">
                Перезапишется: {preview.conflicts.length}
              </Chip>
            )}
            {preview.broken > 0 && (
              <Chip tone="warn" className="num">
                Строк с ошибкой: {preview.broken}
              </Chip>
            )}
            <span className="toolbar__spacer" />
            <Button size="sm" onClick={() => void apply()} disabled={busy || readyRows(preview).length === 0}>
              {preview.broken > 0 ? `Применить ${readyRows(preview).length} правильных строк` : 'Применить'}
            </Button>
          </div>

          {preview.errors.map((message) => (
            <Chip key={message} tone="warn" className="imp__error">
              {message}
            </Chip>
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

          <DataTable
            columns={[
              { key: 'n', title: t('Строка'), width: '12%', align: 'right', cell: (row: PreviewRow) => <span className="num">{row.row}</span> },
              { key: 'student', title: t('Ученик'), width: '30%', cell: (row: PreviewRow) => <b>{row.student_name}</b> },
              {
                key: 'changes',
                title: t('Что изменится'),
                width: '58%',
                cell: (row: PreviewRow) => (
                  <span className="num">
                    {row.changes.length === 0 && <span className="t-note">{t('без изменений')}</span>}
                    {row.changes.map((change) => (
                      <div key={change.field}>
                        {change.field_title}: <span className="t-note">{change.old || t('пусто')}</span> {'→'} <b>{change.new}</b>
                      </div>
                    ))}
                  </span>
                ),
              },
            ]}
            rows={preview.rows}
            rowKey={(row) => row.row}
          />
          {preview.total_rows > preview.rows.length && (
            <p className="muted">
              Показаны первые {preview.rows.length} из {preview.total_rows} строк.
            </p>
          )}
        </div>
      )}
    </>
  )
}

/** Дополнительные вкладки домена: строки, которые файл заводит, а не правит.
 *  У «Поступления» их две — требования вузов и стипендии (фаза 44). */
function extrasOf(domain: Domain): { key: string; tab: string; body: ReactNode }[] {
  if (domain.code === 'behavior') {
    return [
      {
        key: 'contacts',
        tab: 'Контакты родителей',
        body: (
          <RowsImport
            title={t('Файл со списком контактов')}
            note={t('XLSX или CSV, ученик ищется по почте')}
            hint={t(
              'Колонки распознаются по заголовку первой строки: почта ученика, ФИО родителя, кем приходится, телефон, почта, способ связи, примечание, основной. Обязательны первые две.',
            )}
            previewPath="/contacts/import/preview/"
            applyPath="/contacts/import/apply/"
            applyLabel={t('Завести контакты')}
            invalidate={[['contacts']]}
            columns={[
              { key: 'full_name', title: t('ФИО'), cell: (row: ImportedRow) => String(row.full_name || '—') },
              {
                key: 'student',
                title: t('Ученик'),
                cell: (row: ImportedRow) => String(row.student_name || row.student_email || '—'),
              },
              {
                key: 'contact',
                title: t('Связь'),
                cell: (row: ImportedRow) => String(row.phone || row.email || '—'),
              },
            ]}
          />
        ),
      },
    ]
  }
  if (domain.code === 'sport') {
    return [
      {
        key: 'competitions',
        tab: 'Соревнования',
        body: (
          <RowsImport
            title={t('Файл со списком выступлений')}
            note={t('XLSX или CSV, ученик ищется по почте')}
            hint={t(
              'Колонки распознаются по заголовку первой строки: почта ученика, название соревнования, вид спорта, уровень, дата, результат, сертификат, ссылка. Обязательны первые две.',
            )}
            previewPath="/competitions/import/preview/"
            applyPath="/competitions/import/apply/"
            applyLabel={t('Завести выступления')}
            invalidate={[['competitions'], ['dashboard']]}
            columns={[
              { key: 'name', title: t('Соревнование'), cell: (row: ImportedRow) => String(row.name || '—') },
              {
                key: 'student',
                title: t('Участник'),
                cell: (row: ImportedRow) => String(row.student_name || row.student_email || '—'),
              },
              { key: 'result', title: t('Результат'), cell: (row: ImportedRow) => String(row.result || '—') },
            ]}
          />
        ),
      },
    ]
  }
  if (domain.code === 'admission') {
    return [
      { key: 'requirements', tab: 'Требования вузов', body: <RequirementsImport /> },
      { key: 'scholarships', tab: 'Стипендии', body: <ScholarshipsImport /> },
    ]
  }
  if (domain.code === 'exam') return [{ key: 'questions', tab: 'Банк заданий', body: <QuestionsImport /> }]
  return []
}

/** Администратор: выбор домена, потом файл. */
function AdminImport({ domains }: { domains: Domain[] }) {
  // мастер на реестре — главный путь (фаза 72); старый CSV-импорт полей
  // остаётся второй вкладкой: реестр пока знает только колонки таблицы
  // Асем, а поля вне его грузятся прежним сопоставлением (DEFECTS, D42)
  const [mode, setMode] = useState<'wizard' | 'csv'>('wizard')
  const [code, setCode] = useState('')
  const [what, setWhat] = useState('fields')
  const domain = domains.find((d) => d.code === code)
  const extras = domain ? extrasOf(domain) : []
  const extra = extras.find((row) => row.key === what)

  return (
    <div>
      <ScreenHead
        title={t('Импорт')}
      />
      <ScreenTabs
        value={mode}
        onChange={(value) => setMode(value as 'wizard' | 'csv')}
        items={[
          { value: 'wizard', label: t('Мастер импорта') },
          { value: 'csv', label: t('Поля по CSV') },
        ]}
      />

      {mode === 'wizard' && <ImportWizard />}

      {mode === 'csv' && (
        <div className="card card-pad mb-4">
          <label className="imp__domain">
            <span className="eyebrow">{t('Домен')}</span>
            <SelectField
              aria-label={t('Домен')}
              value={code}
              onChange={(event) => {
                setCode(event.target.value)
                setWhat('fields')
              }}
            >
              <option value="">{t('— выберите домен —')}</option>
              {domains.map((row) => (
                <option key={row.code} value={row.code}>
                  {row.title} · {row.owner_name}
                </option>
              ))}
            </SelectField>
            {domain && (
              <span className="muted">
                {t('Правки в журнале будут помечены:')} администратор за домен «{domain.title}»
              </span>
            )}
          </label>
        </div>
      )}

      {mode === 'csv' && domain && extras.length > 0 && (
        <ScreenTabs
          value={what}
          onChange={setWhat}
          items={[
            { value: 'fields', label: t('Данные учеников') },
            ...extras.map((row) => ({ value: row.key, label: t(row.tab) })),
          ]}
        />
      )}

      {/* ключ по домену: смена домена сбрасывает файл и сопоставление —
          старое сопоставление относилось к другому набору полей */}
      {mode === 'csv' && domain && what === 'fields' && <FieldsImport key={domain.code} domain={domain} />}
      {mode === 'csv' && domain && extra && <div key={`${domain.code}-${extra.key}`}>{extra.body}</div>}

      <ImportHistory />
    </div>
  )
}

/** Директор: история загрузок по своему домену и подсказка, куда идти с данными.
 *
 *  У директора по поступлению здесь же мастер таблицы поступления (фаза 65):
 *  таблицу ведёт он сам, и просить администратора залить её было бы лишним
 *  звеном — файл с паролями учеников не должен ходить по рукам. */
function UploadsForDirector({ mine, curator = false }: { mine?: Domain; curator?: boolean }) {
  // владелец домена — тот же мастер, что у администратора (фаза 72):
  // чужие колонки он видит помеченными «домен не ваш, будет пропущен»
  return (
    <div>
      <ScreenHead
        title={t('Импорт')}
        subtitle={
          curator
            ? t(
                'Файл → что заполняем → проверка → готово. Пишутся только ваши группы: лист чужой группы — ошибка листа.',
              )
            : mine
              ? `Файл → что заполняем → проверка → готово. Пишется только домен «${mine.title}».`
              : t('Файл → что заполняем → проверка строк → готово.')
        }
      />
      <ImportWizard />
      {/* подсказка «файлы загружает администратор» — для директоров; куратор
          вносит данные своих групп сам, и руками, и файлом */}
      {!curator && <ManualEntryNote history={false} />}
      <ImportHistory />
    </div>
  )
}

export default function ImportScreen() {
  const { me } = useAuth()
  const meta = useDomainMeta()

  if (meta.isLoading) return <Loading />
  if (meta.error) return <ErrorNote error={meta.error} />
  if (me?.role === 'admin') return <AdminImport domains={meta.data?.domains ?? []} />
  return (
    <UploadsForDirector mine={meta.data?.domains.find((d) => d.is_mine)} curator={me?.role === 'curator'} />
  )
}
