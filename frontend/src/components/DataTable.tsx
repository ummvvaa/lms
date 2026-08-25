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
 *
 * С фазы 32 колонку можно сделать сортируемой, и тогда строки при
 * сортировке переезжают, а не перерисовываются: человек видит, куда
 * уехала строка, на которую он смотрел. Подсветка (`flash`) отмечает
 * только что сохранённое — и гаснет сама.
 */
import { useMemo, useState, type ReactNode } from 'react'
import { motion } from 'motion/react'
import { useRowMotion } from '../motion'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table'

/** Строка таблицы, умеющая переезжать. `motion.create` оборачивает готовый
 *  компонент реестра — переписывать его ради движения не нужно. */
const MotionRow = motion.create(TableRow)

export interface Column<T> {
  key: string
  title: string
  /** ширина колонки: задаётся, а не вычисляется по содержимому */
  width: string
  /** числа и даты — вправо, текст — влево. Заголовок встаёт так же */
  align?: 'left' | 'right'
  cell: (row: T) => ReactNode
  /** по чему сортировать. Не задано — колонка не сортируется */
  sortBy?: (row: T) => string | number | null | undefined
}

type Direction = 'asc' | 'desc'

export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  empty,
  onRowClick,
  flash,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string | number
  /** что показать вместо строк, когда их нет */
  empty?: ReactNode
  onRowClick?: (row: T) => void
  /** ключи строк, которые только что изменились: подсветятся и погаснут */
  flash?: ReadonlySet<string | number>
}) {
  const [sort, setSort] = useState<{ key: string; direction: Direction } | null>(null)
  const row = useRowMotion()

  const sorted = useMemo(() => {
    const column = sort && columns.find((item) => item.key === sort.key)
    if (!column?.sortBy) return rows
    const sign = sort!.direction === 'asc' ? 1 : -1
    // пустое значение всегда внизу: «нет данных» — это не «меньше всех»
    return [...rows].sort((a, b) => {
      const left = column.sortBy!(a)
      const right = column.sortBy!(b)
      if (left === right) return 0
      if (left === null || left === undefined || left === '') return 1
      if (right === null || right === undefined || right === '') return -1
      return left > right ? sign : -sign
    })
  }, [rows, sort, columns])

  if (rows.length === 0 && empty) return <>{empty}</>

  const toggle = (key: string) =>
    setSort((prev) =>
      prev?.key !== key
        ? { key, direction: 'asc' }
        : prev.direction === 'asc'
          ? { key, direction: 'desc' }
          : null,
    )

  return (
    // прокрутка живёт внутри карточки: на узком экране вбок едет таблица,
    // а не вся страница
    <Table className="tbl" containerClassName="tblwrap">
      <colgroup>
        {columns.map((column) => (
          <col key={column.key} style={{ width: column.width }} />
        ))}
      </colgroup>
      <TableHeader>
        <TableRow>
          {columns.map((column) => {
            const active = sort?.key === column.key
            const className = [
              column.align === 'right' ? 'tbl__right' : '',
              column.sortBy ? 'tbl__sortable' : '',
            ]
              .filter(Boolean)
              .join(' ')
            return (
              <TableHead
                key={column.key}
                className={className || undefined}
                aria-sort={active ? (sort!.direction === 'asc' ? 'ascending' : 'descending') : undefined}
                onClick={column.sortBy ? () => toggle(column.key) : undefined}
              >
                {column.title}
                {column.sortBy && (
                  <span className="tbl__caret" aria-hidden="true">
                    {active ? (sort!.direction === 'asc' ? '↑' : '↓') : '↕'}
                  </span>
                )}
              </TableHead>
            )
          })}
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((item) => {
          const key = rowKey(item)
          const classes = [onRowClick ? 'tbl__row--clickable' : '', flash?.has(key) ? 'row--flash' : '']
            .filter(Boolean)
            .join(' ')
          return (
            <MotionRow
              key={key}
              layout={row.layout}
              transition={row.transition}
              className={classes || undefined}
              onClick={onRowClick ? () => onRowClick(item) : undefined}
            >
              {columns.map((column) => (
                <TableCell key={column.key} className={column.align === 'right' ? 'tbl__right' : undefined}>
                  {column.cell(item)}
                </TableCell>
              ))}
            </MotionRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
