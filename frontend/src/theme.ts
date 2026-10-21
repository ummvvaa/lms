/**
 * Тема интерфейса: атрибут `data-theme` на <html>, токены в tokens.css.
 *
 * «Системная» разрешается здесь, а не в CSS-медиазапросе: выбранная
 * руками тема должна перекрывать системную, и проще иметь один источник.
 *
 * Выбор живёт в профиле на сервере (переживает смену устройства) и копией
 * в браузере: до входа и до ответа профиля экран рисуется сразу в выбранной
 * теме, а не мигает системной.
 */
import { readText, writeText } from './lib/storage'

export type ThemePref = 'light' | 'dark' | 'system'

const KEY = 'theme-pref'
const media = window.matchMedia('(prefers-color-scheme: dark)')
let pref: ThemePref = 'system'

function paint() {
  const resolved = pref === 'system' ? (media.matches ? 'dark' : 'light') : pref
  document.documentElement.dataset.theme = resolved
}

/** Выбор, запомненный в этом браузере; нет записи — системная. */
export function storedTheme(): ThemePref {
  const saved = readText(KEY)
  return saved === 'light' || saved === 'dark' || saved === 'system' ? saved : 'system'
}

/** Применить выбор темы и запомнить его в браузере. Зовётся при загрузке профиля и из переключателя. */
export function applyTheme(next: ThemePref) {
  pref = next
  writeText(KEY, next)
  paint()
}

// системная тема меняется на лету — «Системная» следует за ней
media.addEventListener('change', paint)
