/**
 * Профтест: тесты профориентации файлом, прохождение, баллы по шкалам, разборы.
 *
 * Учитель профориентации (при любой роли) и администратор ведут тесты и
 * запускают разбор; результаты читают они же, Асем и куратор своих групп;
 * ученик проходит назначенные тесты и видит свои баллы, разбор — только
 * после «Показать ученику». Сервер — `backend/career/`.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, get, patch, post } from './client'

export interface CareerTestBrief {
  id: number
  title: string
  is_active: boolean
}

export interface CareerTestRow extends CareerTestBrief {
  instruction: string
  analysis_min_score: number
  items: number
  scales: number
  assigned: number
  done: number
  in_progress: number
  file_name: string
  created_at: string
  created_by: { id: number; full_name: string; short: string } | null
}

export interface CareerTestGroup {
  group: number
  code: string
  parallel: number
  whole: boolean
  students: number[]
}

export interface CareerTestDetail extends CareerTestBrief {
  instruction: string
  analysis_min_score: number
  file_name: string
  created_at: string
  created_by: { id: number; full_name: string; short: string } | null
  options: { id: number; label: string; value: number }[]
  scales: { id: number; code: string; title: string; description: string }[]
  items: { id: number; number: number; text: string; scale: string; sign: number; choices: { id: number; label: string; scale: string; value: number }[] }[]
  ranges: { scale: string; low: number; high: number; label: string }[]
  groups: CareerTestGroup[]
}

export interface CareerFileReport {
  ok: boolean
  title: string
  instruction: string
  threshold: number
  options: { label: string; value: number }[]
  scales: { code: string; title: string }[]
  items: number
  ranges: number
  errors: string[]
  warnings: string[]
  detail?: string
}

export interface CareerScore {
  scale: number
  code: string
  title: string
  score: number
  label: string
  low: number
  high: number
}

export interface CareerAttempt {
  id: number
  test: CareerTestBrief
  status: 'in_progress' | 'done'
  started_at: string
  finished_at: string | null
  archived_at: string | null
  threshold: number
  scores?: CareerScore[]
  student?: { id: number; full_name: string; short: string; group: string }
}

export interface CareerDirection {
  id: number
  order: number
  title: string
  reasoning: string
  professions: string
  subjects: string
  exams: string
  programs: { id: number; name: string; university: string; level_title: string }[]
  /** объяснение для ученика, на «ты» — только сотрудникам; ученику приходит в `reasoning` */
  reasoning_student?: string
}

export interface CareerAnalysis {
  id: number
  status: 'running' | 'done' | 'failed'
  status_title: string
  summary: string
  error: string
  created_at: string
  finished_at: string | null
  language: string
  visible_to_student: boolean
  edited_at: string | null
  tests: { id: number; title: string; attempt: number; finished_at: string | null }[]
  directions: CareerDirection[]
  /** версия для ученика (пишется моделью при первом показе) — только сотрудникам */
  summary_student?: string
  has_student_version?: boolean
  /** только сотрудникам: ученику имена не приходят */
  student?: { id: number; full_name: string; short: string; group: string }
  created_by?: { id: number; full_name: string; short: string } | null
  edited_by?: { id: number; full_name: string; short: string } | null
}

export interface CareerGroup {
  id: number
  code: string
  parallel: number
  assignable: boolean
  students: { id: number; full_name: string; short: string; group: string }[]
}

export type CellStatus = 'none' | 'assigned' | 'in_progress' | 'done'

export interface CareerResults {
  group: { id: number; code: string; parallel: number } | null
  tests: (CareerTestBrief & { items: number; assigned: number })[]
  students: {
    id: number
    full_name: string
    short: string
    group: string
    cells: Record<string, { status: CellStatus; attempt: number | null; finished_at?: string | null; answered?: number }>
  }[]
}

export interface CareerAnalyses {
  manage: boolean
  /** показываются ли разборы ученику (флаг сервера); нет — переключателя и версии на «ты» на экране нет */
  student_sees: boolean
  group: { id: number; code: string; parallel: number } | null
  tests: { id: number; title: string; done: number }[]
  analyses: CareerAnalysis[]
}

export interface MyCareer {
  tests: (CareerTestBrief & { instruction: string; items: number; status: CellStatus; attempt: number | null; answered: number; finished_at: string | null })[]
  analyses: CareerAnalysis[]
}

export interface MyAttempt extends CareerAttempt {
  instruction: string
  options?: { id: number; label: string; value: number }[]
  items?: { id: number; number: number; text: string; choices: { id: number; label: string }[] }[]
  answers?: Record<string, { option: number | null; choice: number | null }>
}

export interface StudentCareer {
  student: { id: number; full_name: string; short: string; group: string }
  attempts: CareerAttempt[]
  analyses: CareerAnalysis[]
}

const KEY = ['career']

function useCareerMutation<TInput, TOut>(fn: (input: TInput) => Promise<TOut>, saved = false) {
  const client = useQueryClient()
  return useMutation({
    meta: saved ? { saved: true } : undefined,
    mutationFn: fn,
    onSuccess: () => void client.invalidateQueries({ queryKey: KEY }),
  })
}

function fileBody(file: File): FormData {
  const body = new FormData()
  body.append('file', file)
  return body
}

// --- учитель и читатели ---------------------------------------------------------

export const useCareerTests = (enabled = true) =>
  useQuery({ queryKey: [...KEY, 'tests'], queryFn: () => get<{ manage: boolean; tests: CareerTestRow[] }>('/career/tests/'), enabled })

export const useCareerTest = (id: number | null) =>
  useQuery({ queryKey: [...KEY, 'test', id], queryFn: () => get<CareerTestDetail>(`/career/tests/${id}/`), enabled: id !== null })

export const useCareerPreview = () =>
  useMutation({ mutationFn: (file: File) => api<CareerFileReport>('/career/tests/preview/', { method: 'POST', body: fileBody(file) }) })

export const useCareerUpload = () =>
  useCareerMutation((file: File) => api<CareerTestDetail>('/career/tests/', { method: 'POST', body: fileBody(file) }))

export const useCareerTestPatch = () =>
  useCareerMutation((input: { id: number; is_active?: boolean; analysis_min_score?: number; title?: string }) => {
    const { id, ...body } = input
    return patch<CareerTestDetail>(`/career/tests/${id}/`, body)
  }, true)

export const useCareerTestDelete = () =>
  useCareerMutation((id: number) => api<{ archived: boolean }>(`/career/tests/${id}/`, { method: 'DELETE' }))

export const useCareerAssign = () =>
  useCareerMutation((input: { id: number; groups: { group: number; students: number[] | null }[] }) =>
    api<CareerTestDetail>(`/career/tests/${input.id}/assignments/`, { method: 'PUT', body: JSON.stringify({ groups: input.groups }) }), true)

export const useCareerGroups = (enabled = true) =>
  useQuery({ queryKey: [...KEY, 'groups'], queryFn: () => get<{ manage: boolean; groups: CareerGroup[] }>('/career/groups/'), enabled })

export const useCareerResults = (group: number | null) =>
  useQuery({ queryKey: [...KEY, 'results', group], queryFn: () => get<CareerResults>(`/career/results/?group=${group}`), enabled: group !== null })

export const useCareerAttempt = (id: number | null) =>
  useQuery({ queryKey: [...KEY, 'attempt', id], queryFn: () => get<CareerAttempt>(`/career/attempts/${id}/`), enabled: id !== null })

export const useCareerRetake = () => useCareerMutation((id: number) => post<CareerAttempt>(`/career/attempts/${id}/retake/`))

export const useCareerAnalyses = (group: number | null) =>
  useQuery({ queryKey: [...KEY, 'analyses', group], queryFn: () => get<CareerAnalyses>(`/career/analyses/?group=${group}`), enabled: group !== null })

export interface StartAnalysesResult {
  created: number
  reused: number
  skipped: { student: { id: number; full_name: string; short: string }; reason: string }[]
  job: number | null
}

export const useCareerStartAnalyses = () =>
  useCareerMutation((input: { group: number; tests: number[]; students?: number[] | null; force?: boolean }) => post<StartAnalysesResult>('/career/analyses/', input))

export const useCareerAnalysisPatch = () =>
  useCareerMutation((input: { id: number; summary?: string; summary_student?: string; visible_to_student?: boolean; directions?: Partial<CareerDirection>[] }) => {
    const { id, ...body } = input
    return patch<CareerAnalysis>(`/career/analyses/${id}/`, body)
  }, true)

export const useStudentCareer = (student: number | null) =>
  useQuery({ queryKey: [...KEY, 'student', student], queryFn: () => get<StudentCareer>(`/career/students/${student}/`), enabled: student !== null })

// --- ученик -----------------------------------------------------------------------

export const useMyCareer = (enabled = true) => useQuery({ queryKey: [...KEY, 'my'], queryFn: () => get<MyCareer>('/career/my/'), enabled })

export const useMyAttempt = (id: number | null) =>
  useQuery({ queryKey: [...KEY, 'my-attempt', id], queryFn: () => get<MyAttempt>(`/career/my/attempts/${id}/`), enabled: id !== null })

export const useMyStart = () => useCareerMutation((test: number) => post<MyAttempt>(`/career/my/tests/${test}/start/`))

export const useMyAnswers = () =>
  useMutation({
    mutationFn: (input: { attempt: number; answers: { item: number; option?: number | null; choice?: number | null }[] }) =>
      post<{ answered: number; total: number }>(`/career/my/attempts/${input.attempt}/answers/`, { answers: input.answers }),
  })

export const useMyFinish = () => useCareerMutation((attempt: number) => post<MyAttempt>(`/career/my/attempts/${attempt}/finish/`))
