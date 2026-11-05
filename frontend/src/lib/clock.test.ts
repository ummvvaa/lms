import { describe, expect, it } from 'vitest'
import { fullClock, maskClock, shownClock } from './clock'

describe('поле времени — 24 часа на всех языках', () => {
  it('маска: цифры складываются в «ЧЧ:ММ», лишнее отбрасывается', () => {
    expect(maskClock('1')).toBe('1')
    expect(maskClock('16')).toBe('16')
    expect(maskClock('160')).toBe('16:0')
    expect(maskClock('1600')).toBe('16:00')
    expect(maskClock('16005')).toBe('16:00')
    expect(maskClock('9:3')).toBe('9:3')
    expect(maskClock('93')).toBe('9:3')
    expect(maskClock('930')).toBe('9:30')
    expect(maskClock('245')).toBe('2:45')
    expect(maskClock('2359')).toBe('23:59')
    expect(maskClock('04:00 PM')).toBe('04:00')
    expect(maskClock('abc')).toBe('')
  })

  it('полное время принимается только в границах суток', () => {
    expect(fullClock('16:00')).toBe('16:00')
    expect(fullClock('00:00')).toBe('00:00')
    expect(fullClock('23:59')).toBe('23:59')
    expect(fullClock('24:00')).toBeNull()
    expect(fullClock('12:60')).toBeNull()
    expect(fullClock('16:0')).toBeNull()
    expect(fullClock('9:30')).toBe('09:30')
    expect(fullClock('')).toBeNull()
  })

  it('при уходе из поля недописанное время дописывается', () => {
    expect(fullClock('9', true)).toBe('09:00')
    expect(fullClock('16', true)).toBe('16:00')
    expect(fullClock('9:3', true)).toBe('09:03')
    expect(fullClock('16:', true)).toBe('16:00')
    expect(fullClock(maskClock('930'), true)).toBe('09:30')
    expect(fullClock('25', true)).toBeNull()
    expect(fullClock('', true)).toBeNull()
  })

  it('время с секундами с сервера показывается без них', () => {
    expect(shownClock('17:00:00')).toBe('17:00')
    expect(shownClock('17:00')).toBe('17:00')
    expect(shownClock(null)).toBe('')
  })
})
