import { describe, expect, it } from 'vitest'
import { filterImportRows, importPage, type ImportStatus } from './importRows'

const rows = Array.from({ length: 63 }, (_, index) => ({
  id: index + 1,
  search: `Student ${index + 1}`,
  status: (index === 62 ? 'error' : 'created') as ImportStatus,
}))

describe('import preview across the full file', () => {
  it('keeps the final row accessible beyond the first page', () => {
    expect(importPage(rows, 1).rows).toHaveLength(50)
    expect(importPage(rows, 2).rows.map((row) => row.id)).toEqual(
      Array.from({ length: 13 }, (_, index) => index + 51),
    )
  })
  it('finds errors and names outside the visible page without changing the apply input', () => {
    const before = structuredClone(rows)
    expect(filterImportRows(rows, ' student 63 ', '')).toEqual([rows[62]])
    expect(filterImportRows(rows, '', 'error')).toEqual([rows[62]])
    expect(rows).toEqual(before)
    expect(rows).toHaveLength(63)
  })
  it('returns to an existing page after a filter reduces the result', () => {
    expect(importPage(filterImportRows(rows, '', 'error'), 2)).toEqual({
      page: 1,
      pages: 1,
      rows: [rows[62]],
    })
    expect(importPage([], 2)).toEqual({ page: 1, pages: 1, rows: [] })
  })
})
