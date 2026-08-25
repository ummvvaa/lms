/** Мелкие примитивы интерфейса по дизайн-системе прототипа. */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { animate, useReducedMotion } from 'motion/react'
import { t } from '../i18n'
import { DURATION, EASE } from '../motion'
import { Skeleton } from './ui/skeleton'
import { Tabs, TabsIndicator, TabsList, TabsTrigger } from './ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'

/**
 * Русское склонение существительного при числе.
 *
 * «1 программ в вашем списке» читается как сбой перевода, а чисел
 * в интерфейсе много: счётчики, подзаголовки, подтверждения.
 *
 * Формы: одна, две, пять — `plural(n, ['программа', 'программы', 'программ'])`.
 */
export function plural(count: number, forms: [string, string, string]): string {
  const abs = Math.abs(count) % 100
  const tail = abs % 10
  if (abs > 10 && abs < 20) return forms[2]
  if (tail > 1 && tail < 5) return forms[1]
  if (tail === 1) return forms[0]
  return forms[2]
}

/** «3 программы» — число вместе со склонённым словом. */
export function counted(count: number, forms: [string, string, string]): string {
  return `${count} ${plural(count, forms)}`
}

/**
 * Число, которое накручивается от нуля.
 *
 * Ровно один раз — при первой загрузке страницы, как и договорились
 * в фазе 32. Накрутка на каждое обновление данных превращает дашборд
 * в мигающее табло: числа там меняются сами, без участия человека,
 * и дёргать глаз на каждый ответ сервера незачем.
 *
 * Нечисловое значение («6.5 / 9», «—») показывается как есть: крутить
 * там нечего.
 */
function Counter({ value }: { value: ReactNode }) {
  const numeric = typeof value === 'number' ? value : Number(value)
  const shownAsIs =
    typeof value !== 'number' &&
    (typeof value !== 'string' || value.trim() === '' || !Number.isFinite(numeric))
  const still = useReducedMotion()
  const [shown, setShown] = useState(numeric)
  // накрутили один раз — дальше значение встаёт сразу
  const spun = useRef(false)

  useEffect(() => {
    if (shownAsIs || !Number.isFinite(numeric)) return
    if (spun.current || still) {
      setShown(numeric)
      return
    }
    spun.current = true
    const run = animate(0, numeric, {
      duration: DURATION.slow,
      ease: EASE,
      onUpdate: setShown,
    })
    return () => run.stop()
  }, [numeric, shownAsIs, still])

  if (shownAsIs) return <>{value}</>
  // столько же знаков после запятой, сколько в самом значении:
  // «6.5» не должно доехать до «7»
  const decimals = String(value).includes('.') ? String(value).split('.')[1].length : 0
  return <>{shown.toFixed(decimals)}</>
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <span className="eyebrow">{children}</span>
}

export function ScreenHead({
  title,
  subtitle,
  eyebrow,
}: {
  title: string
  subtitle?: string
  /** надзаголовок над названием секции */
  eyebrow?: string
}) {
  return (
    <header className="head">
      {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
      <h1 className="head__title">{title}</h1>
      {subtitle && <p className="muted head__sub">{subtitle}</p>}
    </header>
  )
}

/**
 * Полоса вкладок экрана.
 *
 * Одна на все экраны, где вкладки есть: карточка ученика, каталог,
 * импорт, роадмап, материалы. Раньше каждый рисовал свой ряд кнопок,
 * и вкладки на соседних экранах отличались на пару пикселей.
 *
 * Подложка активной вкладки переезжает, а не перекрашивается: глаз
 * следит за движением и не теряет, откуда он пришёл. Стрелки и роли
 * приходят от `Tabs` из shadcn — своими кнопками их не было.
 */
export function ScreenTabs<T extends string>({
  value,
  onChange,
  items,
}: {
  value: T
  onChange: (next: T) => void
  items: { value: T; label: ReactNode }[]
}) {
  return (
    <Tabs value={value} onValueChange={(next) => onChange(next as T)} className="tabs">
      <TabsList className="tabs__list">
        <TabsIndicator />
        {items.map((item) => (
          <TabsTrigger key={item.value} value={item.value} className="tabs__tab">
            {item.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}

type Tone = 'ok' | 'warn' | 'risk' | 'brand' | 'mute' | 'teal' | 'indigo'

/**
 * Цвет полосы над карточкой — по смыслу содержимого, а не по вкусу:
 * бирюза у языка, индиго у стандартных тестов, зелёно-бирюзовый
 * у хорошего, винный у риска, оранжевый у своего домена.
 *
 * Полосы нет, если смысла нет: карточка без `accent` остаётся белой,
 * и цветная полоса не превращается в украшение.
 */
export type Accent = 'brand' | 'teal' | 'indigo' | 'ok' | 'warn' | 'risk'

export function accentClass(accent?: Accent): string {
  return accent ? ` card--accent card--${accent}` : ''
}

export function Chip({ tone = 'mute', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`chip chip-${tone}`}>{children}</span>
}

export function Kpi({
  value,
  label,
  note,
  color = 'var(--ink)',
  accent,
}: {
  value: ReactNode
  label: string
  note?: string
  color?: string
  /** цветная полоса сверху — по смыслу числа, а не для красоты */
  accent?: Accent
}) {
  return (
    <div className={`card card-pad kpi${accentClass(accent)}`}>
      <div className="num kpi__value" style={{ color }}>
        <Counter value={value} />
      </div>
      <div className="kpi__label">{label}</div>
      {note && <div className="muted kpi__note">{note}</div>}
    </div>
  )
}

/**
 * Подсказка по наведению.
 *
 * Длинное пояснение на экране превращается в абзац, который никто
 * не читает. Короткая подпись остаётся видимой, а подробности ждут
 * под курсором.
 *
 * С фазы 32 внутри — `Tooltip` из shadcn вместо браузерного `title`:
 * тот появляется через секунду, не открывается с клавиатуры и рисуется
 * системным шрифтом мимо темы. `aria-label` оставлен: подсказка должна
 * читаться и тогда, когда всплывающего окна нет.
 */
export function Hint({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger className="hint" aria-label={text}>
        ?
      </TooltipTrigger>
      <TooltipContent>{text}</TooltipContent>
    </Tooltip>
  )
}

/**
 * Карточка одного блока данных.
 *
 * Заголовок отвечает на вопрос «что это за число»: не «Прогресс»,
 * а «Готовность к подаче». Описание — не больше одной строки, всё
 * длинное уходит в подсказку по наведению.
 */
export function DataCard({
  title,
  note,
  hint,
  right,
  count,
  accent,
  children,
}: {
  title: string
  /** одна строка о том, что внутри; длиннее — в `hint` */
  note?: string
  /** длинное пояснение: показывается по наведению, а не на экране */
  hint?: string
  right?: ReactNode
  /** число записей рядом с заголовком */
  count?: number
  /** цветная полоса сверху — по смыслу содержимого */
  accent?: Accent
  children: ReactNode
}) {
  return (
    <section className={`card card-pad datacard${accentClass(accent)}`}>
      <header className="datacard__head">
        <span className="datacard__title">
          {title}
          {hint && <Hint text={hint} />}
        </span>
        {count !== undefined && <span className="chip chip-mute num">{count}</span>}
        {right}
      </header>
      {note && <p className="muted datacard__note">{note}</p>}
      {children}
    </section>
  )
}

/**
 * Одно значение внутри карточки: число крупно, подпись под ним мелко.
 *
 * Порядок именно такой — сначала глазами ловится величина, потом
 * читается, что это было.
 */
export function Metric({
  value,
  label,
  tone,
  hint,
}: {
  value: ReactNode
  label: string
  tone?: 'ok' | 'warn' | 'risk' | 'brand' | 'mute'
  hint?: string
}) {
  const color = tone === 'mute' ? 'var(--ink-40)' : tone ? `var(--${tone})` : 'var(--ink)'
  return (
    <div className="metric" title={hint}>
      <div className="num metric__value" style={{ color }}>
        <Counter value={value} />
      </div>
      <div className="muted metric__label">{label}</div>
    </div>
  )
}

/** Сетка значений внутри карточки. */
export function MetricRow({ children }: { children: ReactNode }) {
  return <div className="metric__row">{children}</div>
}

/** Пустое значение читается как «—», а не как сломанная вёрстка. */
export function shownValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'да' : 'нет'
  return String(value)
}

export function Bar({ percent, color = 'var(--brand)' }: { percent: number; color?: string }) {
  const width = Math.max(0, Math.min(100, percent))
  return (
    <div className="bar">
      <i style={{ width: `${width}%`, background: color }} />
    </div>
  )
}

/** Кольцо готовности. */
export function Ring({
  percent,
  size = 104,
  color = 'var(--brand)',
  children,
}: {
  percent: number
  size?: number
  color?: string
  children?: ReactNode
}) {
  const r = size / 2 - 8
  const c = 2 * Math.PI * r
  const filled = (Math.max(0, Math.min(100, percent)) / 100) * c
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle className="ring__track" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth="9" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${c - filled}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="ring__inner">{children}</div>
    </div>
  )
}

/** Кольцевая диаграмма распределения. */
export function Donut({
  segments,
  size = 132,
}: {
  segments: { value: number; color: string }[]
  size?: number
}) {
  const r = size / 2 - 11
  const c = 2 * Math.PI * r
  const total = segments.reduce((sum, s) => sum + s.value, 0) || 1
  let offset = 0
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle className="ring__track" cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth="15" />
      {segments.map((segment, i) => {
        const length = (segment.value / total) * c
        const element = (
          <circle
            key={i}
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={segment.color}
            strokeWidth="15"
            strokeDasharray={`${length} ${c - length}`}
            strokeDashoffset={-offset}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        )
        offset += length
        return element
      })}
    </svg>
  )
}

export interface PersonRow {
  student_id: number
  student__last_name: string
  student__first_name: string
}

export function ListPanel<T extends PersonRow>({
  title,
  rows,
  right,
  limit = 12,
  onOpen,
}: {
  title: string
  rows: T[]
  right?: (row: T) => ReactNode
  limit?: number
  onOpen?: (id: number) => void
}) {
  return (
    <div className="card card-pad">
      <div className="panel__head">
        <span className="panel__title">{title}</span>
        <span className="chip chip-mute num">{rows.length}</span>
      </div>
      <div className="panel__list">
        {rows.length === 0 && <p className="muted panel__empty">{t('Никого — это хорошая новость')}</p>}
        {rows.slice(0, limit).map((row) => (
          <button key={row.student_id} className="person" onClick={() => onOpen?.(row.student_id)}>
            <span className="person__name">
              {row.student__last_name} {row.student__first_name}
            </span>
            {right?.(row)}
          </button>
        ))}
      </div>
      {rows.length > limit && <p className="muted panel__more">и ещё {rows.length - limit}</p>}
    </div>
  )
}

/**
 * Плашка «данные не подтверждены» (инвариант №14).
 *
 * Висит над любой записью справочника, попавшей туда не от сотрудника
 * школы и не с официального сайта. Ученику такая запись показывается
 * только вместе с плашкой, и процент соответствия по ней — тоже.
 */
export function UnverifiedNote({
  note = 'Данные не подтверждены, проверьте на сайте вуза',
  website,
  compact = false,
}: {
  note?: string
  /** сайт вуза — чтобы было куда пойти проверять */
  website?: string
  compact?: boolean
}) {
  if (compact) return <Chip tone="warn">{t('не подтверждено')}</Chip>
  return (
    <p className="unverified">
      {note}
      {website && (
        <a className="unverified__link" href={website} target="_blank" rel="noreferrer">
          {t('сайт вуза')}
        </a>
      )}
    </p>
  )
}

/**
 * Что стоит на экране, пока едут данные: серые полоски на месте
 * будущего содержимого, а не крутилка.
 *
 * Крутилка говорит «подожди» и ничего не обещает: экран прыгает,
 * когда данные приходят и занимают другое место. Полоски стоят там же
 * и такого же размера — приходят данные, и ничего не сдвигается.
 *
 * `kind` выбирает форму: строки таблицы, карточки дашборда или пара
 * строк текста. Пульсация гаснет при системной настройке «уменьшить
 * движение» — правило в конце `base.css` снимает её вместе со всеми
 * остальными, а серые полоски остаются на месте.
 */
export function Loading({ kind = 'text', rows = 6 }: { kind?: 'text' | 'table' | 'cards'; rows?: number }) {
  if (kind === 'table') {
    return (
      <div className="skel__table" role="status" aria-label={t('Загрузка…')}>
        <Skeleton className="skel__head" />
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="skel__row" />
        ))}
      </div>
    )
  }
  if (kind === 'cards') {
    return (
      <div className="skel__cards" role="status" aria-label={t('Загрузка…')}>
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="skel__card" />
        ))}
      </div>
    )
  }
  return (
    <div className="skel__text" role="status" aria-label={t('Загрузка…')}>
      <Skeleton className="skel__line" />
      <Skeleton className="skel__line skel__line--short" />
    </div>
  )
}

export function ErrorNote({ error }: { error: unknown }) {
  return <p className="chip chip-risk">{error instanceof Error ? error.message : 'Ошибка загрузки'}</p>
}
