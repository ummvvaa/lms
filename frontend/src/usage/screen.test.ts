import { describe, expect, it } from 'vitest'
import { canonicalUsageScreen } from './screen'
import type { UsageRegistry } from './types'

const registry = {
  client_screens: ['/students/:id', '/dashboard'],
  screens: [
    { key: '/students/:id', title: 'Student', aliases: ['/students/:id'] },
    { key: '/dashboard', title: 'Dashboard', aliases: ['/dashboard'] },
    { key: '/users', title: 'Users', aliases: ['/users'] },
  ],
} as UsageRegistry

describe('canonical usage screens', () => {
  it('returns only a permitted registry key, never the record id', () => {
    expect(canonicalUsageScreen('/students/734', registry)).toBe('/students/:id')
    expect(canonicalUsageScreen('/dashboard', registry)).toBe('/dashboard')
    expect(canonicalUsageScreen('/users', registry)).toBeNull()
    expect(canonicalUsageScreen('/private/734', registry)).toBeNull()
    expect(canonicalUsageScreen('/students/734/private', registry)).toBeNull()
  })
})
