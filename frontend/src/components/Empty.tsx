/**
 * Пустое состояние экрана — один образец на все разделы.
 *
 * Пустая таблица и белое поле выглядят как поломка. Но и три предложения
 * подряд человек не читает. С фазы 33 у каждого пустого состояния одно
 * и то же устройство: иконка раздела, одна строка о том, что здесь
 * появится, одна кнопка следующего шага. Всё, что длиннее, уходит
 * в подсказку по наведению.
 */
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import Icon, { type IconName } from '../layout/icons'
import { Hint } from './ui'
import { Button } from './ui/button'

export default function Empty({
  title,
  what,
  hint,
  action,
  to,
  onAction,
  icon = 'box',
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
  /** иконка раздела — та же, что у него в меню */
  icon?: IconName
  children?: ReactNode
}) {
  const navigate = useNavigate()
  const handle = onAction ?? (to ? () => navigate(to) : undefined)

  return (
    <div className="empty">
      <span className="empty__icon" aria-hidden="true">
        <Icon name={icon} size={22} />
      </span>
      <b className="empty__title">
        {title}
        {hint && <Hint text={hint} />}
      </b>
      <p className="muted empty__what">{what}</p>
      {action && handle && (
        <Button className="empty__action" onClick={handle}>
          {action}
        </Button>
      )}
      {children}
    </div>
  )
}
