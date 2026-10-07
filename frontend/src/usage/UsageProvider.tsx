import { useCallback, useEffect, useMemo, useSyncExternalStore, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useLocation } from 'react-router'
import { useAuth } from '../auth/AuthContext'
import { UsageContext, useTrack } from './context'
import { UsageBuffer } from './buffer'
import { clearUsageSession, subscribeUsageSession, usageOwner, usageSessionSnapshot } from './session'
import { createUsageSender, usageRegistry } from './transport'
import { canonicalUsageScreen } from './screen'

export function useUsageRegistry() {
  const { me } = useAuth()
  return useQuery({
    queryKey: ['usage-registry', me?.id, me?.language, me?.role, me?.teaches, me?.sections],
    queryFn: ({ signal }) => usageRegistry(signal),
    enabled: Boolean(me && !me.must_change_password && usageOwner() === me.id),
    staleTime: 60_000,
    retry: 1,
  })
}

function UsageSession({
  owner,
  session,
  children,
}: {
  owner: number | null
  session: string
  children: ReactNode
}) {
  const location = useLocation()
  const registry = useUsageRegistry()
  const buffer = useMemo(
    () =>
      new UsageBuffer(
        createUsageSender(),
        () => owner !== null && usageOwner() === owner && usageSessionSnapshot() === session,
      ),
    [owner, session],
  )
  const track = useCallback(
    (action: string) => {
      if (!registry.data) return
      const screen = canonicalUsageScreen(location.pathname, registry.data)
      if (!screen) return
      buffer.configure(registry.data)
      buffer.track(action, screen, action === 'screen.open' ? location.pathname : undefined)
    },
    [buffer, registry.data, location.pathname],
  )

  useEffect(() => {
    const unsubscribe = subscribeUsageSession(() => buffer.reset())
    const flush = () => {
      void buffer.flush(document.visibilityState === 'hidden')
    }
    const interval = window.setInterval(flush, Math.max(1000, registry.data?.flush_interval_ms ?? 10_000))
    const hidden = () => {
      if (document.visibilityState === 'hidden') void buffer.flush(true)
    }
    const leaving = () => {
      void buffer.flush(true)
    }
    window.addEventListener('online', flush)
    window.addEventListener('pagehide', leaving)
    document.addEventListener('visibilitychange', hidden)
    return () => {
      unsubscribe()
      window.clearInterval(interval)
      window.removeEventListener('online', flush)
      window.removeEventListener('pagehide', leaving)
      document.removeEventListener('visibilitychange', hidden)
      buffer.reset()
    }
  }, [buffer, registry.data?.flush_interval_ms])

  return <UsageContext.Provider value={track}>{children}</UsageContext.Provider>
}

export function UsageScreenVisit() {
  const track = useTrack('screen.open')
  useEffect(() => {
    track()
  }, [track])
  return null
}

export default function UsageProvider({ children }: { children: ReactNode }) {
  const { me } = useAuth()
  const session = useSyncExternalStore(subscribeUsageSession, usageSessionSnapshot, usageSessionSnapshot)
  const owner = me && !me.must_change_password && usageOwner() === me.id ? me.id : null
  useEffect(() => {
    const changed = (event: StorageEvent) => {
      if (event.key === 'owner' && event.newValue !== String(usageOwner())) clearUsageSession()
    }
    window.addEventListener('storage', changed)
    return () => window.removeEventListener('storage', changed)
  }, [])
  return (
    <UsageSession owner={owner} session={session}>
      {children}
    </UsageSession>
  )
}
