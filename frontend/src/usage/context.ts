import { createContext, useCallback, useContext } from 'react'

/** Общие компоненты не знают ни сессии, ни API, ни значения фильтра. */
export const UsageContext = createContext<((action: string) => void) | null>(null)
export function useTrack(action: string) {
  const track = useContext(UsageContext)
  return useCallback(() => track?.(action), [track, action])
}
