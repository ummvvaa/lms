/**
 * Подписи секций: день недели и час занятия одним словом на всех экранах —
 * у директора, ученика и куратора «Сб 12:00–13:00» пишется одинаково.
 */
import type { SlotRow } from '../../api/sport'
import { t, tk } from '../../i18n'

/** Дни недели по номеру `date.weekday()` на сервере: понедельник — ноль. */
export const WEEKDAYS = [
  tk('Понедельник'),
  tk('Вторник'),
  tk('Среда'),
  tk('Четверг'),
  tk('Пятница'),
  tk('Суббота'),
  tk('Воскресенье'),
]

export const slotTime = (slot: Pick<SlotRow, 'starts' | 'ends'>) => `${slot.starts}–${slot.ends}`

/** «Сб 12:00–13:00» — день коротко с сервера, час цифрами. */
export const slotWords = (slot: Pick<SlotRow, 'day_short' | 'starts' | 'ends'>) =>
  `${slot.day_short} ${slotTime(slot)}`

/** «Суббота, 12:00–13:00» — день полностью. */
export const slotLong = (slot: Pick<SlotRow, 'weekday' | 'starts' | 'ends'>) =>
  t('{day}, {time}', { day: t(WEEKDAYS[slot.weekday]), time: slotTime(slot) })
