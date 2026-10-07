export interface UsageRegistry {
  can_read: boolean
  batch_limit: number
  flush_interval_ms: number
  client_actions: string[]
  client_screens: string[]
  actions: { key: string; title: string; source: 'client' | 'server'; screen: string | null }[]
  screens: { key: string; title: string; aliases: string[] }[]
  roles: { key: string; title: string }[]
}
export interface UsageClientEvent {
  id: string
  action: string
  screen: string
}
export type UsageDimension = 'action' | 'user' | 'role' | 'day'
export interface UsageFilters {
  from?: string
  to?: string
  by: UsageDimension
  action?: string
  screen?: string
  role?: string
  user?: string
}
export interface UsageSummary {
  period: { from: string; to: string }
  by: UsageDimension
  cards: {
    active_users: number
    actions: number
    most_frequent: { key: string; title: string; count: number } | null
    never_logged_in: number
  }
  count: number
  next: string | null
  previous: string | null
  results: { key: string; title: string; count: number; users: number; last_at: string | null }[]
}
