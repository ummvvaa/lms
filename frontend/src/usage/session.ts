/** Очередь событий принадлежит текущей сессии; при смене cookie старые события забываются. */
let owner: number | null = null
let revision = 0
let changing = false
let credential: string | null = null
const listeners = new Set<() => void>()

export function usageSessionChanging() {
  return changing
}
export function usageOwner() {
  return owner
}
export function usageSessionSnapshot() {
  return `${owner ?? ''}:${revision}`
}
export function subscribeUsageSession(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
export function setUsageOwner(next: number | null, confirmedCredential?: string) {
  if (
    changing ||
    (owner === next && (confirmedCredential === undefined || credential === confirmedCredential))
  )
    return
  owner = next
  if (confirmedCredential !== undefined) credential = confirmedCredential
  revision += 1
  listeners.forEach((listener) => listener())
}
export function clearUsageSession() {
  owner = null
  credential = null
  revision += 1
  listeners.forEach((listener) => listener())
}

export function beginUsageSessionChange() {
  changing = true
  clearUsageSession()
}
export function finishUsageSessionChange(next: number | null) {
  changing = false
  setUsageOwner(next)
}
