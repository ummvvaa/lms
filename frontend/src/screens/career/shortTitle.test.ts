import { describe, expect, it } from 'vitest'
import { shortTitle } from './shortTitle'

describe('shortTitle', () => {
  it('names tests by their method', () => {
    expect(shortTitle('Карта интересов (А. Е. Голомшток, модификация А. А. Азбель, А. Г. Грецова)')).toBe('Карта интересов')
    expect(shortTitle('Опросник профессиональных склонностей (Л. Йовайши)')).toBe('Йовайши')
    expect(shortTitle('Дифференциально-диагностический опросник (ДДО, Е. А. Климов)')).toBe('Климов (ДДО)')
  })

  it('keeps titles without an author as they are', () => {
    expect(shortTitle('Пробный короткий тест')).toBe('Пробный короткий тест')
    expect(shortTitle('Очень длинное название теста без автора (вариант для девятых классов)')).toBe(
      'Очень длинное название теста без автора (вариант для девятых классов)',
    )
  })
})
