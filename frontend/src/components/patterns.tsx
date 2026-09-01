/**
 * Общий визуальный язык кабинета (фаза 48).
 *
 * Крупная карточка раздела, карточка-число, строка списка, карточка
 * каталога, ряд чипов-переключателей, полоса-подсказка и приглушённый
 * раздел. Всё это повторяется на десяти экранах ученика, и собрано оно
 * здесь один раз: иначе через три фазы у каждого экрана будет своя
 * карточка, своя строка и своя геометрия.
 *
 * Графика вместо персонажа — там же, ниже: герб школы водяным знаком
 * и одна фигура из палитры раздела. Никаких изображений: рисунок
 * векторный, перекрашивается вместе с темой и обрезается краем карточки.
 */
import type { ReactNode } from 'react'
import Icon, { type IconName } from '../layout/icons'
import { Button } from './ui/button'
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

/** Цвет мягкой плитки под иконкой. */
export type TileTone = 'brand' | 'teal' | 'indigo' | 'ok' | 'warn' | 'risk' | 'mute'

/** Квадратная плитка со скруглением и мягкой заливкой, внутри иконка. */
export function Tile({
  icon,
  tone = 'brand',
  size = 'md',
}: {
  icon: IconName
  tone?: TileTone
  size?: 'sm' | 'md' | 'lg'
}) {
  return (
    <span className={`tile tile--${tone} tile--${size}`} aria-hidden="true">
      <Icon name={icon} size={size === 'lg' ? 20 : size === 'sm' ? 14 : 16} />
    </span>
  )
}

/**
 * Карточка-число: плитка с иконкой слева, подпись и число справа.
 *
 * Порядок один на весь проект — подпись сверху, число снизу: тот же,
 * что у `Kpi` и `Metric` с фазы 33. Стоят рядами по три-четыре
 * и одинаковой высоты, поэтому у карточки нет своей высоты.
 */
export function StatCard({
  icon,
  tone = 'brand',
  label,
  value,
  note,
  onClick,
}: {
  icon: IconName
  tone?: TileTone
  label: string
  value: ReactNode
  /** одна короткая строка под числом */
  note?: string
  onClick?: () => void
}) {
  const inside = (
    <>
      <Tile icon={icon} tone={tone} size="lg" />
      <span className="stat__text">
        <span className="stat__label">{label}</span>
        <span className="num stat__value">{value}</span>
        {note && <span className="stat__note">{note}</span>}
      </span>
    </>
  )
  if (onClick)
    return (
      <button type="button" className="card stat stat--click" onClick={onClick}>
        {inside}
      </button>
    )
  return <div className="card stat">{inside}</div>
}

/** Ряд карточек-чисел: три-четыре в строке, одинаковой высоты. */
export function StatRow({ children }: { children: ReactNode }) {
  return <div className="statrow">{children}</div>
}

/**
 * Ряд чипов-переключателей без общего контейнера.
 *
 * Там, где вариантов много и они в один ряд: секции экзамена,
 * категории ресурсов, форматы тестов. Вкладок здесь быть не может —
 * их подложка переезжает, а десять переездов подряд читаются как рябь.
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

/**
 * Строка списка: плитка слева, заголовок и подпись, справа значение
 * или круглая кнопка со стрелкой.
 *
 * Так устроены ближайшие события, следующие шаги, готовность
 * документов, уведомления и меню профиля.
 */
export function Row({
  icon,
  tone = 'mute',
  lead,
  title,
  note,
  right,
  onOpen,
  openLabel,
  muted = false,
}: {
  icon?: IconName
  tone?: TileTone
  /** вместо плитки — своё содержимое: галочка, дата, кружок */
  lead?: ReactNode
  title: ReactNode
  note?: ReactNode
  /** значение или чип справа */
  right?: ReactNode
  /** переход по строке: рисуется круглая кнопка со стрелкой */
  onOpen?: () => void
  openLabel?: string
  muted?: boolean
}) {
  return (
    <div className={`rowline${muted ? ' rowline--muted' : ''}`}>
      {lead ?? (icon && <Tile icon={icon} tone={tone} />)}
      <span className="rowline__text">
        <span className="rowline__title">{title}</span>
        {note && <span className="rowline__note">{note}</span>}
      </span>
      {right}
      {onOpen && (
        <button type="button" className="roundarrow" onClick={onOpen} aria-label={openLabel ?? t('Открыть')}>
          <Icon name="chevronRight" size={14} />
        </button>
      )}
    </div>
  )
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
  tone = 'brand',
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
    <article className={`catcard catcard--${tone}`}>
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
