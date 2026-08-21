/**
 * Экран предпросмотра предложения.
 *
 * Сортировка по уверенности — сомнительное сверху. Галочки для частичного
 * принятия. «Принять все выше порога» — отдельное явное действие.
 * По каждой строке показан источник.
 */
import { useEffect, useState } from 'react'
import { useApplySuggestion, useSuggestion } from '../api/hooks'
import { ErrorNote, Loading } from '../components/ui'

const STATUS_TITLE: Record<string, string> = {
  draft: 'черновик',
  pending: 'ждёт решения',
  applied: 'применено',
  partially_applied: 'применено частично',
  rejected: 'отклонено',
  reverted: 'откачено',
}

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

  // по умолчанию отмечаем уверенные строки, сомнительные пусть посмотрит человек
  useEffect(() => {
    if (!data) return
    setChecked(new Set(data.changes.filter((c) => Number(c.confidence) >= 0.9).map((c) => c.id)))
  }, [data])

  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const pending = data.changes.filter((c) => !c.is_applied)
  const applied = data.changes.filter((c) => c.is_applied)

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
        <span className="eyebrow">👁 Предпросмотр</span>
        <span className="chip chip-mute">{STATUS_TITLE[data.status] ?? data.status}</span>
        <span className="chip chip-mute num">строк: {data.changes.length}</span>
        {note && <span className="chip chip-ok">{note}</span>}
        <span className="toolbar__spacer" />
        <button
          className="btn btn-ghost btn-sm"
          onClick={() =>
            acceptAbove.mutate(
              { id, threshold: 0.9 },
              { onSuccess: (r) => setNote(`Принято по порогу 0.9: ${r.applied}`) },
            )
          }
          disabled={acceptAbove.isPending || pending.length === 0}
        >
          Принять все выше 0.9
        </button>
        <button
          className="btn btn-primary btn-sm"
          onClick={() =>
            apply.mutate(
              { id, changes: [...checked] },
              { onSuccess: (r) => setNote(`Применено: ${r.applied}`) },
            )
          }
          disabled={apply.isPending || checked.size === 0}
        >
          Применить отмеченные ({checked.size})
        </button>
        {applied.length > 0 && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => revert.mutate(id, { onSuccess: (r) => setNote(`Откачено: ${r.reverted}`) })}
            disabled={revert.isPending}
          >
            Откатить
          </button>
        )}
      </div>

      <table className="history preview">
        <thead>
          <tr>
            <th />
            <th>Ученик</th>
            <th>Поле</th>
            <th>Было → станет</th>
            <th>Уверенность</th>
            <th>Источник</th>
          </tr>
        </thead>
        <tbody>
          {data.changes.map((change) => (
            <tr key={change.id} className={change.is_applied ? 'preview--applied' : undefined}>
              <td>
                <input
                  type="checkbox"
                  checked={checked.has(change.id)}
                  disabled={change.is_applied}
                  onChange={() => toggle(change.id)}
                />
              </td>
              <td style={{ fontWeight: 650 }}>{change.student_name ?? '—'}</td>
              <td className="muted">{change.field_name}</td>
              <td className="num">
                <span className="muted">{change.old_value || '—'}</span> → <b>{change.new_value}</b>
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
      {data.changes.length === 0 && <p className="muted">Строк нет — всё отброшено на проверке домена.</p>}
    </div>
  )
}
