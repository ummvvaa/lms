/**
 * Клетки журнала — из ответа на отметку или оценку, сразу.
 *
 * Запись оценки отвечает составом урока (`roster`) с отметкой, оценкой
 * и комментарием каждого ученика. Раньше журнал ждал полного перезапроса
 * (`GET /journals/<id>/`), а каждое следующее нажатие учителя отменяло
 * идущий перезапрос и начинало заново — при медленном ответе клетка так
 * и стояла пустой (D75, прод 06.10.2026). Теперь клетка колонки урока
 * обновляется из ответа, а перезапрос журнала идёт следом за сводками.
 */
import type { Journal, JournalCell, RosterRow } from './academics'

/** Что приходит в ответе на отметку и на оценку: урок и его состав. */
export interface MarksAnswer {
  lesson: { id: number; course: number; marked?: boolean }
  roster?: RosterRow[]
}

/** Журнал с подставленными клетками колонки урока; не его урок — тот же объект. */
export function patchJournal(journal: Journal, answer: MarksAnswer): Journal {
  if (!answer.roster || journal.course.id !== answer.lesson.course) return journal
  const at = journal.columns.findIndex((column) => column.lesson === answer.lesson.id)
  if (at < 0) return journal
  const byStudent = new Map(answer.roster.map((row) => [row.id, row]))
  let touched = false
  const rows = journal.rows.map((row) => {
    const fresh = byStudent.get(row.id)
    if (!fresh) return row
    const cell: JournalCell = {
      mark: fresh.mark,
      grade: fresh.grade,
      comment: fresh.comment,
      arrived: fresh.arrived ?? null,
      late_by: fresh.late_by ?? null,
      late_as_absent: fresh.late_as_absent ?? false,
    }
    const current = row.cells[at]
    if (current && sameCell(current, cell)) return row
    touched = true
    const cells = row.cells.slice()
    cells[at] = cell
    return { ...row, cells }
  })
  // урок с отметкой или оценкой отмечен: «не отмечен» в шапке колонки гаснет
  const column = journal.columns[at]
  const marked = answer.lesson.marked ?? true
  const columns = column.unmarked && marked ? journal.columns.map((item, index) => (index === at ? { ...item, unmarked: false } : item)) : journal.columns
  if (!touched && columns === journal.columns) return journal
  return { ...journal, rows, columns }
}

function sameCell(a: JournalCell, b: JournalCell): boolean {
  return (
    a.mark === b.mark &&
    a.grade === b.grade &&
    a.comment === b.comment &&
    (a.arrived ?? null) === (b.arrived ?? null) &&
    (a.late_by ?? null) === (b.late_by ?? null) &&
    Boolean(a.late_as_absent) === Boolean(b.late_as_absent)
  )
}
