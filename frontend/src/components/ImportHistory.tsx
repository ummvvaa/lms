/**
 * История загрузок с отменой импорта целиком — плотными строками.
 *
 * Отмена работает тем же способом, что откат предложений: обратный набор
 * изменений через журнал. Поле, которое после загрузки правили руками,
 * откат не трогает и говорит об этом поимённо. Загрузки мастера и файлы
 * полей — в одной таблице, вид загрузки колонкой; после десяти строк —
 * «Показать ещё».
 */
import { useState } from 'react'
import {
  useAdmissionImports,
  useCleanupHistory,
  useHistoryCleanupPreview,
  useImportBatches,
  useRevertImport,
  type AdmissionImportReport,
  type ImportBatchRow,
  type RevertReport,
} from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import ConfirmDialog from './ConfirmDialog'
import DataTable, { type Column } from './DataTable'
import EditDrawer from './EditDrawer'
import ExportButton from './ExportPreview'
import Field from './Field'
import { Row, Rows } from './patterns'
import { Chip, DataCard, ErrorNote, Loading, type Tone } from './ui'
import { Button } from './ui/button'
import { t, tk, tn } from '../i18n'
import { formatDateTime } from '../lib/format'
import '../screens/academics/academics.css'

const STATUS_TONE: Record<string, Tone> = { applied: 'good', reverted: 'neutral', partial: 'warn' }

function when(value: string): string {
  return formatDateTime(value)
}

/** Подписи доменов для чипов истории — те же слова, что в реестре доменов. */
const DOMAIN_TITLES: Record<string, string> = {
  behavior: tk('Профиль и дисциплина'),
  admission: tk('Поступление'),
  exam: tk('Экзамены'),
  talent: tk('Таланты'),
  sport: tk('Спорт'),
  documents: tk('Документы'),
}

/** Вид строки отчёта мастера, как его пишет сервер, — сравнение, человеку не показывается. */
// eslint-disable-next-line i18n-text -- метка вида строки из ответа сервера, не показывается
const DOMAIN_ROW = 'домен'

/** Строка истории: файл полей или загрузка мастера — одним видом. */
type HistoryRow = {
  key: string
  kind: 'batch' | 'wizard'
  file: string
  who: string
  when: string
  domains: string[]
  onBehalf: boolean
  summary: string
  note: string
  status: string
  statusTitle: string
  batch?: ImportBatchRow
  wizard?: AdmissionImportReport
}

/** Очистка истории: записи о загрузках уходят, правки в журнале остаются. */
function CleanupPanel({ onDone }: { onDone: (detail: string) => void }) {
  const [days, setDays] = useState(180)
  const preview = useHistoryCleanupPreview(days, true)
  const cleanup = useCleanupHistory()
  return (
    <div className="acad__form">
      <Field kind="select" name="days" label={t('Старше скольких дней')} value={String(days)} onChange={(value) => setDays(Number(value))} options={[30, 90, 180, 365].map((value) => ({ value: String(value), title: String(value) }))} />
      {preview.data && <p className="t-note">{preview.data.detail}</p>}
      <div className="acad__actions">
        <Button disabled={(preview.data?.entries ?? 0) === 0 || cleanup.isPending} onClick={() => cleanup.mutate(days, { onSuccess: (result) => onDone(result.detail) })}>
          {t('Очистить')}
        </Button>
      </div>
    </div>
  )
}

/** Отчёт загрузки мастера: домены строками, замечания таблицей. */
function WizardReport({ report }: { report: AdmissionImportReport }) {
  const domains = report.rows.filter((row) => row.kind === DOMAIN_ROW)
  const notes = report.rows.filter((row) => row.kind !== DOMAIN_ROW)
  type Note = (typeof notes)[number]
  return (
    <div className="acad__form">
      <Rows>
        {domains.map((row) => (
          <Row key={row.text} icon="layers" title={row.text} />
        ))}
      </Rows>
      <DataCard title={t('Замечания')} count={notes.length || undefined} empty={notes.length === 0 && t('всё загрузилось без замечаний')}>
        <DataTable
          columns={[
            { key: 'sheet', title: t('Лист'), width: '20%', cell: (row: Note) => row.sheet },
            { key: 'row', title: t('Строка'), width: '14%', align: 'right', cell: (row: Note) => <span className="num">{row.row}</span> },
            { key: 'student', title: t('Ученик'), width: '26%', cell: (row: Note) => row.student },
            { key: 'text', title: t('Что случилось'), width: '40%', cell: (row: Note) => row.text },
          ]}
          rows={notes}
          rowKey={(row) => `${row.sheet}-${row.row}-${row.text}`}
          limit={20}
        />
      </DataCard>
      <div className="acad__actions">
        <ExportButton path={`/admission-imports/${report.id}/export/`} fallback="otchet-importa.xlsx" title={tk('Отчёт импорта')} label={tk('Скачать отчёт')} />
      </div>
    </div>
  )
}

const VISIBLE = 10

export default function ImportHistory() {
  const { me } = useAuth()
  const isAdmin = me?.role === 'admin'
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [report, setReport] = useState<RevertReport | null>(null)
  const [panel, setPanel] = useState<{ mode: 'cleanup' } | { mode: 'report'; report: AdmissionImportReport } | null>(null)
  const [ask, setAsk] = useState<ImportBatchRow | null>(null)
  const [flash, setFlash] = useState<string | null>(null)
  const revert = useRevertImport()
  // у куратора есть только загрузки мастера: CSV-загрузки полей — хозяйство
  // администратора, и их список ему закрыт
  const list = useImportBatches({ since, until }, me?.role !== 'curator')
  const wizard = useAdmissionImports()

  const wizardRows: HistoryRow[] = (wizard.data?.rows ?? [])
    .filter((row) => {
      const day = row.created_at.slice(0, 10)
      return (!since || day >= since) && (!until || day <= until)
    })
    .map((row) => ({
      key: `wizard-${row.id}`,
      kind: 'wizard',
      file: row.file_name || t('файл без имени'),
      who: row.uploaded_by || t('автор не сохранён'),
      when: row.created_at,
      domains: row.domains,
      onBehalf: false,
      summary:
        t('учеников {students} · попыток {attempts} · документов {documents} · паролей {credentials}', {
          students: row.students_updated,
          attempts: row.attempts_created,
          documents: row.documents_created,
          credentials: row.credentials_saved,
        }) + (row.rows_skipped > 0 ? t(' · пропущено строк {skipped}', { skipped: row.rows_skipped }) : ''),
      note: t('листов {sheets}', { sheets: row.sheets }),
      status: 'applied',
      statusTitle: t('мастер импорта'),
      wizard: row,
    }))
  const batchRows: HistoryRow[] = (list.data ?? []).map((row) => ({
    key: `batch-${row.id}`,
    kind: 'batch',
    file: row.file_name || row.kind_title,
    // пусто — загрузка старше фазы 29: тогда автора не записывали
    who: row.actor_name || t('автор не сохранён'),
    when: row.created_at,
    domains: row.domain_title ? [row.domain_title] : [],
    // файл залил не владелец домена — администратор за домен: директор должен
    // видеть, откуда взялись значения, которых он не вносил
    onBehalf: Boolean(row.on_behalf && row.domain_title),
    summary:
      t('изменено {updated}', { updated: row.rows_updated }) +
      (row.rows_created > 0 ? t(' · создано {created}', { created: row.rows_created }) : '') +
      (row.rows_failed > 0 ? t(' · с ошибкой {failed}', { failed: row.rows_failed }) : '') +
      t(' · правок в журнале {changes}', { changes: row.changes }),
    note: row.note,
    status: row.status,
    statusTitle: row.status_title,
    batch: row,
  }))
  const rows = [...wizardRows, ...batchRows].sort((a, b) => b.when.localeCompare(a.when))

  const columns: Column<HistoryRow>[] = [
    {
      key: 'file',
      title: t('Файл'),
      width: '30%',
      cell: (row) => (
        <>
          <b>{row.file}</b>
          <span className="t-note">
            {' '}
            · {row.who}
            {row.onBehalf && t(' · администратор за домен «{domain}»', { domain: row.domains[0] ? t(DOMAIN_TITLES[row.domains[0]] ?? row.domains[0]) : '' })}
          </span>
        </>
      ),
      sortBy: (row) => row.file,
    },
    { key: 'when', title: t('Когда'), width: '12%', cell: (row) => <span className="num">{when(row.when)}</span>, sortBy: (row) => row.when },
    {
      key: 'domains',
      title: t('Домен'),
      width: '16%',
      cell: (row) => (row.domains.length === 0 ? <span className="t-note">{t('нет')}</span> : row.domains.map((code) => <Chip key={code} size="sm">{t(DOMAIN_TITLES[code] ?? code)}</Chip>)),
    },
    {
      key: 'summary',
      title: t('Что сделано'),
      width: '22%',
      cell: (row) => (
        <>
          {row.summary}
          {row.note && <span className="t-note"> · {row.note}</span>}
        </>
      ),
    },
    {
      key: 'status',
      title: t('Состояние'),
      width: '10%',
      cell: (row) => (
        <Chip tone={row.kind === 'wizard' ? 'accent' : (STATUS_TONE[row.status] ?? 'neutral')} size="sm">
          {row.statusTitle}
        </Chip>
      ),
      sortBy: (row) => row.status,
    },
    {
      key: 'acts',
      title: '',
      width: '10%',
      align: 'right',
      cell: (row) =>
        row.wizard ? (
          <Button variant="secondary" size="sm" onClick={() => setPanel({ mode: 'report', report: row.wizard! })}>
            {t('Отчёт')}
          </Button>
        ) : row.batch && row.batch.status === 'applied' ? (
          <Button variant="ghost" size="sm" onClick={() => setAsk(row.batch!)}>
            {t('Отменить')}
          </Button>
        ) : undefined,
    },
  ]

  return (
    <DataCard
      title={t('История загрузок')}
      count={rows.length || undefined}
      empty={!list.isLoading && rows.length === 0 && (isAdmin ? t('загрузок пока не было — каждый применённый файл попадёт сюда, и его можно будет отменить целиком') : t('по вашему домену загрузок ещё не было'))}
      right={
        <span className="acad__inline">
          <Field kind="date" name="since" label={t('с')} value={since} onChange={setSince} />
          <Field kind="date" name="until" label={t('по')} value={until} onChange={setUntil} />
          {isAdmin && (
            <Button variant="outline" size="sm" onClick={() => setPanel({ mode: 'cleanup' })}>
              {t('Очистить историю…')}
            </Button>
          )}
        </span>
      }
    >
      {flash && (
        <Chip tone="good" size="sm">
          {flash}
        </Chip>
      )}
      {report && (
        <Rows>
          <Row icon="check" tone="good" title={report.detail} note={report.skipped.length > 0 ? report.skipped.map((item) => `${item.field_title}: ${item.reason}`).join('; ') : undefined} />
        </Rows>
      )}
      {list.isLoading && <Loading kind="table" />}
      {list.isError && <ErrorNote error={list.error} />}
      <DataTable columns={columns} rows={rows} rowKey={(row) => row.key} limit={VISIBLE} />

      <ConfirmDialog
        open={ask !== null}
        title={ask ? t('Отменить загрузку «{file}»?', { file: ask.file_name || ask.kind_title }) : ''}
        what={ask ? tn(ask.changes, 'Прежние значения вернутся у {n} поля.|Прежние значения вернутся у {n} полей.|Прежние значения вернутся у {n} полей.') : ''}
        consequences={[
          t('Поля, которые правили руками уже после загрузки, останутся как есть — о каждом скажем отдельно'),
          t('Возврат тоже попадёт в журнал изменений: по строке на каждое поле'),
          ask && ask.rows_created > 0 ? t('Записи, созданные этой загрузкой ({created}), отмена не удаляет', { created: ask.rows_created }) : t('Загрузка ничего не создавала — только меняла значения'),
        ]}
        confirmLabel={t('Отменить импорт')}
        busy={revert.isPending}
        error={revert.isError ? (revert.error as Error).message : null}
        onCancel={() => setAsk(null)}
        onConfirm={() =>
          ask &&
          revert.mutate(ask.id, {
            onSuccess: (result) => {
              setAsk(null)
              setReport(result)
            },
          })
        }
      />

      <EditDrawer open={panel !== null} onClose={() => setPanel(null)} title={panel?.mode === 'cleanup' ? t('Очистка истории загрузок') : t('Отчёт о загрузке')} sub={panel?.mode === 'report' ? panel.report.file_name : undefined}>
        {panel?.mode === 'cleanup' && (
          <CleanupPanel
            onDone={(detail) => {
              setFlash(detail)
              setPanel(null)
            }}
          />
        )}
        {panel?.mode === 'report' && <WizardReport report={panel.report} />}
      </EditDrawer>
    </DataCard>
  )
}
