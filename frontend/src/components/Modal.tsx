/**
 * Форма поверх содержимого, а не внутри него.
 *
 * Форма, встроенная в поток, сжимает соседей: таблица уползает вниз
 * и влево, колонки меняют ширину, и человек теряет строку, на которую
 * смотрел. Заведение записи не должно перестраивать экран под собой —
 * поэтому все формы создания живут здесь, над страницей.
 */
import { useEffect, type ReactNode } from 'react'
import { t } from '../i18n'

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
  // Esc закрывает: диалог без клавиатурного выхода запирает человека,
  // если кнопка «Отмена» уехала за нижний край на коротком экране
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    // страница под окном не должна прокручиваться вместе с ним
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [onClose])

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
      <button className="modal__backdrop" aria-label={t('Закрыть')} onClick={onClose} />
      <div className={`card modal__box${wide ? ' modal__box--wide' : ''}`}>
        <header className="modal__head">
          <div>
            <b className="modal__title">{title}</b>
            {note && <p className="muted modal__note">{note}</p>}
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            {t('Закрыть')}
          </button>
        </header>
        <div className="modal__body">{children}</div>
      </div>
    </div>
  )
}
