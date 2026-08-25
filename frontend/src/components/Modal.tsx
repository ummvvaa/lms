/**
 * Форма поверх содержимого, а не внутри него.
 *
 * Форма, встроенная в поток, сжимает соседей: таблица уползает вниз
 * и влево, колонки меняют ширину, и человек теряет строку, на которую
 * смотрел. Заведение записи не должно перестраивать экран под собой —
 * поэтому все формы создания живут здесь, над страницей.
 *
 * С фазы 32 внутри — `Dialog` из shadcn: Esc, блокировка прокрутки,
 * ловушка фокуса и появление с уходом достались готовыми, а раньше
 * лежали здесь своим кодом. Снаружи ничего не изменилось: компонент
 * по-прежнему рисуется условно и закрывается через `onClose`.
 */
import type { ReactNode } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog'
import { Separator } from './ui/separator'

export default function Modal({
  title,
  note,
  onClose,
  children,
  wide = false,
}: {
  title: string
  /** одна строка под заголовком; длиннее — в подсказку внутри формы */
  note?: string
  onClose: () => void
  children: ReactNode
  /** широкое окно — для таблиц массового ввода */
  wide?: boolean
}) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className={`modal__box max-h-[calc(100vh-48px)] gap-0 overflow-y-auto p-0 ${
          wide ? 'sm:max-w-[980px]' : 'sm:max-w-[560px]'
        }`}
      >
        <DialogHeader className="modal__head">
          <DialogTitle className="modal__title">{title}</DialogTitle>
          {note && <DialogDescription className="modal__note">{note}</DialogDescription>}
        </DialogHeader>
        <Separator />
        <div className="modal__body">{children}</div>
      </DialogContent>
    </Dialog>
  )
}
