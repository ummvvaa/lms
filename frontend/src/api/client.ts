/**
 * HTTP-клиент. Сессия живёт в httpOnly cookie, поэтому токенов здесь нет —
 * достаточно credentials: 'include' и CSRF-заголовка на небезопасных методах.
 */

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

  const response = await fetch(`/api${path}`, { ...options, method, headers, credentials: 'include' })

  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, body)
  return body as T
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
  const response = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    credentials: 'include',
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => null))

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
