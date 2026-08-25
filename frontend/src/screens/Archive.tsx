/**
 * Архив: что удалено, кем, когда, как это вернуть — и как вычистить.
 *
 * Инвариант №13: удалённое с историей остаётся в базе. Отсюда его
 * возвращают вместе со связями, а с фазы 28 — и стирают навсегда, если
 * оно уже не нужно. Журнал изменений переживает и это: он остаётся
 * и показывает имя, каким оно было на момент удаления.
 */
import { useState } from 'react'
import {
  useArchive,
  useCleanupArchive,
  useCleanupPreview,
  usePurgeFromArchive,
  usePurgePreview,
  usePurgedJournal,
  useRestoreFromArchive,
  type ArchiveRow,
} from '../api/hooks'
import Empty from '../components/Empty'
import { Chip, ErrorNote, Loading, ScreenHead } from '../components/ui'
import './archive.css'
import { t } from '../i18n'
import { NativeSelect } from '../components/ui/native-select'
import { Input } from '../components/ui/input'
import { Switch } from '../components/ui/switch'

function when(value: string): string {
  return new Date(value).toLocaleString('ru', { dateStyle: 'short', timeStyle: 'short' })
}

/** Диалог безвозвратного удаления: слово набирают руками, обратного хода нет. */
function PurgeDialog({
  row,
  onClose,
  onDone,
}: {
  row: ArchiveRow
  onClose: () => void
  onDone: (d: string) => void
}) {
  const preview = usePurgePreview(row.id)
  const purge = usePurgeFromArchive()
  const [word, setWord] = useState('')

  const data = preview.data
  const required = data?.confirm_word ?? 'УДАЛИТЬ'

  return (
    <div className="card card-pad arch__purge">
      <b>{data?.what ?? `Удалить «${row.title}» навсегда?`}</b>
      {preview.isLoading && <Loading kind="table" />}
      {data && (
        <>
          {data.summary && <p className="muted arch__summary">Вместе с записью уйдёт: {data.summary}</p>}
          <ul className="arch__consequences">
            {data.consequences.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="muted arch__typed">
            {t('Наберите')} «{required}», {t('чтобы подтвердить')}
          </p>
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <Input
              value={word}
              aria-label={t('Слово подтверждения')}
              onChange={(event) => setWord(event.target.value)}
            />
            <button
              className="btn btn-primary btn-sm"
              disabled={word.trim().toUpperCase() !== required || purge.isPending}
              onClick={() =>
                purge.mutate(
                  { id: row.id, confirm: word.trim().toUpperCase() },
                  {
                    onSuccess: (result) => {
                      onDone(result.detail)
                      onClose()
                    },
                  },
                )
              }
            >
              {t('Удалить навсегда')}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={onClose}>
              {t('Отмена')}
            </button>
          </div>
          {purge.isError && <ErrorNote error={purge.error} />}
        </>
      )}
    </div>
  )
}

/** Журнал удалённой навсегда записи: карточки нет, а история осталась. */
function PurgedJournal({ id }: { id: number }) {
  const journal = usePurgedJournal(id)
  const rows = journal.data?.rows ?? []

  if (journal.isLoading) return <Loading kind="table" />
  if (rows.length === 0)
    return <p className="muted arch__summary">{t('Записей журнала по этой записи нет.')}</p>

  return (
    <div className="arch__journal">
      {rows.map((row) => (
        <p key={row.id} className="arch__journalrow">
          <span className="muted">{when(row.created_at)}</span> · {row.object_title} · {row.field_title}:{' '}
          {row.old_display || '—'} → {row.new_display || '—'}{' '}
          <span className="muted">({row.actor_name})</span>
        </p>
      ))}
    </div>
  )
}

function Row({ row, onFlash }: { row: ArchiveRow; onFlash: (detail: string) => void }) {
  const restore = useRestoreFromArchive()
  const [purging, setPurging] = useState(false)
  const [journal, setJournal] = useState(false)

  return (
    <article className="card card-pad arch__row">
      <div className="row-between arch__head">
        <div>
          <b className="arch__title">{row.title}</b>
          <p className="muted arch__sub">
            {row.kind} · удалил {row.actor_name || 'неизвестно кто'} · {when(row.created_at)}
          </p>
        </div>
        {row.purged_at ? (
          <Chip tone="risk">удалено навсегда {when(row.purged_at)}</Chip>
        ) : row.restored_at ? (
          <Chip tone="ok">возвращено {when(row.restored_at)}</Chip>
        ) : (
          <Chip tone="warn">{t('в архиве')}</Chip>
        )}
      </div>

      {row.summary && !row.purged_at && (
        <p className="muted arch__summary">Вместе с записью ушло: {row.summary}</p>
      )}

      <div className="arch__actions">
        {!row.restored_at && !row.purged_at && (
          <>
            <button
              className="btn btn-ghost btn-sm"
              disabled={restore.isPending}
              onClick={() => restore.mutate(row.id, { onSuccess: (result) => onFlash(result.detail) })}
            >
              {restore.isPending ? 'Возвращаем…' : 'Восстановить'}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setPurging((v) => !v)}>
              {t('Удалить навсегда')}
            </button>
          </>
        )}
        {row.purged_at && (
          <button className="btn btn-ghost btn-sm" onClick={() => setJournal((v) => !v)}>
            {journal ? t('Скрыть журнал') : t('Журнал изменений')}
          </button>
        )}
        {restore.isError && <ErrorNote error={restore.error} />}
      </div>

      {purging && <PurgeDialog row={row} onClose={() => setPurging(false)} onDone={onFlash} />}
      {journal && <PurgedJournal id={row.id} />}
    </article>
  )
}

/** Массовая очистка: всё, что пролежало в архиве дольше срока. */
function Cleanup({ onFlash }: { onFlash: (detail: string) => void }) {
  const [open, setOpen] = useState(false)
  const [days, setDays] = useState(180)
  const [word, setWord] = useState('')
  const preview = useCleanupPreview(days, open)
  const cleanup = useCleanupArchive()

  if (!open) {
    return (
      <button className="btn btn-ghost btn-sm" onClick={() => setOpen(true)}>
        {t('Очистить архив старше…')}
      </button>
    )
  }

  const data = preview.data

  return (
    <div className="card card-pad arch__purge">
      <div className="row-between">
        <b>{t('Очистка архива')}</b>
        <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
          {t('Скрыть')}
        </button>
      </div>
      <div className="toolbar" style={{ margin: '10px 0' }}>
        <label className="arch__toggle">
          {t('Старше скольких дней')}
          <NativeSelect
            value={days}
            aria-label={t('Старше скольких дней')}
            onChange={(event) => setDays(Number(event.target.value))}
          >
            {[30, 90, 180, 365].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </NativeSelect>
        </label>
      </div>

      {preview.isLoading && <Loading kind="table" />}
      {data && (
        <>
          <p className="muted arch__summary">
            {t('Уйдёт удалений:')} {data.entries ?? 0}
          </p>
          {(data.kinds ?? []).length > 0 && (
            <ul className="arch__consequences">
              {(data.kinds ?? []).map((kind) => (
                <li key={kind.title}>
                  {kind.title}: {kind.count}
                </li>
              ))}
            </ul>
          )}
          <ul className="arch__consequences">
            {data.consequences.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="muted arch__typed">
            {t('Наберите')} «{data.confirm_word}», {t('чтобы подтвердить')}
          </p>
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <Input
              value={word}
              aria-label={t('Слово подтверждения')}
              onChange={(event) => setWord(event.target.value)}
            />
            <button
              className="btn btn-primary btn-sm"
              disabled={
                word.trim().toUpperCase() !== data.confirm_word ||
                (data.entries ?? 0) === 0 ||
                cleanup.isPending
              }
              onClick={() =>
                cleanup.mutate(
                  { days, confirm: word.trim().toUpperCase() },
                  {
                    onSuccess: (result) => {
                      onFlash(result.detail)
                      setOpen(false)
                      setWord('')
                    },
                  },
                )
              }
            >
              {t('Очистить')}
            </button>
          </div>
          {cleanup.isError && <ErrorNote error={cleanup.error} />}
        </>
      )}
    </div>
  )
}

export default function Archive() {
  const [onlyPending, setOnlyPending] = useState(true)
  // сообщение о возврате живёт на экране, а не в строке: строка уходит
  // из списка сразу после восстановления, и подтверждение исчезало вместе с ней
  const [flash, setFlash] = useState<string | null>(null)
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
          <Switch checked={onlyPending} onCheckedChange={setOnlyPending} />
          {t('Показывать только то, что ещё в архиве')}
        </label>
        <span className="muted arch__hint">Записей: {rows.length}</span>
        <Cleanup onFlash={setFlash} />
      </div>

      {flash && <p className="chip chip-ok arch__flash">{flash}</p>}

      {list.isLoading && <Loading kind="table" />}
      {list.isError && <ErrorNote error={list.error} />}

      {!list.isLoading && rows.length === 0 && (
        <Empty
          title={t('Архив пуст')}
          what={t('Сюда попадает всё удалённое — и отсюда же возвращается.')}
          hint={t(
            'Ученики, вузы из их списков, задачи и эссе. Запись возвращается вместе со всем, что ушло с ней.',
          )}
        />
      )}

      <div className="arch__list">
        {rows.map((row) => (
          <Row key={row.id} row={row} onFlash={setFlash} />
        ))}
      </div>
    </section>
  )
}
