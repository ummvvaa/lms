/**
 * D75: после ответа на оценку клетка журнала обновляется из ответа, а не ждёт
 * перезапроса журнала. Журнал чужого курса и чужой урок не трогаются.
 */
import { describe, expect, it } from 'vitest'
import type { Journal, JournalColumn, RosterRow } from './academics'
import { patchJournal, type MarksAnswer } from './journalPatch'

function column(lesson: number, extra: Partial<JournalColumn> = {}): JournalColumn {
  return {
    lesson,
    date: '2026-10-06',
    weekday: 'вт',
    slot: 1,
    kind: 'fo',
    kind_label: 'ФО',
    max_score: null,
    state: 'past',
    future: false,
    unmarked: true,
    locked: false,
    may_grade: true,
    may_mark: true,
    teacher: '',
    topic: '',
    is_today: true,
    ...extra,
  }
}

function journal(): Journal {
  const student = (id: number, name: string) => ({ id, full_name: name, short: name, group: 'TOKYO', cells: [{ mark: null, grade: null, comment: '' }, { mark: null, grade: null, comment: '' }], stats: {} as Journal['rows'][number]['stats'] })
  return {
    course: { id: 1372 } as Journal['course'],
    period: { code: 'q1', title: '1 четверть', from: '2026-09-01', to: '2026-10-23' },
    periods: [],
    quarter: null,
    scheme: 'fo',
    columns: [column(36823), column(36824, { unmarked: false })],
    rows: [student(1, 'Ким Алия'), student(2, 'Ли Данияр')],
  } as unknown as Journal
}

function roster(rows: Partial<RosterRow>[]): RosterRow[] {
  return rows.map((row) => ({ id: 0, full_name: '', short: '', group: '', mark: null, grade: null, comment: '', excused: false, absences: 0, fo_avg: null, ...row }) as RosterRow)
}

describe('patchJournal', () => {
  it('ставит оценку и отметку в клетку урока из ответа и гасит «не отмечен»', () => {
    const answer: MarksAnswer = {
      lesson: { id: 36823, course: 1372, marked: true },
      roster: roster([
        { id: 1, mark: 'present', grade: 8, comment: 'Teest teeeest' },
        { id: 2, mark: 'absent', grade: null, comment: '' },
      ]),
    }
    const next = patchJournal(journal(), answer)
    expect(next.rows[0].cells[0]).toMatchObject({ grade: 8, comment: 'Teest teeeest', mark: 'present' })
    expect(next.rows[1].cells[0]).toMatchObject({ mark: 'absent', grade: null })
    // соседняя колонка не тронута
    expect(next.rows[0].cells[1]).toEqual({ mark: null, grade: null, comment: '' })
    expect(next.columns[0].unmarked).toBe(false)
    expect(next.columns[1].unmarked).toBe(false)
  })

  it('чужой курс и чужой урок возвращают тот же объект — кэш не пересобирается зря', () => {
    const before = journal()
    expect(patchJournal(before, { lesson: { id: 36823, course: 999 }, roster: roster([{ id: 1, grade: 7 }]) })).toBe(before)
    expect(patchJournal(before, { lesson: { id: 1, course: 1372 }, roster: roster([{ id: 1, grade: 7 }]) })).toBe(before)
    expect(patchJournal(before, { lesson: { id: 36823, course: 1372 } })).toBe(before)
  })

  it('опоздание приходит с временем прихода и признаком «считается пропуском»', () => {
    const next = patchJournal(journal(), {
      lesson: { id: 36823, course: 1372, marked: true },
      roster: roster([{ id: 1, mark: 'late', arrived: '08:25', late_by: 25, late_as_absent: true }]),
    })
    expect(next.rows[0].cells[0]).toEqual({ mark: 'late', grade: null, comment: '', arrived: '08:25', late_by: 25, late_as_absent: true })
  })

  it('снятая оценка уходит из клетки', () => {
    const marked = patchJournal(journal(), { lesson: { id: 36823, course: 1372 }, roster: roster([{ id: 1, grade: 8 }]) })
    const cleared = patchJournal(marked, { lesson: { id: 36823, course: 1372 }, roster: roster([{ id: 1, grade: null }]) })
    expect(cleared.rows[0].cells[0].grade).toBeNull()
  })
})
