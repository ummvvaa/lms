/**
 * Архив: что удалено, кем, когда, как это вернуть — и как вычистить.
 *
 * Инвариант №13: удалённое с историей остаётся в базе. Отсюда его
 * возвращают вместе со связями, а с фазы 28 — и стирают навсегда, если
 * оно уже не нужно. Журнал изменений переживает и это: он остаётся
 * и показывает имя, каким оно было на момент удаления. Удалённые уроки
 * приходят сюда тем же путём и возвращаются той же кнопкой.
 *
 * Вид — таблица: тип, что, кто и когда удалил, состояние, возврат в строке;
 * стирание и журнал — в правой панели.
 */
import { useMemo, useState } from 'react'
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
import DataTable, { type Column } from '../components/DataTable'
import EditDrawer from '../components/EditDrawer'
import Field from '../components/Field'
import { Row, Rows, Segmented } from '../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { formatDateTime } from '../lib/format'
import './academics/academics.css'

function when(value: string): string {
  return formatDateTime(value)
}

/** Безвозвратное удаление: слово набирают руками, обратного хода нет. */
function PurgePanel({ row, onDone }: { row: ArchiveRow; onDone: (detail: string) => void }) {
  const preview = usePurgePreview(row.id)
  const purge = usePurgeFromArchive()
  const [word, setWord] = useState('')
  const data = preview.data
  // подтверждение осмысленным вводом: где у записи есть почта,
  // набирают её — так видно, кого именно стирают
  // eslint-disable-next-line i18n-text -- слово сверяет сервер (`core/archive.py`, CONFIRM_WORD): перевод сломал бы проверку
  const confirm = data?.confirm ?? { kind: 'word' as const, value: data?.confirm_word ?? 'УДАЛИТЬ', email: '' }
  const byEmail = confirm.kind === 'email'
  const typed = word.trim()
  const matches = byEmail ? typed.toLowerCase() === confirm.value.toLowerCase() : typed.toUpperCase() === confirm.value

  if (preview.isLoading) return <Loading kind="table" />
  if (!data) return null
  if (data.refusal) return <Chip tone="warn">{data.refusal}</Chip>
  return (
    <div className="acad__form">
      <b className="t-card">{data.what}</b>
      {(data.kept?.length ?? 0) > 0 && (
        <DataCard title={t('Останется')}>
          <Rows>
            {data.kept!.map((line) => (
              <Row key={line.title} title={line.title} value={<span className="num">{line.count}</span>} />
            ))}
          </Rows>
        </DataCard>
      )}
      {(data.erased?.length ?? 0) > 0 && (
        <DataCard title={t('Исчезнет совсем')}>
          <Rows>
            {data.erased!.map((line) => (
              <Row key={line.title} title={line.title} note={line.note || undefined} value={<span className="num">{line.count}</span>} />
            ))}
          </Rows>
        </DataCard>
      )}
      {[...(data.impact ?? []), ...(data.consequences ?? [])].length > 0 && (
        <DataCard title={t('На что повлияет')}>
          <Rows>
            {[...(data.impact ?? []), ...(data.consequences ?? [])].map((line) => (
              <Row key={line} icon="alert" tone="warn" title={line} />
            ))}
          </Rows>
        </DataCard>
      )}
      <Field
        name="confirm"
        label={byEmail ? t('Наберите почту, чтобы подтвердить: {email}', { email: confirm.value }) : t('Наберите «{word}», чтобы подтвердить', { word: confirm.value })}
        value={word}
        placeholder={byEmail ? confirm.value : undefined}
        onChange={setWord}
      />
      <div className="acad__actions">
        <Button
          variant="destructive"
          disabled={!matches || purge.isPending}
          onClick={() => purge.mutate({ id: row.id, confirm: byEmail ? typed : typed.toUpperCase() }, { onSuccess: (result) => onDone(result.detail) })}
        >
          {t('Удалить навсегда')}
        </Button>
      </div>
      {purge.isError && <ErrorNote error={purge.error} />}
    </div>
  )
}

/** Журнал удалённой навсегда записи: карточки нет, а история осталась. */
function PurgedJournal({ id }: { id: number }) {
  const journal = usePurgedJournal(id)
  const rows = journal.data?.rows ?? []
  if (journal.isLoading) return <Loading kind="table" />
  return (
    <DataCard title={t('Журнал изменений')} count={rows.length || undefined} empty={rows.length === 0 && t('записей журнала по этой записи нет')}>
      <Rows>
        {rows.map((row) => (
          <Row
            key={row.id}
            title={`${row.object_title} · ${row.field_title}`}
            note={`${when(row.created_at)} · ${row.old_display || t('пусто')} → ${row.new_display || t('пусто')} · ${row.actor_name}`}
          />
        ))}
      </Rows>
    </DataCard>
  )
}

/** Массовая очистка: всё, что пролежало в архиве дольше срока. */
function CleanupPanel({ onDone }: { onDone: (detail: string) => void }) {
  const [days, setDays] = useState(180)
  const [word, setWord] = useState('')
  const preview = useCleanupPreview(days, true)
  const cleanup = useCleanupArchive()
  const data = preview.data
  return (
    <div className="acad__form">
      <Field kind="select" name="days" label={t('Старше скольких дней')} value={String(days)} onChange={(value) => setDays(Number(value))} options={[30, 90, 180, 365].map((value) => ({ value: String(value), title: String(value) }))} />
      {preview.isLoading && <Loading kind="table" />}
      {data && (
        <>
          <DataCard title={t('Будет стёрто')} count={data.entries ?? 0} empty={(data.entries ?? 0) === 0 && t('старше этого срока в архиве ничего нет')}>
            <Rows>
              {(data.kinds ?? []).map((kind) => (
                <Row key={kind.title} title={kind.title} value={<span className="num">{kind.count}</span>} />
              ))}
              {(data.consequences ?? []).map((line) => (
                <Row key={line} icon="alert" tone="warn" title={line} />
              ))}
            </Rows>
          </DataCard>
          <Field name="confirm" label={t('Наберите «{word}», чтобы подтвердить', { word: data.confirm_word })} value={word} onChange={setWord} />
          <div className="acad__actions">
            <Button
              variant="destructive"
              disabled={word.trim().toUpperCase() !== data.confirm_word || (data.entries ?? 0) === 0 || cleanup.isPending}
              onClick={() => cleanup.mutate({ days, confirm: word.trim().toUpperCase() }, { onSuccess: (result) => onDone(result.detail) })}
            >
              {t('Очистить')}
            </Button>
          </div>
          {cleanup.isError && <ErrorNote error={cleanup.error} />}
        </>
      )}
    </div>
  )
}

export default function Archive() {
  const [onlyPending, setOnlyPending] = useState(true)
  const [kind, setKind] = useState('')
  const [panel, setPanel] = useState<{ mode: 'purge' | 'journal'; row: ArchiveRow } | { mode: 'cleanup' } | null>(null)
  // сообщение о возврате живёт на экране, а не в строке: строка уходит
  // из списка сразу после восстановления, и подтверждение исчезало вместе с ней
  const [flash, setFlash] = useState<string | null>(null)
  const list = useArchive(onlyPending)
  const restore = useRestoreFromArchive()
  const all = useMemo(() => list.data ?? [], [list.data])
  const kinds = useMemo(() => Array.from(new Set(all.map((row) => row.kind))).sort(), [all])
  const rows = kind ? all.filter((row) => row.kind === kind) : all

  const done = (detail: string) => {
    setFlash(detail)
    setPanel(null)
  }

  const columns: Column<ArchiveRow>[] = [
    { key: 'kind', title: t('Тип'), width: '14%', cell: (row) => row.kind, sortBy: (row) => row.kind },
    {
      key: 'title',
      title: t('Что'),
      width: '30%',
      cell: (row) => (
        <>
          <b>{row.title}</b>
          {row.summary && !row.purged_at && <span className="t-note"> · {row.summary}</span>}
        </>
      ),
      sortBy: (row) => row.title,
    },
    { key: 'who', title: t('Кто удалил'), width: '16%', cell: (row) => row.actor_name || <span className="t-note">{t('неизвестно кто')}</span> },
    { key: 'when', title: t('Когда'), width: '12%', cell: (row) => <span className="num">{when(row.created_at)}</span>, sortBy: (row) => row.created_at },
    {
      key: 'state',
      title: t('Состояние'),
      width: '14%',
      cell: (row) =>
        row.purged_at ? (
          <Chip tone="bad" size="sm">
            {t('удалено навсегда {date}', { date: when(row.purged_at) })}
          </Chip>
        ) : row.restored_at ? (
          <Chip tone="good" size="sm">
            {t('возвращено {date}', { date: when(row.restored_at) })}
          </Chip>
        ) : (
          <Chip tone="warn" size="sm">
            {t('в архиве')}
          </Chip>
        ),
      sortBy: (row) => (row.purged_at ? 2 : row.restored_at ? 1 : 0),
    },
    {
      key: 'acts',
      title: '',
      width: '14%',
      align: 'right',
      cell: (row) => (
        <span className="acad__inline">
          {!row.restored_at && !row.purged_at && (
            <>
              <Button variant="secondary" size="sm" disabled={restore.isPending} onClick={() => restore.mutate(row.id, { onSuccess: (result) => setFlash(result.detail), onError: (error) => setFlash(error.message) })}>
                {t('Вернуть')}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setPanel({ mode: 'purge', row })}>
                {t('Стереть')}
              </Button>
            </>
          )}
          {row.purged_at && (
            <Button variant="ghost" size="sm" onClick={() => setPanel({ mode: 'journal', row })}>
              {t('Журнал изменений')}
            </Button>
          )}
        </span>
      ),
    },
  ]

  return (
    <div>
      <ScreenHead
        title={t('Архив')}
        actions={
          <Button variant="outline" onClick={() => setPanel({ mode: 'cleanup' })}>
            {t('Очистить архив старше…')}
          </Button>
        }
      />

      <div className="acad__toolbar">
        <Segmented<string> value={kind} onChange={setKind} label={t('Тип записи')} items={[{ value: '', label: t('Все {count}', { count: all.length }) }, ...kinds.map((value) => ({ value, label: `${value} ${all.filter((row) => row.kind === value).length}` }))]} />
        <Field usageFilter kind="checkbox" name="pending" label={t('Показывать только то, что ещё в архиве')} checked={onlyPending} onChange={setOnlyPending} />
      </div>

      {flash && (
        <Chip tone="good" size="sm">
          {flash}
        </Chip>
      )}
      {list.isLoading && <Loading kind="table" />}
      {list.isError && <ErrorNote error={list.error} />}

      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard title={t('Удалённое')} count={rows.length || undefined} empty={!list.isLoading && rows.length === 0 && t('архив пуст — сюда попадает всё удалённое и отсюда же возвращается')}>
            <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} limit={30} />
          </DataCard>
        </div>
      </div>

      <EditDrawer
        open={panel !== null}
        onClose={() => setPanel(null)}
        title={panel?.mode === 'cleanup' ? t('Очистка архива') : panel?.mode === 'journal' ? t('Журнал изменений') : t('Удалить навсегда')}
        sub={panel && panel.mode !== 'cleanup' ? panel.row.title : undefined}
      >
        {panel?.mode === 'purge' && <PurgePanel key={panel.row.id} row={panel.row} onDone={done} />}
        {panel?.mode === 'journal' && <PurgedJournal id={panel.row.id} />}
        {panel?.mode === 'cleanup' && <CleanupPanel onDone={done} />}
      </EditDrawer>
    </div>
  )
}
