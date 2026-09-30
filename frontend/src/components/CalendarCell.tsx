/**
 * Ячейка месяца.
 *
 * Образец — сетка в `docs/ui/language/Calendar.html` и ячейка дня из
 * `docs/ui/reference.html`: клетка высотой
 * `--cal-cell-h` на подложке `--surface-2`, номер дня подписью `.t-note`,
 * сегодня — номер в кружке `--accent`, день соседнего месяца — `--ink-4`,
 * события — строчки с точкой тона, лишние — словом «ещё N».
 *
 * У карточки календаря на главной два прежних вида, и они живут здесь же:
 * `compact` — кружок с числом и точкой в карточке календаря ноутбука,
 * `phone` — кнопка с числом и точками по числу событий. Их разметка
 * и классы (`calcard__day*`, `calcell*`) не меняются: по ним смотрят
 * браузерные проверки и стили карточки в `home.css`.
 *
 * `day` пустой — пустая клетка на месте дня соседней недели.
 */
import { tn } from '../i18n'

export type CalendarCellTone = 'accent' | 'good' | 'warn' | 'bad' | 'info' | 'neutral'

export interface CalendarCellEvent {
  title: string
  tone?: CalendarCellTone
}

export type CalendarCellView = 'full' | 'compact' | 'phone'

/** Отметок событий в клетке месяца — не больше четырёх, дальше «+N».
 *  Названий в клетке нет: они читаются полными строками по нажатию
 *  на день (решение владельца, 27.09.2026). */
const MAX_MARKS = 4

/** Точек под числом на телефоне — не больше трёх: четвёртая уже не считается. */
const MAX_DOTS = 3

export default function CalendarCell({
  day,
  view = 'full',
  today = false,
  outside = false,
  picked = false,
  events = [],
  work = [],
  onPick,
  label,
  className,
}: {
  /** число месяца; без него — пустая клетка */
  day: number | null
  view?: CalendarCellView
  today?: boolean
  /** день соседнего месяца */
  outside?: boolean
  /** выбранный день */
  picked?: boolean
  events?: CalendarCellEvent[]
  /** подписи работ дня (СОР, СОЧ): день подсвечен, подпись видна в клетке */
  work?: string[]
  onPick?: () => void
  /** подпись для читалки, например «15 октября, среда» */
  label?: string
  className?: string
}) {
  const extra = className ? ` ${className}` : ''

  if (view === 'compact') {
    if (day === null) return <span />
    return (
      <span
        className={`num calcard__day${today ? ' calcard__day--today' : ''}${
          events.length > 0 ? ' calcard__day--marked' : ''
        }${extra}`}
      >
        {day}
      </span>
    )
  }

  if (view === 'phone') {
    if (day === null) return <span className="calcell" />
    const dots = Math.min(events.length, MAX_DOTS)
    return (
      <button
        type="button"
        className={`calcell${picked ? ' calcell--picked' : ''}${work.length ? ' calcell--work' : ''}${extra}`}
        aria-pressed={picked}
        aria-label={label}
        onClick={onPick}
      >
        <span className={`num calcell__day${today ? ' calcell__day--today' : ''}`}>{day}</span>
        <span className="calcell__dots" aria-hidden="true">
          {Array.from({ length: dots }, (_, dot) => (
            <i key={dot} />
          ))}
        </span>
      </button>
    )
  }

  const classes = `calcell calcell--full${today ? ' calcell--today' : ''}${outside ? ' calcell--outside' : ''}${
    picked ? ' calcell--picked' : ''
  }${work.length ? ' calcell--work' : ''}${extra}`
  if (day === null) return <span className={`${classes} calcell--empty`} aria-hidden="true" />

  const shown = events.slice(0, MAX_MARKS)
  const rest = events.length - shown.length
  const inner = (
    <>
      <span className="calcell__day t-note num">{day}</span>
      {work.length > 0 && (
        <span className="calcell__work">
          {work.slice(0, 2).map((caption) => (
            <span key={caption} className="calcell__worktitle t-note">
              {caption}
            </span>
          ))}
          {work.length > 2 && <span className="calcell__more t-note num">+{work.length - 2}</span>}
        </span>
      )}
      {events.length > 0 && (
        <span className="calcell__marks" aria-label={tn(events.length, '{n} событие|{n} события|{n} событий')}>
          {shown.map((event, index) => (
            <i key={index} className={`calcell__mark calcell__event--${event.tone ?? 'neutral'}`} title={event.title} />
          ))}
          {rest > 0 && <span className="calcell__more t-note num">+{rest}</span>}
        </span>
      )}
    </>
  )

  if (onPick) {
    return (
      <button type="button" className={classes} aria-pressed={picked} aria-label={label} onClick={onPick}>
        {inner}
      </button>
    )
  }
  return (
    <div className={classes} aria-label={label}>
      {inner}
    </div>
  )
}
