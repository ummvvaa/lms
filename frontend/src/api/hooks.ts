/** Запросы к API через TanStack Query. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'
import type { DomainMeta, Paginated } from './types'

export interface StudentRow {
  id: number
  full_name: string
  email: string
  grade: number
  group: number | null
  group_code: string | null
  graduation_year: number
}

export interface ReadinessPart {
  code: string
  title: string
  value: number
  weight: number
  recoverable: number
}

export interface Readiness {
  score: number
  parts: ReadinessPart[]
  weakest: string | null
  weakest_title: string | null
}

export type ProfileValues = Record<string, unknown>

export interface StudentCard extends StudentRow {
  last_name: string
  first_name: string
  middle_name: string
  is_active: boolean
  behavior: ProfileValues
  admission: ProfileValues
  exam: ProfileValues
  talent: ProfileValues
  sport: ProfileValues
  readiness?: Readiness
}

export interface AuditEntry {
  id: number
  created_at: string
  model_label: string
  field_name: string
  domain_code: string
  old_value: string
  new_value: string
  source: string
  actor_name: string
}

export interface BatchChange {
  student: number
  model: string
  field: string
  value: unknown
  expected?: unknown
}

export interface BatchResult {
  applied: number
  skipped: number
  audit_entries: number
  rejected: { student?: number; field?: string; reason: string }[]
  conflicts: { student: number; field: string; expected: string; actual: string }[]
}

export const useDomainMeta = () =>
  useQuery({ queryKey: ['domains'], queryFn: () => get<DomainMeta>('/meta/domains/'), staleTime: 5 * 60_000 })

export function useStudents(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') search.set(k, String(v))
  })
  const qs = search.toString()
  return useQuery({
    queryKey: ['students', qs],
    queryFn: () => get<Paginated<StudentCard>>(`/students/${qs ? `?${qs}` : ''}`),
    placeholderData: (prev) => prev,
  })
}

export const useStudent = (id: number | null) =>
  useQuery({
    queryKey: ['student', id],
    queryFn: () => get<StudentCard>(`/students/${id}/`),
    enabled: id !== null,
  })

export const useStudentHistory = (id: number | null) =>
  useQuery({
    queryKey: ['student', id, 'history'],
    queryFn: () => get<AuditEntry[]>(`/students/${id}/history/`),
    enabled: id !== null,
  })

export const useMyProfile = () =>
  useQuery({ queryKey: ['student', 'me'], queryFn: () => get<StudentCard>('/students/me/') })

export const useDashboard = <T>(code: string) =>
  useQuery({ queryKey: ['dashboard', code], queryFn: () => get<T>(`/dashboards/${code}/`) })

export function useBatchSave() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changes: BatchChange[]) => post<BatchResult>('/batch/save/', { changes }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['students'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

// --- Фаза 4: соответствие, роадмап, эссе ---

export interface MatchCriterion {
  code: string
  title: string
  current: number | null
  threshold: number
  gap: number
  gap_exact: number
  is_met: boolean
  is_unknown: boolean
  phrase: string
}

export interface MatchResult {
  program: number
  program_name: string
  university_name: string
  country: string
  status: 'open' | 'gap' | 'unknown'
  has_requirements: boolean
  is_open: boolean
  summary: string
  criteria: MatchCriterion[]
}

export interface WhatIf {
  ielts_delta: number
  sat_delta: number
  open_before: number
  open_after: number
  unlocked: MatchResult[]
}

export type TaskStatus = 'todo' | 'in_progress' | 'review' | 'done'

export interface Task {
  id: number
  student: number
  title: string
  category: string
  priority: 'high' | 'medium' | 'low'
  description: string
  status: TaskStatus
  due_date: string | null
  due_date_effective: string | null
  from_deadline: boolean
  university_name: string | null
  comments: { id: number; text: string; author_name: string; created_at: string }[]
}

export interface EssayVersion {
  id: number
  number: number
  text: string
  word_count: number
  author_name: string
  created_at: string
}

export interface Essay {
  id: number
  student: number
  program: number | null
  program_name: string | null
  essay_type: string
  title: string
  status: 'draft' | 'review' | 'revision' | 'done'
  versions: EssayVersion[]
  comments: { id: number; text: string; author_name: string; created_at: string }[]
}

export const useMyUniversities = (studentId?: number) =>
  useQuery({
    queryKey: ['match', 'my-universities', studentId ?? 'me'],
    queryFn: () => get<MatchResult[]>(`/match/my-universities/${studentId ? `?student=${studentId}` : ''}`),
  })

export const useOpenPrograms = (studentId?: number, onlyOpen = false) =>
  useQuery({
    queryKey: ['match', 'open', studentId ?? 'me', onlyOpen],
    queryFn: () => {
      const params = new URLSearchParams()
      if (studentId) params.set('student', String(studentId))
      if (onlyOpen) params.set('only_open', '1')
      const qs = params.toString()
      return get<MatchResult[]>(`/match/open-programs/${qs ? `?${qs}` : ''}`)
    },
  })

export function useWhatIf() {
  return useMutation({
    mutationFn: (payload: { ielts_delta?: number; sat_delta?: number; student?: number }) =>
      post<WhatIf>('/match/what-if/', payload),
  })
}

export const useMyTasks = () =>
  useQuery({ queryKey: ['tasks', 'my'], queryFn: () => get<Task[]>('/tasks/my/') })

export function useTaskStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: TaskStatus }) =>
      post<Task>(`/tasks/${id}/status/`, { status }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })
}

export const useMyEssays = (studentId?: number) =>
  useQuery({
    queryKey: ['essays', studentId ?? 'me'],
    queryFn: () => get<Paginated<Essay>>(`/essays/${studentId ? `?student=${studentId}` : ''}`),
  })

export function useAddEssayVersion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, text }: { id: number; text: string }) =>
      post<EssayVersion>(`/essays/${id}/versions/`, { text }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['essays'] })
    },
  })
}

// --- Фаза 5: предложения и именованные действия ---

export interface SuggestionChange {
  id: number
  student: number | null
  student_name: string | null
  model_label: string
  field_name: string
  old_value: string
  new_value: string
  confidence: string
  source_ref: string
  source_quote: string
  is_accepted: boolean
  is_applied: boolean
  conflict: string
}

export interface Suggestion {
  id: number
  author_name: string
  role: string
  domain_code: string
  command: string
  source_type: string
  source_ref: string
  status: 'draft' | 'pending' | 'applied' | 'partially_applied' | 'rejected' | 'reverted'
  created_at: string
  changes: SuggestionChange[]
}

export interface Ambiguity {
  query: string
  candidates: { student: number; full_name: string; group: string | null; confidence: number }[]
  is_ambiguous: boolean
  is_missing: boolean
  raw?: string
  values?: Record<string, unknown>
}

export interface CommandButton {
  code: string
  title: string
  hint: string
  input_kind: 'text' | 'file' | 'image' | 'selection' | 'none'
}

export interface TaskState<T> {
  id: string
  state: 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE'
  progress?: { stage: string }
  result?: T
  error?: string
}

export interface PasteResult {
  suggestion: number
  rows: number
  ambiguities: Ambiguity[]
  rejected: { reason: string; field?: string }[]
}

export const useCommands = () =>
  useQuery({
    queryKey: ['commands'],
    queryFn: () => get<{ commands: CommandButton[] }>('/commands/'),
    staleTime: 5 * 60_000,
  })

export const useSuggestions = () =>
  useQuery({ queryKey: ['suggestions'], queryFn: () => get<Paginated<Suggestion>>('/suggestions/') })

export const useSuggestion = (id: number | null) =>
  useQuery({
    queryKey: ['suggestion', id],
    queryFn: () => get<Suggestion>(`/suggestions/${id}/`),
    enabled: id !== null,
  })

export function usePaste() {
  return useMutation({ mutationFn: (text: string) => post<{ task: string }>('/commands/paste/', { text }) })
}

/** Опрос статуса фоновой задачи: эндпойнт вернул id, показываем прогресс. */
export function useTaskPolling<T>(taskId: string | null) {
  return useQuery({
    queryKey: ['task', taskId],
    queryFn: () => get<TaskState<T>>(`/tasks/status/${taskId}/`),
    enabled: taskId !== null,
    refetchInterval: (query) => {
      const state = query.state.data?.state
      return state === 'SUCCESS' || state === 'FAILURE' ? false : 1000
    },
  })
}

export function useApplySuggestion() {
  const queryClient = useQueryClient()
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['suggestion'] })
    void queryClient.invalidateQueries({ queryKey: ['suggestions'] })
    void queryClient.invalidateQueries({ queryKey: ['students'] })
  }
  return {
    apply: useMutation({
      mutationFn: ({ id, changes }: { id: number; changes?: number[] }) =>
        post<{ applied: number; conflicts: unknown[] }>(`/suggestions/${id}/apply/`, { changes }),
      onSuccess: invalidate,
    }),
    acceptAbove: useMutation({
      mutationFn: ({ id, threshold }: { id: number; threshold: number }) =>
        post<{ applied: number; selected: number }>(`/suggestions/${id}/accept-above/`, { threshold }),
      onSuccess: invalidate,
    }),
    revert: useMutation({
      mutationFn: (id: number) => post<{ reverted: number }>(`/suggestions/${id}/revert/`),
      onSuccess: invalidate,
    }),
    resolve: useMutation({
      mutationFn: ({ id, ...body }: { id: number } & Record<string, unknown>) =>
        post<SuggestionChange>(`/suggestions/${id}/resolve-ambiguity/`, body),
      onSuccess: invalidate,
    }),
  }
}
