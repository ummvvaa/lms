/**
 * Панель, свёрнутая на телефоне (фаза 76).
 *
 * Поиск и фильтры над списком на ноутбуке занимают одну строку, а на 390
 * пикселях — четыре: до первой карточки уходил почти весь первый экран.
 * Здесь панель сворачивается в строку «Поиск и фильтры — Развернуть»,
 * как «Начало работы» у директоров; на ноутбуке содержимое рисуется
 * как есть. Панель с уже выбранным фильтром открыта сразу: свёрнутый
 * фильтр, который режет список, человек не найдёт.
 */
import { useState, type ReactNode } from 'react'
import { usePhone } from '../phone'
import { t } from '../i18n'
import { Button } from './ui/button'

export default function PhoneFold({
  children,
  label,
  active = false,
}: {
  children: ReactNode
  /** строка свёрнутого вида */
  label?: string
  /** фильтр уже выбран — панель открыта сразу */
  active?: boolean
}) {
  const phone = usePhone()
  const [open, setOpen] = useState(false)
  if (!phone) return <>{children}</>
  const shown = open || active
  return (
    <div className={`fold${shown ? ' fold--open' : ''}`}>
      <div className="fold__head">
        <span className="fold__label">{label ?? t('Поиск и фильтры')}</span>
        <Button variant="outline" size="sm" aria-expanded={shown} onClick={() => setOpen(!shown)}>
          {shown ? t('Свернуть') : t('Развернуть')}
        </Button>
      </div>
      {shown && <div className="fold__body">{children}</div>}
    </div>
  )
}
