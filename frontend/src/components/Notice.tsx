/**
 * Пояснительная плашка (фаза 75).
 *
 * На ноутбуке — абзац как он есть. На телефоне абзац на четыре строки
 * над каждым списком съедает половину экрана, поэтому там плашка
 * сворачивается до одной строки с «подробнее» и раскрывается по нажатию.
 *
 * Строка для свёрнутого вида — `summary`; без неё берётся первое
 * предложение текста. Кнопки и формы внутри (`children` сложнее текста)
 * показываются только в раскрытом виде.
 */
import { useState, type ReactNode } from 'react'
import Icon, { type IconName } from '../layout/icons'
import { usePhone } from '../phone'
import { t } from '../i18n'

/** Первое предложение текста — до точки, восклицания или двоеточия. */
export function firstSentence(node: ReactNode): string {
  const text = textOf(node).trim()
  const match = text.match(/^(.+?[.!?:])(\s|$)/)
  const head = match ? match[1] : text
  // двоеточие и точка в конце строки-заголовка не нужны
  return head.replace(/[.:]$/, '')
}

function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (typeof node === 'object' && 'props' in node)
    return textOf((node as { props: { children?: ReactNode } }).props.children)
  return ''
}

export default function Notice({
  children,
  summary,
  icon,
  tone = 'plain',
  className,
  open: openByDefault = false,
}: {
  children: ReactNode
  /** одна строка свёрнутого вида; без неё — первое предложение */
  summary?: string
  icon?: IconName
  /** `warn` — предупреждение на жёлтой подложке; `plain` — серая */
  tone?: 'plain' | 'warn' | 'brand'
  className?: string
  /** на телефоне раскрыта сразу */
  open?: boolean
}) {
  const phone = usePhone()
  const [open, setOpen] = useState(openByDefault)
  const folded = phone && !open
  const line = summary ?? firstSentence(children)

  return (
    <div
      className={`notice notice--${tone}${folded ? ' notice--folded' : ''}${className ? ` ${className}` : ''}`}
      role="note"
    >
      {icon && (
        <span className="notice__icon" aria-hidden="true">
          <Icon name={icon} size={15} />
        </span>
      )}
      <div className="notice__body">
        {/* на телефоне — одна строка и кнопка; раскрытие ниже, а не вместо неё,
            чтобы человек видел, что именно раскрыл */}
        {phone && (
          <div className="notice__line">
            <span className="notice__summary">{line}</span>
            <button
              type="button"
              className="notice__more"
              aria-expanded={open}
              onClick={() => setOpen((value) => !value)}
            >
              {open ? t('скрыть') : t('подробнее')}
            </button>
          </div>
        )}
        {!folded && <div className="notice__text">{children}</div>}
      </div>
    </div>
  )
}
