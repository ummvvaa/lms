/**
 * Календарь на цветной карточке: сетка месяца и панель событий.
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
import { useNavigate } from 'react-router-dom'
import Icon from '../layout/icons'
import { usePhone } from '../phone'
import { t } from '../i18n'
import { Row, Rows, Segmented } from './patterns'
import { counted } from './ui'

/* Месяц в строке события сокращён — «27 сент.», а не «27 сентября»:
   дата стоит своей колонкой перед названием, и полное слово уносило
   строку на два ряда. Короткие месяцы не сокращаются: «мая» короче
   любой отсечки. */
export const MONTHS = [
  'янв.',
  'февр.',
  'марта',
  'апр.',
  'мая',
  'июня',
  'июля',
  'авг.',
  'сент.',
  'окт.',
  'нояб.',
  'дек.',
]

export const MONTH_NAMES = [
  'Январь',
  'Февраль',
  'Март',
  'Апрель',
  'Май',
  'Июнь',
  'Июль',
  'Август',
  'Сентябрь',
  'Октябрь',
  'Ноябрь',
  'Декабрь',
]

export const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

/** Дата события коротко: «15 окт.» или «Сегодня». */
export function shortDate(iso: string, today: string): string {
  if (iso === today) return t('Сегодня')
  const date = new Date(iso)
  return `${date.getDate()} ${t(MONTHS[date.getMonth()])}`
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

/**
 * Чем событие является — словом.
 *
 * Сервер отдаёт код вида (`exam`, `deadline`, …), а подпись собирает
 * интерфейс: в ленте телефона у строки обязана быть вторая строка,
 * иначе «Пробный SAT» и «Дедлайн Стэнфорда» выглядят одинаково.
 */
export const EVENT_KIND_TITLE: Record<string, string> = {
  exam: 'Экзамен',
  deadline: 'Дедлайн вуза',
  competition: 'Соревнование',
  olympiad: 'Олимпиада',
  scholarship: 'Стипендия',
  task: 'Задача',
}

/** Сколько строк ленты видно сразу: больше не помещается в первый экран. */
const FEED_ROWS = 4

/** Точек под числом дня — не больше трёх: четвёртая уже не считается. */
const MAX_DOTS = 3

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

  const marked = useMemo(() => new Set(events.map((event) => event.date)), [events])
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
    <div className="home__calhead">
      <b>
        {t(MONTH_NAMES[month.getMonth()])} {month.getFullYear()}
      </b>
      <button
        type="button"
        className="home__calnav"
        onClick={() => setShift((n) => n - 1)}
        aria-label={t('Предыдущий месяц')}
      >
        <Icon name="chevronLeft" size={14} />
      </button>
      <button
        type="button"
        className="home__calnav"
        onClick={() => setShift((n) => n + 1)}
        aria-label={t('Следующий месяц')}
      >
        <Icon name="chevronRight" size={14} />
      </button>
    </div>
  )

  /* --- ноутбук и планшет: построенное фазами 49–50, без единой правки --- */
  if (!phone) {
    return (
      <section className={`hero hero--indigo home__cal${className ? ` ${className}` : ''}`}>
        <div className="home__calleft">
          {monthHead}
          <div className="home__calgrid">
            {WEEKDAYS.map((day) => (
              <span key={day} className="home__calweekday">
                {t(day)}
              </span>
            ))}
            {cells.map((day, index) => {
              if (day === null) return <span key={`x${index}`} />
              const iso = isoOf(month.getFullYear(), month.getMonth(), day)
              return (
                <span
                  key={iso}
                  className={`num home__calday${iso === today ? ' home__calday--today' : ''}${
                    marked.has(iso) ? ' home__calday--marked' : ''
                  }`}
                >
                  {day}
                </span>
              )
            })}
          </div>
        </div>

        <div className="home__calpanel">
          <span className="home__panelhead">{t(panelTitle)}</span>
          {nearest.length === 0 && <p className="muted home__calempty">{t(emptyText)}</p>}
          <Rows>
            {nearest.map((event, index) => (
              <Row
                key={`${event.date}-${index}`}
                lead={
                  withDateColumn ? (
                    <span className="home__when">{shortDate(event.date, today)}</span>
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
    const title = `${t(MONTH_NAMES[date.getMonth()])}${
      date.getFullYear() === base.getFullYear() ? '' : ` ${date.getFullYear()}`
    }`
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
    <section className={`hero hero--indigo home__cal home__cal--phone${className ? ` ${className}` : ''}`}>
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
        <div className="home__calpanel calfeed">
          <span className="home__panelhead">{t(panelTitle)}</span>
          {upcoming.length === 0 && <p className="muted home__calempty">{t(emptyText)}</p>}
          {shown.map((group) => (
            <div key={group.key} className="calfeed__group">
              <span className="calfeed__month">{group.title}</span>
              {group.rows.map((event, index) => (
                <button
                  key={`${event.date}-${index}`}
                  type="button"
                  className="calfeed__row"
                  onClick={() => open(event)}
                >
                  <span className="calfeed__when">
                    <b className="num">{new Date(event.date).getDate()}</b>
                    <span className="calfeed__weekday">
                      {t(WEEKDAYS[(new Date(event.date).getDay() + 6) % 7])}
                    </span>
                  </span>
                  <span className="calfeed__body">
                    <span className="calfeed__title">{event.title}</span>
                    {noteOf(event) && <span className="muted calfeed__note">{noteOf(event)}</span>}
                  </span>
                  {event.right}
                </button>
              ))}
            </div>
          ))}
          {hidden > 0 && (
            <button type="button" className="calfeed__more" onClick={() => setExpanded(true)}>
              {t('Ещё')} {counted(hidden, ['событие', 'события', 'событий'])}
            </button>
          )}
        </div>
      ) : (
        <>
          {monthHead}
          <div className="home__calgrid calgrid--phone">
            {WEEKDAYS.map((weekday) => (
              <span key={weekday} className="home__calweekday">
                {t(weekday)}
              </span>
            ))}
            {cells.map((cell, index) => {
              if (cell === null) return <span key={`x${index}`} className="calcell" />
              const iso = isoOf(month.getFullYear(), month.getMonth(), cell)
              const dots = Math.min((byDay.get(iso) ?? []).length, MAX_DOTS)
              return (
                <button
                  key={iso}
                  type="button"
                  className={`calcell${iso === day ? ' calcell--picked' : ''}`}
                  aria-pressed={iso === day}
                  onClick={() => setPicked(iso)}
                >
                  <span className={`num calcell__day${iso === today ? ' calcell__day--today' : ''}`}>
                    {cell}
                  </span>
                  <span className="calcell__dots" aria-hidden="true">
                    {Array.from({ length: dots }, (_, dot) => (
                      <i key={dot} />
                    ))}
                  </span>
                </button>
              )
            })}
          </div>

          <div className="home__calpanel calday">
            <span className="home__panelhead">
              {dayDate.getDate()} {t(MONTHS[dayDate.getMonth()])}
            </span>
            {dayEvents.length === 0 && (
              <p className="muted home__calempty">{t('В этот день ничего не намечено.')}</p>
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
