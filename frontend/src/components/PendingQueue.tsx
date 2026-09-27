/**
 * Очередь «Ждут вашего решения» (фаза 49).
 *
 * Общий элемент всех пяти кабинетов: с фазы 37 данные о себе вносит
 * ученик, а директор подтверждает. Строка — чекбокс, аватар, кто и класс,
 * что внёс, было → стало чипами и чип характера правки. Внизу —
 * «Подтвердить отмеченные»; отклонение просит причину, и ученик её видит.
 *
 * Данные те же, что на экране предложений: `/suggestions/from-students/`.
 * Второй источник той же очереди разошёлся бы с первым в понимании того,
 * что считать ждущим решения.
 */
import { useState } from 'react'
import { Chip, DataCard, EmptyNote, type Tone } from './ui'
import { toast } from 'sonner'
import { useReviewSuggestion, useStudentQueue, type StudentQueueRow } from '../api/hooks'
import { t } from '../i18n'
import { LIST_LIMIT } from './patterns'
import { Button } from './ui/button'
import { Checkbox } from './ui/checkbox'
import { Input } from './ui/input'
import './queue.css'

const KIND_TONE: Record<string, Tone> = { new: 'neutral', edit: 'warn', gap: 'bad' }

/** Инициалы для аватара: только буквы, слово с другим знаком пропускаем. */
function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter((word) => /^\p{L}/u.test(word))
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join('')
}

function QueueRow({
  row,
  checked,
  onCheck,
}: {
  row: StudentQueueRow
  checked: boolean
  onCheck: (value: boolean) => void
}) {
  const { review } = useReviewSuggestion()
  const [reason, setReason] = useState<string | null>(null)
  const change = row.changes[0]

  const confirm = () =>
    review.mutate(
      { id: row.id, decision: 'confirm' },
      {
        onSuccess: () => toast.success(t('Подтверждено — значение записано в профиль')),
        onError: (error) => toast.error(error.message),
      },
    )

  const decline = () =>
    review.mutate(
      { id: row.id, decision: 'decline', reason: reason ?? '' },
      {
        onSuccess: () => toast.success(t('Отклонено — ученик увидит причину')),
        onError: (error) => toast.error(error.message),
      },
    )

  return (
    <div className="pqueue__row" data-suggestion={row.id}>
      <Checkbox
        checked={checked}
        onCheckedChange={(value) => onCheck(value === true)}
        aria-label={`${t('Отметить')}: ${row.student_name}`}
      />
      <span className="pqueue__avatar" aria-hidden="true">
        {initials(row.student_name)}
      </span>
      <span className="pqueue__who">
        <b>
          {row.student_name}
          {row.student_group ? ` · ${row.student_group}` : ''}
        </b>
        <span className="muted">{change ? change.field_title : row.domain_title}</span>
      </span>

      <span className="pqueue__values">
        <Chip tone="neutral">{change?.old_display || change?.old_value || t('не было')}</Chip>
        <span aria-hidden="true" className="pqueue__arrow">
          →
        </span>
        <Chip tone="neutral">{change?.new_display || change?.new_value}</Chip>
      </span>
      <Chip tone={KIND_TONE[row.kind?.code ?? 'edit']}>{t(row.kind?.title ?? 'Правка')}</Chip>

      {reason === null ? (
        <span className="pqueue__actions">
          <Button size="sm" disabled={review.isPending} onClick={confirm}>
            {t('Подтвердить')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setReason('')}>
            {t('Отклонить')}
          </Button>
        </span>
      ) : (
        <span className="pqueue__actions pqueue__actions--wide">
          <Input
            value={reason}
            placeholder={t('Причина — её прочитает ученик')}
            aria-label={t('Причина отклонения')}
            onChange={(event) => setReason(event.target.value)}
          />
          <Button size="sm" disabled={review.isPending || !reason.trim()} onClick={decline}>
            {t('Отклонить')}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setReason(null)}>
            {t('Отмена')}
          </Button>
        </span>
      )}
    </div>
  )
}

export default function PendingQueue({
  title = 'Ждут вашего решения',
  note,
  limit = 6,
  fold = false,
}: {
  title?: string
  /** одна строка о том, что именно внесли ученики этого домена */
  note?: string
  limit?: number
  /**
   * Правила дашбордов фазы 80: пустая очередь — одна строка, длинная —
   * пять строк и «Показать все» на месте. Включается дашбордом: у остальных
   * кабинетов раскладка прежняя.
   */
  fold?: boolean
}) {
  const queue = useStudentQueue()
  const { confirmMany } = useReviewSuggestion()
  const [checked, setChecked] = useState<number[]>([])

  const rows = queue.data?.results ?? []
  const [all, setAll] = useState(false)
  const shown = fold ? (all ? rows : rows.slice(0, LIST_LIMIT)) : rows.slice(0, limit)

  if (fold && rows.length === 0) return <DataCard title={t(title)} empty={t('никто ничего не внёс')} />

  return (
    <section className="card card-pad pqueue" id="student-queue">
      <header className="pqueue__head">
        <span className="pqueue__title">
          <b>{t(title)}</b>
          {note && <span className="muted">{t(note)}</span>}
        </span>
        <Chip tone="warn" className="num">
          {rows.length}
        </Chip>
      </header>

      {rows.length === 0 && <EmptyNote what="ничего не ждёт решения" who="ученики пока ничего не внесли" />}

      {shown.map((row) => (
        <QueueRow
          key={row.id}
          row={row}
          checked={checked.includes(row.id)}
          onCheck={(value) =>
            setChecked((prev) => (value ? [...prev, row.id] : prev.filter((id) => id !== row.id)))
          }
        />
      ))}

      {fold && rows.length > LIST_LIMIT && (
        <Button variant="link" size="sm" className="showall" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? t('Свернуть') : `${t('Показать все')} (${rows.length})`}
        </Button>
      )}

      {rows.length > 0 && (
        <div className="pqueue__foot">
          <Button
            size="sm"
            disabled={confirmMany.isPending || checked.length === 0}
            onClick={() =>
              confirmMany.mutate(checked, {
                onSuccess: (result) => {
                  toast.success(`${t('Подтверждено предложений:')} ${result.confirmed}`)
                  setChecked([])
                },
                onError: (error) => toast.error(error.message),
              })
            }
          >
            {t('Подтвердить отмеченные')}
            {checked.length > 0 ? ` (${checked.length})` : ''}
          </Button>
          <span className="muted pqueue__note">{t('Отклонение просит причину — ученик её увидит')}</span>
        </div>
      )}
    </section>
  )
}
