/**
 * Пустое состояние экрана.
 *
 * Пустая таблица и белое поле выглядят как поломка. Экран без данных
 * обязан объяснить, что это за раздел, что здесь появится, и дать одну
 * кнопку следующего шага — тогда пустота читается как приглашение.
 */
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

export default function Empty({
  title,
  what,
  action,
  to,
  onAction,
  children,
}: {
  /** что это за раздел */
  title: string
  /** что здесь появится и откуда возьмётся */
  what: string
  /** подпись единственной кнопки следующего действия */
  action?: string
  /** куда она ведёт */
  to?: string
  onAction?: () => void
  children?: ReactNode
}) {
  const navigate = useNavigate()
  const handle = onAction ?? (to ? () => navigate(to) : undefined)

  return (
    <div className="card card-pad empty">
      <b className="empty__title">{title}</b>
      <p className="muted empty__what">{what}</p>
      {action && handle && (
        <button className="btn btn-primary btn-sm empty__action" onClick={handle}>
          {action}
        </button>
      )}
      {children}
    </div>
  )
}
