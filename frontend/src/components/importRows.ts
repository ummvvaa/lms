/** Предпросмотр не меняет исходные строки: применение использует ответ сервера целиком. */
export type ImportStatus = 'created' | 'updated' | 'skipped' | 'error'
export const IMPORT_PAGE_SIZE = 50
export interface SearchableImportRow {
  status: ImportStatus
  search: string
}
export function filterImportRows<T extends SearchableImportRow>(
  rows: T[],
  query: string,
  status: string,
): T[] {
  const needle = query.trim().toLocaleLowerCase()
  return rows.filter(
    (row) =>
      (!status || row.status === status) && (!needle || row.search.toLocaleLowerCase().includes(needle)),
  )
}
export function importPage<T>(rows: T[], requested: number) {
  const pages = Math.max(1, Math.ceil(rows.length / IMPORT_PAGE_SIZE))
  const page = Math.min(Math.max(1, requested), pages)
  return { page, pages, rows: rows.slice((page - 1) * IMPORT_PAGE_SIZE, page * IMPORT_PAGE_SIZE) }
}
