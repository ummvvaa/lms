/** Мелкие примитивы интерфейса: шапка экрана, показатель, чип, карточка блока. */
import {
  Children,
  Fragment,
  isValidElement,
  useEffect,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from 'react'
import { Link } from 'react-router-dom'
import { animate, useReducedMotion } from 'motion/react'
import { t } from '../i18n'
import { DURATION, EASE } from '../motion'
import { usePhone } from '../phone'
import Icon from '../layout/icons'
import { Button } from './ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from './ui/dropdown-menu'
import { Skeleton } from './ui/skeleton'
import { Tabs, TabsIndicator, TabsList, TabsTrigger } from './ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'
import { Badge, type BadgeVariant } from './ui/badge'

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

/** Пилюля рядом с заголовком: область, группа, фильтр. Нажимается, если есть чем. */
export interface HeadPill {
  label: string
  /** выбранная — графитовая */
  on?: boolean
  onClick?: () => void
}

/**
 * Заголовок экрана — один образец на все экраны.
 *
 * Слева название, над ним крошка «‹ Родитель», если экран вложенный,
 * под ним пилюли и одна строка описания — только когда она передана.
 * Справа в той же строке — действия экрана: главная кнопка залитая,
 * вторичные с рамкой. Кнопки стояли на каждом экране по-своему —
 * в панели под заголовком, в карточке, в углу таблицы, — и человеку
 * приходилось искать их заново на каждом переходе.
 */
export function ScreenHead({
  title,
  subtitle,
  eyebrow,
  crumb,
  pills,
  actions,
}: {
  title: string
  subtitle?: string
  /** надзаголовок над названием секции */
  eyebrow?: string
  /** родительский экран: крошка «‹ Ученики» над заголовком */
  crumb?: { label: string; to: string }
  /** пилюли под заголовком: «11A · 24 ученика», «Все мои группы» */
  pills?: HeadPill[]
  /** основные действия экрана — кнопки справа от названия */
  actions?: ReactNode
}) {
  const phone = usePhone()
  return (
    <header className="head">
      <div className="head__text">
        {crumb && (
          <Link className="head__crumb" to={crumb.to}>
            <Icon name="chevronLeft" size={14} />
            {crumb.label}
          </Link>
        )}
        {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
        <h1 className="head__title">{title}</h1>
        {pills && pills.length > 0 && (
          <div className="head__pills">
            {pills.map((pill) =>
              pill.onClick ? (
                <button
                  key={pill.label}
                  type="button"
                  className={`head__pill${pill.on ? ' head__pill--on' : ''}`}
                  aria-pressed={pill.on}
                  onClick={pill.onClick}
                >
                  {pill.label}
                </button>
              ) : (
                <span key={pill.label} className={`head__pill${pill.on ? ' head__pill--on' : ''}`}>
                  {pill.label}
                </span>
              ),
            )}
          </div>
        )}
        {subtitle && <p className="head__sub">{subtitle}</p>}
      </div>
      {actions && (
        <div className="head__actions">{phone ? <PhoneActions>{actions}</PhoneActions> : actions}</div>
      )}
    </header>
  )
}

/** Кнопки шапки без обёрток-фрагментов: с ними работает сворачивание в меню. */
function flatActions(node: ReactNode): ReactNode[] {
  return Children.toArray(node).flatMap((child) =>
    isValidElement(child) && child.type === Fragment
      ? flatActions((child.props as { children?: ReactNode }).children)
      : [child],
  )
}

type ButtonElement = ReactElement<{
  variant?: string
  onClick?: () => void
  disabled?: boolean
  children?: ReactNode
}>

const isButton = (node: ReactNode): node is ButtonElement => isValidElement(node) && node.type === Button

/**
 * Действия шапки на телефоне (фаза 75): одна кнопка «Действия» с меню.
 *
 * Четыре кнопки над таблицей занимали три строки на 390 пикселях.
 * Главное действие — кнопка без `variant`, то есть залитая, — остаётся
 * на виду, если оно одно; остальные уходят в меню. Элемент шапки, который
 * не `Button` (кнопка с собственным окном), остаётся как есть: его
 * состояние живёт в нём самом, и переносить его в меню нельзя.
 */
function PhoneActions({ children }: { children: ReactNode }) {
  const items = flatActions(children)
  const buttons = items.filter(isButton)
  if (buttons.length < 2) return <>{children}</>

  const primary = buttons.find((button) => !button.props.variant || button.props.variant === 'default')
  const rest = buttons.filter((button) => button !== primary)
  const others = items.filter((item) => !isButton(item))
  // меню ради одного пункта хуже кнопки: второе действие остаётся кнопкой
  if (rest.length < 2) return <>{children}</>

  return (
    <>
      {primary}
      {others}
      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="outline" size="sm" className="head__menubtn" />}>
          {t('Действия')}
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="rowmenu__panel head__menu">
          {rest.map((button, index) => (
            <DropdownMenuItem
              key={index}
              className="rowmenu__item"
              disabled={button.props.disabled}
              onClick={button.props.onClick}
            >
              {button.props.children}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </>
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
  // на телефоне полоса прокручивается вбок (фаза 75), и выбранная
  // вкладка обязана быть на виду — иначе человек не знает, где он
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    box.current
      ?.querySelector<HTMLElement>('.tabs__tab[data-selected], .tabs__tab[aria-selected="true"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [value])

  return (
    <div ref={box}>
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
    </div>
  )
}

/**
 * Тон состояния: подтверждено и норма, ждёт и внимание, отклонено
 * и просрочено, нейтральная пометка, свой домен.
 *
 * Прежние имена (`ok`, `risk`, `brand`, `mute`, `teal`, `indigo`)
 * остаются псевдонимами, чтобы старые вызовы не сломались: бирюза
 * и индиго стали нейтральной пометкой и вторичным графитом.
 */
export type Tone =
  | 'good'
  | 'warn'
  | 'bad'
  | 'info'
  | 'neutral'
  | 'accent'
  | 'ok'
  | 'risk'
  | 'brand'
  | 'mute'
  | 'teal'
  | 'indigo'

/** Прежнее имя тона → имя нового языка. */
const TONE_ALIAS: Record<Tone, 'good' | 'warn' | 'bad' | 'info' | 'neutral' | 'accent'> = {
  good: 'good',
  ok: 'good',
  warn: 'warn',
  bad: 'bad',
  risk: 'bad',
  info: 'info',
  teal: 'info',
  neutral: 'neutral',
  mute: 'neutral',
  indigo: 'neutral',
  accent: 'accent',
  brand: 'accent',
}

export function toneOf(tone: Tone): 'good' | 'warn' | 'bad' | 'info' | 'neutral' | 'accent' {
  return TONE_ALIAS[tone] ?? 'neutral'
}

/**
 * Цветная полоса над карточкой — из прежнего языка. Карточка нового
 * языка отличается от полотна только цветом, и полосы у неё нет;
 * имя оставлено, пока экраны передают `accent`, и ничего не рисует.
 */
export type Accent = 'brand' | 'teal' | 'indigo' | 'ok' | 'warn' | 'risk'

export function accentClass(): string {
  return ''
}

/**
 * Чип состояния: подложка `*-bg`, текст `*`, пилюля высотой 22.
 * Внутри — `Badge` из реестра: своих чипов в разметке нет.
 */
export function Chip({
  tone = 'neutral',
  size,
  className,
  children,
}: {
  tone?: Tone
  /** мелкий — в строке таблицы и рядом с числом */
  size?: 'sm'
  className?: string
  children: ReactNode
}) {
  return (
    <Badge variant={toneOf(tone) as BadgeVariant} data-size={size} className={className}>
      {children}
    </Badge>
  )
}

/** Значения нет: null, пусто и прочерк из старых ответов — всё одно. */
function isEmptyValue(value: ReactNode): boolean {
  return value === null || value === undefined || value === '' || value === '—'
}

/**
 * Показатель: подпись капителью над числом, число крупно, подпись под
 * ним мелко. Один разбор на все ряды чисел — дашборды, карточка ученика,
 * профиль подбора.
 *
 * Тон красит само число: цветных полос над карточкой нет. Пустое
 * значение — слово «нет» серым, а не прочерк: прочерк читается как
 * поломка, слово — как факт. Действие стоит справа от числа текстом
 * или делает показатель кнопкой целиком (`to`, `onClick`); то и другое
 * сразу — нельзя, кнопка в кнопке не живёт.
 */
export function Kpi({
  value,
  label,
  note,
  tone,
  none,
  action,
  to,
  onClick,
}: {
  value: ReactNode
  label: string
  /** одна короткая строка под числом */
  note?: string
  tone?: Tone
  /** слово вместо пустого значения: «не сдавал»; по умолчанию «нет» */
  none?: string
  /** действие текстом справа от числа */
  action?: { label: string; to?: string; onClick?: () => void }
  /** куда ведёт показатель целиком */
  to?: string
  onClick?: () => void
}) {
  const colour = tone ? toneOf(tone) : 'neutral'
  const empty = isEmptyValue(value)
  const inner = (
    <>
      <span className="kpi__label t-caps">{label}</span>
      <span className="kpi__line">
        {empty ? (
          <span className="kpi__value kpi__value--none">{none ?? t('нет')}</span>
        ) : (
          <span className="kpi__value num">
            <Counter value={value} />
          </span>
        )}
        {action &&
          (action.to ? (
            <Link className="kpi__action" to={action.to}>
              {action.label}
            </Link>
          ) : (
            <button type="button" className="kpi__action" onClick={action.onClick}>
              {action.label}
            </button>
          ))}
      </span>
      {note && <span className="kpi__note">{note}</span>}
    </>
  )
  // `stat` — прежнее имя, на него смотрят браузерные сценарии
  const className = `kpi stat${colour === 'neutral' ? '' : ` kpi--${colour}`}`
  if (!action && to)
    return (
      <Link className={`${className} kpi--link`} to={to}>
        {inner}
      </Link>
    )
  if (!action && onClick)
    return (
      <button type="button" className={`${className} kpi--link`} onClick={onClick}>
        {inner}
      </button>
    )
  return <div className={className}>{inner}</div>
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

/** Одна фраза пустого состояния на весь интерфейс (фазы 80, 81). */
export const EMPTY_CARD = 'пока пусто'

/**
 * Строка «здесь пока ничего» внутри живой карточки.
 *
 * Каждый экран писал своё: «Заметок пока нет», «Пробников ещё не было»,
 * «Здесь пусто. Строки появятся, когда…» — восемьдесят семь разных фраз
 * об одном. Разные слова читаются как разные положения дел, а выглядят
 * как недоделка.
 *
 * Одна строка высотой со строку списка, а не абзац: слева фраза и кто
 * это ведёт, справа — что нажать (правило П-4). Роль может внести
 * сама — кнопка тут же; не может — «напомнить» тому, кто может.
 */
export function EmptyNote({
  what = EMPTY_CARD,
  who,
  action,
}: {
  /** чего именно нет: «пробников ещё не было» */
  what?: string
  /** кто это ведёт: «ведёт Кымбат», «вносит ученик» */
  who?: string
  /** что можно нажать прямо отсюда */
  action?: ReactNode
}) {
  return (
    <div className="emptynote">
      <span className="emptynote__what">
        {t(what)}
        {who && <span className="emptynote__who">{t(who)}</span>}
      </span>
      {action && <span className="emptynote__act">{action}</span>}
    </div>
  )
}

/**
 * Карточка одного блока данных: белая на полотне, без рамки и тени.
 *
 * Заголовок отвечает на вопрос «что это за число»: не «Прогресс»,
 * а «Готовность к подаче». Рядом с ним счётчик чипом и действие справа.
 * Описание — не больше одной строки, всё длинное уходит в подсказку
 * по наведению.
 */
export function DataCard({
  title,
  note,
  hint,
  right,
  count,
  className,
  empty,
  emptyAction,
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
  /** прежняя цветная полоса сверху: принимается, но не рисуется */
  accent?: Accent
  /** место карточки в раскладке экрана — `grid-area` задаёт экран */
  className?: string
  /**
   * Карточке нечего показать: она сворачивается в одну строку — название,
   * состояние словами («дедлайнов нет», общее «пока пусто») и действие
   * кнопкой в строке. Растянутая карточка с пустой таблицей занимала
   * место живых.
   */
  empty?: string | boolean
  /** что можно сделать прямо из свёрнутой строки: «Внести», «Напомнить задачей» */
  emptyAction?: ReactNode
  children?: ReactNode
}) {
  if (empty)
    return (
      <section className={`card datacard datacard--folded${className ? ` ${className}` : ''}`}>
        <span className="datacard__title">{title}</span>
        <span className="datacard__empty">{empty === true ? t(EMPTY_CARD) : empty}</span>
        {emptyAction && <span className="datacard__emptyact">{emptyAction}</span>}
      </section>
    )
  return (
    <section className={`card card-pad datacard${className ? ` ${className}` : ''}`}>
      <header className="datacard__head">
        <span className="datacard__title t-card">
          {title}
          {hint && <Hint text={hint} />}
        </span>
        {count !== undefined && <Chip className="num">{count}</Chip>}
        {right}
      </header>
      {note && <p className="datacard__note">{note}</p>}
      {children}
    </section>
  )
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
        <Chip className="num">{rows.length}</Chip>
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
  return (
    <Chip tone="bad" className="badge--line">
      {error instanceof Error ? error.message : 'Ошибка загрузки'}
    </Chip>
  )
}
