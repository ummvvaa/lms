/**
 * Меню строки: всё, кроме основного действия.
 *
 * Опасное — в конце и за чертой: рядом с обычными кнопками удаление
 * нажимают промахом, а обратного хода у него нет. Одно и то же меню
 * у пользователей и в справочнике — правило одно, и выглядеть оно
 * должно одинаково.
 *
 * С фазы 32 внутри — `DropdownMenu` из shadcn: стрелки, Esc, закрытие
 * по клику мимо и возврат фокуса на кнопку приехали готовыми. Свой
 * пункт (`RowMenuItem`) нужен, потому что внутри некоторых пунктов
 * живёт `DeleteButton` со своим диалогом: он должен открыться, а меню
 * при этом закрыться, а не забрать нажатие себе.
 */
import type { ReactNode } from 'react'
import { t } from '../i18n'
import { Button } from './ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu'

export default function RowMenu({ children }: { children: ReactNode }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant="outline" size="icon-sm" className="rowmenu__button" />}
        aria-label={t('Ещё действия')}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <circle cx="5" cy="12" r="1.7" />
          <circle cx="12" cy="12" r="1.7" />
          <circle cx="19" cy="12" r="1.7" />
        </svg>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="rowmenu__panel">
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/** Пункт меню. `risk` — опасное действие: цвет тревоги и место в конце. */
export function RowMenuItem({
  children,
  onClick,
  disabled = false,
  risk = false,
  /** пункт сам открывает диалог — закрывать меню нажатием не надо */
  keepOpen = false,
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  risk?: boolean
  keepOpen?: boolean
}) {
  return (
    <DropdownMenuItem
      className="rowmenu__item"
      variant={risk ? 'destructive' : 'default'}
      disabled={disabled}
      closeOnClick={!keepOpen}
      onClick={onClick}
    >
      {children}
    </DropdownMenuItem>
  )
}

export function RowMenuSeparator() {
  return <DropdownMenuSeparator className="rowmenu__sep" />
}
