/**
 * Пустое состояние экрана.
 *
 * Пустая таблица и белое поле выглядят как поломка. Но и три предложения
 * подряд человек не читает: с фазы 30 здесь одна фраза о том, что тут
 * появится, и одна кнопка следующего шага. Всё, что длиннее, уходит
 * в подсказку по наведению.
 */
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Hint } from './ui'

export default function Empty({
  title,
  what,
  hint,
  action,
  to,
  onAction,
  children,
}: {
  /** что это за раздел — одна строка */
  title: string
  /** одна фраза о том, что здесь появится */
  what: string
  /** подробности: показываются по наведению, а не на экране */
  hint?: string
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
      <b className="empty__title">
        {title}
        {hint && <Hint text={hint} />}
      </b>
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
