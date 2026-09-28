/**
 * Правая панель правки.
 *
 * Образец — панель в `docs/ui/language/Directory.html` (350 на ноутбуке,
 * в `Settings.html` — 330) и `drawer` из `docs/ui/reference.html`:
 * заголовок `.t-card` с подзаголовком `.t-note`, тело с полями `Field`,
 * подвал с главной и вторичной кнопкой. Ширина — `--drawer-w`
 * в `language.css`. На телефоне та же панель выезжает снизу на всю ширину.
 *
 * Построена поверх `Sheet` из реестра: фокус, Esc, затемнение и портал —
 * его. Здесь только состав и вид.
 */
import { type ReactNode } from 'react'
import { usePhone } from '../phone'
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from './ui/sheet'

export default function EditDrawer({
  open,
  onClose,
  title,
  sub,
  children,
  footer,
  className,
}: {
  open: boolean
  /** закрытие по кнопке, Esc и затемнению — всё сюда */
  onClose: () => void
  title: ReactNode
  /** подзаголовок: чья запись и что правится */
  sub?: ReactNode
  children: ReactNode
  /** кнопки подвала: первая — главная, она растягивается */
  footer?: ReactNode
  className?: string
}) {
  const phone = usePhone()
  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
    >
      <SheetContent side={phone ? 'bottom' : 'right'} className={`drawer${className ? ` ${className}` : ''}`}>
        <span className="drawer__grabber" aria-hidden="true" />
        <SheetHeader className="drawer__head">
          <SheetTitle className="drawer__title t-card">{title}</SheetTitle>
          {sub && <SheetDescription className="drawer__sub t-note">{sub}</SheetDescription>}
        </SheetHeader>
        <div className="drawer__body">{children}</div>
        {footer && <SheetFooter className="drawer__foot">{footer}</SheetFooter>}
      </SheetContent>
    </Sheet>
  )
}
