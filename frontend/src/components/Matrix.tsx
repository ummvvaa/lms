/**
 * Матрица «строки × колонки» с клавиатурой.
 *
 * Образец — журнал `gradebook` и `KEY_HOOK` из
 * `docs/ui/reference-src/src/screens/teacher.js`, стили `.gb` из
 * `styles.css`, экран `docs/ui/language/Journal.html`: липкий первый
 * столбец с именами, шапка колонок капителью, клетки `--cell-w` × `--cell-h`,
 * выделенная клетка — кольцо `--accent`, заблокированная — `--ink-4`.
 *
 * Клавиатура: стрелки — соседняя клетка, Enter — вниз, Esc — снять
 * выделение; печатный символ, Backspace и Delete уходят в `onKey(cell, key)`.
 * Что значит символ и можно ли писать в заблокированную клетку, решает
 * вызывающий: здесь нет ни оценок, ни отметок — только сетка и выделение.
 * Выделение живёт внутри, пока не передан `selected`; тогда им управляет
 * вызывающий, а компонент лишь сообщает о смене через `onSelect`.
 *
 * На телефоне матрица не показывается — компонент отдаёт `null`,
 * и вызывающий рисует список.
 */
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { usePhone } from '../phone'
import { t } from '../i18n'

export interface MatrixRow {
  key: string | number
  title: ReactNode
  /** подпись рядом с названием: группа, подгруппа */
  sub?: ReactNode
}

export interface MatrixColumn {
  key: string | number
  title: ReactNode
  /** вторая строка шапки: день недели, вид работы */
  sub?: ReactNode
}

/** Клетка — индексы строки и колонки, с нуля. */
export interface MatrixCell {
  row: number
  col: number
}

export type MatrixTone = 'good' | 'warn' | 'bad' | 'info' | 'neutral'

/** Клетка, в которой стоит узел: по атрибутам, которые ставит разметка ниже. */
function cellOf(node: HTMLElement): MatrixCell | null {
  const found = node.closest<HTMLElement>('[data-row][data-col]')
  if (!found) return null
  return { row: Number(found.dataset.row), col: Number(found.dataset.col) }
}

const clamp = (value: number, max: number) => Math.min(Math.max(value, 0), max)

export default function Matrix({
  rows,
  columns,
  cell,
  locked,
  tone,
  selected,
  onSelect,
  onKey,
  rowHead,
  label,
  className,
}: {
  rows: MatrixRow[]
  columns: MatrixColumn[]
  /** содержимое клетки */
  cell: (row: MatrixRow, column: MatrixColumn) => ReactNode
  /** клетка, которую не правят: отличается только видом */
  locked?: (row: MatrixRow, column: MatrixColumn) => boolean
  /** подложка клетки по смыслу содержимого */
  tone?: (row: MatrixRow, column: MatrixColumn) => MatrixTone | undefined
  /** выделенная клетка; без этого пропса выделение живёт внутри */
  selected?: MatrixCell | null
  onSelect?: (cell: MatrixCell | null) => void
  onKey?: (cell: MatrixCell, key: string) => void
  /** заголовок первого столбца */
  rowHead?: ReactNode
  /** подпись сетки для читалки */
  label?: string
  className?: string
}) {
  const phone = usePhone()
  const box = useRef<HTMLDivElement>(null)
  // нажатие мышью выделяет по клику; фокус, который оно вызывает раньше,
  // не должен выделять второй раз
  const byPointer = useRef(false)
  const [inner, setInner] = useState<MatrixCell | null>(null)
  const current = selected === undefined ? inner : selected
  const row = current?.row
  const col = current?.col

  const select = (next: MatrixCell | null) => {
    setInner(next)
    onSelect?.(next)
  }

  // выделенная клетка получает фокус: так стрелки и буквы приходят в сетку,
  // а не в страницу
  useEffect(() => {
    if (row === undefined || col === undefined || !box.current) return
    const node = box.current.querySelector<HTMLElement>(`[data-row="${row}"][data-col="${col}"]`)
    if (node && document.activeElement !== node) node.focus()
  }, [row, col])

  if (phone) return null

  const move = (from: MatrixCell, dRow: number, dCol: number) =>
    select({ row: clamp(from.row + dRow, rows.length - 1), col: clamp(from.col + dCol, columns.length - 1) })

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement
    // поле внутри клетки печатает само
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
    const at = current ?? cellOf(target)
    if (!at) return
    switch (event.key) {
      case 'ArrowRight':
        move(at, 0, 1)
        break
      case 'ArrowLeft':
        move(at, 0, -1)
        break
      case 'ArrowDown':
      case 'Enter':
        move(at, 1, 0)
        break
      case 'ArrowUp':
        move(at, -1, 0)
        break
      case 'Escape':
        select(null)
        break
      case 'Backspace':
      case 'Delete':
        onKey?.(at, event.key)
        break
      default:
        if (event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) return
        onKey?.(at, event.key)
    }
    event.preventDefault()
  }

  return (
    <div ref={box} className={`matrix${className ? ` ${className}` : ''}`} onKeyDown={onKeyDown}>
      <table className="matrix__table" role="grid" aria-label={label}>
        <thead>
          <tr>
            <th className="matrix__stu" scope="col">
              <span className="t-caps">{rowHead ?? t('Ученик')}</span>
            </th>
            {columns.map((column) => (
              <th key={column.key} className="matrix__col" scope="col">
                <span className="matrix__coltitle t-caps">{column.title}</span>
                {column.sub && <span className="matrix__colsub t-note">{column.sub}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((line, rowIndex) => (
            <tr key={line.key}>
              <th className="matrix__stu" scope="row">
                <span className="matrix__name">
                  <span className="matrix__ix num">{rowIndex + 1}</span>
                  <span className="matrix__title">{line.title}</span>
                  {line.sub && <span className="matrix__sub">{line.sub}</span>}
                </span>
              </th>
              {columns.map((column, colIndex) => {
                const on = current?.row === rowIndex && current?.col === colIndex
                const lock = locked?.(line, column) ?? false
                const shade = tone?.(line, column)
                // без выделения в сетку входят с первой клетки
                const reachable = on || (!current && rowIndex === 0 && colIndex === 0)
                return (
                  <td
                    key={column.key}
                    role="gridcell"
                    className={`matrix__cell num${on ? ' matrix__cell--on' : ''}${lock ? ' matrix__cell--locked' : ''}${
                      shade ? ` matrix__cell--${shade}` : ''
                    }`}
                    data-row={rowIndex}
                    data-col={colIndex}
                    tabIndex={reachable ? 0 : -1}
                    aria-selected={on || undefined}
                    onPointerDown={() => {
                      byPointer.current = true
                    }}
                    onPointerUp={() => {
                      byPointer.current = false
                    }}
                    onFocus={() => {
                      if (!byPointer.current && !on) select({ row: rowIndex, col: colIndex })
                    }}
                    onClick={() => select({ row: rowIndex, col: colIndex })}
                  >
                    {cell(line, column)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
