/**
 * Меню строки: всё, кроме основного действия.
 *
 * Опасное — в конце и за чертой: рядом с обычными кнопками удаление
 * нажимают промахом, а обратного хода у него нет. Одно и то же меню
 * у пользователей и в справочнике — правило одно, и выглядеть оно
 * должно одинаково.
 */
import { useState, type ReactNode } from 'react'
import { t } from '../i18n'

export default function RowMenu({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="rowmenu">
      <button
        className="btn btn-ghost btn-sm rowmenu__button"
        aria-label={t('Ещё действия')}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        ⋯
      </button>
      {open && (
        <>
          <span className="rowmenu__back" role="presentation" onClick={() => setOpen(false)} />
          <span className="rowmenu__panel card" onClick={() => setOpen(false)}>
            {children}
          </span>
        </>
      )}
    </span>
  )
}
