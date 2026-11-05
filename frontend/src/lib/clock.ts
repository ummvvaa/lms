/**
 * Время суток в поле формы — всегда 24 часа, «16:00», на всех языках.
 *
 * Нативное `input[type=time]` рисует время по настройкам устройства: при
 * 12-часовом формате системы директор видел «04:00 PM». Поле времени
 * (`Field kind="time"`) поэтому — обычный текст с маской «ЧЧ:ММ»; здесь
 * разбор набранного, без интерфейса.
 */

/**
 * Что показать в поле, пока человек набирает: только цифры и одно двоеточие.
 * «1600» → «16:00»; час из одной цифры понятен сам: «930» → «9:30» (часа «93» не бывает).
 */
export function maskClock(text: string): string {
  if (text.includes(':')) {
    const [hours, minutes = ''] = text.split(':')
    return `${hours.replace(/\D/g, '').slice(0, 2)}:${minutes.replace(/\D/g, '').slice(0, 2)}`
  }
  const digits = text.replace(/\D/g, '').slice(0, 4)
  if (digits.length < 2) return digits
  if (Number(digits.slice(0, 2)) > 23) return `${digits[0]}:${digits.slice(1, 3)}`
  return digits.length > 2 ? `${digits.slice(0, 2)}:${digits.slice(2)}` : digits
}

/**
 * Полное время «ЧЧ:ММ» из набранного («16:00», «9:30») — или `null`, если это ещё не время.
 * `loose` — при уходе из поля: «9» → «09:00», «9:3» → «09:03», «16:» → «16:00».
 */
export function fullClock(text: string, loose = false): string | null {
  const value = text.trim()
  let hours: string
  let minutes: string
  const strict = /^(\d{1,2}):(\d{2})$/.exec(value)
  if (strict) [, hours, minutes] = strict
  else if (!loose) return null
  else {
    const parts = /^(\d{1,2})(?::(\d{0,2}))?$/.exec(value)
    if (!parts) return null
    ;[, hours, minutes = ''] = parts
  }
  const h = Number(hours)
  const m = Number(minutes || 0)
  if (h > 23 || m > 59) return null
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

/** Значение поля из данных: «17:00:00» с сервера показывается как «17:00». */
export function shownClock(value: string | number | null | undefined): string {
  const text = String(value ?? '')
  return /^\d{2}:\d{2}/.test(text) ? text.slice(0, 5) : text
}
