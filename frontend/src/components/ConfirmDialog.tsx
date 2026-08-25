/**
 * Подтверждение удаления.
 *
 * Не «Вы уверены?», а именно что уйдёт и что за этим последует: сколько
 * связанных записей затронется и можно ли будет вернуть. Для массового
 * удаления и для удаления ученика просим набрать слово — случайный клик
 * так не проходит.
 *
 * Кнопка удаления стоит отдельно и выглядит иначе, чем сохранение
 * (см. `.btn-danger`): рядом с «Сохранить» ей не место. Фокус при
 * открытии уходит на «Отмена» — случайный Enter не должен ничего
 * удалять, и `initialFocus` у диалога shadcn держит ровно это.
 */
import { useEffect, useRef, useState } from 'react'
import { t } from '../i18n'
import { Dialog, DialogContent, DialogTitle } from './ui/dialog'
import { Input } from './ui/input'

export interface ConfirmProps {
  open: boolean
  /** Заголовок с названием того, что удаляют */
  title: string
  /** Что именно уйдёт: «4 вуза, 12 задач и 3 эссе» */
  what?: string
  /** Что за этим последует — по одной короткой строке */
  consequences?: string[]
  /** Слово, которое надо набрать. Пусто — набирать ничего не нужно */
  confirmWord?: string
  confirmLabel?: string
  cancelLabel?: string
  busy?: boolean
  error?: string | null
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmDialog({
  open,
  title,
  what,
  consequences = [],
  confirmWord = '',
  confirmLabel = 'Удалить',
  cancelLabel = 'Отмена',
  busy = false,
  error = null,
  onConfirm,
  onCancel,
}: ConfirmProps) {
  const [typed, setTyped] = useState('')
  const cancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (open) setTyped('')
  }, [open])

  const ready = !confirmWord || typed.trim() === confirmWord

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent
        className="confirm sm:max-w-[440px]"
        showCloseButton={false}
        initialFocus={cancelRef}
        aria-label={title}
      >
        <DialogTitle className="confirm__title">{title}</DialogTitle>
        {what && <p className="confirm__what">{what}</p>}
        {consequences.length > 0 && (
          <ul className="confirm__list">
            {consequences.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        )}

        {confirmWord && (
          <label className="confirm__field">
            <span className="muted">
              {t('Наберите ')}
              <b>{confirmWord}</b>
              {t(', чтобы подтвердить')}
            </span>
            <Input
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              placeholder={confirmWord}
              aria-label={`Наберите ${confirmWord}`}
            />
          </label>
        )}

        {error && <p className="chip chip-risk confirm__error">{error}</p>}

        <div className="confirm__actions">
          <button ref={cancelRef} className="btn btn-ghost" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button className="btn btn-danger" onClick={onConfirm} disabled={busy || !ready}>
            {busy ? 'Удаляем…' : confirmLabel}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
