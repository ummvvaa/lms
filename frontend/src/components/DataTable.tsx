/**
 * Таблица с заданными колонками.
 *
 * Раньше каждая таблица размечалась своими `<td>` вручную: заголовки
 * жили отдельно от значений и разъезжались с ними, числа выравнивались
 * по левому краю рядом с текстом, ширина колонок прыгала от содержимого,
 * и одна длинная фамилия перекашивала весь экран.
 *
 * Здесь колонка описывается один раз — подпись, ширина, выравнивание, —
 * и заголовок с ячейкой берут их из одного места. Разъехаться им негде.
 *
 * Колонку можно сделать сортируемой, и тогда строки при сортировке
 * переезжают, а не перерисовываются: человек видит, куда уехала строка,
 * на которую он смотрел. Подсветка (`flash`) отмечает только что
 * сохранённое — и гаснет сама. Выбранная строка (`selected`) остаётся
 * подсвеченной, длинный список режется по `limit` и раскрывается
 * подвалом «Показаны N из M».
 */
import { useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { motion } from 'motion/react'
import { useRowMotion } from '../motion'
import { ListFoot } from './patterns'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table'

/** Строка таблицы, умеющая переезжать. `motion.create` оборачивает готовый
 *  компонент реестра — переписывать его ради движения не нужно. */
const MotionRow = motion.create(TableRow)

export interface Column<T> {
  key: string
  title: string
  /** полное название колонки — подсказкой при наведении на короткую шапку */
  hint?: string
  /** ширина колонки: задаётся, а не вычисляется по содержимому */
  width: string
  /** числа и даты — вправо, текст — влево. Заголовок встаёт так же */
  align?: 'left' | 'right'
  cell: (row: T) => ReactNode
  /** по чему сортировать. Не задано — колонка не сортируется */
  sortBy?: (row: T) => string | number | null | undefined
  /** кнопки строки: одной линией справа, клетка их не режет и не переносит;
   *  на телефоне — внизу карточки справа. Ширина колонки — числом под кнопки */
  actions?: boolean
}

type Direction = 'asc' | 'desc'

/** Что в строке нажимается само по себе: клик по нему не считается кликом по строке. */
const INTERACTIVE = 'button, a, input, select, textarea, label, [role="checkbox"], [role="menuitem"], [role="switch"]'

export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  empty,
  onRowClick,
  flash,
  selected,
  rowClass,
  limit,
  foot,
  minWidth,
  fit = false,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string | number
  /** что показать вместо строк, когда их нет */
  empty?: ReactNode
  onRowClick?: (row: T) => void
  /** ключи строк, которые только что изменились: подсветятся и погаснут */
  flash?: ReadonlySet<string | number>
  /** выбранная строка: остаётся подсвеченной, пока с ней работают */
  selected?: (row: T) => boolean
  /** свой класс строки по данным: строка с ошибкой в мастере, пропущенная строка */
  rowClass?: (row: T) => string | undefined
  /** сколько строк видно сразу; остальное — под «Показать все» */
  limit?: number
  /** свой подвал: сводка, пояснение */
  foot?: ReactNode
  /** наименьшая ширина таблицы: колонок много — прокрутка внутри карточки,
   *  первая колонка закреплена, шапки не режутся (правило 4, 27.09.2026) */
  minWidth?: string
  /** таблица всегда в ширину карточки, без прокрутки вбок: текст в клетках
   *  и шапки переносятся между словами, слово шире колонки ломается, только
   *  если не влезает целиком. Узкие колонки — числом, текстовые — `auto` */
  fit?: boolean
}) {
  const [sort, setSort] = useState<{ key: string; direction: Direction } | null>(null)
  const [open, setOpen] = useState(false)
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

  const cut = limit !== undefined && !open && sorted.length > limit
  const shown = cut ? sorted.slice(0, limit) : sorted
  const showFoot = foot !== undefined || (limit !== undefined && sorted.length > limit)

  return (
    <>
      {/* прокрутка живёт внутри карточки: на узком экране вбок едет таблица,
          а не вся страница */}
      <Table className={minWidth ? 'tbl tbl--wide' : fit ? 'tbl tbl--fit' : 'tbl'} containerClassName="tblwrap" style={minWidth ? ({ '--tbl-min': minWidth } as CSSProperties) : undefined}>
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
                't-caps',
                column.align === 'right' ? 'tbl__right' : '',
                column.actions ? 'tbl__acts' : '',
                column.sortBy ? 'tbl__sortable' : '',
              ]
                .filter(Boolean)
                .join(' ')
              return (
                <TableHead
                  key={column.key}
                  className={className}
                  title={column.hint}
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
          {shown.map((item) => {
            const key = rowKey(item)
            const classes = [
              onRowClick ? 'tbl__row--clickable' : '',
              selected?.(item) ? 'tbl__row--selected' : '',
              flash?.has(key) ? 'row--flash' : '',
              rowClass?.(item) ?? '',
            ]
              .filter(Boolean)
              .join(' ')
            return (
              <MotionRow
                key={key}
                layout={row.layout}
                transition={row.transition}
                className={classes || undefined}
                aria-selected={selected ? selected(item) : undefined}
                onClick={
                  onRowClick
                    ? (event) => {
                        // флажок, кнопка или ссылка в клетке — своё действие, строку не открывает
                        if ((event.target as HTMLElement).closest(INTERACTIVE)) return
                        onRowClick(item)
                      }
                    : undefined
                }
              >
                {columns.map((column, index) => (
                  <TableCell
                    key={column.key}
                    className={[column.align === 'right' ? 'tbl__right' : '', column.actions ? 'tbl__acts' : ''].filter(Boolean).join(' ') || undefined}
                    /* подпись колонки едет с ячейкой: на телефоне строка
                       становится карточкой из пар «подпись — значение»,
                       а шапки там нет вовсе. Первая колонка —
                       заголовок карточки, подпись ей не нужна */
                    data-label={index === 0 ? undefined : column.title}
                    data-head={index === 0 ? '' : undefined}
                  >
                    {column.actions ? <span className="tbl__buttons">{column.cell(item)}</span> : column.cell(item)}
                  </TableCell>
                ))}
              </MotionRow>
            )
          })}
        </TableBody>
      </Table>
      {showFoot && (
        <div className="tbl__foot">
          {limit !== undefined && sorted.length > limit ? (
            <ListFoot
              shown={shown.length}
              total={sorted.length}
              open={open}
              onToggle={() => setOpen(!open)}
            />
          ) : null}
          {foot}
        </div>
      )}
    </>
  )
}
