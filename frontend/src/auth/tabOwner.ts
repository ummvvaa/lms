/**
 * Чья это вкладка: память браузера не переживает смену пользователя (фаза 80).
 *
 * Кабинет куратора помнит выбранную группу в `sessionStorage`, путь ученика —
 * скрытую полосу шага. Вкладка при этом одна на всех, кто входит с этого
 * компьютера: новый куратор получал группу прежнего и видел «AMSTERDAM ·
 * 0 учеников». Поэтому вкладка записывает, кто в ней работает, и при входе
 * другого человека `sessionStorage` стирается целиком — не по ключам, чтобы
 * следующий ключ не повторил ту же ошибку.
 *
 * В `localStorage` лежат жесты человека («пропустил подсказку», «свернул
 * карточку», «закрепил путь»): они переживают заходы, но не смену человека
 * на общем компьютере. Их список — здесь; режим календаря (`calendar.mode.*`)
 * привязан к роли, а не к человеку, и остаётся.
 */
const OWNER = 'owner'

/** Жесты одного человека в `localStorage` — новому пользователю они не достаются. */
const PERSONAL_KEYS = [
  'journey.pinned',
  'journey.skipped',
  'essay.guide.seen',
  'first-run-seen',
  'getting-started-folded',
]

function read(storage: Storage): string | null {
  try {
    return storage.getItem(OWNER)
  } catch {
    // приватное окно закрывает хранилище — стирать и нечего
    return null
  }
}

/**
 * Отметить вкладку за пользователем. Возвращает «хозяин сменился» —
 * тогда и кэш запросов прежнего человека больше не годится.
 */
export function claimTab(userId: number): boolean {
  const id = String(userId)
  let changed = false
  try {
    const tab = read(sessionStorage)
    if (tab !== id) {
      // вкладка без записи о хозяине — тоже чужая: запись появилась вместе со сверкой
      changed = tab !== null
      sessionStorage.clear()
      sessionStorage.setItem(OWNER, id)
    }
    const device = read(localStorage)
    if (device !== id) {
      // без записи не трогаем: на своём устройстве жесты человека остаются его
      if (device !== null) {
        changed = true
        for (const key of PERSONAL_KEYS) localStorage.removeItem(key)
      }
      localStorage.setItem(OWNER, id)
    }
  } catch {
    // хранилище закрыто — помнить нечего, стирать тоже
  }
  return changed
}

/** Выход из системы: память вкладки стирается сразу, не дожидаясь следующего входа. */
export function releaseTab() {
  try {
    sessionStorage.clear()
  } catch {
    // ничего
  }
}
