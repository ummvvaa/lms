/**
 * Таблица с заданными колонками.
 *
 * До фазы 31 каждая таблица размечалась своими `<td>` вручную: заголовки
 * жили отдельно от значений и разъезжались с ними, числа выравнивались
 * по левому краю рядом с текстом, ширина колонок прыгала от содержимого,
 * и одна длинная фамилия перекашивала весь экран.
 *
 * Здесь колонка описывается один раз — подпись, ширина, выравнивание, —
 * и заголовок с ячейкой берут их из одного места. Разъехаться им негде.
 */
import type { ReactNode } from 'react'

export interface Column<T> {
  key: string
  title: string
  /** ширина колонки: задаётся, а не вычисляется по содержимому */
  width: string
  /** числа и даты — вправо, текст — влево. Заголовок встаёт так же */
  align?: 'left' | 'right'
  cell: (row: T) => ReactNode
}

export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  empty,
  onRowClick,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string | number
  /** что показать вместо строк, когда их нет */
  empty?: ReactNode
  onRowClick?: (row: T) => void
}) {
  if (rows.length === 0 && empty) return <>{empty}</>

  return (
    // прокрутка живёт внутри карточки: на узком экране вбок едет таблица,
    // а не вся страница
    <div className="tblwrap">
      <table className="tbl">
        <colgroup>
          {columns.map((column) => (
            <col key={column.key} style={{ width: column.width }} />
          ))}
        </colgroup>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} className={column.align === 'right' ? 'tbl__right' : undefined}>
                {column.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className={onRowClick ? 'tbl__row--clickable' : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((column) => (
                <td key={column.key} className={column.align === 'right' ? 'tbl__right' : undefined}>
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
