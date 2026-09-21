/**
 * Хранилище браузера, которое не роняет экран (фаза 81).
 *
 * Приватное окно, закрытые куки и политика сайта делают `localStorage`
 * недоступным — обращение к нему бросает `SecurityError`. Каркас читал
 * «путь закреплён» напрямую, и в таком браузере падал весь интерфейс,
 * а не одна кнопка. Жесты человека не настолько важны, чтобы ради них
 * ломать экран: нет хранилища — считаем, что жеста не было.
 */

/** Флаг из хранилища: нет доступа — `false`. */
export function readFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
}

/** Строка из хранилища: нет доступа — значение по умолчанию. */
export function readText(key: string, fallback = ''): string {
  try {
    return localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}

/** Записать или убрать значение. Нет доступа — тихо ничего. */
export function writeText(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    // хранилище закрыто: жест не переживёт перезагрузку, и только
  }
}
