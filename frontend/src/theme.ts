/**
 * Тема интерфейса: атрибут `data-theme` на <html>, токены в tokens.css.
 *
 * «Как в системе» разрешается здесь, а не в CSS-медиазапросе: выбранная
 * руками тема должна перекрывать системную, и проще иметь один источник.
 */
export type ThemePref = 'light' | 'dark' | 'system'

const media = window.matchMedia('(prefers-color-scheme: dark)')
let pref: ThemePref = 'system'

function paint() {
  const resolved = pref === 'system' ? (media.matches ? 'dark' : 'light') : pref
  document.documentElement.dataset.theme = resolved
}

/** Применить выбор темы. Зовётся при загрузке профиля и из переключателя. */
export function applyTheme(next: ThemePref) {
  pref = next
  paint()
}

// системная тема меняется на лету — «как в системе» следует за ней
media.addEventListener('change', paint)
