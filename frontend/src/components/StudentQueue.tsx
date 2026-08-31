/**
 * Очередь «От учеников» на экране предложений (фаза 37).
 *
 * Ученики вносят данные о себе, решение принимает владелец домена.
 * Сервер отдаёт строки отсортированными по расхождению: IELTS 8.5
 * вместо 6.0 директор видит первым. Действия: подтвердить, поправить
 * и подтвердить, отклонить с причиной; отмеченные — подтвердить разом.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useReviewSuggestion, useStudentQueue, type StudentQueueRow } from '../api/hooks'
import { t } from '../i18n'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Checkbox } from './ui/checkbox'
import { Input } from './ui/input'

function Row({
  row,
  checked,
  onCheck,
}: {
  row: StudentQueueRow
  checked: boolean
  onCheck: (value: boolean) => void
}) {
  const { review } = useReviewSuggestion()
  const [mode, setMode] = useState<'view' | 'edit' | 'decline'>('view')
  const [reason, setReason] = useState('')
  const [edited, setEdited] = useState<Record<string, string>>({})

  const confirm = (values?: Record<string, string>) =>
    review.mutate(
      { id: row.id, decision: 'confirm', values },
      {
        onSuccess: () => toast.success(t('Подтверждено — значение записано в профиль')),
        onError: (error) => toast.error(error.message),
      },
    )

  const decline = () =>
    review.mutate(
      { id: row.id, decision: 'decline', reason },
      {
        onSuccess: () => toast.success(t('Отклонено — ученик увидит причину')),
        onError: (error) => toast.error(error.message),
      },
    )

  return (
    <div className="squeue__row" data-suggestion={row.id}>
      <Checkbox
        checked={checked}
        onCheckedChange={(value) => onCheck(value === true)}
        aria-label={`${t('Отметить')}: ${row.student_name}`}
      />
      <div className="squeue__body">
        <div className="squeue__what">
          <b>{row.student_name}</b>
          <span className="muted"> · {new Date(row.created_at).toLocaleString('ru')}</span>
          {row.divergence >= 0.2 && <Badge variant="warn">{t('сильно расходится')}</Badge>}
        </div>
        {row.changes.map((change) => (
          <p key={change.id} className="muted squeue__change">
            {change.field_title}:{' '}
            {change.new_object_key ? (
              <b>{change.new_display || change.new_value}</b>
            ) : (
              <>
                {change.old_display || change.old_value || '—'} →{' '}
                <b>{change.new_display || change.new_value}</b>
              </>
            )}
            {mode === 'edit' && (
              <Input
                className="squeue__editinput"
                value={edited[String(change.id)] ?? change.new_value}
                onChange={(e) => setEdited((prev) => ({ ...prev, [String(change.id)]: e.target.value }))}
                aria-label={`${t('Поправить')}: ${change.field_title}`}
              />
            )}
          </p>
        ))}
        {mode === 'decline' && (
          <Input
            className="squeue__editinput"
            value={reason}
            placeholder={t('Причина — её прочитает ученик')}
            onChange={(e) => setReason(e.target.value)}
            aria-label={t('Причина отклонения')}
          />
        )}
      </div>
      <div className="squeue__actions">
        {mode === 'view' && (
          <>
            <Button size="sm" disabled={review.isPending} onClick={() => confirm()}>
              {t('Подтвердить')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setMode('edit')}>
              {t('Поправить')}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setMode('decline')}>
              {t('Отклонить')}
            </Button>
          </>
        )}
        {mode === 'edit' && (
          <>
            <Button size="sm" disabled={review.isPending} onClick={() => confirm(edited)}>
              {t('Подтвердить с правкой')}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setMode('view')}>
              {t('Отмена')}
            </Button>
          </>
        )}
        {mode === 'decline' && (
          <>
            <Button size="sm" disabled={review.isPending || !reason.trim()} onClick={decline}>
              {t('Отклонить с причиной')}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setMode('view')}>
              {t('Отмена')}
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

export default function StudentQueue() {
  const queue = useStudentQueue()
  const { confirmMany } = useReviewSuggestion()
  const [checked, setChecked] = useState<number[]>([])

  const rows = queue.data?.results ?? []
  if (rows.length === 0) return null

  const confirmChecked = () =>
    confirmMany.mutate(checked, {
      onSuccess: (result) => {
        toast.success(`${t('Подтверждено предложений:')} ${result.confirmed}`)
        setChecked([])
      },
      onError: (error) => toast.error(error.message),
    })

  return (
    <div className="card card-pad" id="student-queue">
      <span className="eyebrow">{t('От учеников')}</span>
      <p className="muted squeue__note">
        {t('Ученики внесли это о себе. Сначала — то, что сильнее расходится с текущими данными.')}
      </p>
      {rows.map((row) => (
        <Row
          key={row.id}
          row={row}
          checked={checked.includes(row.id)}
          onCheck={(value) =>
            setChecked((prev) => (value ? [...prev, row.id] : prev.filter((id) => id !== row.id)))
          }
        />
      ))}
      {checked.length > 1 && (
        <div className="squeue__bulk">
          <Button size="sm" disabled={confirmMany.isPending} onClick={confirmChecked}>
            {t('Подтвердить отмеченные')} ({checked.length})
          </Button>
        </div>
      )}
    </div>
  )
}
