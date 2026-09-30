/**
 * Табличный режим: плотный ввод по своему домену.
 *
 * Колонки берутся из /api/meta/domains/, а не хардкодятся — реестр доменов
 * остаётся единственным источником правды (инвариант №2). Изменения копятся
 * в локальном черновике и уходят одним батч-запросом: сами через две секунды
 * после последней правки или сразу по кнопке «Сохранить».
 *
 * Защита от гонки прежняя: батч несёт `expected`, и правку соседа сервер
 * не затирает молча, а возвращает конфликтом.
 *
 * С фазы 35 это основной инструмент пяти директоров — файлы грузит только
 * администратор. Поэтому таблица ведёт себя как электронная: Tab и стрелки
 * ходят по ячейкам, вставка из буфера ложится прямоугольником (и в списки
 * тоже), значение растягивается вниз маркером в углу ячейки, Ctrl+Z
 * отменяет последнее действие, а отклонённая ячейка подсвечивается
 * с причиной — остальные при этом сохраняются.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'motion/react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { useBatchSave, useDomainMeta, useStudents, type BatchChange, type StudentCard } from '../api/hooks'
import { useConnection, useReconnected } from '../api/useConnection'
import { profileModelOf, type DomainField } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { usePhone } from '../phone'
import Notice from '../components/Notice'
import Empty from '../components/Empty'
import ManualEntryNote from '../components/ManualEntryNote'
import StudentRegistry from '../components/StudentRegistry'
import { Chip, counted, ErrorNote, Loading, ScreenHead, type Tone } from '../components/ui'
import { useRowMotion } from '../motion'
import './table.css'
import { t, tk, tn } from '../i18n'
import { PublishStudents } from '../assistant/context'
import { SelectField } from '../components/SelectField'
import { PARALLELS, parallelTitle } from '../lib/parallels'
import { Input } from '../components/ui/input'
import { Button } from '../components/ui/button'
import { QuickCell, QuickGrid } from '../components/ui/quick-grid'
import PhoneFold from '../components/PhoneFold'

/** Ключ ячейки в черновике. */
const cellKey = (studentId: number, field: string) => `${studentId}:${field}`

/** Столько учеников забираем за раз — это же потолок `StandardPagination`. */
const PAGE_SIZE = 500

/**
 * Через сколько после последней правки уходит батч.
 *
 * Две секунды — компромисс: человек успевает допечатать число целиком,
 * но не успевает уйти со страницы, думая, что всё сохранено.
 */
const AUTOSAVE_DELAY = 2000

/** Подписи состояния автосохранения — их читает человек, а не машина. Ключи перевода: показываются через `t()`. */
const SYNC_TITLES: Record<string, { text: string; tone: Tone }> = {
  dirty: { text: tk('есть несохранённые изменения'), tone: 'warn' },
  saving: { text: tk('сохраняется…'), tone: 'neutral' },
  saved: { text: tk('сохранено'), tone: 'good' },
  rejected: { text: tk('сохранено не всё — посмотрите, что не прошло'), tone: 'bad' },
  offline: { text: tk('нет связи — правки сохранены и уйдут сами'), tone: 'bad' },
}

interface Draft {
  [key: string]: { student: number; model: string; field: string; value: string; original: string }
}

/** Одно действие для отмены: какие ячейки и что в них было до него. */
interface UndoEntry {
  cells: { student: number; field: string; before: string }[]
}

/** Сколько действий помним для отмены. Дальше — «Отменить правки» целиком. */
const UNDO_DEPTH = 50

/** Растягивание значения вниз: откуда тянем и докуда дотянули. */
interface Fill {
  row: number
  col: number
  to: number
}

/** Ввод для поля с выбором: подпись из списка тоже принимается — так вставляют из Excel. */
function choiceValue(field: DomainField, text: string): string {
  if (!field.choices) return text
  const low = text.trim().toLowerCase()
  if (low === '') return ''
  const hit = field.choices.find((c) => c.value.toLowerCase() === low || c.title.toLowerCase() === low)
  return hit ? hit.value : text.trim()
}

function displayValue(student: StudentCard, domainKey: string, field: DomainField | string): string {
  const profile = (student as unknown as Record<string, Record<string, unknown>>)[domainKey]
  const name = typeof field === 'string' ? field : field.name
  // ссылка на справочник показывается названием: ключ записи человеку
  // ничего не говорит, а сервер понимает и название (фаза 18)
  if (typeof field !== 'string' && field.type === 'reference') {
    return String(profile?.[`${name}_name`] ?? '')
  }
  const raw = profile?.[name]
  if (raw === null || raw === undefined) return ''
  // «да» и «нет» — на языке человека; разбор ввода понимает и их, и русские
  if (typeof raw === 'boolean') return raw ? t('да') : t('нет')
  // выбор из списка показывается подписью, а не кодом: на телефоне карточка
  // строки писала «can_execute» (найдено в 76-й); сервер принимает и код
  if (typeof field !== 'string' && field.choices) {
    const choice = field.choices.find((item) => item.value === String(raw))
    if (choice) return choice.title
  }
  return String(raw)
}

/** Приводим введённое к тому, что ждёт API. */
function parseValue(field: DomainField, text: string): unknown {
  const trimmed = text.trim()
  if (trimmed === '') return field.type === 'boolean' ? false : null
  if (field.type === 'boolean')
    // eslint-disable-next-line i18n-text -- слова, которые разбор ввода принимает за «да», не показываются
    return ['да', t('да').toLowerCase(), 'yes', 'true', '1', '+'].includes(trimmed.toLowerCase())
  if (field.type === 'integer') {
    const n = Number(trimmed.replace(',', '.'))
    return Number.isFinite(n) ? Math.round(n) : trimmed
  }
  if (field.type === 'number') return trimmed.replace(',', '.')
  return trimmed
}

/** Числовые фильтры, которые умеет `StudentFilter` на бэке. */
const RANGE_FILTERS = ['ielts_min', 'ielts_max', 'sat_min', 'sat_max'] as const

/** Подписи фильтров — фразы со значением `{value}`: порядок слов у языков разный. */
const FILTER_TITLES: Record<string, string> = {
  ielts_min: tk('IELTS от {value}'),
  ielts_max: tk('IELTS до {value}'),
  sat_min: tk('SAT от {value}'),
  sat_max: tk('SAT до {value}'),
}

export default function TableScreen() {
  const navigate = useNavigate()
  const phone = usePhone()
  const { me } = useAuth()
  const [params, setParams] = useSearchParams()
  const meta = useDomainMeta()
  const [group, setGroup] = useState('')
  // параллель — фильтр сотрудника; ученику её не выбирают
  const [parallel, setParallel] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  // Таблица открывается на чтение (фаза 49): данные о себе вносит ученик,
  // директор подтверждает их в очереди. Ручной ввод остался — он ушёл
  // во второстепенную кнопку, а не исчез
  const [locked, setLocked] = useState(true)
  const [draft, setDraft] = useState<Draft>({})
  // строки, которые только что сохранились: подсветятся и погаснут
  const [flashed, setFlashed] = useState<ReadonlySet<number>>(new Set())
  const rowMotion = useRowMotion()
  const [problems, setProblems] = useState<string[]>([])
  // отказ по ячейке: ключ → причина. Ячейка подсвечивается и не теряет
  // значения, остальные сохраняются как обычно
  const [cellProblems, setCellProblems] = useState<Record<string, string>>({})
  // стек отмены: одно действие — одна запись, вставка и растягивание
  // считаются одним действием, набор в одной ячейке склеивается
  const undoRef = useRef<UndoEntry[]>([])
  const [undoDepth, setUndoDepth] = useState(0)
  // черновик в ref: обработчикам нужно текущее значение ячейки, а замыкания
  // видят снимок на момент рендера
  const draftRef = useRef<Draft>({})
  // активная ячейка — у неё рисуется маркер растягивания; и само растягивание
  const [active, setActive] = useState<{ row: number; col: number } | null>(null)
  const [fill, setFill] = useState<Fill | null>(null)
  // состояние автосохранения: черновик → сохраняется → сохранено.
  // «offline» значит, что правки копятся и уйдут, когда связь вернётся
  const [sync, setSync] = useState<'idle' | 'dirty' | 'saving' | 'saved' | 'rejected' | 'offline'>('idle')
  const gridRef = useRef<HTMLTableElement>(null)
  const saveRef = useRef<() => Promise<void>>(async () => {})
  // отправка уже идёт: второй вызов подряд (два события `online`, таймер
  // поверх ручного «Сохранить») слал бы тот же снимок ещё раз и получал
  // конфликт с самим собой — «кто-то уже поставил» своё же значение
  const inFlight = useRef(false)

  // 500 — потолок сервера. Школа помещается в одну страницу, но если
  // учеников больше, переключатель ниже показывает это явно: молча
  // обрезанный список хуже, чем список с постраничной навигацией.
  // плитки дашборда приводят сюда с фильтром в адресе — иначе клик по
  // «12 IELTS < 6.0» некуда девать
  const range: Record<string, string> = Object.fromEntries(
    RANGE_FILTERS.map((name) => [name, params.get(name) ?? '']).filter(([, value]) => value !== ''),
  )
  const students = useStudents({ group, parallel, search, page, page_size: PAGE_SIZE, ...range })
  const batch = useBatchSave()

  const myDomain = meta.data?.domains.find((d) => d.is_mine)
  // профиль домена всегда первая модель — она один-к-одному со Student
  const profileModel = myDomain ? profileModelOf(myDomain) : undefined
  const columns = useMemo(() => profileModel?.fields ?? [], [profileModel])
  const dirtyCount = Object.keys(draft).length

  // --- автосохранение --------------------------------------------------
  // Правки уходят батчем через две секунды после последней. Кнопка
  // «Сохранить» остаётся: явное действие должно быть доступно всегда.
  useEffect(() => {
    if (dirtyCount === 0) return
    // то, что сервер уже отклонил, само себя не отправляет по кругу:
    // ждём, пока человек поправит значение
    if (sync === 'rejected') return
    if (sync !== 'saving') setSync((prev) => (prev === 'offline' ? prev : 'dirty'))
    if (!navigator.onLine) {
      setSync('offline')
      return
    }
    const timer = window.setTimeout(() => void saveRef.current(), AUTOSAVE_DELAY)
    return () => window.clearTimeout(timer)
    // `sync` намеренно не в зависимостях: иначе смена состояния сама
    // перезапускала бы таймер и сохранение не наступало бы никогда
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, dirtyCount])

  // связь вернулась — отправляем накопленное и говорим об этом. Два
  // источника: браузер (`online`) и наш слой связи с сервером (фаза 36):
  // вайфай может быть на месте, а бэкенд — перезапускаться
  const resend = useCallback(() => {
    if (Object.keys(draftRef.current).length === 0) return
    toast.info(t('Связь вернулась — отправляем накопленные правки'))
    void saveRef.current()
  }, [])
  useReconnected(resend)
  const connection = useConnection()
  useEffect(() => {
    const onOffline = () => setSync('offline')
    window.addEventListener('online', resend)
    window.addEventListener('offline', onOffline)
    return () => {
      window.removeEventListener('online', resend)
      window.removeEventListener('offline', onOffline)
    }
  }, [resend])
  useEffect(() => {
    if (connection.offline && Object.keys(draftRef.current).length > 0) setSync('offline')
  }, [connection.offline])

  // предупреждение при уходе со страницы с несохранёнными правками
  useEffect(() => {
    if (dirtyCount === 0) return
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirtyCount])

  /** Текущее значение ячейки: черновик, а если его нет — то, что в базе. */
  const currentValue = useCallback(
    (student: StudentCard, field: DomainField): string => {
      const dirty = draftRef.current[cellKey(student.id, field.name)]
      return dirty ? dirty.value : myDomain ? displayValue(student, myDomain.code, field) : ''
    },
    [myDomain],
  )

  /**
   * Записать значения в ячейки одним действием.
   *
   * `coalesce` — набор в одной и той же ячейке: каждая буква не должна
   * становиться отдельным шагом отмены, иначе Ctrl+Z возвращает по букве.
   */
  const commit = useCallback(
    (
      changes: { student: StudentCard; field: DomainField; text: string }[],
      options: { coalesce?: boolean } = {},
    ) => {
      if (!myDomain || !profileModel || changes.length === 0) return
      const entry: UndoEntry = {
        cells: changes.map(({ student, field }) => ({
          student: student.id,
          field: field.name,
          before: currentValue(student, field),
        })),
      }
      const top = undoRef.current[undoRef.current.length - 1]
      const sameCell =
        options.coalesce &&
        top &&
        top.cells.length === 1 &&
        entry.cells.length === 1 &&
        top.cells[0].student === entry.cells[0].student &&
        top.cells[0].field === entry.cells[0].field
      if (!sameCell) {
        undoRef.current = [...undoRef.current.slice(-(UNDO_DEPTH - 1)), entry]
        setUndoDepth(undoRef.current.length)
      }

      const next = { ...draftRef.current }
      for (const { student, field, text } of changes) {
        const original = displayValue(student, myDomain.code, field)
        const key = cellKey(student.id, field.name)
        if (text === original) delete next[key]
        else
          next[key] = {
            student: student.id,
            model: profileModel.label,
            field: field.name,
            value: text,
            original,
          }
      }
      draftRef.current = next
      setDraft(next)
      setSync((prev) => (prev === 'rejected' ? 'dirty' : prev))
      // ячейку, которую человек поправил, больше не считаем отклонённой
      setCellProblems((prev) => {
        const keys = changes.map(({ student, field }) => cellKey(student.id, field.name))
        if (!keys.some((key) => key in prev)) return prev
        const copy = { ...prev }
        keys.forEach((key) => delete copy[key])
        return copy
      })
    },
    [myDomain, profileModel, currentValue],
  )

  const setCell = useCallback(
    (student: StudentCard, field: DomainField, text: string) =>
      commit([{ student, field, text }], { coalesce: true }),
    [commit],
  )

  /** Отменить последнее действие: вернуть ячейкам то, что в них было. */
  const undo = useCallback(() => {
    const entry = undoRef.current.pop()
    setUndoDepth(undoRef.current.length)
    if (!entry || !myDomain || !profileModel) return
    const list = students.data?.results ?? []
    const next = { ...draftRef.current }
    for (const cell of entry.cells) {
      const student = list.find((s) => s.id === cell.student)
      const field = columns.find((f) => f.name === cell.field)
      if (!student || !field) continue
      const original = displayValue(student, myDomain.code, field)
      const key = cellKey(student.id, field.name)
      if (cell.before === original) delete next[key]
      else
        next[key] = {
          student: student.id,
          model: profileModel.label,
          field: field.name,
          value: cell.before,
          original,
        }
    }
    draftRef.current = next
    setDraft(next)
    setSync((prev) => (prev === 'rejected' ? 'dirty' : prev))
    toast.info(t('Последнее действие отменено'))
  }, [columns, myDomain, profileModel, students.data])

  /**
   * Вставка из буфера: TSV из Excel раскладывается по ячейкам вправо и вниз —
   * колонкой, строкой или прямоугольником. Ложится и в списки: подпись
   * варианта («высокая») превращается в его ключ. Одно действие для отмены.
   */
  const onPaste = useCallback(
    (
      event: React.ClipboardEvent<HTMLInputElement | HTMLSelectElement>,
      rowIndex: number,
      colIndex: number,
    ) => {
      const text = event.clipboardData.getData('text/plain')
      const isSelect = event.currentTarget instanceof HTMLSelectElement
      // обычная вставка в одну ячейку ввода — как в любое поле; в список
      // браузер сам ничего не вставит, поэтому его берём на себя всегда
      if (!isSelect && !text.includes('\t') && !text.includes('\n')) return
      event.preventDefault()

      const rows = text.replace(/\r/g, '').replace(/\n$/, '').split('\n')
      const list = students.data?.results ?? []
      const changes: { student: StudentCard; field: DomainField; text: string }[] = []
      let width = 0
      rows.forEach((line, r) => {
        const student = list[rowIndex + r]
        if (!student) return
        const cells = line.split('\t')
        width = Math.max(width, cells.length)
        cells.forEach((cell, c) => {
          const field = columns[colIndex + c]
          if (field) changes.push({ student, field, text: choiceValue(field, cell.trim()) })
        })
      })
      commit(changes)
      toast.info(t('Вставлено: {rows} × {cols} — строк × колонок', { rows: rows.length, cols: width }))
    },
    [columns, commit, students.data],
  )

  /** Растягивание вниз: значение активной ячейки копируется до той, где отпустили. */
  const finishFill = useCallback(() => {
    if (!fill) return
    const list = students.data?.results ?? []
    const source = list[fill.row]
    const field = columns[fill.col]
    setFill(null)
    if (!source || !field || fill.to === fill.row) return
    const value = currentValue(source, field)
    const [from, to] = fill.to > fill.row ? [fill.row + 1, fill.to] : [fill.to, fill.row - 1]
    const changes: { student: StudentCard; field: DomainField; text: string }[] = []
    for (let r = from; r <= to; r += 1) {
      const student = list[r]
      if (student) changes.push({ student, field, text: value })
    }
    commit(changes)
    toast.info(t('Заполнено ячеек: {n}', { n: changes.length }))
  }, [columns, commit, currentValue, fill, students.data])

  // мышь отпускают где угодно, не обязательно над ячейкой
  useEffect(() => {
    if (!fill) return
    const up = () => finishFill()
    window.addEventListener('mouseup', up)
    return () => window.removeEventListener('mouseup', up)
  }, [fill, finishFill])

  /**
   * Клавиши, как в электронной таблице.
   *
   * Tab / Shift+Tab — следующая и предыдущая ячейка, с переносом на другую
   * строку; Enter / Shift+Enter — вниз и вверх; стрелки вверх-вниз — по
   * колонке; вправо-влево — по строке, когда курсор упёрся в край текста
   * или текст выделен целиком (иначе они двигают курсор, как и должны);
   * Escape снимает фокус; Ctrl+Z отменяет последнее действие; Ctrl+D
   * копирует значение из ячейки выше — как в Excel без выделения.
   */
  const onKeyDown = (
    event: React.KeyboardEvent<HTMLInputElement | HTMLSelectElement>,
    row: number,
    col: number,
  ) => {
    const moveTo = (r: number, c: number): boolean => {
      // ячейка — ввод или список: стрелки ходят по обоим
      const target = gridRef.current?.querySelector<HTMLInputElement | HTMLSelectElement>(
        `.cell[data-row="${r}"][data-col="${c}"]`,
      )
      if (!target) return false
      event.preventDefault()
      target.focus()
      if (target instanceof HTMLInputElement) target.select()
      return true
    }
    const move = (dr: number, dc: number) => moveTo(row + dr, col + dc)
    const control = event.ctrlKey || event.metaKey
    const el = event.currentTarget
    const isSelect = el instanceof HTMLSelectElement

    if (control && event.key.toLowerCase() === 'z' && !event.shiftKey) {
      event.preventDefault()
      undo()
      return
    }
    if (control && event.key.toLowerCase() === 'd') {
      event.preventDefault()
      const list = students.data?.results ?? []
      const above = list[row - 1]
      const student = list[row]
      const field = columns[col]
      if (above && student && field) commit([{ student, field, text: currentValue(above, field) }])
      return
    }
    if (event.key === 'Tab') {
      if (event.shiftKey) {
        if (!moveTo(row, col - 1)) moveTo(row - 1, columns.length - 1)
      } else if (!moveTo(row, col + 1)) moveTo(row + 1, 0)
      return
    }
    if (event.key === 'Enter') {
      move(event.shiftKey ? -1 : 1, 0)
      return
    }
    // у списка стрелки вверх-вниз выбирают значение — по сетке водят Tab, Enter и Escape
    if (event.key === 'ArrowDown' && !isSelect) move(1, 0)
    else if (event.key === 'ArrowUp' && !isSelect) move(-1, 0)
    else if ((event.key === 'ArrowRight' || event.key === 'ArrowLeft') && !isSelect) {
      const input = el as HTMLInputElement
      const length = input.value.length
      const whole = length > 0 && input.selectionStart === 0 && input.selectionEnd === length
      const atEnd = input.selectionStart === length
      const atStart = input.selectionEnd === 0
      if (event.key === 'ArrowRight' && (whole || atEnd)) move(0, 1)
      if (event.key === 'ArrowLeft' && (whole || atStart)) move(0, -1)
    } else if (event.key === 'Escape') (event.target as HTMLElement).blur()
  }

  async function save() {
    if (inFlight.current) return
    inFlight.current = true
    try {
      await sendDraft()
    } finally {
      inFlight.current = false
    }
    // пока снимок летел, человек продолжал печатать: таймер автосохранения
    // упёрся в `inFlight` и ничего не отправил — досылаем сами
    if (Object.keys(draftRef.current).length > 0 && navigator.onLine && !connection.offline) {
      window.setTimeout(() => void saveRef.current(), AUTOSAVE_DELAY)
    }
  }

  async function sendDraft() {
    // снимок черновика на момент отправки: пока запрос летит, человек
    // продолжает печатать, и очистка целиком стирала бы новые правки
    const sending = { ...draft }
    const keys = Object.keys(sending)
    if (keys.length === 0) return

    const changes: BatchChange[] = Object.values(sending).map((cell) => {
      const field = columns.find((f) => f.name === cell.field)!
      return {
        student: cell.student,
        model: cell.model,
        field: cell.field,
        value: parseValue(field, cell.value),
        // сервер сверит прежнее значение и не затрёт чужую правку
        expected: cell.original,
      }
    })

    setSync('saving')
    let result
    try {
      result = await batch.mutateAsync(changes)
    } catch (error) {
      // связь пропала — правки остаются в черновике и уйдут сами,
      // когда сеть вернётся. Терять набранное нельзя
      setSync('offline')
      setFlashed(new Set())
      setProblems([
        error instanceof Error ? error.message : t('Не удалось сохранить — правки сохранены в черновике'),
      ])
      return
    }

    // отклонённые и конфликтные ячейки остаются в черновике: человек
    // должен видеть, что именно не прошло, и поправить это на месте
    const kept = new Set(
      [...result.rejected, ...result.conflicts]
        .filter((row) => row.student !== undefined && row.field !== undefined)
        .map((row) => cellKey(row.student as number, row.field as string)),
    )
    const next = { ...draftRef.current }
    for (const key of keys) {
      if (kept.has(key)) continue
      // ячейку, изменённую заново уже после отправки, не трогаем
      if (next[key] && next[key].value === sending[key].value) delete next[key]
    }
    draftRef.current = next
    setDraft(next)
    // причина отказа — у самой ячейки: список внизу человек находит не сразу,
    // а красная ячейка с подсказкой видна там, где он печатал
    const byCell: Record<string, string> = {}
    result.conflicts.forEach((c) => {
      if (c.student !== undefined && c.field !== undefined)
        byCell[cellKey(c.student as number, c.field as string)] = t('кто-то уже поставил «{value}»', { value: c.actual_display })
    })
    result.rejected.forEach((r) => {
      if (r.student !== undefined && r.field !== undefined)
        byCell[cellKey(r.student as number, r.field as string)] = r.reason
    })
    setCellProblems(byCell)
    // «сохранено» только если действительно сохранилось: молчаливая
    // галочка над отклонённой правкой — худший вид обмана
    setSync(kept.size > 0 ? 'rejected' : 'saved')
    const parts = [t('Сохранено: {n}', { n: result.applied })]
    if (result.conflicts.length) parts.push(t('конфликтов: {n}', { n: result.conflicts.length }))
    if (result.rejected.length) parts.push(t('отклонено: {n}', { n: result.rejected.length }))
    // подсвечиваем ровно те строки, которые ушли в базу: конфликтные
    // и отклонённые остались в черновике и подсветки не заслужили
    setFlashed(new Set(keys.filter((key) => !kept.has(key)).map((key) => sending[key].student)))
    // уведомление вместо плашки в панели: плашку человек находит глазами
    // не сразу, а сообщение о сохранении должно догнать его само
    if (kept.size > 0) toast.warning(parts.join(' · '))
    else toast.success(parts.join(' · '))
    // причина отказа важнее числа: «7,5» вместо «7.5» человек исправит сам,
    // если ему сказать, что именно не подошло
    setProblems([
      ...result.conflicts.map(
        (c) =>
          t('{field}: кто-то уже поставил «{actual}», ваше «{expected}» не применено', {
            field: c.field_title,
            actual: c.actual_display,
            expected: c.expected_display,
          }),
      ),
      ...result.rejected.map((r) => r.reason),
    ])
  }
  saveRef.current = save

  /** Сбросить черновик. Без этого передумать можно только перезагрузкой. */
  function cancel() {
    draftRef.current = {}
    undoRef.current = []
    setUndoDepth(0)
    setDraft({})
    setFlashed(new Set())
    setProblems([])
    setCellProblems({})
    setSync('idle')
  }

  if (meta.isLoading || students.isLoading) return <Loading kind="table" />
  if (meta.error) return <ErrorNote error={meta.error} />
  // у администратора «Таблица» — реестр школы: завести ученика, класс,
  // группа. С фазы 68 он правит и все домены, но не здесь: таблица быстрого
  // ввода — по одному домену, а у него их пять; доменные поля он правит
  // в карточке ученика, где каждый домен помечен «вы редактируете»
  if (me?.role === 'admin') return <StudentRegistry />
  if (!myDomain || !profileModel) {
    return (
      <div>
        <ScreenHead title={t('Таблица')} />
        <Empty
          icon="table"
          title={t('У вашей роли нет своего домена')}
          what={t('Табличный ввод — по полям своего домена, а у вашей роли его нет.')}
        />
      </div>
    )
  }

  const rows = students.data?.results ?? []
  const total = students.data?.count ?? rows.length
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const groups = [...new Set(rows.map((s) => s.group_code).filter(Boolean))].sort()

  return (
    <div>
      <PublishStudents ids={rows.map((s) => s.id)} />
      <ScreenHead
        title={t('Таблица')}
        subtitle={
          // подзаголовок и плашка под ним говорили одно и то же слово в слово
          // (найдено в 74-й): объяснение теперь только в плашке
          locked
            ? t('Поля домена «{domain}».', { domain: myDomain.title })
            : t(
                'Только поля домена «{domain}». Tab и стрелки — по ячейкам, вставка из Excel ложится прямоугольником, маркер в углу тянет значение вниз, Ctrl+Z отменяет.',
                { domain: myDomain.title },
              )
        }
        actions={
          // На телефоне таблица только читается (фаза 51): ходьба стрелками,
          // вставка прямоугольником и растягивание значения — работа
          // за столом, и кнопка «Внести вручную» вела бы в сетку,
          // в которую пальцем не попасть
          phone ? undefined : locked ? (
            <Button variant="outline" size="sm" onClick={() => setLocked(false)}>
              {t('Внести вручную')}
            </Button>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setLocked(true)}>
              {t('Вернуть на чтение')}
            </Button>
          )
        }
      />

      {/* С фазы 49 таблица директора открывается на чтение: данные о себе
          вносит ученик, а директор подтверждает их в очереди. Ручной ввод
          никуда не делся — он ушёл во второстепенную кнопку, потому что
          перестал быть главным путём */}
      {locked && (
        <Notice icon="lock" className="tblnote" summary={t('Значения меняет ученик, вы подтверждаете')}>
          <span>
            {phone
              ? t('Значения меняет ученик, вы подтверждаете их в очереди. Вносить руками — с компьютера.')
              : t('Значения меняет ученик, вы подтверждаете их в очереди на дашборде.')}
          </span>
          {!phone && (
            <Button variant="link" size="sm" className="tipbar__action" onClick={() => setLocked(false)}>
              {t('Внести вручную')}
            </Button>
          )}
        </Notice>
      )}

      {/* Подсказка о том, откуда берутся файлы, нужна в обоих режимах:
          она объясняет не правку, а то, что загрузку делает администратор
          (обещание фазы 35) */}
      <ManualEntryNote />

      <PhoneFold active={Boolean(search || group || parallel)}>
      <div className="toolbar">
        <Input
          placeholder={t('Поиск по имени')}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(1)
          }}
        />
        <SelectField
          value={group}
          onChange={(e) => {
            setGroup(e.target.value)
            setPage(1)
          }}
        >
          <option value="">{t('Все группы')}</option>
          {groups.map((code) => (
            <option key={code} value={code!}>
              {code}
            </option>
          ))}
        </SelectField>
        {/* домен поступления и экзаменов ведётся только у 11 — выбирать там нечего */}
        {(myDomain?.parallels ?? []).length > 1 && (
          <SelectField
            aria-label={t('Параллель')}
            value={parallel}
            onChange={(e) => {
              setParallel(e.target.value)
              setPage(1)
            }}
          >
            <option value="">{t('Все параллели')}</option>
            {PARALLELS.map((value) => (
              <option key={value} value={String(value)}>
                {parallelTitle(value)}
              </option>
            ))}
          </SelectField>
        )}
        <Chip tone="neutral" className="num">
          {total > rows.length
            ? tn(total, '{shown} из {n} ученика|{shown} из {n} учеников|{shown} из {n} учеников', { shown: rows.length })
            : counted(rows.length, 'ученик|ученика|учеников')}
        </Chip>

        <span className="toolbar__spacer" />
        {!locked && SYNC_TITLES[sync] && (
          <Chip tone={SYNC_TITLES[sync].tone} data-sync={sync}>
            { }
            {t(SYNC_TITLES[sync].text)}
            {dirtyCount > 0 && sync !== 'saved' && <span className="num"> · {dirtyCount}</span>}
          </Chip>
        )}
        {!locked && (
          <>
            <Button variant="outline" size="sm" onClick={undo} disabled={undoDepth === 0} title="Ctrl+Z">
              {t('Вернуть')}
            </Button>
            <Button variant="outline" size="sm" onClick={cancel} disabled={dirtyCount === 0}>
              {t('Отменить правки')}
            </Button>
            <Button size="sm" onClick={() => void save()} disabled={dirtyCount === 0 || batch.isPending}>
              {batch.isPending ? t('Сохраняю…') : t('Сохранить')}
            </Button>
          </>
        )}
      </div>
      </PhoneFold>

      {Object.keys(range).length > 0 && (
        <div className="toolbar">
          <span className="muted">{t('Фильтр из дашборда:')}</span>
          {Object.entries(range).map(([name, value]) => (
            <Chip key={name} tone="accent" className="num">
              {FILTER_TITLES[name] ? t(FILTER_TITLES[name], { value }) : `${name} ${value}`}
            </Chip>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setParams(new URLSearchParams())
              setPage(1)
            }}
          >
            {t('Снять фильтр')}
          </Button>
        </div>
      )}

      {problems.length > 0 && (
        <div className="card card-pad mb-3 border-(--bad)">
          <span className="eyebrow">{t('Не сохранилось')}</span>
          <ul className="bullets">
            {problems.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </div>
      )}

      {rows.length === 0 && (
        <Empty
          icon="table"
          title={search || group || parallel ? t('По этому фильтру никого нет') : t('Учеников пока нет')}
          what={
            search || group || parallel
              ? t('Ни один ученик не подошёл под поиск и выбранную группу. Снимите фильтры, чтобы увидеть всех.')
              : t(
                  'Учеников заводит администратор списком на экране «Пользователи». Как только они появятся, здесь будет строка на каждого — с полями домена «{domain}», вставкой из Excel и переходом по Tab.',
                  { domain: myDomain.title },
                )
          }
          action={search || group || parallel ? t('Снять фильтры') : undefined}
          onAction={
            search || group || parallel
              ? () => {
                  setSearch('')
                  setGroup('')
                  setParallel('')
                }
              : undefined
          }
        />
      )}

      {/* Телефон: строка таблицы становится карточкой — имя заголовком,
          остальное парами «подпись — значение». Сетка в двенадцать колонок
          на 390 пикселях едет вбок, а вбок на телефоне не ездят */}
      {phone && (
        <div className="tblcards" hidden={rows.length === 0}>
          {rows.map((student) => (
            <div key={student.id} className="card card-pad tblcard">
              <Button variant="link" className="tblcard__name" onClick={() => navigate(`/students/${student.id}`)}>
                {student.full_name}
              </Button>
              <dl className="tblcard__pairs">
                <div className="tblcard__pair">
                  <dt>{t('Группа')}</dt>
                  <dd className="num">{student.group_code ?? t('нет')}</dd>
                </div>
                {columns.map((field) => (
                  <div key={field.name} className="tblcard__pair">
                    <dt title={field.title}>{field.short}</dt>
                    <dd className="num">{displayValue(student, myDomain.code, field) || t('нет')}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      )}

      <QuickGrid
        gridRef={gridRef}
        hidden={phone || rows.length === 0}
        head={
          <tr>
            <th className="sticky-col">{t('Ученик')}</th>
            <th className="col-narrow">{t('Гр.')}</th>
            {columns.map((field) => (
              <th key={field.name} title={field.title}>
                {field.short}
              </th>
            ))}
          </tr>
        }
      >
            {rows.map((student, rowIndex) => (
              <motion.tr
                key={student.id}
                layout={rowMotion.layout}
                transition={rowMotion.transition}
                className={flashed.has(student.id) ? 'row--flash' : undefined}
              >
                <td className="sticky-col">
                  <Button variant="link" size="sm" className="cell-link" onClick={() => navigate(`/students/${student.id}`)}>
                    {student.full_name}
                  </Button>
                </td>
                <td>
                  <span className="cell cell-ro num">{student.group_code ?? t('нет')}</span>
                </td>
                {columns.map((field, colIndex) => {
                  const key = cellKey(student.id, field.name)
                  const dirty = draft[key]
                  const value = dirty ? dirty.value : displayValue(student, myDomain.code, field)
                  const problem = cellProblems[key]
                  const isActive = active?.row === rowIndex && active.col === colIndex
                  const inFill =
                    fill !== null &&
                    fill.col === colIndex &&
                    rowIndex >= Math.min(fill.row, fill.to) &&
                    rowIndex <= Math.max(fill.row, fill.to)
                  const cellClass = `${dirty ? ' cell-dirty' : ''}${problem ? ' cell-error' : ''}`
                  const common = {
                    'data-row': rowIndex,
                    'data-col': colIndex,
                    title: problem,
                    onFocus: () => setActive({ row: rowIndex, col: colIndex }),
                    onKeyDown: (e: React.KeyboardEvent<HTMLInputElement | HTMLSelectElement>) =>
                      onKeyDown(e, rowIndex, colIndex),
                    onPaste: (e: React.ClipboardEvent<HTMLInputElement | HTMLSelectElement>) =>
                      onPaste(e, rowIndex, colIndex),
                  }
                  // маркер растягивания — в углу активной ячейки; тянется мышью вниз
                  // или вверх по колонке, отпустили — значение легло во все ячейки
                  const handle = isActive && !fill && (
                    <span
                      className="cell-fill"
                      title={t('Растянуть значение по колонке')}
                      onMouseDown={(e) => {
                        e.preventDefault()
                        setFill({ row: rowIndex, col: colIndex, to: rowIndex })
                      }}
                    />
                  )
                  // поле с выбором — список с подписями, а не ввод ключа с подсказкой:
                  // директор видел `can_execute` там, где везде вокруг стоят слова
                  if (field.choices) {
                    return (
                      <td
                        key={field.name}
                        className={inFill ? 'cell-fillrange' : undefined}
                        onMouseEnter={() =>
                          fill && fill.col === colIndex && setFill({ ...fill, to: rowIndex })
                        }
                      >
                        <QuickCell
                          kind="select"
                          className={`cell cell-select${cellClass}`}
                          value={value}
                          disabled={locked}
                          options={field.choices}
                          empty={t('нет')}
                          onChange={(next) => setCell(student, field, next)}
                          {...common}
                        />
                        {handle}
                      </td>
                    )
                  }
                  return (
                    <td
                      key={field.name}
                      className={inFill ? 'cell-fillrange' : undefined}
                      onMouseEnter={() => fill && fill.col === colIndex && setFill({ ...fill, to: rowIndex })}
                    >
                      <QuickCell
                        kind="text"
                        className={`cell num${cellClass}`}
                        value={value}
                        readOnly={locked}
                        onChange={(next) => setCell(student, field, next)}
                        {...common}
                      />
                      {handle}
                    </td>
                  )
                })}
              </motion.tr>
            ))}
      </QuickGrid>

      {pages > 1 && (
        <div className="toolbar mt-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1 || dirtyCount > 0}
          >
            {t('← Предыдущие')}
          </Button>
          <Chip tone="neutral" className="num">
            {t('страница {page} из {pages}', { page, pages })}
          </Chip>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.min(pages, p + 1))}
            disabled={page === pages || dirtyCount > 0}
          >
            {t('Следующие →')}
          </Button>
          {dirtyCount > 0 && <span className="muted">{t('Сначала сохраните правки')}</span>}
        </div>
      )}
    </div>
  )
}
