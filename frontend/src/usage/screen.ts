import { matchPath } from 'react-router'
import type { UsageRegistry } from './types'

export function canonicalUsageScreen(pathname: string, registry: UsageRegistry): string | null {
  const allowed = new Set(registry.client_screens)
  return (
    registry.screens.find(
      (screen) =>
        allowed.has(screen.key) &&
        (screen.aliases.length ? screen.aliases : [screen.key]).some((path) =>
          matchPath({ path, end: true }, pathname),
        ),
    )?.key ?? null
  )
}
