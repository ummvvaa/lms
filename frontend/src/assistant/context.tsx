/**
 * Контекст экрана для помощника: какие ученики сейчас отфильтрованы.
 *
 * «Поставь всем задачу» после фильтра означает «этим отфильтрованным»,
 * а не всем двумстам пятидесяти. Экраны со списками публикуют сюда
 * текущий набор, помощник отдаёт его серверу вместе с вопросом.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

interface AssistantScreenValue {
  /** id учеников, видимых сейчас на экране после фильтров */
  students: number[]
  setStudents: (ids: number[]) => void
}

const AssistantScreenContext = createContext<AssistantScreenValue>({
  students: [],
  setStudents: () => {},
})

export function AssistantScreenProvider({ children }: { children: ReactNode }) {
  const [students, setStudentsState] = useState<number[]>([])
  const setStudents = useCallback((ids: number[]) => {
    setStudentsState((prev) =>
      prev.length === ids.length && prev.every((v, i) => v === ids[i]) ? prev : ids,
    )
  }, [])
  const value = useMemo(() => ({ students, setStudents }), [students, setStudents])
  return <AssistantScreenContext.Provider value={value}>{children}</AssistantScreenContext.Provider>
}

export function useAssistantScreen(): AssistantScreenValue {
  return useContext(AssistantScreenContext)
}

/** Публикация списка с экрана: рендерится внутри экрана со списком. */
export function PublishStudents({ ids }: { ids: number[] }) {
  const { setStudents } = useAssistantScreen()
  const key = ids.join(',')
  useEffect(() => {
    setStudents(key ? key.split(',').map(Number) : [])
    return () => setStudents([])
  }, [key, setStudents])
  return null
}
