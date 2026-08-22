/**
 * Подтверждение удаления.
 *
 * Не «Вы уверены?», а именно что уйдёт и что за этим последует: сколько
 * связанных записей затронется и можно ли будет вернуть. Для массового
 * удаления и для удаления ученика просим набрать слово — случайный клик
 * так не проходит.
 *
 * Кнопка удаления стоит отдельно и выглядит иначе, чем сохранение
 * (см. `.btn-danger`): рядом с «Сохранить» ей не место.
 */
import { useEffect, useRef, useState } from 'react'

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
    if (!open) return
    setTyped('')
    // фокус уходит на «Отмена»: случайный Enter не должен ничего удалять
    cancelRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  if (!open) return null

  const ready = !confirmWord || typed.trim() === confirmWord

  return (
    <div className="confirm__backdrop" role="presentation" onClick={onCancel}>
      <div
        className="confirm"
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="confirm__title">{title}</h2>
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
              Наберите <b>{confirmWord}</b>, чтобы подтвердить
            </span>
            <input
              className="input"
              value={typed}
              autoFocus
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
      </div>
    </div>
  )
}
