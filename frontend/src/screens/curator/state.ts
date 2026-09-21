/**
 * Выбранная группа куратора — одна на весь кабинет (фаза 61).
 *
 * Живёт в адресе экрана (`?group=CHICAGO`) и переживает переход между
 * разделами через `sessionStorage`: куратор разбирает очередь одной
 * группы, уходит в учеников и возвращается — фильтр обязан остаться.
 * Не в профиле на сервере: это не настройка человека, а состояние
 * текущей работы, и на другом устройстве оно не нужно.
 *
 * Запомненное значение — не источник групп (фаза 80). Источник один:
 * действующие назначения куратора (`useMyGroups`). Выбор из адреса
 * и из памяти вкладки сверяется с ними на каждом экране: группа чужая,
 * снятая или ушедшая в архив — молча заменяется первой назначенной.
 * Раньше такое значение уходило в запросы как есть: вкладка помнила
 * AMSTERDAM прежнего куратора, сервер честно отвечал «пусто», а шапка
 * печатала «AMSTERDAM · 0 учеников».
 */
import { useCallback, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useCuratorProfile, type CuratorGroup } from '../../api/hooks'
import { useAuth } from '../../auth/AuthContext'

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

function remember(next: string) {
  try {
    if (next === ALL) sessionStorage.removeItem(KEY)
    else sessionStorage.setItem(KEY, next)
  } catch {
    // ничего: фильтр просто не переживёт переход между разделами
  }
}

/**
 * Группы куратора — действующие назначения, и только они.
 *
 * Переключатель стоит и на экране «Пробники», общем с Кымбат и администратором:
 * у них назначений нет, сверять выбор не с чем, и профиль куратора они
 * не запрашивают — сервер ответил бы 403.
 */
export function useMyGroups(): { groups: CuratorGroup[]; ready: boolean } {
  const { me } = useAuth()
  const { data } = useCuratorProfile(me?.role === 'curator')
  return { groups: data?.groups ?? [], ready: data !== undefined }
}

/**
 * Выбор, сверенный с назначениями: своя группа — её код как в справочнике,
 * «все» — «все», остальное — первая назначенная (а без групп — «все»).
 */
export function settled(asked: string, groups: CuratorGroup[]): string {
  if (asked === ALL) return ALL
  const own = groups.find((row) => row.code.toLowerCase() === asked.toLowerCase())
  if (own) return own.code
  return groups[0]?.code ?? ALL
}

/** Текущая группа и переключатель. Значение из адреса важнее запомненного. */
export function useGroup(): [string, (next: string) => void] {
  const [params, setParams] = useSearchParams()
  const { groups, ready } = useMyGroups()
  const asked = params.get('group') || remembered()
  // пока назначения не пришли, сверять не с чем: кабинет в это время
  // экраны не рисует (`CuratorCabinet`), запрос с чужим кодом не уходит
  const group = ready ? settled(asked, groups) : asked

  const setGroup = useCallback(
    (next: string) => {
      remember(next)
      const updated = new URLSearchParams(params)
      if (next === ALL) updated.delete('group')
      else updated.set('group', next)
      setParams(updated, { replace: true })
    },
    [params, setParams],
  )

  // чужое значение не остаётся ни в памяти вкладки, ни в адресе
  useEffect(() => {
    if (ready && group !== asked) setGroup(group)
  }, [ready, group, asked, setGroup])

  return [group, setGroup]
}
