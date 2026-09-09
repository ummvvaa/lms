/**
 * Предпросмотр документа с решением (фаза 62).
 *
 * Один и тот же для матрицы «Документы», вкладки карточки и строки очереди:
 * файл открывается только после входа, по своему маршруту, прямой ссылки нет.
 * Если у документа есть строка очереди — рядом «Подтвердить» и «Отклонить»
 * тем же хуком, что решает баллы; подтверждённый можно вернуть в очередь
 * («Снять подтверждение»). Файла нет — окно не открывается: вместо него
 * ставится задача ученику.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useReviewSuggestion, useRevokeDocument } from '../../api/hooks'
import Modal from '../../components/Modal'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { t } from '../../i18n'

/** Четыре частые причины отказа — из прототипа. Те же, что у баллов. */
export const DOCUMENT_REASONS = [
  'Нет подтверждающего файла',
  'Скан нечёткий',
  'Не совпадает с сертификатом',
  'Не тот документ',
]

export const STATE_TONE: Record<string, 'ok' | 'warn' | 'risk' | 'mute' | 'indigo'> = {
  confirmed: 'ok',
  pending: 'warn',
  rejected: 'risk',
  expiring: 'indigo',
  none: 'mute',
}

export const STATE_TITLE: Record<string, string> = {
  confirmed: 'подтверждён',
  pending: 'ждёт проверки',
  rejected: 'отклонён',
  expiring: 'истекает',
  none: 'нет',
}

export interface PreviewTarget {
  id: number
  title: string
  studentName: string
  fileName: string
  contentType: string
  /** документ-ссылка (фаза 65): файла нет, предпросмотр ведёт наружу */
  isLink?: boolean
  externalUrl?: string
  state: string
  expiresAt: string | null
  rejectReason: string
  /** строка очереди, если документ ждёт проверки */
  suggestion: number | null
}

export default function DocumentPreview({ target, onClose }: { target: PreviewTarget; onClose: () => void }) {
  const { review } = useReviewSuggestion()
  const revoke = useRevokeDocument()
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState('')
  const url = `/api/documents/${target.id}/file/`
  const isImage = target.contentType.startsWith('image/')
  // документ-ссылка (фаза 65): файла у нас нет, показывать нечего —
  // вместо рамки предпросмотра стоит сама ссылка, она открывается
  // в новой вкладке тем же маршрутом, с той же проверкой прав
  const isLink = target.isLink ?? false

  const decide = (decision: 'confirm' | 'decline') => {
    if (!target.suggestion) return
    review.mutate(
      { id: target.suggestion, decision, reason: decision === 'decline' ? reason : undefined },
      {
        onSuccess: () => {
          toast.success(
            decision === 'confirm' ? t('Документ подтверждён') : t('Отклонено — ученик увидит причину'),
          )
          onClose()
        },
        onError: (error) => toast.error(error.message),
      },
    )
  }

  return (
    <Modal title={`${target.title} · ${target.studentName}`} onClose={onClose} wide>
      <div className="cdoc">
        {!isLink && (
          <div className="cdoc__frame">
            {isImage ? (
              <img src={url} alt={target.title} className="cdoc__image" />
            ) : (
              <iframe src={url} title={target.title} className="cdoc__pdf" />
            )}
          </div>
        )}
        {isLink && (
          <p className="muted">{t('Документ лежит вне системы — файла у нас нет, есть ссылка на него.')}</p>
        )}
        <dl className="ckv">
          <dt>{isLink ? t('Ссылка') : t('Файл')}</dt>
          <dd>{isLink ? (target.externalUrl ?? '') : target.fileName}</dd>
          <dt>{t('Проверка')}</dt>
          <dd>
            <Badge variant={STATE_TONE[target.state] ?? 'mute'}>
              {t(STATE_TITLE[target.state] ?? target.state)}
            </Badge>
          </dd>
          <dt>{t('Срок действия')}</dt>
          <dd>{target.expiresAt ? new Date(target.expiresAt).toLocaleDateString('ru') : t('не указан')}</dd>
          {target.rejectReason && (
            <>
              <dt>{t('Причина отклонения')}</dt>
              <dd>{target.rejectReason}</dd>
            </>
          )}
          <dt>{t('Доступ')}</dt>
          <dd>
            {isLink
              ? t('ссылка открывается после входа и только своим')
              : t('только после входа, прямой ссылки нет')}
          </dd>
        </dl>

        {declining && (
          <div className="ctask__field">
            <Input
              value={reason}
              placeholder={t('Причина — её прочитает ученик')}
              onChange={(e) => setReason(e.target.value)}
              aria-label={t('Причина отклонения')}
            />
            <div className="ctask__hints">
              {DOCUMENT_REASONS.map((hint) => (
                <button key={hint} type="button" className="squeue__hint" onClick={() => setReason(t(hint))}>
                  {t(hint)}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="ctask__actions">
          <Button variant="outline" onClick={() => window.open(url, '_blank', 'noopener')}>
            {t('Открыть в новой вкладке')}
          </Button>
          <span className="cfilters__spacer" />
          {target.suggestion && !declining && (
            <>
              <Button variant="outline" onClick={() => setDeclining(true)}>
                {t('Отклонить')}
              </Button>
              <Button disabled={review.isPending} onClick={() => decide('confirm')}>
                {t('Подтвердить')}
              </Button>
            </>
          )}
          {target.suggestion && declining && (
            <>
              <Button variant="ghost" onClick={() => setDeclining(false)}>
                {t('Отмена')}
              </Button>
              <Button disabled={review.isPending || !reason.trim()} onClick={() => decide('decline')}>
                {t('Отклонить с причиной')}
              </Button>
            </>
          )}
          {!target.suggestion && (target.state === 'confirmed' || target.state === 'expiring') && (
            <Button
              variant="outline"
              disabled={revoke.isPending}
              onClick={() =>
                revoke.mutate(target.id, {
                  onSuccess: () => {
                    toast.success(t('Документ вернулся в очередь'))
                    onClose()
                  },
                  onError: (error) => toast.error(error.message),
                })
              }
            >
              {t('Снять подтверждение')}
            </Button>
          )}
          {!target.suggestion && target.state === 'rejected' && (
            <Button variant="ghost" onClick={onClose}>
              {t('Закрыть')}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}
