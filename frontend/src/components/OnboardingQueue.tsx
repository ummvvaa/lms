/**
 * Анкета первого входа — отдельным списком у директора домена (D16).
 *
 * Это не очередь решений: ответы анкеты уже лежат в профиле как слова
 * ученика и подтверждения не ждут. Список нужен, чтобы директор видел,
 * что появилось, и мог поправить или снять кривое. Предложения с «Моих
 * данных» — другое: они ждут решения в очереди ниже. Слияние отложено
 * решением владельца фазы 64 — вернёмся, если директора начнут править
 * анкету руками.
 */
import { useState } from 'react'
import { usePendingOnboarding, useReviewOnboarding } from '../api/hooks'
import { t } from '../i18n'
import { Input } from './ui/input'
import { Button } from './ui/button'

export default function OnboardingQueue() {
  const pending = usePendingOnboarding()
  const review = useReviewOnboarding()
  const [edited, setEdited] = useState<Record<number, string>>({})

  const rows = pending.data ?? []
  if (rows.length === 0) return null

  return (
    <div className="card card-pad queue" id="onboarding-queue">
      <span className="eyebrow">{t('Заполнили при входе')}</span>
      <p className="muted queue__note">
        {t(
          'Ответы анкеты первого входа уже в профиле — как слова ученика, в журнале они помечены анкетой. Решения они не ждут: здесь их можно поправить или снять.',
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
            <Button
              size="sm"
              disabled={review.isPending}
              onClick={() => review.mutate({ id: row.id, decision: 'confirm', value: edited[row.id] })}
            >
              {t('Подтвердить')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={review.isPending}
              onClick={() => review.mutate({ id: row.id, decision: 'decline' })}
            >
              {t('Снять')}
            </Button>
          </div>
        </div>
      ))}
    </div>
  )
}
