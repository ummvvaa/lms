/**
 * Сетка быстрого ввода: таблица директора с полями прямо в клетках.
 *
 * Клетка — поле ввода или список; клавиатура (Tab, стрелки, Enter),
 * вставка из Excel и растягивание значения по колонке живут на экране
 * таблицы, здесь только разметка. Один элемент на весь интерфейс:
 * матрица журнала (`Matrix`) держит буквы, эта сетка — свободные значения.
 */
import type { ClipboardEvent, KeyboardEvent, ReactNode, Ref } from 'react'

export function QuickGrid({
  gridRef,
  head,
  children,
  hidden,
}: {
  gridRef: Ref<HTMLTableElement>
  /** строка заголовков */
  head: ReactNode
  children: ReactNode
  hidden?: boolean
}) {
  return (
    <div className="card grid-wrap" hidden={hidden}>
      <table className="grid-tbl" ref={gridRef}>
        <thead>{head}</thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

type CellCommon = {
  className?: string
  value: string
  title?: string
  'data-row': number
  'data-col': number
  onFocus: () => void
  onKeyDown: (event: KeyboardEvent<HTMLInputElement | HTMLSelectElement>) => void
  onPaste: (event: ClipboardEvent<HTMLInputElement | HTMLSelectElement>) => void
  onChange: (value: string) => void
}

type CellProps =
  | (CellCommon & { kind: 'select'; disabled?: boolean; options: { value: string; title: string }[]; empty: string })
  | (CellCommon & { kind: 'text'; readOnly?: boolean })

/** Клетка сетки: список с подписями или свободное значение. */
export function QuickCell(props: CellProps) {
  const { className, value, title, onFocus, onKeyDown, onPaste, onChange } = props
  const common = {
    className,
    value,
    title,
    'data-row': props['data-row'],
    'data-col': props['data-col'],
    onFocus,
    onKeyDown,
    onPaste,
  }
  if (props.kind === 'select')
    return (
      <select {...common} disabled={props.disabled} onChange={(event) => onChange(event.target.value)}>
        <option value="">{props.empty}</option>
        {props.options.map((choice) => (
          <option key={choice.value} value={choice.value}>
            {choice.title}
          </option>
        ))}
      </select>
    )
  return <input {...common} readOnly={props.readOnly} onChange={(event) => onChange(event.target.value)} />
}
