/**
 * История загрузок с отменой импорта целиком.
 *
 * Отмена работает тем же способом, что откат предложений: обратный набор
 * изменений через журнал. Поле, которое после загрузки правили руками,
 * откат не трогает и говорит об этом поимённо.
 */
import { useState } from 'react'
import { useImportBatches, useRevertImport, type ImportBatchRow, type RevertReport } from '../api/hooks'
import ConfirmDialog from './ConfirmDialog'
import { Chip, ErrorNote, Loading } from './ui'

const STATUS_TONE: Record<string, 'ok' | 'warn' | 'mute'> = {
  applied: 'ok',
  reverted: 'mute',
  partial: 'warn',
}

function when(value: string): string {
  return new Date(value).toLocaleString('ru', { dateStyle: 'short', timeStyle: 'short' })
}

function Row({ row, onReverted }: { row: ImportBatchRow; onReverted: (report: RevertReport) => void }) {
  const [ask, setAsk] = useState(false)
  const revert = useRevertImport()

  return (
    <article className="card card-pad imp__row">
      <div className="row-between imp__head">
        <div>
          <b>{row.file_name || row.kind_title}</b>
          <p className="muted imp__sub">
            {row.actor_name || 'неизвестно кто'} · {when(row.created_at)} · строк в файле {row.rows_total}
          </p>
        </div>
        <Chip tone={STATUS_TONE[row.status] ?? 'mute'}>{row.status_title}</Chip>
      </div>

      <p className="muted imp__sub">
        Изменено записей: {row.rows_updated}
        {row.rows_created > 0 && ` · создано: ${row.rows_created}`}
        {row.rows_failed > 0 && ` · с ошибкой: ${row.rows_failed}`} · правок в журнале: {row.changes}
      </p>
      {row.note && <p className="muted imp__sub">{row.note}</p>}

      {row.status === 'applied' && (
        <div className="imp__actions">
          <button className="btn btn-danger btn-sm" onClick={() => setAsk(true)}>
            Отменить импорт
          </button>
          {revert.isError && <ErrorNote error={revert.error} />}
        </div>
      )}

      <ConfirmDialog
        open={ask}
        title={`Отменить загрузку «${row.file_name || row.kind_title}»?`}
        what={`Прежние значения вернутся у ${row.changes} полей.`}
        consequences={[
          'Поля, которые правили руками уже после загрузки, останутся как есть — о каждом скажем отдельно',
          'Возврат тоже попадёт в журнал изменений: по строке на каждое поле',
          row.rows_created > 0
            ? `Записи, созданные этой загрузкой (${row.rows_created}), отмена не удаляет`
            : 'Загрузка ничего не создавала — только меняла значения',
        ]}
        confirmLabel="Отменить импорт"
        busy={revert.isPending}
        error={revert.isError ? (revert.error as Error).message : null}
        onCancel={() => setAsk(false)}
        onConfirm={() =>
          revert.mutate(row.id, {
            onSuccess: (report) => {
              setAsk(false)
              onReverted(report)
            },
          })
        }
      />
    </article>
  )
}

/** Столько загрузок показываем сразу: остальное — по кнопке. */
const VISIBLE = 5

export default function ImportHistory() {
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [all, setAll] = useState(false)
  const [report, setReport] = useState<RevertReport | null>(null)
  const list = useImportBatches({ since, until })
  const rows = list.data ?? []
  const shown = all ? rows : rows.slice(0, VISIBLE)

  return (
    <section className="card card-pad imp">
      <div className="row-between imp__toolbar">
        <span className="eyebrow">📜 История загрузок</span>
        <div className="imp__filters">
          <label className="imp__filter">
            с
            <input
              className="input"
              type="date"
              value={since}
              aria-label="Загрузки с даты"
              onChange={(event) => setSince(event.target.value)}
            />
          </label>
          <label className="imp__filter">
            по
            <input
              className="input"
              type="date"
              value={until}
              aria-label="Загрузки по дату"
              onChange={(event) => setUntil(event.target.value)}
            />
          </label>
        </div>
      </div>

      {report && (
        <div className="imp__report">
          <p className="chip chip-ok">{report.detail}</p>
          {report.skipped.length > 0 && (
            <ul className="imp__skipped">
              {report.skipped.map((item) => (
                <li key={item.entry}>
                  {item.field_title}: {item.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {list.isLoading && <Loading />}
      {list.isError && <ErrorNote error={list.error} />}

      {!list.isLoading && rows.length === 0 && (
        <p className="muted imp__empty">
          Загрузок пока не было. Каждый применённый файл попадёт сюда, и его можно будет отменить целиком.
        </p>
      )}

      <div className="imp__list">
        {shown.map((row) => (
          <Row key={row.id} row={row} onReverted={setReport} />
        ))}
      </div>

      {rows.length > VISIBLE && (
        <button className="btn btn-ghost btn-sm queue__more" onClick={() => setAll(!all)}>
          {all ? 'Показать только последние' : `Показать все — ещё ${rows.length - VISIBLE}`}
        </button>
      )}
    </section>
  )
}
