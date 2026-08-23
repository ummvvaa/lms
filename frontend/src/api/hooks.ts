/** Запросы к API через TanStack Query. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, get, patch, post } from './client'
import type { DomainMeta, Paginated, Role } from './types'

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
  /** домены без данных: в расчёт не вошли, но показать их надо */
  skipped: { code: string; title: string }[]
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

export interface MatchPosition {
  code: string
  title: string
  weight: number
  achievement: number
  percent: number
  is_met: boolean
  is_unknown: boolean
  gap_phrase: string
  criteria: MatchCriterion[]
}

export interface MatchResult {
  program: number
  program_name: string
  university_name: string
  country: string
  status: 'open' | 'gap' | 'unknown'
  has_requirements: boolean
  is_open: boolean
  /** соответствие требованиям, 0..100. Это не шанс поступления (инвариант №11) */
  percent: number
  summary: string
  breakdown: MatchPosition[]
  criteria: MatchCriterion[]
  /** данные программы подтверждены директором по поступлению (инвариант №14) */
  is_verified: boolean
  /** текст плашки над непроверенными данными; пусто — плашки нет */
  verification_note: string
}

export interface WhatIf {
  ielts_delta: number
  sat_delta: number
  gpa_delta: number
  open_before: number
  open_after: number
  unlocked: MatchResult[]
  results: (MatchResult & { percent_before: number; became_open: boolean })[]
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
    mutationFn: (payload: {
      ielts_delta?: number
      sat_delta?: number
      gpa_delta?: number
      student?: number
    }) => post<WhatIf>('/match/what-if/', payload),
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
      // XP и «задания на сегодня» живут в другом запросе: без этого
      // галочка ставится, а панель прогресса остаётся прежней
      void queryClient.invalidateQueries({ queryKey: ['game'] })
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
  return useMutation({
    mutationFn: ({ text, command }: { text: string; command?: string }) =>
      post<{ task: string }>('/commands/paste/', { text, command }),
  })
}

/** «Загрузить файл»: разбор идёт в фоне, ответ — id задачи. */
export function useUploadCommand() {
  return useMutation({
    mutationFn: (file: File) => {
      const body = new FormData()
      body.append('file', file)
      return api<{ task: string }>('/commands/upload/', { method: 'POST', body })
    },
  })
}

export interface Explanation {
  summary: string
  detail?: string
  source?: string
  [key: string]: unknown
}

/** «Объясни соответствие»: объяснение по паре ученик × программа. */
export function useExplainMatch() {
  return useMutation({
    mutationFn: ({ student, program }: { student: number; program: number }) =>
      post<{ task: string }>('/commands/explain-match/', { student, program }),
  })
}

export interface ListBalance {
  student: number
  student_name: string
  total: number
  counts: Record<string, number>
  target: Record<string, number>
  gaps: Record<string, number>
  advice: string
  programs: { program: number; tier: string; university_name: string; program_name: string }[]
}

export const useListBalance = (studentId: number | null) =>
  useQuery({
    queryKey: ['list-balance', studentId],
    queryFn: () => get<ListBalance>(`/match/list-balance/?student=${studentId}`),
    enabled: studentId !== null,
  })

export interface ProgramRow {
  id: number
  university_name: string
  name: string
  country: string
}

export const usePrograms = () =>
  useQuery({
    queryKey: ['programs'],
    queryFn: () => get<Paginated<ProgramRow>>('/programs/?page_size=500'),
    staleTime: 5 * 60_000,
  })

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

// --- Фаза 6: выпускники, менторство, дайджест ---

export interface Alumnus {
  id: number
  full_name: string
  graduation_year: number
  university_name: string | null
  program_name: string | null
  country: string
  current_occupation: string
  admission_gpa: string | null
  admission_ielts: string | null
  admission_sat: number | null
  admission_activities: number
  mentorship_consent: boolean
  applications: {
    id: number
    university_name: string
    program_name: string
    outcome: string
    scholarship: string
  }[]
}

export interface MentorshipRequest {
  id: number
  student: number
  student_name: string
  alumnus: number
  alumnus_name: string
  topic: string
  message: string
  status: string
  is_visible_to_alumnus: boolean
  review_note: string
  created_at: string
}

export interface ArchivedEssay {
  id: number
  author_label: string
  university_name: string
  program_name: string
  essay_type: string
  title: string
  text: string
}

export interface Digest {
  domain: string | null
  domain_title?: string
  changes: number
  by_field: { field_name: string; n: number }[]
  sources: Record<string, number>
  pending: { id: number; command: string; source_type: string; n: number }[]
  recent: {
    field_name: string
    old_value: string
    new_value: string
    source: string
    created_at: string
  }[]
}

export function useAlumni(filters: Record<string, string | undefined>) {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([k, v]) => {
    if (v) params.set(k, v)
  })
  const qs = params.toString()
  return useQuery({
    queryKey: ['alumni', qs],
    queryFn: () => get<Paginated<Alumnus>>(`/alumni/${qs ? `?${qs}` : ''}`),
    placeholderData: (prev) => prev,
  })
}

export const useArchivedEssays = () =>
  useQuery({
    queryKey: ['archived-essays'],
    queryFn: () => get<Paginated<ArchivedEssay>>('/archived-essays/'),
  })

export const useMentorships = () =>
  useQuery({ queryKey: ['mentorship'], queryFn: () => get<Paginated<MentorshipRequest>>('/mentorship/') })

export function useRequestMentorship() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { alumnus: number; topic: string; message?: string }) =>
      post<MentorshipRequest>('/mentorship/request/', body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['mentorship'] })
    },
  })
}

export function useReviewMentorship() {
  const queryClient = useQueryClient()
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['mentorship'] })
  }
  return {
    approve: useMutation({
      mutationFn: ({ id, note }: { id: number; note?: string }) =>
        post<MentorshipRequest>(`/mentorship/${id}/approve/`, { note }),
      onSuccess: invalidate,
    }),
    decline: useMutation({
      mutationFn: ({ id, note }: { id: number; note?: string }) =>
        post<MentorshipRequest>(`/mentorship/${id}/decline/`, { note }),
      onSuccess: invalidate,
    }),
  }
}

export const useDigest = () => useQuery({ queryKey: ['digest'], queryFn: () => get<Digest>('/digest/') })

export function useLinkIdentity() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (email: string) => post<unknown>('/auth/identities/link/', { email }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['me'] })
    },
  })
}

// --- Фаза 9: управление учётными записями ---

export interface ManagedUser {
  id: number
  email: string
  full_name: string
  role: Role
  role_title: string
  is_active: boolean
  sees_whole_school: boolean
  must_change_password: boolean
  has_password: boolean
  date_joined: string
  password_changed_at: string | null
}

export const useUsers = (search: string) =>
  useQuery({
    queryKey: ['users', search],
    queryFn: () => get<ManagedUser[]>(`/users/${search ? `?search=${encodeURIComponent(search)}` : ''}`),
    placeholderData: (prev) => prev,
  })

export function useCreateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { email: string; full_name?: string; role?: Role }) =>
      post<ManagedUser>('/users/', body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

export function useUpdateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: { id: number } & Partial<
      Pick<ManagedUser, 'role' | 'is_active' | 'sees_whole_school' | 'full_name'>
    >) => patch<ManagedUser>(`/users/${id}/`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

export interface InviteResult {
  created: number
  invited: number
  skipped: { email: string; reason: string }[]
}

export function useInviteUsers() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { emails: string[]; role?: Role }) => post<InviteResult>('/users/invite/', body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

// --- Фаза 10: каталог вузов и подбор ---

export interface RoundInfo {
  id: number
  round_type: string
  round_title: string
  deadline: string
  source_url: string
  is_verified: boolean
}

export interface MyEntry {
  id: number
  tier: string
  added_by: string
  is_confirmed: boolean
  can_remove: boolean
}

export interface CatalogCard extends MatchResult {
  university: number
  university_website: string
  level: 'high' | 'medium' | 'low'
  rounds: RoundInfo[]
  in_my_list: boolean
  my_entry: MyEntry | null
}

export interface CatalogFacets {
  countries: string[]
  majors: string[]
  round_types: string[]
  levels: { code: string; title: string; from: number; to: number }[]
  list_limit: number
}

export const useCatalogFacets = () =>
  useQuery({
    queryKey: ['catalog', 'facets'],
    queryFn: () => get<CatalogFacets>('/catalog/facets/'),
    staleTime: 5 * 60_000,
  })

export function useCatalog(filters: Record<string, string>) {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([k, v]) => {
    if (v) params.set(k, v)
  })
  const qs = params.toString()
  return useQuery({
    queryKey: ['catalog', qs],
    queryFn: () => get<{ count: number; results: CatalogCard[] }>(`/catalog/${qs ? `?${qs}` : ''}`),
    placeholderData: (prev) => prev,
  })
}

function invalidateCatalog(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['catalog'] })
  void queryClient.invalidateQueries({ queryKey: ['match'] })
}

export function useAddToMyList() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { program: number; tier: string }) => post<MyEntry>('/catalog/add/', body),
    onSuccess: () => invalidateCatalog(queryClient),
  })
}

export function useRemoveFromMyList() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api<void>(`/catalog/remove/${id}/`, { method: 'DELETE' }),
    onSuccess: () => invalidateCatalog(queryClient),
  })
}

export interface PendingAddition {
  id: number
  student: number
  student_name: string
  program: number
  university_name: string
  program_name: string
  tier: string
  created_at: string
}

export const usePendingAdditions = () =>
  useQuery({
    queryKey: ['catalog', 'pending'],
    queryFn: () => get<PendingAddition[]>('/catalog/pending/'),
  })

export function useReviewAddition() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, decision, tier }: { id: number; decision: 'confirm' | 'decline'; tier?: string }) =>
      post(`/catalog/pending/${id}/`, { decision, tier }),
    onSuccess: () => invalidateCatalog(queryClient),
  })
}

export interface PickedProgram extends CatalogCard {
  why: string
  missing: string
  next_round: RoundInfo | null
}

export interface PickResult {
  picks: PickedProgram[]
  note: string
  offline: boolean
  filters: { country: string; major: string }
}

export function usePickPrograms() {
  return useMutation({
    mutationFn: (text: string) => post<PickResult>('/catalog/pick/', { text }),
  })
}

// --- Фаза 11: онбординг и геймификация ---

export interface OnboardingQuestion {
  code: string
  title: string
  hint: string
  kind: 'text' | 'choice' | 'number' | 'decimal' | 'bool'
  target: string
  domain: string
  placeholder: string
  options: { value: string; title: string }[]
}

export interface OnboardingState {
  status: 'in_progress' | 'completed' | 'skipped'
  total: number
  answered: number
  next: OnboardingQuestion | null
  questions: OnboardingQuestion[]
  answers: Record<string, string>
  completed_at: string | null
}

export const useOnboarding = () =>
  useQuery({
    queryKey: ['onboarding'],
    queryFn: () => get<OnboardingState>('/onboarding/'),
    retry: false,
  })

export function useAnswerOnboarding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { question: string; value: string }) =>
      post<{ state: OnboardingState }>('/onboarding/answer/', body),
    onSuccess: (result) => {
      queryClient.setQueryData(['onboarding'], result.state)
      void queryClient.invalidateQueries({ queryKey: ['student', 'me'] })
      void queryClient.invalidateQueries({ queryKey: ['game'] })
    },
  })
}

export function useSkipOnboarding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => post<OnboardingState>('/onboarding/skip/'),
    onSuccess: (state) => queryClient.setQueryData(['onboarding'], state),
  })
}

export interface PendingAnswer {
  id: number
  student: number
  student_name: string
  question: string
  question_title: string
  value: string
  target: string
  domain: string
  created_at: string
}

export const usePendingOnboarding = () =>
  useQuery({
    queryKey: ['onboarding', 'pending'],
    queryFn: () => get<PendingAnswer[]>('/onboarding/pending/'),
  })

export function useReviewOnboarding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, decision, value }: { id: number; decision: 'confirm' | 'decline'; value?: string }) =>
      post(`/onboarding/pending/${id}/`, { decision, value }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['onboarding'] })
      void queryClient.invalidateQueries({ queryKey: ['students'] })
    },
  })
}

export interface TodayTask {
  id: number
  title: string
  category: string
  priority: string
  status: TaskStatus
  due_date: string | null
  days_left: number | null
  from_deadline: boolean
  university_name: string | null
  xp: number
}

export interface GameState {
  xp: number
  level: number
  level_progress: number
  level_step: number
  streak_days: number
  best_streak: number
  active_today: boolean
  streak_phrase: string
  recent: { kind: string; kind_title: string; amount: number; note: string; created_at: string }[]
  today: TodayTask[]
  awards: { kind: string; title: string; amount: number }[]
}

export const useGameState = () =>
  useQuery({ queryKey: ['game'], queryFn: () => get<GameState>('/game/me/'), retry: false })

// --- Фаза 12: центр подготовки ---

export interface PrepOption {
  id: number
  letter: string
  text: string
}

export interface PrepQuestion {
  answer_id: number
  question: number
  text: string
  section: string
  topic: string
  difficulty: string
  options: PrepOption[]
  chosen: number | null
  answered: boolean
  is_correct?: boolean
  correct_option?: number | null
  correct_letter?: string
  explanation?: string
  source?: string
}

export interface PrepSession {
  id: number
  exam_type: string
  section: string
  difficulty: string
  status: 'running' | 'finished' | 'abandoned'
  total: number
  answered: number
  correct: number | null
  percent: number | null
  questions: PrepQuestion[]
  /** появляется у мока */
  run?: number
  mock?: string
  time_limit_minutes?: number
  shortages?: { section: string; asked: number; available: number }[]
}

export interface PrepReview extends PrepSession {
  weak_topics: { topic: string; total: number; correct: number; percent: number }[]
  recommendation: string
  seconds_spent: number
  score?: number | null
  attempt?: number | null
  counted_in_profile?: boolean
  note?: string
}

export interface MockExam {
  id: number
  title: string
  exam_type: string
  time_limit_minutes: number
  description: string
  is_active: boolean
  sections: { id: number; section: string; section_title: string; question_count: number; order: number }[]
}

export interface BankRow {
  exam_type: string
  section: string
  section_title: string
  topic: string
  difficulty: string
  n: number
}

export const useBankOverview = () =>
  useQuery({
    queryKey: ['prep', 'bank'],
    queryFn: () => get<{ total: number; rows: BankRow[] }>('/prep/bank/'),
  })

export const useMockExams = () =>
  useQuery({
    queryKey: ['prep', 'mocks'],
    queryFn: () => get<Paginated<MockExam>>('/prep/mocks/'),
  })

export function useStartPractice() {
  return useMutation({
    mutationFn: (body: { exam_type: string; section?: string; difficulty?: string; size?: number }) =>
      post<PrepSession>('/prep/practice/start/', body),
  })
}

export function useStartMock() {
  return useMutation({ mutationFn: (id: number) => post<PrepSession>(`/prep/mocks/${id}/start/`) })
}

export function useAnswerQuestion() {
  return useMutation({
    mutationFn: ({
      session,
      ...body
    }: {
      session: number
      answer_id: number
      option: number
      seconds?: number
    }) => post<{ answered: boolean }>(`/prep/practice/${session}/answer/`, body),
  })
}

export function useFinishSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ session, seconds }: { session: number; seconds: number }) =>
      post<PrepReview>(`/prep/practice/${session}/finish/`, { seconds }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['game'] })
      void queryClient.invalidateQueries({ queryKey: ['tasks'] })
      void queryClient.invalidateQueries({ queryKey: ['attempts'] })
      void queryClient.invalidateQueries({ queryKey: ['prep', 'runs'] })
    },
  })
}

export interface MyRun {
  id: number
  mock: string
  exam_type: string
  session: number
  status: string
  score: number | null
  counted_in_profile: boolean
  created_at: string
}

export const useMyRuns = () =>
  useQuery({ queryKey: ['prep', 'runs'], queryFn: () => get<MyRun[]>('/prep/runs/my/') })

export interface PlatformMock {
  id: number
  student: number
  student_name: string
  mock: string
  exam_type: string
  score: number | null
  correct: number
  total: number
  counted_in_profile: boolean
  reviewed_at: string | null
  created_at: string
}

export const usePlatformMocks = () =>
  useQuery({ queryKey: ['prep', 'platform'], queryFn: () => get<PlatformMock[]>('/prep/runs/platform/') })

export function useReviewMock() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, count_it }: { id: number; count_it: boolean }) =>
      post(`/prep/runs/${id}/review/`, { count_it }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['prep', 'platform'] })
      void queryClient.invalidateQueries({ queryKey: ['students'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export interface Attempt {
  id: number
  student: number
  exam_type: string
  attempt_format: string
  source: string
  date: string
  total_score: string | null
}

export const useAttempts = (examType?: string) =>
  useQuery({
    queryKey: ['attempts', examType ?? 'all'],
    queryFn: () =>
      get<Paginated<Attempt>>(
        `/attempts/${examType ? `?exam_type=${examType}&page_size=200` : '?page_size=200'}`,
      ),
  })

// --- Фаза 13: стартовый справочник и подтверждение данных ---

export interface SeedStats {
  universities: number
  programs: number
  unverified: number
  held_by_students: number
  own_universities: number
  detail?: string
  removed?: { universities: number; programs: number; student_links: number; kept_universities: number }
}

export const useSeedStats = (enabled = true) =>
  useQuery({
    queryKey: ['catalog', 'seed'],
    queryFn: () => get<SeedStats>('/catalog/seed/'),
    enabled,
  })

function invalidateDirectory(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['catalog'] })
  void queryClient.invalidateQueries({ queryKey: ['universities'] })
  void queryClient.invalidateQueries({ queryKey: ['match'] })
}

/** Завести стартовый справочник из 20 вузов. */
export function useCreateSeedCatalog() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => post<SeedStats>('/catalog/seed/'),
    onSuccess: () => invalidateDirectory(queryClient),
  })
}

/** Удалить стартовый справочник. Заведённое школой остаётся на месте. */
export function useDropSeedCatalog() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (force: boolean) =>
      api<SeedStats>(`/catalog/seed/${force ? '?force=1' : ''}`, { method: 'DELETE' }),
    onSuccess: () => invalidateDirectory(queryClient),
  })
}

export type VerifiableKind = 'university' | 'program' | 'requirement' | 'round'

export interface VerifyResult {
  kind: VerifiableKind
  id: number
  is_verified: boolean
  changed: number
  verification_note: string
  detail: string
}

/** Снять с записи справочника плашку «данные не подтверждены». */
export function useVerifyRecord() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { kind: VerifiableKind; id: number; verified: boolean }) =>
      post<VerifyResult>('/catalog/verify/', body),
    onSuccess: () => invalidateDirectory(queryClient),
  })
}

export interface DirectoryUniversity {
  id: number
  name: string
  country: string
  website: string
  domain: string
  is_active: boolean
  data_source: 'school' | 'seed' | 'import' | 'sync'
  is_verified: boolean
  verified_at: string | null
  verification_note: string
}

export const useDirectory = (search = '') =>
  useQuery({
    queryKey: ['universities', search],
    queryFn: () =>
      // потолок страницы поднят: справочник школы целиком помещается на экран,
      // а листать его постранично незачем
      get<Paginated<DirectoryUniversity>>(
        `/universities/?page_size=300${search ? `&search=${encodeURIComponent(search)}` : ''}`,
      ),
  })

// --- Фаза 14: удаление, архив и история загрузок ---

export interface DeletePreview {
  model: string
  id: number
  title: string
  kind: string
  /** мягкое удаление: запись уйдёт в архив и вернётся оттуда */
  soft: boolean
  what: string
  summary: string
  related: { title: string; count: number }[]
  related_count: number
  consequences: string[]
  /** слово, которое надо набрать; пусто — набирать не нужно */
  confirm_word: string
  blocked?: boolean
}

export const useDeletePreview = (model: string, id: number | null) =>
  useQuery({
    queryKey: ['delete-preview', model, id],
    queryFn: () => get<DeletePreview>(`/delete-preview/?model=${model}&id=${id}`),
    enabled: id !== null,
    staleTime: 0,
    gcTime: 0,
  })

export interface DeleteResult {
  detail: string
  archived?: number
  related_count?: number
}

/** Удаление любой записи. Путь — тот же, что у её списка. */
export function useDeleteRecord(path: string, invalidate: string[][]) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api<DeleteResult>(`${path}${id}/`, { method: 'DELETE' }),
    onSuccess: () => {
      invalidate.forEach((key) => void queryClient.invalidateQueries({ queryKey: key }))
      void queryClient.invalidateQueries({ queryKey: ['archive'] })
    },
  })
}

export interface ArchiveRow {
  id: number
  model: string
  object_id: string
  title: string
  kind: string
  summary: string
  related_count: number
  actor_name: string
  created_at: string
  restored_at: string | null
  restored_by_name: string
}

export const useArchive = (onlyPending: boolean) =>
  useQuery({
    queryKey: ['archive', onlyPending],
    queryFn: () => get<ArchiveRow[]>(`/archive/${onlyPending ? '?restored=false' : ''}`),
  })

export function useRestoreFromArchive() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<{ restored: number; detail: string }>(`/archive/${id}/restore/`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['archive'] })
      void queryClient.invalidateQueries({ queryKey: ['students'] })
      void queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

export interface ImportBatchRow {
  id: number
  file_name: string
  kind: string
  kind_title: string
  domain_code: string
  rows_total: number
  rows_created: number
  rows_updated: number
  rows_failed: number
  status: 'applied' | 'reverted' | 'partial'
  status_title: string
  actor: number | null
  actor_name: string
  created_at: string
  reverted_at: string | null
  changes: number
  note: string
}

export const useImportBatches = (filters: { actor?: string; since?: string; until?: string }) => {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([k, v]) => {
    if (v) params.set(k, v)
  })
  const qs = params.toString()
  return useQuery({
    queryKey: ['imports', qs],
    queryFn: () => get<ImportBatchRow[]>(`/imports/${qs ? `?${qs}` : ''}`),
  })
}

export interface RevertReport {
  reverted: number
  skipped: { entry: number; field: string; student?: number; reason: string }[]
  status: string
  detail: string
}

export function useRevertImport() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<RevertReport>(`/imports/${id}/revert/`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['imports'] })
      void queryClient.invalidateQueries({ queryKey: ['students'] })
    },
  })
}

export interface StudyGroupRow {
  id: number
  code: string
  grade: number
  curator: string
  is_active: boolean
  students_count: number
}

export const useStudyGroups = () =>
  useQuery({
    queryKey: ['groups'],
    queryFn: () => get<Paginated<StudyGroupRow>>('/groups/?page_size=200'),
  })

export interface StudentWrite {
  last_name: string
  first_name: string
  middle_name?: string
  email: string
  grade: number
  group?: number | null
  graduation_year: number
}

/** Заведение карточки ученика. Пять профилей создаются на сервере сразу. */
export function useCreateStudent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: StudentWrite) => post<StudentRow>('/students/', body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['students'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

/** Дочерние строки ученика — то, что директор ведёт на его карточке. */
export interface StudentRowsBundle {
  universities: {
    id: number
    program_name: string
    university_name: string
    tier: string
    application_status: string
    added_by: string
  }[]
  attempts: Attempt[]
  activities: { id: number; title: string; category: string; date: string | null; is_confirmed: boolean }[]
  competitions: { id: number; name: string; date: string | null; result: string }[]
  tasks: Task[]
  essays: Essay[]
}

export function useStudentRows(studentId: number | null) {
  return useQuery({
    queryKey: ['student-rows', studentId],
    enabled: studentId !== null,
    queryFn: async (): Promise<StudentRowsBundle> => {
      const query = `?student=${studentId}&page_size=200`
      const [universities, attempts, activities, competitions, tasks, essays] = await Promise.all([
        get<Paginated<StudentRowsBundle['universities'][number]>>(`/student-universities/${query}`),
        get<Paginated<Attempt>>(`/attempts/${query}`),
        get<Paginated<StudentRowsBundle['activities'][number]>>(`/activities/${query}`),
        get<Paginated<StudentRowsBundle['competitions'][number]>>(`/competitions/${query}`),
        get<Paginated<Task>>(`/tasks/${query}`),
        get<Paginated<Essay>>(`/essays/${query}`),
      ])
      return {
        universities: universities.results,
        attempts: attempts.results,
        activities: activities.results,
        competitions: competitions.results,
        tasks: tasks.results,
        essays: essays.results,
      }
    },
  })
}

export interface DirectoryProgram {
  id: number
  university: number
  university_name: string
  name: string
  level: string
  is_active: boolean
  is_verified: boolean
  verification_note: string
  requirement: { id: number; min_gpa: string | null; min_ielts: string | null; is_verified: boolean } | null
  rounds: RoundInfo[]
}

export const useProgramsOf = (universityId: number | null) =>
  useQuery({
    queryKey: ['programs', universityId],
    enabled: universityId !== null,
    queryFn: () => get<Paginated<DirectoryProgram>>(`/programs/?university=${universityId}&page_size=200`),
  })

export function useCreateStudyGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { code: string; grade: number; curator: string }) =>
      post<StudyGroupRow>('/groups/', body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['groups'] }),
  })
}

// --- Фаза 15: понятность интерфейса ---

export interface StartStep {
  code: string
  title: string
  hint: string
  path: string
  done: boolean
  count: number | null
  total: number | null
  action: string
}

export interface GettingStarted {
  role: Role
  title: string
  done: number
  total: number
  /** всё выполнено — панель больше не нужна */
  complete: boolean
  steps: StartStep[]
}

export const useGettingStarted = () =>
  useQuery({
    queryKey: ['getting-started'],
    queryFn: () => get<GettingStarted>('/getting-started/'),
    staleTime: 30_000,
  })

// --- Фаза 16: поиск по системе ---

export interface SearchHit {
  id: number
  title: string
  note: string
  path: string
}

export interface SearchGroup {
  code: 'students' | 'universities' | 'programs'
  title: string
  rows: SearchHit[]
}

export interface SearchResult {
  query: string
  total: number
  groups: SearchGroup[]
  detail: string
}

export function useSearch(query: string) {
  const trimmed = query.trim()
  return useQuery({
    queryKey: ['search', trimmed],
    enabled: trimmed.length >= 2,
    queryFn: () => get<SearchResult>(`/search/?q=${encodeURIComponent(trimmed)}`),
    placeholderData: (prev) => prev,
    staleTime: 15_000,
  })
}
