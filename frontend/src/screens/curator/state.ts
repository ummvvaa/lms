/**
 * Выбранная группа куратора — одна на весь кабинет (фаза 61).
 *
 * Живёт в адресе экрана (`?group=CHICAGO`) и переживает переход между
 * разделами через `sessionStorage`: куратор разбирает очередь одной
 * группы, уходит в учеников и возвращается — фильтр обязан остаться.
 * Не в профиле на сервере: это не настройка человека, а состояние
 * текущей работы, и на другом устройстве оно не нужно.
 */
import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

const KEY = 'curator-group'

/** Все мои группы. Отдельным значением, а не пустой строкой: пустое читается как «не выбрано». */
export const ALL = 'all'

function remembered(): string {
  try {
    return sessionStorage.getItem(KEY) || ALL
  } catch {
    // приватное окно закрывает хранилище — работаем без памяти
    return ALL
  }
}

/** Текущая группа и переключатель. Значение из адреса важнее запомненного. */
export function useGroup(): [string, (next: string) => void] {
  const [params, setParams] = useSearchParams()
  const fromUrl = params.get('group')
  const group = fromUrl || remembered()

  const setGroup = useCallback(
    (next: string) => {
      try {
        sessionStorage.setItem(KEY, next)
      } catch {
        // ничего: фильтр просто не переживёт переход между разделами
      }
      const updated = new URLSearchParams(params)
      if (next === ALL) updated.delete('group')
      else updated.set('group', next)
      setParams(updated, { replace: true })
    },
    [params, setParams],
  )

  return [group, setGroup]
}
