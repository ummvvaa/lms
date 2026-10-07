import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'
import type { UsageFilters, UsageSummary } from './types'

export function usageParams(filters: UsageFilters) {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value)
  })
  return params
}
export function useUsageSummary(filters: UsageFilters, page: number, enabled: boolean) {
  const params = usageParams(filters)
  params.set('page', String(page))
  params.set('page_size', '50')
  const query = params.toString()
  return useQuery({
    queryKey: ['usage-summary', query],
    queryFn: () => get<UsageSummary>(`/usage/?${query}`),
    enabled,
  })
}
