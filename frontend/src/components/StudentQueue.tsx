/**
 * Очередь «От учеников» на экране предложений (фаза 37).
 *
 * Ученики вносят данные о себе, решение принимает владелец домена.
 * Сервер отдаёт строки отсортированными по расхождению: IELTS 8.5
 * вместо 6.0 директор видит первым. Действия: подтвердить, поправить
 * и подтвердить, отклонить с причиной; отмеченные — подтвердить разом.
 *
 * С фазы 61 ту же строку показывает кабинет куратора: он берёт `QueueRow`
 * и рисует вокруг неё свою шапку с вкладками и порядком. Второй такой же
 * строки в проекте нет — иначе решение куратора и решение директора
 * начали бы расходиться в мелочах, а это одно и то же действие.
 */
import { useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { useReviewSuggestion, useStudentQueue, type StudentQueueRow } from '../api/hooks'
import { t } from '../i18n'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Checkbox } from './ui/checkbox'
import { Input } from './ui/input'

export function QueueRow({
  row,
  checked = false,
  onCheck,
  reasons = [],
  onPreview,
  escalate,
}: {
  row: StudentQueueRow
  checked?: boolean
  /** без обработчика чекбокса нет вовсе: отметка, по которой ничего
   *  не происходит, обманывает так же, как кнопка без действия.
   *  Так очередь на главной показывает строки без массового
   *  подтверждения (фаза 61) */
  onCheck?: (value: boolean) => void
  /** подсказки причин отклонения — их показывает кабинет куратора (фаза 61) */
  reasons?: string[]
  /** строка документа (фаза 62): предпросмотр файла открывает кабинет куратора */
  onPreview?: (row: StudentQueueRow) => void
  /** передать владельцу домена — действие куратора (фаза 62) */
  escalate?: (row: StudentQueueRow) => ReactNode
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
      {onCheck && (
        <Checkbox
          checked={checked}
          onCheckedChange={(value) => onCheck(value === true)}
          aria-label={`${t('Отметить')}: ${row.student_name}`}
        />
      )}
      <div className="squeue__body">
        <div className="squeue__what">
          <b>{row.student_name}</b>
          {row.student_group && <Badge variant="mute">{row.student_group}</Badge>}
          {/* время подачи своим элементом: эталоны раскладки маскируют
              именно его — оно настоящее и меняется каждым прогоном */}
          <span className="muted squeue__when"> · {new Date(row.created_at).toLocaleString('ru')}</span>
          {row.divergence >= 0.2 && <Badge variant="warn">{t('сильно расходится')}</Badge>}
          {/* порог скачка считает сервер: у куратора и у владельца домена
              «резкий скачок» обязан значить одно и то же (фаза 61) */}
          {row.sharp_jump && <Badge variant="risk">{t('резкий скачок')}</Badge>}
          {row.document && <Badge variant="mute">{t('документ')}</Badge>}
          {/* переданное куратором — у владельца домена сверху, с его именем и словами (фаза 62) */}
          {row.escalated && (
            <Badge variant="indigo">
              {t('от куратора')} {row.escalated_by_name}
            </Badge>
          )}
        </div>
        {row.escalated && row.escalation_comment && (
          <p className="muted squeue__change">«{row.escalation_comment}»</p>
        )}
        {row.document && (
          <p className="muted squeue__change">
            {row.document.doc_type_title}: <b>{row.document.file_name}</b>
            {row.document.expires_at &&
              ` · ${t('до')} ${new Date(row.document.expires_at).toLocaleDateString('ru')}`}
          </p>
        )}
        {!row.document &&
          row.changes.map((change) => (
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
          <>
            <Input
              className="squeue__editinput"
              value={reason}
              placeholder={t('Причина — её прочитает ученик')}
              onChange={(e) => setReason(e.target.value)}
              aria-label={t('Причина отклонения')}
            />
            {reasons.length > 0 && (
              <div className="squeue__reasons">
                {reasons.map((hint) => (
                  <button key={hint} type="button" className="squeue__hint" onClick={() => setReason(hint)}>
                    {hint}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
      <div className="squeue__actions">
        {mode === 'view' && (
          <>
            {row.document && (
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  onPreview ? onPreview(row) : window.open(row.document?.file_url, '_blank', 'noopener')
                }
              >
                {t('Открыть файл')}
              </Button>
            )}
            <Button size="sm" disabled={review.isPending} onClick={() => confirm()}>
              {t('Подтвердить')}
            </Button>
            {/* «Поправить» для документа нет — нечего править */}
            {!row.document && (
              <Button variant="outline" size="sm" onClick={() => setMode('edit')}>
                {t('Поправить')}
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => setMode('decline')}>
              {t('Отклонить')}
            </Button>
            {escalate?.(row)}
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
        <QueueRow
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
