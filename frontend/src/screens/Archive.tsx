/**
 * Архив: что удалено, кем, когда и как это вернуть.
 *
 * Инвариант №13: удалённое с историей остаётся в базе. Этот экран —
 * единственное место, где его видно, и единственная кнопка, которой его
 * возвращают вместе со всеми связями.
 */
import { useState } from 'react'
import { useArchive, useRestoreFromArchive, type ArchiveRow } from '../api/hooks'
import { Chip, ErrorNote, Loading, ScreenHead } from '../components/ui'
import './archive.css'
import { t } from '../i18n'

function when(value: string): string {
  return new Date(value).toLocaleString('ru', { dateStyle: 'short', timeStyle: 'short' })
}

function Row({ row, onRestored }: { row: ArchiveRow; onRestored: (detail: string) => void }) {
  const restore = useRestoreFromArchive()

  return (
    <article className="card card-pad arch__row">
      <div className="row-between arch__head">
        <div>
          <b className="arch__title">{row.title}</b>
          <p className="muted arch__sub">
            {row.kind} · удалил {row.actor_name || 'неизвестно кто'} · {when(row.created_at)}
          </p>
        </div>
        {row.restored_at ? (
          <Chip tone="ok">возвращено {when(row.restored_at)}</Chip>
        ) : (
          <Chip tone="warn">{t('в архиве')}</Chip>
        )}
      </div>

      {row.summary && <p className="muted arch__summary">Вместе с записью ушло: {row.summary}</p>}

      <div className="arch__actions">
        {!row.restored_at && (
          <button
            className="btn btn-ghost btn-sm"
            disabled={restore.isPending}
            onClick={() => restore.mutate(row.id, { onSuccess: (result) => onRestored(result.detail) })}
          >
            {restore.isPending ? 'Возвращаем…' : 'Восстановить'}
          </button>
        )}
        {restore.isError && <ErrorNote error={restore.error} />}
      </div>
    </article>
  )
}

export default function Archive() {
  const [onlyPending, setOnlyPending] = useState(true)
  // сообщение о возврате живёт на экране, а не в строке: строка уходит
  // из списка сразу после восстановления, и подтверждение исчезало вместе с ней
  const [restored, setRestored] = useState<string | null>(null)
  const list = useArchive(onlyPending)
  const rows = list.data ?? []

  return (
    <section className="screen">
      <ScreenHead
        eyebrow={t('Архив')}
        title={t('Удалённое')}
        subtitle={t('Записи с историей не пропадают: отсюда их возвращают вместе со связями')}
      />

      <div className="arch__toolbar">
        <label className="arch__toggle">
          <input
            type="checkbox"
            checked={onlyPending}
            onChange={(event) => setOnlyPending(event.target.checked)}
          />
          {t('Показывать только то, что ещё в архиве')}
        </label>
        <span className="muted arch__hint">Записей: {rows.length}</span>
      </div>

      {restored && <p className="chip chip-ok arch__flash">{restored}</p>}

      {list.isLoading && <Loading />}
      {list.isError && <ErrorNote error={list.error} />}

      {!list.isLoading && rows.length === 0 && (
        <div className="card card-pad arch__empty">
          <b>{t('Архив пуст')}</b>
          <p className="muted">
            {t(
              'Здесь появится всё, что удалили: ученики, вузы из их списков, задачи и эссе. Каждую запись можно вернуть вместе со связями.',
            )}
          </p>
        </div>
      )}

      <div className="arch__list">
        {rows.map((row) => (
          <Row key={row.id} row={row} onRestored={setRestored} />
        ))}
      </div>
    </section>
  )
}
