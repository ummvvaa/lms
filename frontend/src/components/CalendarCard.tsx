/**
 * Календарь-карточка: сетка месяца и панель событий на белой карточке языка.
 *
 * На ноутбуке и планшете — ровно то, что построено фазами 49 и 50:
 * слева сетка месяца, справа белая панель ближайших. Ничего не менялось.
 *
 * На телефоне (фаза 51) сетка месяца в 390 пикселей превращается
 * в семь колонок по сорок с числами, в которые не попасть пальцем,
 * а панель рядом не помещается вовсе. Поэтому здесь два режима
 * с переключателем в шапке карточки:
 *
 *   • «Лента» — по умолчанию: только будущее, по месяцам, крупной
 *     строкой с числом и днём недели. Первым делом человек с телефона
 *     смотрит «что ближайшее», а не «какое сегодня число»;
 *   • «Месяц» — та же сетка, но крупная: ячейка не ниже 34px, число
 *     в кружке 24px, под числом точки по числу событий дня, а под
 *     сеткой — панель выбранного дня.
 *
 * Выбранный режим переживает заходы: он лежит в `localStorage` ключом
 * с ролью, потому что у ученика и у директора это разные привычки
 * и одно устройство на семью — обычное дело.
 */
import { useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import Icon from '../layout/icons'
import { usePhone } from '../phone'
import { t, tn } from '../i18n'
import { Row, Rows, Segmented } from './patterns'
import { Button } from './ui/button'
import CalendarCell from './CalendarCell'
import { formatDayMonthShort, formatYearMonth, monthName, weekdayName } from '../lib/format'
import { useTrack } from '../usage/context'
import './calendar-card.css'

/** Дни недели от понедельника на языке интерфейса: «Пн», «Дс», «Mon». */
export const weekdays = (): string[] => [0, 1, 2, 3, 4, 5, 6].map((index) => weekdayName(index))

/* Месяц в строке события сокращён — «27 сент.», а не «27 сентября»:
   дата стоит своей колонкой перед названием, и полное слово уносило
   строку на два ряда. */
/** Дата события коротко: «15 окт.» или «Сегодня». */
export function shortDate(iso: string, today: string): string {
  if (iso === today) return t('Сегодня')
  return formatDayMonthShort(iso)
}

export function isoOf(year: number, month: number, day: number): string {
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

export interface CalendarCardEvent {
  date: string
  title: string
  /** подпись под названием на ноутбуке: чем событие является и кого касается */
  note?: ReactNode
  /** подпись в телефонной ленте. Не задана — берётся `note`.
   *  Разные они там, где в подписи стоит дата: в ленте дата уже слева */
  feedNote?: ReactNode
  /** метка справа — например «ждёт проверки» */
  right?: ReactNode
  /** куда ведёт строка; без адреса строка не открывается */
  link?: string
}

/** Сколько строк ленты видно сразу: больше не помещается в первый экран. */
const FEED_ROWS = 4

type Mode = 'feed' | 'month'

function storedMode(key: string): Mode {
  try {
    return localStorage.getItem(key) === 'month' ? 'month' : 'feed'
  } catch {
    // приватный режим браузера: спрашивать некого, показываем ленту
    return 'feed'
  }
}

/**
 * Подпись строки в ленте.
 *
 * Вид события повторять незачем, если название с него и начинается:
 * сервер называет задачи «Задача: …», и вторая строка «Задача» под ней
 * не добавляет ничего, а место занимает.
 */
function noteOf(event: CalendarCardEvent): ReactNode {
  const note = event.feedNote ?? event.note
  if (typeof note === 'string' && event.title.toLowerCase().startsWith(note.toLowerCase())) return null
  return note
}

export default function CalendarCard({
  events,
  today,
  panelTitle,
  emptyText,
  storageKey,
  className,
  withDateColumn = true,
}: {
  events: CalendarCardEvent[]
  /** сегодняшний день строкой `ГГГГ-ММ-ДД` — считает сервер, не браузер */
  today: string
  panelTitle: string
  emptyText: string
  /** ключ памяти режима: `calendar.mode.<роль>` */
  storageKey: string
  className?: string
  /** дата отдельной колонкой слева от названия (у стартов она в подписи) */
  withDateColumn?: boolean
}) {
  const navigate = useNavigate()
  const trackFilter = useTrack('filter.change')
  const phone = usePhone()
  const [shift, setShift] = useState(0)
  const [mode, setMode] = useState<Mode>(() => storedMode(storageKey))
  const [expanded, setExpanded] = useState(false)
  const [picked, setPicked] = useState<string | null>(null)

  // пока ответ календаря не пришёл, `today` пустой: `new Date('')` даёт
  // Invalid Date, и сетка месяца падала на `Array(NaN)` — экран уходил
  // в границу ошибок ещё до первой отрисовки
  const parsed = new Date(today)
  const base = Number.isNaN(parsed.getTime()) ? new Date() : parsed
  const month = new Date(base.getFullYear(), base.getMonth() + shift, 1)
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
  const lead = (month.getDay() + 6) % 7
  const cells: (number | null)[] = [
    ...Array<null>(lead).fill(null),
    ...Array.from({ length: daysInMonth }, (_, index) => index + 1),
  ]

  const byDay = useMemo(() => {
    const map = new Map<string, CalendarCardEvent[]>()
    for (const event of events) map.set(event.date, [...(map.get(event.date) ?? []), event])
    return map
  }, [events])

  const nearest = events.slice(0, 5)

  const setModeAndRemember = (next: Mode) => {
    setMode(next)
    try {
      localStorage.setItem(storageKey, next)
    } catch {
      // память браузера закрыта — режим просто не переживёт заход
    }
  }

  const open = (event: CalendarCardEvent) => {
    if (event.link) navigate(event.link)
  }

  const monthHead = (
    <div className="calcard__head">
      <b>
        {formatYearMonth(month.getFullYear(), month.getMonth())}
      </b>
      <Button variant="ghost" size="icon-sm" className="calcard__nav" onClick={() => { trackFilter(); setShift((n) => n - 1) }} aria-label={t('Предыдущий месяц')}>
        <Icon name="chevronLeft" size={14} />
      </Button>
      <Button variant="ghost" size="icon-sm" className="calcard__nav" onClick={() => { trackFilter(); setShift((n) => n + 1) }} aria-label={t('Следующий месяц')}>
        <Icon name="chevronRight" size={14} />
      </Button>
    </div>
  )

  /* --- ноутбук и планшет: построенное фазами 49–50, без единой правки --- */
  if (!phone) {
    return (
      <section className={`card card-pad calcard${className ? ` ${className}` : ''}`}>
        <div className="calcard__left">
          {monthHead}
          <div className="calcard__grid">
            {weekdays().map((day) => (
              <span key={day} className="calcard__weekday">
                {day}
              </span>
            ))}
            {cells.map((day, index) => {
              if (day === null) return <CalendarCell key={`x${index}`} day={null} view="compact" />
              const iso = isoOf(month.getFullYear(), month.getMonth(), day)
              return (
                <CalendarCell
                  key={iso}
                  day={day}
                  view="compact"
                  today={iso === today}
                  events={byDay.get(iso)}
                />
              )
            })}
          </div>
        </div>

        <div className="calcard__panel">
          <span className="calcard__panelhead">{t(panelTitle)}</span>
          {nearest.length === 0 && <p className="muted calcard__empty">{t(emptyText)}</p>}
          <Rows>
            {nearest.map((event, index) => (
              <Row
                key={`${event.date}-${index}`}
                lead={
                  withDateColumn ? (
                    <span className="calcard__when">{shortDate(event.date, today)}</span>
                  ) : undefined
                }
                title={event.title}
                note={event.note}
                right={event.right}
                onOpen={event.link ? () => open(event) : undefined}
                openLabel={t('Открыть событие')}
              />
            ))}
          </Rows>
        </div>
      </section>
    )
  }

  /* --- телефон: два режима --------------------------------------------- */

  const upcoming = events.filter((event) => event.date >= today)
  const groups: { key: string; title: string; rows: CalendarCardEvent[] }[] = []
  for (const event of upcoming) {
    const date = new Date(event.date)
    const key = `${date.getFullYear()}-${date.getMonth()}`
    const title = date.getFullYear() === base.getFullYear() ? monthName(date.getMonth()) : formatYearMonth(date.getFullYear(), date.getMonth())
    const last = groups[groups.length - 1]
    if (last && last.key === key) last.rows.push(event)
    else groups.push({ key, title, rows: [event] })
  }

  // сколько строк показываем: до нажатия «Ещё N событий» — четыре
  let left = expanded ? upcoming.length : FEED_ROWS
  const shown = groups
    .map((group) => {
      const rows = group.rows.slice(0, Math.max(left, 0))
      left -= rows.length
      return { ...group, rows }
    })
    .filter((group) => group.rows.length > 0)
  const hidden = upcoming.length - Math.min(upcoming.length, expanded ? upcoming.length : FEED_ROWS)

  const day = picked ?? today
  const dayEvents = byDay.get(day) ?? []
  const dayDate = new Date(day)

  return (
    <section className={`card card-pad calcard calcard--phone${className ? ` ${className}` : ''}`}>
      <div className="calmode">
        <Segmented
          value={mode}
          onChange={setModeAndRemember}
          label={t('Вид календаря')}
          items={[
            { value: 'feed' as Mode, label: t('Лента') },
            { value: 'month' as Mode, label: t('Месяц') },
          ]}
        />
      </div>

      {mode === 'feed' ? (
        <div className="calcard__panel calfeed">
          <span className="calcard__panelhead">{t(panelTitle)}</span>
          {upcoming.length === 0 && <p className="muted calcard__empty">{t(emptyText)}</p>}
          {shown.map((group) => (
            <div key={group.key} className="calfeed__group">
              <span className="calfeed__month">{group.title}</span>
              {group.rows.map((event, index) => (
                <Button
                  key={`${event.date}-${index}`}
                  variant="ghost"
                  className="calfeed__row"
                  onClick={() => open(event)}
                >
                  <span className="calfeed__when">
                    <b className="num">{new Date(event.date).getDate()}</b>
                    <span className="calfeed__weekday">
                      {weekdayName((new Date(event.date).getDay() + 6) % 7)}
                    </span>
                  </span>
                  <span className="calfeed__body">
                    <span className="calfeed__title">{event.title}</span>
                    {noteOf(event) && <span className="muted calfeed__note">{noteOf(event)}</span>}
                  </span>
                  {event.right}
                </Button>
              ))}
            </div>
          ))}
          {hidden > 0 && (
            <Button variant="ghost" className="calfeed__more" onClick={() => setExpanded(true)}>
              {tn(hidden, 'Ещё {n} событие|Ещё {n} события|Ещё {n} событий')}
            </Button>
          )}
        </div>
      ) : (
        <>
          {monthHead}
          <div className="calcard__grid calgrid--phone">
            {weekdays().map((weekday) => (
              <span key={weekday} className="calcard__weekday">
                {weekday}
              </span>
            ))}
            {cells.map((cell, index) => {
              if (cell === null) return <CalendarCell key={`x${index}`} day={null} view="phone" />
              const iso = isoOf(month.getFullYear(), month.getMonth(), cell)
              return (
                <CalendarCell
                  key={iso}
                  day={cell}
                  view="phone"
                  today={iso === today}
                  picked={iso === day}
                  events={byDay.get(iso)}
                  onPick={() => setPicked(iso)}
                />
              )
            })}
          </div>

          <div className="calcard__panel calday">
            <span className="calcard__panelhead">
              {formatDayMonthShort(dayDate)}
            </span>
            {dayEvents.length === 0 && (
              <p className="muted calcard__empty">{t('В этот день ничего не намечено.')}</p>
            )}
            <Rows>
              {dayEvents.map((event, index) => (
                <Row
                  key={`${event.date}-${index}`}
                  title={event.title}
                  note={event.feedNote ?? event.note}
                  right={event.right}
                  onOpen={event.link ? () => open(event) : undefined}
                  openLabel={t('Открыть событие')}
                />
              ))}
            </Rows>
          </div>
        </>
      )}
    </section>
  )
}
