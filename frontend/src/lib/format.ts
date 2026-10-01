/**
 * Даты, месяцы, дни недели и числа на языке интерфейса — одно место на фронт.
 *
 * Всё идёт через `Intl` по часовому поясу школы: момент из базы и дата без
 * времени показываются по Алматы, а не по часам браузера. Вызывать
 * `toLocaleDateString`, `toLocaleString` и `new Intl.*` в экранах запрещает
 * правило `no-raw-locale` — там язык снова оказался бы зашит.
 *
 * Казахский — особый случай. В Chromium (и в сборке Playwright) казахских
 * данных `Intl` нет вовсе: месяц выходит «M09», день недели — «Wed», число —
 * «12,345.6». Поэтому названия месяцев и дней недели для казахского берутся
 * из словаря (`t()` по русскому названию), а числа и даты цифрами — по записи
 * `ru-RU`: в Казахстане она та же — «30.09.2026», «12 345,6».
 */
import { intlLocale, language, t, tk } from '../i18n'
import { SCHOOL_TIME_ZONE } from './dates'

type DateInput = string | number | Date

/** Дата без времени (`ГГГГ-ММ-ДД`) — полночь UTC: по Алматы тот же день. */
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

const MONTHS = [
  tk('январь'),
  tk('февраль'),
  tk('март'),
  tk('апрель'),
  tk('май'),
  tk('июнь'),
  tk('июль'),
  tk('август'),
  tk('сентябрь'),
  tk('октябрь'),
  tk('ноябрь'),
  tk('декабрь'),
]
const MONTHS_SHORT = [
  tk('янв.'),
  tk('февр.'),
  tk('мар.'),
  tk('апр.'),
  tk('мая'),
  tk('июн.'),
  tk('июл.'),
  tk('авг.'),
  tk('сент.'),
  tk('окт.'),
  tk('нояб.'),
  tk('дек.'),
]
const WEEKDAYS = [
  tk('понедельник'),
  tk('вторник'),
  tk('среда'),
  tk('четверг'),
  tk('пятница'),
  tk('суббота'),
  tk('воскресенье'),
]
const WEEKDAYS_SHORT = [tk('пн'), tk('вт'), tk('ср'), tk('чт'), tk('пт'), tk('сб'), tk('вс')]

function toDate(value: DateInput): Date {
  if (value instanceof Date) return value
  if (typeof value === 'string' && DATE_ONLY.test(value)) return new Date(`${value}T00:00:00Z`)
  return new Date(value)
}

/** Казахский: названия из словаря, цифры — по записи `ru-RU`. */
const kazakh = () => language() === 'kk'
/** Локаль для цифр: у казахского — `ru-RU`, данных `kk-KZ` в браузере может не быть. */
export const numberLocale = () => (kazakh() ? 'ru-RU' : intlLocale())

const cache = new Map<string, Intl.DateTimeFormat>()

function dateFormat(options: Intl.DateTimeFormatOptions, locale = numberLocale()): Intl.DateTimeFormat {
  const key = `${locale}|${JSON.stringify(options)}`
  let format = cache.get(key)
  if (!format) {
    format = new Intl.DateTimeFormat(locale, { timeZone: SCHOOL_TIME_ZONE, ...options })
    cache.set(key, format)
  }
  return format
}

/** Год, месяц (0–11), число и день недели (0 — понедельник) по времени школы. */
function parts(value: DateInput): { year: number; month: number; day: number; weekday: number } {
  const found = dateFormat({ year: 'numeric', month: 'numeric', day: 'numeric', weekday: 'short' }, 'en-US').formatToParts(toDate(value))
  const get = (type: string) => found.find((part) => part.type === type)?.value ?? ''
  const weekday = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].indexOf(get('weekday'))
  return { year: Number(get('year')), month: Number(get('month')) - 1, day: Number(get('day')), weekday }
}

/** Первая буква заглавная: «сентябрь 2026 г.» → «Сентябрь 2026 г.». */
function capital(text: string): string {
  return text ? text[0].toLocaleUpperCase(intlLocale()) + text.slice(1) : text
}

/** «30.09.2026», «30/09/2026». */
export function formatDate(value: DateInput): string {
  return dateFormat({ day: '2-digit', month: '2-digit', year: 'numeric' }).format(toDate(value))
}

/** «30.09.2026, 14:05». */
export function formatDateTime(value: DateInput): string {
  return dateFormat({ day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(toDate(value))
}

/** «30 сентября 2026 г., 14:05». */
export function formatDateTimeLong(value: DateInput): string {
  if (kazakh()) return t('{date}, {time}', { date: formatDateLong(value), time: formatTime(value) })
  return dateFormat({ dateStyle: 'long', timeStyle: 'short', hourCycle: 'h23' }).format(toDate(value))
}

/** «14:05». */
export function formatTime(value: DateInput): string {
  return dateFormat({ hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(toDate(value))
}

/** «25 сентября», «25 қыркүйек», «25 September». */
export function formatDayMonth(value: DateInput): string {
  if (kazakh()) {
    const { day, month } = parts(value)
    return t('{day} {month}', { day, month: t(MONTHS[month]) })
  }
  return dateFormat({ day: 'numeric', month: 'long' }).format(toDate(value))
}

/** «15 окт.» — коротко, для ленты событий. */
export function formatDayMonthShort(value: DateInput): string {
  if (kazakh()) {
    const { day, month } = parts(value)
    return t('{day} {month}', { day, month: t(MONTHS_SHORT[month]) })
  }
  return dateFormat({ day: 'numeric', month: 'short' }).format(toDate(value))
}

/** «25 сентября 2026 г.», «2026 ж. 25 қыркүйек». */
export function formatDateLong(value: DateInput): string {
  if (kazakh()) {
    const { year, day, month } = parts(value)
    return t('{day} {month} {year} г.', { day, month: t(MONTHS[month]), year })
  }
  return dateFormat({ day: 'numeric', month: 'long', year: 'numeric' }).format(toDate(value))
}

/** «Сентябрь 2026 г.» — месяц с годом, с заглавной. */
export function formatMonthYear(value: DateInput): string {
  if (kazakh()) {
    const { year, month } = parts(value)
    return t('{month} {year} г.', { month: t(MONTHS[month]), year })
  }
  return capital(dateFormat({ month: 'long', year: 'numeric' }).format(toDate(value)))
}

/** «Сентябрь 2026 г.» по году и номеру месяца 0–11. */
export function formatYearMonth(year: number, monthIndex: number): string {
  return formatMonthYear(new Date(Date.UTC(year, monthIndex, 15)))
}

/** Название месяца по номеру 0–11: «Сентябрь»; `short` — «сент.». */
export function monthName(index: number, width: 'long' | 'short' = 'long'): string {
  if (kazakh()) return width === 'long' ? capital(t(MONTHS[index])) : t(MONTHS_SHORT[index])
  const name = dateFormat({ month: width }).format(new Date(Date.UTC(2026, index, 15)))
  return width === 'long' ? capital(name) : name
}

/** День недели по номеру от понедельника (0–6): «Пн»; `long` — «Понедельник». */
export function weekdayName(index: number, width: 'long' | 'short' = 'short'): string {
  if (kazakh()) return capital(t((width === 'long' ? WEEKDAYS : WEEKDAYS_SHORT)[index]))
  // 5 января 2026 года — понедельник
  return capital(dateFormat({ weekday: width }).format(new Date(Date.UTC(2026, 0, 5 + index, 12))))
}

/** День недели даты внутри фразы: «среда», «сәрсенбі», «Wednesday». */
export function formatWeekday(value: DateInput, width: 'long' | 'short' = 'long'): string {
  if (kazakh()) return t((width === 'long' ? WEEKDAYS : WEEKDAYS_SHORT)[parts(value).weekday])
  return dateFormat({ weekday: width }).format(toDate(value))
}

/** Число в записи языка: «1 500,5», «1,500.5». */
export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(numberLocale(), options).format(value)
}
