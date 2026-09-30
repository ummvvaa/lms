/**
 * Перевод интерфейса. Ключ — исходная русская строка, как она написана
 * в коде; словари kk и en лежат рядом. Нет перевода — остаётся русский,
 * интерфейс не падает. Что перевод есть у каждого ключа, проверяет
 * правило `lms-i18n/keys` (`npm run lint`) и `backend/core/tests/test_i18n.py`.
 *
 * Подстановки — `{имя}` в строке: `t('Сохранено: {name}', { name })`.
 * Число со словом — `tn(n, '{n} урок|{n} урока|{n} уроков')`: формы через
 * черту, форму выбирает `Intl.PluralRules` по языку. Русских форм три
 * (один, два, пять), английских две (one, other), казахская — одна: после
 * числа существительное не меняется («5 сабақ»). Перевод может дать и одну
 * форму на все числа.
 *
 * Термины не переводятся и в словари не попадают: IELTS, TOEFL, SAT, ACT,
 * Common App, reach/target/safety, GPA, названия вузов и программ.
 */
import { readText, writeText } from '../lib/storage'
import { en } from './en'
import { kk } from './kk'

export type Lang = 'ru' | 'kk' | 'en'

const DICTS: Record<Lang, Record<string, string> | null> = { ru: null, kk, en }

/** Локаль `Intl` для языка: английский — британский, день раньше месяца, как в школе. */
const LOCALES: Record<Lang, string> = { ru: 'ru-RU', kk: 'kk-KZ', en: 'en-GB' }

/**
 * Порядок форм в строке с чертой — по категориям `Intl.PluralRules`.
 * Дробное число по-русски — «1,5 урока»: категория `other` берёт вторую форму.
 */
const PLURAL_ORDER: Record<Lang, Intl.LDMLPluralRule[]> = {
  ru: ['one', 'few', 'many'],
  kk: ['one', 'other'],
  en: ['one', 'other'],
}

let current: Lang = 'ru'
const pluralRules = new Map<Lang, Intl.PluralRules>()

/** Сменить язык. Перерисовку экранов делает провайдер в App. */
export function setLanguage(lang: Lang) {
  current = lang
  document.documentElement.lang = lang
}

const DEVICE_KEY = 'lms.language'
const LANGS: Lang[] = ['ru', 'kk', 'en']

/**
 * Язык до входа — на экране входа и по ссылке из письма: последний язык
 * человека на этом устройстве, иначе язык браузера, иначе русский.
 */
export function deviceLanguage(): Lang {
  const saved = readText(DEVICE_KEY)
  if (saved && (LANGS as string[]).includes(saved)) return saved as Lang
  for (const tag of typeof navigator === 'undefined' ? [] : navigator.languages ?? []) {
    const base = tag.slice(0, 2).toLowerCase()
    if ((LANGS as string[]).includes(base)) return base as Lang
  }
  return 'ru'
}

/** Запомнить язык вошедшего — экран входа на этом устройстве откроется на нём. */
export function rememberLanguage(lang: Lang) {
  writeText(DEVICE_KEY, lang)
}

/** Текущий язык интерфейса. */
export function language(): Lang {
  return current
}

/** Локаль `Intl` текущего языка — только для `lib/format.ts`. */
export function intlLocale(): string {
  return LOCALES[current]
}

export type Params = Record<string, string | number | null | undefined>

/** Подставить `{имя}` из params; неизвестное имя остаётся как есть. */
function fill(text: string, params?: Params): string {
  if (!params) return text
  return text.replace(/\{(\w+)\}/g, (whole, name: string) => {
    const value = params[name]
    return value === undefined || value === null ? whole : String(value)
  })
}

/** Перевод строки без подстановок. Пробелы по краям ключа сохраняются. */
function lookup(source: string): string {
  const dict = DICTS[current]
  if (!dict) return source
  const direct = dict[source]
  if (direct !== undefined) return direct
  const trimmed = source.trim()
  const inner = dict[trimmed]
  if (inner !== undefined && trimmed) return source.replace(trimmed, inner)
  return source
}

/** Перевод по исходной строке с подстановками `{имя}`. */
export function t(source: string, params?: Params): string {
  return fill(lookup(source), params)
}

/**
 * Помечает строку ключом перевода там, где перевести сразу нельзя: в таблицах
 * подписей на уровне модуля. Переводит `t(значение)` при показе. Сама строка
 * не меняется — метка нужна проверке `lms-i18n`.
 */
export function tk<T extends string>(source: T): T {
  return source
}

/** Форма из строки «форма|форма|форма» для числа на текущем языке. */
function pickForm(count: number, forms: string): string {
  const parts = forms.split('|')
  if (parts.length === 1) return parts[0]
  let rules = pluralRules.get(current)
  if (!rules) {
    rules = new Intl.PluralRules(LOCALES[current])
    pluralRules.set(current, rules)
  }
  const category = rules.select(count)
  const order = PLURAL_ORDER[current]
  const index = order.indexOf(category)
  // «other» русского дробного числа и всё незнакомое — вторая форма, если она есть
  return parts[index >= 0 && index < parts.length ? index : Math.min(1, parts.length - 1)]
}

/** Число в записи языка: «1 500», «1,500». */
export function formatCount(count: number): string {
  return new Intl.NumberFormat(LOCALES[current]).format(count)
}

/**
 * Фраза с числом: `tn(n, '{n} урок|{n} урока|{n} уроков')`. `{n}` — число
 * в записи языка; остальные подстановки — из params.
 */
export function tn(count: number, forms: string, params?: Params): string {
  return fill(pickForm(count, lookup(forms)), { ...params, n: formatCount(count) })
}

/** Одно слово в нужной форме, без числа: `plural(n, 'программа|программы|программ')`. */
export function plural(count: number, forms: string): string {
  return pickForm(count, lookup(forms))
}

/** «3 программы» — число вместе со словом в нужной форме. */
export function counted(count: number, forms: string): string {
  // eslint-disable-next-line i18n-concat -- число и слово: порядок «5 сабақ», «5 lessons» одинаков во всех трёх языках
  return `${formatCount(count)} ${plural(count, forms)}`
}
