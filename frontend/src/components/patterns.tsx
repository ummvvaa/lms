/**
 * Общий визуальный язык кабинета.
 *
 * Крупная карточка раздела, ряд показателей, строка списка, карточка
 * каталога, сегментный переключатель, полоса-подсказка и приглушённый
 * раздел. Всё это повторяется на десятках экранов, и собрано оно
 * здесь один раз: иначе у каждого экрана будет своя карточка, своя
 * строка и своя геометрия.
 *
 * Графика вместо персонажа — там же, ниже: герб школы водяным знаком
 * и одна фигура из палитры раздела. Никаких изображений: рисунок
 * векторный, перекрашивается вместе с темой и обрезается краем карточки.
 */
import {
  Children,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react'
import { Link } from 'react-router-dom'
import Icon, { type IconName } from '../layout/icons'
import { Button } from './ui/button'
import { toneOf, type Tone } from './ui'
import { t } from '../i18n'
import './patterns.css'

/** Цвет раздела. Подбор и план — оранжевый, подготовка — бирюза,
 *  стипендии — индиго, портфолио — тёплый графит. */
export type HeroTone = 'brand' | 'teal' | 'indigo' | 'ink'

/** Какая фигура лежит в правой части карточки. Больше двух фигур
 *  на карточку не бывает: герб плюс одна из этих. */
export type HeroFigure = 'rings' | 'arcs' | 'dots' | 'none'

/**
 * Герб школы водяным знаком: щит, повторяющий очертания настоящего.
 *
 * Векторный, а не файл логотипа: файл оранжевый и на оранжевой заливке
 * превратился бы в пятно, а этот рисуется цветом фактуры и в тёмной
 * теме гаснет вместе с ней.
 */
function Shield() {
  return <path d="M132 26 190 47v58c0 38-27 62-58 71-31-9-58-33-58-71V47z" fill="var(--hero-mark)" />
}

/** Фигура раздела: кольца, дуги или сетка точек. */
function Figure({ kind }: { kind: HeroFigure }) {
  if (kind === 'none') return null
  if (kind === 'dots')
    return (
      <g fill="var(--hero-figure)">
        {Array.from({ length: 7 }, (_, row) =>
          Array.from({ length: 7 }, (_, col) => (
            <circle key={`${row}-${col}`} cx={64 + col * 26} cy={30 + row * 26} r="2.4" />
          )),
        )}
      </g>
    )
  if (kind === 'arcs')
    return (
      <g fill="none" stroke="var(--hero-figure)" strokeWidth="1.5">
        <path d="M20 200C20 96 104 12 208 12" />
        <path d="M62 200C62 119 128 53 209 53" />
        <path d="M104 200C104 143 150 97 207 97" />
      </g>
    )
  return (
    <g fill="none" stroke="var(--hero-figure)" strokeWidth="1.5">
      <circle cx="132" cy="96" r="86" />
      <circle cx="132" cy="96" r="60" />
      <circle cx="132" cy="96" r="34" />
    </g>
  )
}

/**
 * Правая треть крупной карточки.
 *
 * Обрезается краем — так рисунок читается как продолжение чего-то
 * большего, а не как картинка, вписанная в рамку. Текста и кнопок
 * не касается: они лежат в своей колонке.
 */
function HeroDecor({ figure, glyph }: { figure: HeroFigure; glyph?: string }) {
  return (
    <div className="hero__decor" aria-hidden="true">
      <svg viewBox="0 0 240 200" preserveAspectRatio="xMidYMid slice">
        <Figure kind={figure} />
        {glyph ? (
          <text className="hero__glyph" x="132" y="150" textAnchor="middle">
            {glyph}
          </text>
        ) : (
          <Shield />
        )}
      </svg>
    </div>
  )
}

/**
 * Крупная карточка раздела.
 *
 * Опознавательный знак кабинета: одна на экран, сверху, на сплошном
 * цвете. Стоит там, где раздел открывается впервые и надо объяснить,
 * зачем он, — а не над каждым списком подряд.
 */
export function Hero({
  tone = 'brand',
  eyebrow,
  title,
  note,
  chips,
  action,
  aside,
  figure = 'rings',
  glyph,
  compact = false,
  className,
  children,
}: {
  tone?: HeroTone
  /** мелкая надпись над заголовком */
  eyebrow?: ReactNode
  title: ReactNode
  /** одна-две строки о том, зачем раздел */
  note?: ReactNode
  /** факты чипами: сколько занимает, что внутри, сколько записей */
  chips?: ReactNode
  /** кнопка действия — белым по цвету раздела */
  action?: ReactNode
  /** правая колонка внутри карточки: плитки-числа плана */
  aside?: ReactNode
  figure?: HeroFigure
  /** крупная буква или число фоном вместо герба */
  glyph?: string
  /** узкий вариант: карточка стоит в ряду с другой */
  compact?: boolean
  /** свой класс — там, где карточка тянется по высоте соседней */
  className?: string
  children?: ReactNode
}) {
  return (
    <section
      className={`hero hero--${tone}${compact ? ' hero--compact' : ''}${className ? ` ${className}` : ''}`}
    >
      <HeroDecor figure={figure} glyph={glyph} />
      <div className="hero__body">
        <div className="hero__text">
          {eyebrow && <span className="hero__eyebrow">{eyebrow}</span>}
          <h2 className="hero__title">{title}</h2>
          {note && <p className="hero__note">{note}</p>}
          {chips && <div className="hero__chips">{chips}</div>}
          {children}
          {action && <div className="hero__action">{action}</div>}
        </div>
        {aside && <div className="hero__aside">{aside}</div>}
      </div>
    </section>
  )
}

/** Чип внутри крупной карточки: подложка от её собственного фона. */
export function HeroChip({ children, strong = false }: { children: ReactNode; strong?: boolean }) {
  return <span className={`hero__chip${strong ? ' hero__chip--strong' : ''}`}>{children}</span>
}

/** Плитка-число внутри крупной карточки. */
export function HeroTile({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div className="hero__tile">
      <div className="num hero__tilevalue">{value}</div>
      <div className="hero__tilelabel">{label}</div>
    </div>
  )
}

/** Полоса прогресса внутри крупной карточки — на своём фоне. */
export function HeroBar({ percent }: { percent: number }) {
  const width = Math.max(0, Math.min(100, percent))
  return (
    <div className="hero__bar">
      <i style={{ width: `${width}%` }} />
    </div>
  )
}

/** Цвет мягкой плитки под иконкой — тон состояния, прежние имена — псевдонимы. */
export type TileTone = Tone

/** Квадратная плитка со скруглением и мягкой заливкой, внутри иконка. */
export function Tile({
  icon,
  tone = 'accent',
  size = 'md',
}: {
  icon: IconName
  tone?: TileTone
  size?: 'sm' | 'md' | 'lg'
}) {
  return (
    <span className={`tile tile--${toneOf(tone)} tile--${size}`} aria-hidden="true">
      <Icon name={icon} size={size === 'lg' ? 20 : size === 'sm' ? 14 : 16} />
    </span>
  )
}

/**
 * Ряд показателей (`Kpi`): четыре в ряд на ноутбуке, два на два на телефоне.
 *
 * Число плиток уходит в разметку (`data-count`): по нему CSS решает, как делить
 * ряд. Четыре плитки в узкой колонке раньше вставали «три плюс одна» — одинокая
 * плитка под рядом читается как отдельный блок и ломает сетку (правило П-5).
 */
export function StatRow({ children }: { children: ReactNode }) {
  return (
    <div className="statrow" data-count={Children.count(children)}>
      {children}
    </div>
  )
}

/**
 * Сегментный переключатель: серая подложка, выбранный сегмент белый.
 *
 * Там, где вариантов немного и они в один ряд: секции экзамена,
 * категории ресурсов, вид календаря. Вкладок здесь быть не может —
 * вкладки делят экран, а сегменты — один и тот же список.
 */
export function Segmented<T extends string>({
  value,
  onChange,
  items,
  label,
}: {
  value: T
  onChange: (next: T) => void
  items: { value: T; label: ReactNode; icon?: IconName }[]
  /** подпись группы для читалки экрана */
  label?: string
}) {
  return (
    <div className="segrow" role="group" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          className={`segrow__item${item.value === value ? ' segrow__item--on' : ''}`}
          aria-pressed={item.value === value}
          onClick={() => onChange(item.value)}
        >
          {item.icon && <Icon name={item.icon} size={14} />}
          {item.label}
        </button>
      ))}
    </div>
  )
}

/** Список строк: разделены тонкой линией, а не отдельными карточками. */
export function Rows({ children }: { children: ReactNode }) {
  return <div className="rowlist">{children}</div>
}

/** Сколько строк списка видно сразу; остальное — под «Показать все». */
export const LIST_LIMIT = 5

/**
 * Подвал длинного списка: слева «Показаны N из M», справа «Показать все M».
 *
 * Один на списки и таблицы: раскрытие на месте и в карточке, и под
 * таблицей выглядит одинаково.
 */
export function ListFoot({
  shown,
  total,
  open,
  onToggle,
  to,
}: {
  shown: number
  total: number
  open?: boolean
  onToggle?: () => void
  /** полный экран вместо раскрытия на месте */
  to?: string
}) {
  return (
    <div className="showall">
      <span className="showall__count">
        {t('Показаны')} {shown} {t('из')} {total}
      </span>
      {to ? (
        <Link className="showall__more" to={to}>
          {t('Показать все')} {total}
        </Link>
      ) : (
        onToggle && (
          <button type="button" className="showall__more" aria-expanded={open} onClick={onToggle}>
            {open ? t('Свернуть') : `${t('Показать все')} ${total}`}
          </button>
        )
      )}
    </div>
  )
}

/**
 * Длинный список на дашборде: пять строк и подвал «Показаны 5 из 12 ·
 * Показать все 12».
 *
 * Раскрывается на месте: увести человека на другой экран ради шестой
 * строки — потерять место, где он был. Ссылка на полный экран, если она
 * есть, встаёт в подвал вместо раскрытия (`to`).
 */
export function ShowAll({
  children,
  limit = LIST_LIMIT,
  to,
}: {
  children: ReactNode
  limit?: number
  /** полный экран: подвал ведёт туда, а не раскрывает список */
  to?: string
}) {
  const [open, setOpen] = useState(false)
  const items = Children.toArray(children)
  if (items.length <= limit) return <>{items}</>
  const shown = open ? items : items.slice(0, limit)
  return (
    <>
      {shown}
      <ListFoot
        shown={shown.length}
        total={items.length}
        open={open}
        onToggle={() => setOpen(!open)}
        to={to}
      />
    </>
  )
}

/** Инициалы для аватара: первые буквы двух первых слов имени. */
export function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase())
    .join('')
}

/** Значения нет: null, пусто и прочерк из старых ответов — всё одно. */
function isEmptyValue(value: ReactNode): boolean {
  return value === null || value === undefined || value === '' || value === '—'
}

/**
 * Строка данных: лид слева (инициалы, иконка или число), заголовок
 * и подпись, справа значение, время, кнопки в строке и шеврон.
 *
 * Так устроены ближайшие события, следующие шаги, готовность
 * документов, очередь и ученики группы. Прочерка в позиции значения
 * строка не рисует никогда: пустое значение — слово «нет» серым
 * (`none`), а если ни слова, ни кнопки не дано — строки нет вовсе.
 *
 * Строка целиком становится ссылкой или кнопкой, когда переход есть,
 * а справа ничего нажимаемого: иначе шеврон нажимается отдельно —
 * кнопка в кнопке не живёт.
 */
export function Row({
  icon,
  tone = 'neutral',
  lead,
  avatar,
  title,
  note,
  right,
  value,
  none,
  when,
  acts,
  chev = false,
  to,
  onOpen,
  openLabel,
  muted = false,
}: {
  icon?: IconName
  tone?: TileTone
  /** вместо плитки — своё содержимое: галочка, дата, кружок */
  lead?: ReactNode
  /** имя человека: лид — его инициалы на серой подложке */
  avatar?: string
  title: ReactNode
  note?: ReactNode
  /** чип или своё содержимое справа */
  right?: ReactNode
  /** значение справа крупно; пустое — см. `none` */
  value?: ReactNode
  /** слово вместо пустого значения: `true` — «нет», строка — своё */
  none?: string | boolean
  /** время или дата справа мелко */
  when?: ReactNode
  /** кнопки в строке */
  acts?: ReactNode
  /** шеврон без своего действия: строкой управляет родитель */
  chev?: boolean
  /** куда ведёт строка */
  to?: string
  onOpen?: () => void
  openLabel?: string
  muted?: boolean
}) {
  const hasValueSlot = value !== undefined
  const empty = hasValueSlot && isEmptyValue(value)
  const noneWord = none === true ? t('нет') : none
  // пустое значение без слова и без кнопки — строки нет: прочерка не бывает
  if (empty && !noneWord && !acts && !right) return null

  const leadNode =
    lead ??
    (avatar ? (
      <span className="rowline__lead" aria-hidden="true">
        {initials(avatar)}
      </span>
    ) : (
      icon && <Tile icon={icon} tone={tone} />
    ))
  const valueNode = !hasValueSlot ? null : empty ? (
    noneWord && <span className="rowline__none">{noneWord}</span>
  ) : (
    <span className="rowline__value num">{value}</span>
  )
  // переход по всей строке — только когда справа нечего нажимать
  const whole = (to !== undefined || onOpen !== undefined) && !acts && !right
  const chevron = (
    <span className="rowline__chev" aria-hidden="true">
      <Icon name="chevronRight" size={16} />
    </span>
  )
  const inner = (
    <>
      {leadNode}
      <span className="rowline__text">
        <span className="rowline__title">{title}</span>
        {note && <span className="rowline__note">{note}</span>}
      </span>
      {right}
      {valueNode}
      {when && <span className="rowline__when">{when}</span>}
      {acts && <span className="rowline__acts">{acts}</span>}
      {whole || chev ? chevron : null}
      {!whole && to !== undefined && (
        <Link className="rowline__open" to={to} aria-label={openLabel ?? t('Открыть')}>
          <Icon name="chevronRight" size={16} />
        </Link>
      )}
      {!whole && to === undefined && onOpen && (
        <button
          type="button"
          className="rowline__open"
          onClick={onOpen}
          aria-label={openLabel ?? t('Открыть')}
        >
          <Icon name="chevronRight" size={16} />
        </button>
      )}
    </>
  )
  const className = `rowline${muted ? ' rowline--muted' : ''}${whole ? ' rowline--link' : ''}`
  if (whole && to !== undefined)
    return (
      <Link className={className} to={to}>
        {inner}
      </Link>
    )
  // имя кнопки — сам текст строки: подпись перехода здесь только затемнила бы его
  if (whole)
    return (
      <button type="button" className={className} onClick={onOpen}>
        {inner}
      </button>
    )
  return <div className={className}>{inner}</div>
}

/**
 * Карточка каталога: стипендии, ресурсы, вузы, тесты.
 *
 * Сверху цветная область с крупной иконкой, ниже заголовок с переносом,
 * серый подзаголовок, чипы, сетка два на два и ссылка через тонкую
 * линию. Заголовок переносится, а не режется многоточием: обрезанное
 * название вуза человеку ничего не говорит.
 */
export function CatalogCard({
  icon,
  tone = 'accent',
  title,
  subtitle,
  chips,
  facts,
  footer,
  onFooter,
  favorite,
  onFavorite,
  favoriteLabel,
}: {
  icon: IconName
  tone?: TileTone
  title: ReactNode
  subtitle?: ReactNode
  chips?: ReactNode
  /** сетка два на два: значение и подпись под ним */
  facts?: { value: ReactNode; label: string; tone?: 'ok' | 'warn' | 'risk' }[]
  footer?: string
  onFooter?: () => void
  /** сердечко в правом верхнем углу: контурное, заполняется нажатием */
  favorite?: boolean
  onFavorite?: () => void
  favoriteLabel?: string
}) {
  return (
    <article className={`catcard catcard--${toneOf(tone)}`}>
      <div className="catcard__top">
        <Icon name={icon} size={26} />
        {onFavorite && (
          <button
            type="button"
            className={`catcard__heart${favorite ? ' catcard__heart--on' : ''}`}
            onClick={onFavorite}
            aria-pressed={favorite}
            aria-label={favoriteLabel ?? t('В избранное')}
          >
            <Icon name="heart" size={16} />
          </button>
        )}
      </div>
      <div className="catcard__body">
        <h3 className="catcard__title">{title}</h3>
        {subtitle && <p className="catcard__sub">{subtitle}</p>}
        {chips && <div className="catcard__chips">{chips}</div>}
        {facts && facts.length > 0 && (
          <div className="catcard__facts">
            {facts.map((fact, index) => (
              <div key={index} className="catcard__fact">
                <div className={`catcard__factvalue${fact.tone ? ` catcard__factvalue--${fact.tone}` : ''}`}>
                  {fact.value}
                </div>
                <div className="catcard__factlabel">{fact.label}</div>
              </div>
            ))}
          </div>
        )}
      </div>
      {footer && (
        <button type="button" className="catcard__foot" onClick={onFooter}>
          {footer}
          <Icon name="chevronRight" size={13} />
        </button>
      )}
    </article>
  )
}

/**
 * Полоса-подсказка над содержимым.
 *
 * Появляется, когда ученик пропустил шаг. Закрывается крестиком
 * и в этой сессии не возвращается: подсказка, которую нельзя убрать,
 * через день читается как часть шапки.
 */
export function TipBar({
  text,
  action,
  onAction,
  onClose,
}: {
  text: string
  action?: string
  onAction?: () => void
  onClose?: () => void
}) {
  return (
    <div className="tipbar">
      <Icon name="bulb" size={15} />
      <span className="tipbar__text">{text}</span>
      {action && onAction && (
        <button type="button" className="tipbar__action" onClick={onAction}>
          {action}
        </button>
      )}
      {onClose && (
        <button type="button" className="tipbar__close" onClick={onClose} aria-label={t('Закрыть')}>
          <Icon name="close" size={14} />
        </button>
      )}
    </div>
  )
}

/**
 * Раздел, который откроется позже.
 *
 * Содержимое видно, но приглушено и не нажимается, а сверху — карточка
 * с объяснением, что для этого сделать. Пустой экран не отличить
 * от поломки, а отказ без объяснения — от несправедливости.
 *
 * К чужим доменам приём не относится: там раздел отбивается без
 * объяснений, потому что дело не в шагах ученика, а в данных других
 * детей (инвариант №7).
 */
export function Dimmed({
  title,
  what,
  action,
  onAction,
  tone = 'ink',
  children,
}: {
  title: string
  what: string
  action?: string
  onAction?: () => void
  tone?: HeroTone
  children: ReactNode
}) {
  return (
    <div className="dimmed">
      <Hero
        tone={tone}
        eyebrow={t('Пока закрыто')}
        title={title}
        note={what}
        figure="arcs"
        action={action && onAction && <Button onClick={onAction}>{action}</Button>}
      />
      <div className="dimmed__veil" aria-hidden="true">
        {children}
      </div>
    </div>
  )
}

/** Один сюжет карусели: те же поля, что у крупной карточки раздела. */
export interface CarouselSlide {
  key: string
  tone: HeroTone
  eyebrow: ReactNode
  title: ReactNode
  note?: ReactNode
  action?: ReactNode
  figure?: HeroFigure
}

/** Через сколько миллисекунд карусель листается сама. */
export const CAROUSEL_INTERVAL = 7000

/**
 * Карусель крупных карточек (фаза 49).
 *
 * Не украшение: каждый сюжет — приглашение закрыть одно незакрытое
 * место. Листается сама раз в несколько секунд и останавливается под
 * курсором — иначе карточка уезжает ровно тогда, когда её начали читать.
 * Пустой список сюда не приходит вовсе: без сюжетов карусели нет,
 * и её место занимает соседний блок.
 */
export function Carousel({ slides, className }: { slides: CarouselSlide[]; className?: string }) {
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  // палец, ведущий слайд: на телефоне карусель листают им, а не стрелками
  // (стрелки там спрятаны). Живого перетаскивания нет намеренно —
  // человеку нужен следующий сюжет, а не резинка под пальцем
  const swipeFrom = useRef<number | null>(null)
  const count = slides.length
  const current = count > 0 ? index % count : 0

  useEffect(() => {
    if (paused || count < 2) return
    const timer = window.setInterval(() => setIndex((n) => (n + 1) % count), CAROUSEL_INTERVAL)
    return () => window.clearInterval(timer)
  }, [paused, count])

  if (count === 0) return null
  const go = (step: number) => setIndex((n) => (n + step + count) % count)

  /** Свайп засчитывается от 40 пикселей: короче — это промах по кнопке. */
  const SWIPE = 40
  const swipeStart = (event: ReactPointerEvent) => {
    swipeFrom.current = event.clientX
  }
  const swipeEnd = (event: ReactPointerEvent) => {
    if (swipeFrom.current === null) return
    const moved = event.clientX - swipeFrom.current
    swipeFrom.current = null
    if (Math.abs(moved) >= SWIPE) go(moved < 0 ? 1 : -1)
  }

  return (
    <div
      className={`caro${className ? ` ${className}` : ''}`}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <div
        className="caro__track"
        style={{ transform: `translateX(-${current * 100}%)` }}
        onPointerDown={swipeStart}
        onPointerUp={swipeEnd}
      >
        {slides.map((slide) => (
          <div key={slide.key} className="caro__slide">
            <Hero
              tone={slide.tone}
              eyebrow={slide.eyebrow}
              title={slide.title}
              note={slide.note}
              action={slide.action}
              figure={slide.figure ?? 'rings'}
              className="caro__hero"
            />
          </div>
        ))}
      </div>
      {count > 1 && (
        <>
          <div className="caro__dots">
            {slides.map((slide, position) => (
              <button
                key={slide.key}
                type="button"
                className={`caro__dot${position === current ? ' caro__dot--on' : ''}`}
                aria-label={`${t('Сюжет')} ${position + 1}`}
                aria-current={position === current}
                onClick={() => setIndex(position)}
              />
            ))}
          </div>
          <button
            type="button"
            className="caro__arrow caro__arrow--prev"
            onClick={() => go(-1)}
            aria-label={t('Предыдущий')}
          >
            <Icon name="chevronLeft" size={15} />
          </button>
          <button
            type="button"
            className="caro__arrow caro__arrow--next"
            onClick={() => go(1)}
            aria-label={t('Следующий')}
          >
            <Icon name="chevronRight" size={15} />
          </button>
        </>
      )}
    </div>
  )
}
