/**
 * Экран предпросмотра предложения.
 *
 * Сортировка по уверенности — сомнительное сверху. Галочки для частичного
 * принятия. «Принять все выше порога» — отдельное явное действие.
 * По каждой строке показан источник.
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { useApplySuggestion, useSuggestion } from '../api/hooks'
import { ErrorNote, Loading } from '../components/ui'
import { t } from '../i18n'
import { Checkbox } from '../components/ui/checkbox'

function tone(confidence: number): string {
  if (confidence >= 0.9) return 'chip-ok'
  if (confidence >= 0.75) return 'chip-warn'
  return 'chip-risk'
}

export default function SuggestionPreview({ id }: { id: number }) {
  const { data, isLoading, error } = useSuggestion(id)
  const { apply, acceptAbove, revert } = useApplySuggestion()
  const [checked, setChecked] = useState<Set<number>>(new Set())
  const [note, setNote] = useState<string | null>(null)
  // применённые строки подсвечиваются и гаснут: после «Принять все выше 0.9»
  // их бывает сразу несколько десятков, и без подсветки непонятно, какие
  const [flashed, setFlashed] = useState<ReadonlySet<number>>(new Set())

  /** Отметить строки как только что применённые и сказать об этом вслух. */
  function markApplied(ids: Iterable<number>, text: string) {
    setNote(text)
    setFlashed(new Set(ids))
    toast.success(text)
  }

  // по умолчанию отмечаем уверенные строки, сомнительные пусть посмотрит человек
  useEffect(() => {
    if (!data) return
    setChecked(new Set(data.changes.filter((c) => Number(c.confidence) >= 0.9).map((c) => c.id)))
  }, [data])

  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const pending = data.changes.filter((c) => !c.is_applied)
  const appliedRows = data.changes.filter((c) => c.is_applied)
  const appliedIds = appliedRows.map((c) => c.id)

  function toggle(changeId: number) {
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(changeId)) next.delete(changeId)
      else next.add(changeId)
      return next
    })
  }

  return (
    <div className="card card-pad" style={{ marginTop: 16 }}>
      <div className="toolbar">
        <span className="eyebrow">{t('Предпросмотр')}</span>
        <span className="chip chip-mute">{data.status_title}</span>
        <span className="chip chip-mute num">строк: {data.changes.length}</span>
        {note && <span className="chip chip-ok">{note}</span>}
        <span className="toolbar__spacer" />
        <button
          className="btn btn-ghost btn-sm"
          onClick={() =>
            acceptAbove.mutate(
              { id, threshold: 0.9 },
              {
                onSuccess: (r) =>
                  markApplied(
                    pending.filter((c) => Number(c.confidence) >= 0.9).map((c) => c.id),
                    `Принято по порогу 0.9: ${r.applied}`,
                  ),
              },
            )
          }
          disabled={acceptAbove.isPending || pending.length === 0}
        >
          {t('Принять все выше 0.9')}
        </button>
        <button
          className="btn btn-primary btn-sm"
          onClick={() =>
            apply.mutate(
              { id, changes: [...checked] },
              { onSuccess: (r) => markApplied(checked, `Применено: ${r.applied}`) },
            )
          }
          disabled={apply.isPending || checked.size === 0}
        >
          Применить отмеченные ({checked.size})
        </button>
        {appliedRows.length > 0 && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() =>
              revert.mutate(id, {
                onSuccess: (r) => markApplied(appliedIds, `Откачено: ${r.reverted}`),
              })
            }
            disabled={revert.isPending}
          >
            {t('Откатить')}
          </button>
        )}
      </div>

      <table className="history preview">
        <thead>
          <tr>
            <th />
            <th>{t('Ученик')}</th>
            <th>{t('Поле')}</th>
            <th>{t('Было → станет')}</th>
            <th>{t('Уверенность')}</th>
            <th>{t('Источник')}</th>
          </tr>
        </thead>
        <tbody>
          {data.changes.map((change) => (
            <tr
              key={change.id}
              className={
                [change.is_applied ? 'preview--applied' : '', flashed.has(change.id) ? 'row--flash' : '']
                  .filter(Boolean)
                  .join(' ') || undefined
              }
            >
              <td>
                <Checkbox
                  checked={checked.has(change.id)}
                  disabled={change.is_applied}
                  onCheckedChange={() => toggle(change.id)}
                />
              </td>
              <td style={{ fontWeight: 650 }}>{change.student_name ?? '—'}</td>
              <td className="muted">{change.field_title}</td>
              <td className="num">
                <span className="muted">{change.old_display || '—'}</span> → <b>{change.new_display}</b>
                {change.conflict && <div className="chip chip-risk">{change.conflict}</div>}
              </td>
              <td>
                <span className={`chip ${tone(Number(change.confidence))} num`}>
                  {Math.round(Number(change.confidence) * 100)}%
                </span>
              </td>
              <td className="muted preview__source">{change.source_quote || change.source_ref || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.changes.length === 0 && (
        <p className="muted">{t('Строк нет — всё отброшено на проверке домена.')}</p>
      )}
    </div>
  )
}
