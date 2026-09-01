/**
 * HTTP-клиент. Сессия живёт в httpOnly cookie, поэтому токенов здесь нет —
 * достаточно credentials: 'include' и CSRF-заголовка на небезопасных методах.
 */

import { NetworkError, suspectOffline } from './connection'

export { NetworkError, isNetworkError } from './connection'

export class ApiError extends Error {
  constructor(
    public status: number,
    public payload: unknown,
  ) {
    super(
      typeof payload === 'object' && payload && 'detail' in payload
        ? String(payload.detail)
        : `HTTP ${status}`,
    )
    this.name = 'ApiError'
  }
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  // FormData свой Content-Type ставит сам — вместе с boundary, который
  // мы знать не можем. Подставить сюда application/json значит сломать
  // любую загрузку файла: сервер получит multipart с чужим заголовком
  const isForm = typeof FormData !== 'undefined' && options.body instanceof FormData
  if (!headers.has('Content-Type') && options.body && !isForm) {
    headers.set('Content-Type', 'application/json')
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) headers.set('X-CSRFToken', csrfToken())

  let response: Response
  try {
    response = await fetch(`/api${path}`, { ...options, method, headers, credentials: 'include' })
  } catch {
    // запрос не дошёл: обрыв, перезапуск, отказ соединения. Это не «не вошёл»
    // и не ошибка данных — приложение переходит в режим «нет связи» (фаза 36)
    suspectOffline()
    throw new NetworkError()
  }

  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => null)
  if (isGatewayFailure(response.status, body)) {
    suspectOffline()
    throw new NetworkError()
  }
  if (!response.ok) throw new ApiError(response.status, body)
  return body as T
}

/**
 * Ответил не сервер, а прокси перед ним: nginx отвечает 502/503/504, Vite —
 * 500 без JSON («proxy error»). Настоящая пятисотка сервера приходит
 * с JSON-телом и остаётся обычной ошибкой запроса.
 *
 * 503 отвечает и наш сервер — когда раздел честно недоступен (профтест
 * без ключа модели). У такого ответа есть JSON с причиной, и показывать
 * вместо неё «Нет связи с сервером» значит прятать объяснение, ради
 * которого этот код и выбран.
 */
function isGatewayFailure(status: number, body: unknown): boolean {
  if (status === 502 || status === 504) return true
  return (status === 500 || status === 503) && body === null
}

export const get = <T>(path: string) => api<T>(path)
export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
export const patch = <T>(path: string, body: unknown) =>
  api<T>(path, { method: 'PATCH', body: JSON.stringify(body) })

/**
 * Скачать файл, который сервер собрал по запросу.
 *
 * Обычный `api()` разбирает ответ как JSON — здесь приходит CSV, и его
 * надо отдать браузеру как файл. Ссылки на такой файл не существует:
 * он живёт ровно один ответ и на сервере не хранится.
 */
export async function download(path: string, body: unknown, filename: string): Promise<void> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      credentials: 'include',
      body: JSON.stringify(body),
    })
  } catch {
    suspectOffline()
    throw new NetworkError()
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    if (isGatewayFailure(response.status, payload)) {
      suspectOffline()
      throw new NetworkError()
    }
    throw new ApiError(response.status, payload)
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
