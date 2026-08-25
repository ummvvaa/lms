/**
 * Что ученики написали о себе — отдельным списком у директора домена.
 *
 * Данные от ученика не приравниваются к проверенным: пока строка
 * не подтверждена, по журналу видно, что число назвал он.
 */
import { useState } from 'react'
import { usePendingOnboarding, useReviewOnboarding } from '../api/hooks'
import { t } from '../i18n'
import { Input } from './ui/input'

export default function OnboardingQueue() {
  const pending = usePendingOnboarding()
  const review = useReviewOnboarding()
  const [edited, setEdited] = useState<Record<number, string>>({})

  const rows = pending.data ?? []
  if (rows.length === 0) return null

  return (
    <div className="card card-pad queue" id="onboarding-queue">
      <span className="eyebrow">{t('Ученики заполнили о себе')}</span>
      <p className="muted queue__note">
        {t(
          'Это слова ученика, а не проверенный факт. Подтвердите или поправьте — до этого значение помечено в журнале как анкета.',
        )}
      </p>
      {rows.map((row) => (
        <div key={row.id} className="queue__row">
          <div className="queue__what">
            <b>{row.student_name}</b>
            <span className="muted queue__question"> · {row.question_title}</span>
          </div>
          <Input
            className="queue__value"
            value={edited[row.id] ?? row.value}
            onChange={(e) => setEdited((prev) => ({ ...prev, [row.id]: e.target.value }))}
            aria-label={`Значение: ${row.question_title}`}
          />
          <div className="queue__actions">
            <button
              className="btn btn-primary btn-sm"
              disabled={review.isPending}
              onClick={() => review.mutate({ id: row.id, decision: 'confirm', value: edited[row.id] })}
            >
              {t('Подтвердить')}
            </button>
            <button
              className="btn btn-ghost btn-sm"
              disabled={review.isPending}
              onClick={() => review.mutate({ id: row.id, decision: 'decline' })}
            >
              {t('Снять')}
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
