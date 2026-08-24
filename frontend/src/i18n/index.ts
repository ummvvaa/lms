/**
 * Перевод интерфейса. Ключ — исходная русская строка, как она написана
 * в коде; словари kk и en лежат рядом. Нет перевода — остаётся русский,
 * интерфейс не падает.
 *
 * Термины не переводятся и в словари не попадают: IELTS, TOEFL, SAT, ACT,
 * Common App, reach/target/safety, GPA, названия вузов и программ.
 */
import { en } from './en'
import { kk } from './kk'

export type Lang = 'ru' | 'kk' | 'en'

const DICTS: Record<Lang, Record<string, string> | null> = { ru: null, kk, en }

let current: Lang = 'ru'

/** Сменить язык. Перерисовку экранов делает провайдер в App. */
export function setLanguage(lang: Lang) {
  current = lang
  document.documentElement.lang = lang
}

export function getLanguage(): Lang {
  return current
}

/** Перевод по исходной строке. Пробелы по краям ключа сохраняются. */
export function t(source: string): string {
  const dict = DICTS[current]
  if (!dict) return source
  const direct = dict[source]
  if (direct !== undefined) return direct
  const trimmed = source.trim()
  const inner = dict[trimmed]
  if (inner !== undefined && trimmed) return source.replace(trimmed, inner)
  return source
}
