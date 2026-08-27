/** Состояние связи для компонентов — подписка на `connection.ts`. */
import { useEffect, useState } from 'react'
import { getConnection, subscribeConnection, type ConnectionState } from './connection'

export function useConnection(): ConnectionState {
  const [state, setState] = useState<ConnectionState>(getConnection)
  useEffect(() => subscribeConnection((next) => setState(next)), [])
  return state
}

/** Вызвать `handler`, когда связь вернулась: черновики досылаются сами. */
export function useReconnected(handler: () => void): void {
  useEffect(
    () =>
      subscribeConnection((_state, event) => {
        if (event === 'reconnected') handler()
      }),
    [handler],
  )
}
