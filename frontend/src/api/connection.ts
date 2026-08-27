/**
 * Связь с сервером: одна на всё приложение (фаза 36, D3).
 *
 * Сетевая ошибка — обрыв, перезапуск бэкенда, «proxy error» от Vite —
 * не значит «не вошёл». Клиент API сообщает сюда о подозрении, здесь
 * проверяется, отвечает ли сервер вообще, и если нет — приложение
 * переходит в режим «нет связи»: запросы React Query ставятся на паузу
 * (`onlineManager`), сверху появляется полоса, а переподключение идёт
 * само с нарастающей задержкой. Как только сервер ответил, всё
 * продолжается с того же места — без перезагрузки и без входа заново.
 */
import { onlineManager } from '@tanstack/react-query'

export interface ConnectionState {
  /** сервер не отвечает */
  offline: boolean
  /** номер попытки переподключения, с единицы */
  attempt: number
  /** через сколько секунд следующая попытка */
  nextIn: number
}

type Listener = (state: ConnectionState, event: 'change' | 'reconnected') => void

/** Задержки между попытками, секунды: быстро в начале, потом раз в 15 секунд. */
const DELAYS = [1, 2, 4, 8, 15]

let state: ConnectionState = { offline: false, attempt: 0, nextIn: 0 }
const listeners = new Set<Listener>()
let timer: number | null = null
let probing = false

function emit(event: 'change' | 'reconnected') {
  listeners.forEach((listener) => listener(state, event))
}

function set(next: Partial<ConnectionState>, event: 'change' | 'reconnected' = 'change') {
  state = { ...state, ...next }
  emit(event)
}

/** Сервер достижим, если ответил хоть чем-то: 401 — тоже ответ. */
async function reachable(): Promise<boolean> {
  try {
    const response = await fetch('/api/auth/me/', { credentials: 'include', cache: 'no-store' })
    return response.status < 500
  } catch {
    return false
  }
}

function schedule() {
  const delay = DELAYS[Math.min(state.attempt, DELAYS.length - 1)]
  set({ nextIn: delay })
  timer = window.setTimeout(() => void probe(), delay * 1000)
}

async function probe() {
  timer = null
  if (probing) return
  probing = true
  const ok = await reachable()
  probing = false
  if (ok) {
    onlineManager.setOnline(true)
    set({ offline: false, attempt: 0, nextIn: 0 }, 'reconnected')
    return
  }
  set({ attempt: state.attempt + 1 })
  schedule()
}

/**
 * Клиент подозревает, что сервера нет. Проверяем сами: если это была
 * настоящая пятисотка живого сервера, режим «нет связи» не включится.
 */
export function suspectOffline(): void {
  if (state.offline || probing) return
  void (async () => {
    if (await reachable()) return
    onlineManager.setOnline(false)
    set({ offline: true, attempt: 1 })
    schedule()
  })()
}

/** Попробовать прямо сейчас, не дожидаясь таймера — кнопка на полосе. */
export function retryNow(): void {
  if (!state.offline) return
  if (timer !== null) {
    window.clearTimeout(timer)
    timer = null
  }
  void probe()
}

export function getConnection(): ConnectionState {
  return state
}

export function subscribeConnection(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Ошибка сети — не ответ сервера, а его отсутствие. */
export class NetworkError extends Error {
  constructor(message = 'Нет связи с сервером') {
    super(message)
    this.name = 'NetworkError'
  }
}

export function isNetworkError(error: unknown): boolean {
  return error instanceof NetworkError
}
