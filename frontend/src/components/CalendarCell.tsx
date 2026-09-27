/**
 * Ячейка месяца.
 *
 * Образец — сетка в `docs/ui/language/Calendar.html` и ячейка дня из
 * `docs/ui/reference-src/src/screens/student.js`: клетка высотой
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
import { t } from '../i18n'

export type CalendarCellTone = 'accent' | 'good' | 'warn' | 'bad' | 'info' | 'neutral'

export interface CalendarCellEvent {
  title: string
  tone?: CalendarCellTone
}

export type CalendarCellView = 'full' | 'compact' | 'phone'

/** Строчек событий в клетке — не больше двух, остальное словом «ещё N». */
const MAX_LINES = 2

/** Точек под числом на телефоне — не больше трёх: четвёртая уже не считается. */
const MAX_DOTS = 3

export default function CalendarCell({
  day,
  view = 'full',
  today = false,
  outside = false,
  picked = false,
  events = [],
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
        className={`calcell${picked ? ' calcell--picked' : ''}${extra}`}
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
  }${extra}`
  if (day === null) return <span className={`${classes} calcell--empty`} aria-hidden="true" />

  const shown = events.slice(0, MAX_LINES)
  const rest = events.length - shown.length
  const inner = (
    <>
      <span className="calcell__day t-note num">{day}</span>
      {shown.map((event, index) => (
        <span
          key={index}
          className={`calcell__event calcell__event--${event.tone ?? 'neutral'}`}
          title={event.title}
        >
          <i className="calcell__tone" aria-hidden="true" />
          <span className="calcell__eventtitle">{event.title}</span>
        </span>
      ))}
      {rest > 0 && (
        <span className="calcell__more t-note">
          {t('ещё')} {rest}
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
