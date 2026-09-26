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
import DataTable from '../components/DataTable'
import { Chip, ErrorNote, Loading, type Tone } from '../components/ui'
import { t } from '../i18n'
import { Checkbox } from '../components/ui/checkbox'
import { Button } from '../components/ui/button'

function tone(confidence: number): Tone {
  if (confidence >= 0.9) return 'good'
  if (confidence >= 0.75) return 'warn'
  return 'bad'
}

type Change = NonNullable<ReturnType<typeof useSuggestion>['data']>['changes'][number]

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
    <div className="card card-pad mt-4">
      <div className="toolbar">
        <span className="eyebrow">{t('Предпросмотр')}</span>
        <Chip tone="mute">{data.status_title}</Chip>
        <Chip tone="mute" className="num">
          строк: {data.changes.length}
        </Chip>
        {note && <Chip tone="ok">{note}</Chip>}
        <span className="toolbar__spacer" />
        <Button
          variant="outline"
          size="sm"
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
        </Button>
        <Button
          size="sm"
          onClick={() =>
            apply.mutate(
              { id, changes: [...checked] },
              { onSuccess: (r) => markApplied(checked, `Применено: ${r.applied}`) },
            )
          }
          disabled={apply.isPending || checked.size === 0}
        >
          Применить отмеченные ({checked.size})
        </Button>
        {appliedRows.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              revert.mutate(id, {
                onSuccess: (r) => markApplied(appliedIds, `Откачено: ${r.reverted}`),
              })
            }
            disabled={revert.isPending}
          >
            {t('Откатить')}
          </Button>
        )}
      </div>

      <DataTable
        columns={[
          { key: 'pick', title: '', width: '5%', cell: (change: Change) => <Checkbox checked={checked.has(change.id)} disabled={change.is_applied} aria-label={`${t('Отметить строку')}: ${change.field_title}`} onCheckedChange={() => toggle(change.id)} /> },
          { key: 'student', title: t('Ученик'), width: '18%', cell: (change: Change) => <b>{change.student_name ?? t('нет')}</b>, sortBy: (change: Change) => change.student_name ?? '' },
          { key: 'field', title: t('Поле'), width: '17%', cell: (change: Change) => change.field_title, sortBy: (change: Change) => change.field_title },
          {
            key: 'change',
            title: t('Было и станет'),
            width: '28%',
            cell: (change: Change) => (
              <span className="num">
                <span className="t-note">{change.old_display || t('пусто')}</span> {'→'} <b>{change.new_display}</b>
                {change.conflict && (
                  <Chip tone="bad" size="sm">
                    {change.conflict}
                  </Chip>
                )}
              </span>
            ),
          },
          { key: 'confidence', title: t('Уверенность'), width: '12%', align: 'right', cell: (change: Change) => <Chip tone={tone(Number(change.confidence))} size="sm" className="num">{Math.round(Number(change.confidence) * 100)}%</Chip>, sortBy: (change: Change) => Number(change.confidence) },
          { key: 'source', title: t('Источник'), width: '20%', cell: (change: Change) => <span className="t-note preview__source">{change.source_quote || change.source_ref || t('нет')}</span> },
        ]}
        rows={data.changes}
        rowKey={(change) => change.id}
        flash={flashed}
        selected={(change) => change.is_applied}
        empty={t('строк нет — всё отброшено на проверке домена')}
      />
    </div>
  )
}
