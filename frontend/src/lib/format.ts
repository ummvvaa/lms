/**
 * Даты, месяцы, дни недели и числа на языке интерфейса — одно место на фронт.
 *
 * Всё идёт через `Intl` с локалью текущего языка (`i18n.intlLocale`) и по
 * часовому поясу школы: момент из базы и дата без времени показываются
 * по Алматы, а не по часам браузера. Вызывать `toLocaleDateString`,
 * `toLocaleString` и `new Intl.*` в экранах запрещает правило
 * `lms-i18n/no-raw-locale` — там язык снова оказался бы зашит.
 */
import { intlLocale } from '../i18n'
import { SCHOOL_TIME_ZONE } from './dates'

type DateInput = string | number | Date

/** Дата без времени (`ГГГГ-ММ-ДД`) — полночь UTC: по Алматы тот же день. */
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

function toDate(value: DateInput): Date {
  if (value instanceof Date) return value
  if (typeof value === 'string' && DATE_ONLY.test(value)) return new Date(`${value}T00:00:00Z`)
  return new Date(value)
}

const cache = new Map<string, Intl.DateTimeFormat>()

function dateFormat(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${intlLocale()}|${JSON.stringify(options)}`
  let format = cache.get(key)
  if (!format) {
    format = new Intl.DateTimeFormat(intlLocale(), { timeZone: SCHOOL_TIME_ZONE, ...options })
    cache.set(key, format)
  }
  return format
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
  return dateFormat({ dateStyle: 'long', timeStyle: 'short', hourCycle: 'h23' }).format(toDate(value))
}

/** «14:05». */
export function formatTime(value: DateInput): string {
  return dateFormat({ hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(toDate(value))
}

/** «25 сентября», «25 қыркүйек», «25 September». */
export function formatDayMonth(value: DateInput): string {
  return dateFormat({ day: 'numeric', month: 'long' }).format(toDate(value))
}

/** «15 окт.» — коротко, для ленты событий. */
export function formatDayMonthShort(value: DateInput): string {
  return dateFormat({ day: 'numeric', month: 'short' }).format(toDate(value))
}

/** «25 сентября 2026 г.». */
export function formatDateLong(value: DateInput): string {
  return dateFormat({ day: 'numeric', month: 'long', year: 'numeric' }).format(toDate(value))
}

/** «Сентябрь 2026 г.» — месяц с годом, с заглавной. */
export function formatMonthYear(value: DateInput): string {
  return capital(dateFormat({ month: 'long', year: 'numeric' }).format(toDate(value)))
}

/** «Сентябрь 2026 г.» по году и номеру месяца 0–11. */
export function formatYearMonth(year: number, monthIndex: number): string {
  return formatMonthYear(new Date(Date.UTC(year, monthIndex, 15)))
}

/** Название месяца по номеру 0–11: «Сентябрь»; `short` — «сент.». */
export function monthName(index: number, width: 'long' | 'short' = 'long'): string {
  const name = dateFormat({ month: width }).format(new Date(Date.UTC(2026, index, 15)))
  return width === 'long' ? capital(name) : name
}

/** День недели по номеру от понедельника (0–6): «Пн»; `long` — «Понедельник». */
export function weekdayName(index: number, width: 'long' | 'short' = 'short'): string {
  // 5 января 2026 года — понедельник
  return capital(dateFormat({ weekday: width }).format(new Date(Date.UTC(2026, 0, 5 + index, 12))))
}

/** День недели даты внутри фразы: «среда», «сәрсенбі», «Wednesday». */
export function formatWeekday(value: DateInput, width: 'long' | 'short' = 'long'): string {
  return dateFormat({ weekday: width }).format(toDate(value))
}

/** Число в записи языка: «1 500,5», «1,500.5». */
export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(intlLocale(), options).format(value)
}
