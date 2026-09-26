/**
 * «Сегодня» по Алматы — одно место на весь фронт (D60).
 *
 * `new Date().toISOString().slice(0, 10)` отдаёт день по UTC: с полуночи
 * до пяти утра по Алматы это ещё вчера, и посещаемость, задача или документ
 * подставляли вчерашнюю дату. Школа живёт по одному часовому поясу, и день
 * берётся по нему, а не по часам браузера и не по UTC.
 */
export const SCHOOL_TIME_ZONE = 'Asia/Almaty'

/** Дата в виде `ГГГГ-ММ-ДД` для момента `at` по времени школы. */
export function dayInSchoolZone(at: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: SCHOOL_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(at)
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? ''
  return `${get('year')}-${get('month')}-${get('day')}`
}

/** Сегодня по Алматы. */
export const todayAlmaty = (): string => dayInSchoolZone()

/** День через `days` дней от сегодня по Алматы. */
export function daysFromToday(days: number): string {
  const at = new Date()
  at.setUTCDate(at.getUTCDate() + days)
  return dayInSchoolZone(at)
}
