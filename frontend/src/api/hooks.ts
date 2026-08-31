/** Запросы к API через TanStack Query. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, get, patch, post } from './client'
import type { DomainMeta, Me, Paginated, Role } from './types'

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
  model_title: string
  domain_code: string
  /** человеческое название поля — считает сервер по реестру доменов */
  field_title: string
  field_short: string
  old_display: string
  new_display: string
  source: string
  source_title: string
  actor_name: string
  /** за какой домен действовал автор, если не за свой: администратор при загрузке (фаза 35) */
  acting_for: string
  /** готовая фраза «за домен «Экзамены»» или пусто */
  acting_for_title: string
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
  rejected: { student?: number; field?: string; field_title?: string; reason: string }[]
  conflicts: {
    student: number
    field: string
    field_title: string
    expected: string
    actual: string
    expected_display: string
    actual_display: string
  }[]
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
    // без связи таблица хочет отказ, а не паузу: черновик остаётся у неё,
    // индикатор говорит «нет связи», а дослать его она умеет сама (фаза 36)
    networkMode: 'always',
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
  plan: number | null
  plan_university: string | null
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
    meta: { saved: true },
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
  model_title: string
  new_object_key: string
  field_title: string
  field_short: string
  old_value: string
  new_value: string
  old_display: string
  new_display: string
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
  command_title: string
  source_type: string
  source_title: string
  source_ref: string
  status: 'draft' | 'pending' | 'applied' | 'partially_applied' | 'rejected' | 'reverted'
  status_title: string
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

/** «Вставить как есть». `domain` нужен только администратору: он вставляет за выбранный домен (фаза 35). */
export function usePaste() {
  return useMutation({
    mutationFn: ({ text, command, domain }: { text: string; command?: string; domain?: string }) =>
      post<{ task: string }>('/commands/paste/', { text, command, domain }),
  })
}

/** «Загрузить файл»: разбор идёт в фоне, ответ — id задачи. Только администратор, за выбранный домен. */
export function useUploadCommand() {
  return useMutation({
    mutationFn: ({ file, domain }: { file: File; domain: string }) => {
      const body = new FormData()
      body.append('file', file)
      body.append('domain', domain)
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

// --- Фаза 37: ученик вносит, директор подтверждает ---

export interface ProposeRow {
  model: string
  field: string
  value: string | number | boolean | null
  object_id?: string
  new_object_key?: string
}

export interface ProposeResult {
  suggestions: number[]
  accepted: number
  rejected: { field: string; reason: string }[]
}

/** Ученик отправляет данные о себе на проверку владельцу домена. */
export function usePropose() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (rows: ProposeRow[]) => post<ProposeResult>('/suggestions/propose/', { rows }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['my-proposals'] })
      void queryClient.invalidateQueries({ queryKey: ['journey'] })
    },
  })
}

export interface MyProposalChange {
  model: string
  field: string
  field_title: string
  object_id: string
  new_object_key: string
  new_value: string
  is_applied: boolean
}

export interface MyProposal {
  id: number
  status: string
  status_title: string
  reject_reason: string
  created_at: string
  resolved_at: string | null
  changes: MyProposalChange[]
}

/** Свои предложения: по ним кабинет ставит пометку «ждёт проверки». */
export const useMyProposals = (enabled = true) =>
  useQuery({
    queryKey: ['my-proposals'],
    queryFn: () => get<{ results: MyProposal[] }>('/suggestions/mine/'),
    enabled,
  })

export interface StudentQueueRow {
  id: number
  student: number | null
  student_name: string
  domain: string
  domain_title: string
  created_at: string
  divergence: number
  changes: SuggestionChange[]
}

/** Очередь «От учеников»: сначала то, что сильнее расходится с текущим. */
export const useStudentQueue = () =>
  useQuery({
    queryKey: ['student-queue'],
    queryFn: () => get<{ results: StudentQueueRow[] }>('/suggestions/from-students/'),
  })

/** Решение по предложению ученика: подтвердить, поправить, отклонить с причиной. */
export function useReviewSuggestion() {
  const queryClient = useQueryClient()
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['student-queue'] })
    void queryClient.invalidateQueries({ queryKey: ['suggestions'] })
    void queryClient.invalidateQueries({ queryKey: ['students'] })
  }
  return {
    review: useMutation({
      mutationFn: ({
        id,
        decision,
        reason,
        values,
      }: {
        id: number
        decision: 'confirm' | 'decline'
        reason?: string
        values?: Record<string, string>
      }) =>
        post<{ applied?: number; status: string }>(`/suggestions/${id}/review/`, {
          decision,
          reason,
          values,
        }),
      onSuccess: invalidate,
    }),
    confirmMany: useMutation({
      mutationFn: (suggestions: number[]) =>
        post<{ confirmed: number }>('/suggestions/from-students/confirm/', { suggestions }),
      onSuccess: invalidate,
    }),
  }
}

export interface JourneyStep {
  code: string
  title: string
  hint: string
  path: string
  action: string
  done: boolean
  locked: boolean
  lock_reason: string
  count?: number
  total?: number
}

export interface JourneyState {
  done: number
  total: number
  complete: boolean
  steps: JourneyStep[]
}

/** Лестница шагов ученика — главный экран, пока путь не пройден. */
export const useJourney = (enabled = true) =>
  useQuery({ queryKey: ['journey'], queryFn: () => get<JourneyState>('/journey/'), enabled })

// --- Фаза 38: портфолио ---

export interface PortfolioSection {
  code: string
  title: string
  value: number
  tab: string
}

export interface PortfolioState {
  percent: number
  sections: PortfolioSection[]
  next_steps: { text: string; tab: string }[]
  documents: { code: string; title: string; done: boolean }[]
  academics: { gpa: string | null; ielts: string | null; sat: number | null; ent: string | null }
}

/** Портфолио ученика: процент заполнения, следующие шаги, чек-лист. */
export const usePortfolio = () =>
  useQuery({ queryKey: ['portfolio'], queryFn: () => get<PortfolioState>('/portfolio/') })

export interface StudentDocumentRow {
  id: number
  student: number
  student_name: string
  doc_type: string
  doc_type_title: string
  title: string
  content_type: string
  size: number
  issued_date: string | null
  expires_at: string | null
  note: string
  created_at: string
}

/** Документы портфолио: список, загрузка и удаление своих. */
export function useDocuments(studentId?: number | null) {
  const queryClient = useQueryClient()
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['documents'] })
    void queryClient.invalidateQueries({ queryKey: ['portfolio'] })
  }
  const query = useQuery({
    queryKey: ['documents', studentId ?? 'me'],
    queryFn: () =>
      get<Paginated<StudentDocumentRow>>(`/documents/${studentId ? `?student=${studentId}` : ''}`),
  })
  const uploadDocument = useMutation({
    mutationFn: (input: {
      file: File
      doc_type: string
      title?: string
      issued_date?: string
      expires_at?: string
      note?: string
    }) => {
      const body = new FormData()
      body.append('file', input.file)
      body.append('doc_type', input.doc_type)
      if (input.title) body.append('title', input.title)
      if (input.issued_date) body.append('issued_date', input.issued_date)
      if (input.expires_at) body.append('expires_at', input.expires_at)
      if (input.note) body.append('note', input.note)
      return api<StudentDocumentRow>('/documents/', { method: 'POST', body })
    },
    onSuccess: invalidate,
  })
  const removeDocument = useMutation({
    mutationFn: (id: number) => api<{ archived: number }>(`/documents/${id}/`, { method: 'DELETE' }),
    onSuccess: invalidate,
  })
  return { query, uploadDocument, removeDocument }
}

// --- Фаза 39: цели по экзаменам, календарь ---

export interface ExamGoalRow {
  id: number
  student: number
  student_name: string
  exam: number
  exam_name: string
  target_score: string | null
  exam_date: string | null
  registration_date: string | null
  note: string
}

/** Цели по экзаменам: ученик видит свои, сотрудники — по ученику. */
export const useExamGoals = (studentId?: number | null) =>
  useQuery({
    queryKey: ['exam-goals', studentId ?? 'me'],
    queryFn: () => get<Paginated<ExamGoalRow>>(`/exam-goals/${studentId ? `?student=${studentId}` : ''}`),
  })

/** Правка и удаление целей — академический директор на «Пробных». */
export function useExamGoalRows() {
  const queryClient = useQueryClient()
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['exam-goals'] })
    void queryClient.invalidateQueries({ queryKey: ['goals-attention'] })
  }
  return {
    create: useMutation({
      mutationFn: (body: Record<string, unknown>) => post<ExamGoalRow>('/exam-goals/', body),
      onSuccess: invalidate,
      meta: { saved: true },
    }),
    update: useMutation({
      mutationFn: ({ id, ...body }: { id: number } & Record<string, unknown>) =>
        patch<ExamGoalRow>(`/exam-goals/${id}/`, body),
      onSuccess: invalidate,
      meta: { saved: true },
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<{ archived: number }>(`/exam-goals/${id}/`, { method: 'DELETE' }),
      onSuccess: invalidate,
    }),
  }
}

export interface AttentionRow {
  id: number
  name: string
  exam?: string
  date?: string
}

/** Списки академическому директору: без целей, экзамен на неделе, без регистрации. */
export const useGoalsAttention = () =>
  useQuery({
    queryKey: ['goals-attention'],
    queryFn: () =>
      get<{ no_goals: AttentionRow[]; exam_this_week: AttentionRow[]; not_registered: AttentionRow[] }>(
        '/exam-goals/attention/',
      ),
  })

export interface CalendarEvent {
  kind: string
  title: string
  date: string
  link: string
  pending: boolean
}

export interface CalendarState {
  today: string
  events: CalendarEvent[]
  nearest: (CalendarEvent & { days_left: number }) | null
}

/** Календарь ученика: события с датами и ближайшее с отсчётом. */
export const useCalendar = (enabled = true) =>
  useQuery({ queryKey: ['calendar'], queryFn: () => get<CalendarState>('/calendar/'), enabled })

export interface AtGoalState {
  available: boolean
  ielts_goal?: string | null
  sat_goal?: number | null
  open_before: number
  open_after: number
  unlocked: { program: number; university_name: string; program_name: string }[]
}

/** «Если сдашь на цель, откроется вот это» — соответствие, не шанс (инвариант №11). */
export const useAtGoal = () =>
  useQuery({ queryKey: ['at-goal'], queryFn: () => get<AtGoalState>('/match/at-goal/') })


// --- Фаза 42: центр подготовки ---

export interface CenterExam {
  exam_type: string
  title: string
  bank_total: number
  solved: number
}

export const useCenterExams = () =>
  useQuery({ queryKey: ['prep-center', 'exams'], queryFn: () => get<{ exams: CenterExam[] }>('/prep/center/exams/') })

export interface CenterSection {
  section: string
  title: string
  total: number
  solved: number
}

export const useCenterSections = (exam: string | null) =>
  useQuery({
    queryKey: ['prep-center', 'sections', exam],
    queryFn: () => get<{ sections: CenterSection[] }>(`/prep/center/${exam}/sections/`),
    enabled: exam !== null,
  })

export interface CenterTopic {
  topic: string
  total: number
  solved: number
  percent: number
}

export const useCenterTopics = (exam: string | null, section: string | null) =>
  useQuery({
    queryKey: ['prep-center', 'topics', exam, section],
    queryFn: () => get<{ topics: CenterTopic[] }>(`/prep/center/${exam}/${section}/topics/`),
    enabled: exam !== null && section !== null,
  })

export interface CenterStatistics {
  forecast: { enough: boolean; need_more: number; answered: number; share_percent: number; score: number | null }
  to_goal: number | null
  growth: number | null
  streak: number
  best_streak: number
  calendar: Record<string, number>
  weak_topics: { topic: string; total: number; correct: number; percent: number }[]
  achievements: { kind: string; title: string; amount: number; earned: boolean; count: number }[]
}

export const useCenterStatistics = (exam: string | null) =>
  useQuery({
    queryKey: ['prep-center', 'stats', exam],
    queryFn: () => get<CenterStatistics>(`/prep/center/${exam}/statistics/`),
    enabled: exam !== null,
  })

export interface TheoryLesson {
  id: number
  exam_type: string
  section: string
  section_title: string
  title: string
  level: string
  level_title: string
  reading_minutes: number
  body: string
  has_file: boolean
  order: number
  is_active: boolean
}

export const useTheory = (exam: string | null) =>
  useQuery({
    queryKey: ['prep-theory', exam],
    queryFn: () => get<Paginated<TheoryLesson>>(`/prep/theory/${exam ? `?exam_type=${exam}` : ''}`),
    enabled: exam !== null,
  })

/** Управление теорией — академический директор на «Пробных». */
export function useTheoryRows() {
  const queryClient = useQueryClient()
  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['prep-theory'] })
  return {
    create: useMutation({
      meta: { saved: true },
      mutationFn: (body: Partial<TheoryLesson>) => post<TheoryLesson>('/prep/theory/', body),
      onSuccess: invalidate,
    }),
    update: useMutation({
      meta: { saved: true },
      mutationFn: ({ id, ...body }: { id: number } & Partial<TheoryLesson>) =>
        patch<TheoryLesson>(`/prep/theory/${id}/`, body),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<unknown>(`/prep/theory/${id}/`, { method: 'DELETE' }),
      onSuccess: invalidate,
    }),
  }
}

// --- Фаза 41: план поступления по вузу ---

export interface PlanCounters {
  total: number
  done: number
  in_progress: number
  remaining: number
}

export interface ApplicationPlan {
  id: number
  student: number
  program: number
  admission_round: number | null
  university_name: string
  program_name: string
  level_title: string
  round_type: string | null
  deadline: string | null
  generation_status: 'none' | 'running' | 'done' | 'failed'
  generation_offline: boolean
  counters: PlanCounters
  days_left: number | null
  progress: number
  created_at: string
}

export const usePlans = () =>
  useQuery({ queryKey: ['plans'], queryFn: () => get<Paginated<ApplicationPlan>>('/application-plans/') })

export const usePlan = (id: number | null) =>
  useQuery({
    queryKey: ['plan', id],
    queryFn: () => get<ApplicationPlan>(`/application-plans/${id}/`),
    enabled: id !== null,
    refetchInterval: (query) => (query.state.data?.generation_status === 'running' ? 1500 : false),
  })

export interface PlanTaskStages {
  stages: { category: string; tasks: Task[] }[]
}

export const usePlanTasks = (id: number | null) =>
  useQuery({
    queryKey: ['plan-tasks', id],
    queryFn: () => get<PlanTaskStages>(`/application-plans/${id}/tasks/`),
    enabled: id !== null,
  })

export const usePlanPreview = (id: number | null, enabled: boolean) =>
  useQuery({
    queryKey: ['plan-preview', id],
    queryFn: () => get<Suggestion>(`/application-plans/${id}/preview/`),
    enabled: id !== null && enabled,
  })

export function usePlanActions() {
  const queryClient = useQueryClient()
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['plans'] })
    void queryClient.invalidateQueries({ queryKey: ['plan'] })
    void queryClient.invalidateQueries({ queryKey: ['plan-tasks'] })
    void queryClient.invalidateQueries({ queryKey: ['tasks'] })
  }
  return {
    create: useMutation({
      mutationFn: (body: { program: number; admission_round?: number }) =>
        post<ApplicationPlan>('/application-plans/', body),
      onSuccess: invalidate,
    }),
    applyTasks: useMutation({
      mutationFn: (id: number) => post<{ applied: number }>(`/application-plans/${id}/apply_tasks/`, {}),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: number) =>
        api<{ archived: number }>(`/application-plans/${id}/`, { method: 'DELETE' }),
      onSuccess: invalidate,
    }),
  }
}

export interface PlanAttention {
  total: number
  stalled: {
    id: number
    student: number
    student_name: string
    university: string
    deadline: string
    days_left: number
  }[]
}

/** Директору по поступлению: планы учеников и застрявшие при близком дедлайне. */
export const usePlanAttention = (enabled = true) =>
  useQuery({
    queryKey: ['plan-attention'],
    queryFn: () => get<PlanAttention>('/application-plans/attention/'),
    enabled,
  })

// --- Фаза 40: подбор вузов ---

export interface SelectionStage {
  code: string
  title: string
  at: number
}

export interface SelectionResultRow {
  id: number
  program: number
  program_name: string
  university: number
  university_name: string
  country: string
  world_rank: number | null
  is_verified: boolean
  percent_now: number
  percent_goal: number
  tier: string
  tier_title: string
  section: 'top' | 'strong' | 'other'
  is_favorite: boolean
  in_my_list: boolean
}

export interface SelectionRun {
  id: number
  status: 'running' | 'done' | 'failed'
  status_title: string
  stage: string
  stages: SelectionStage[]
  progress: number
  major: string
  level: string
  level_title: string
  countries: string[]
  created_at: string
  finished_at: string | null
  error: string
  profile: {
    gpa: string | null
    ielts: string | null
    sat: number | null
    grade: number | null
    graduation_year: number | null
  }
  funnel: { catalog: number; filtered: number; analyzed: number; final: number }
  strategy: { position: string; improve: string; next_step: string; offline: boolean }
  results?: SelectionResultRow[]
  methodology?: string[]
  tiers?: Record<string, number>
}

export const useSelectionRuns = () =>
  useQuery({
    queryKey: ['selection-runs'],
    queryFn: () => get<{ results: SelectionRun[] }>('/selection/runs/'),
  })

export const useSelectionRun = (id: number | null) =>
  useQuery({
    queryKey: ['selection-run', id],
    queryFn: () => get<SelectionRun>(`/selection/runs/${id}/`),
    enabled: id !== null,
    // пока считается — опрашиваем; готовый результат не трогаем
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 1500 : false),
  })

/** Плашка поверх любого экрана: есть ли считающийся прогон. */
export const useActiveSelection = (enabled = true) =>
  useQuery({
    queryKey: ['selection-active'],
    queryFn: () => get<{ run: SelectionRun | null }>('/selection/runs/active/'),
    enabled,
    refetchInterval: (query) => (query.state.data?.run ? 1500 : 30_000),
  })

export function useStartSelection() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { major?: string; level?: string; countries?: string[] }) =>
      post<SelectionRun>('/selection/runs/start/', body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['selection-runs'] })
      void queryClient.invalidateQueries({ queryKey: ['selection-active'] })
      void queryClient.invalidateQueries({ queryKey: ['journey'] })
    },
  })
}

export interface SelectionExplain {
  percent: number
  snapshot_percent: number
  percent_goal: number
  profile_changed: boolean
  profile_changed_note?: string
  summary: string
  breakdown: {
    code: string
    title: string
    weight: number
    percent: number
    is_met: boolean
    is_unknown: boolean
    gap_phrase: string
    criteria: { title: string; current: number | null; threshold: number; gap: number }[]
  }[]
  is_verified: boolean
  verification_note: string
}

export const useSelectionExplain = (run: number, program: number | null) =>
  useQuery({
    queryKey: ['selection-explain', run, program],
    queryFn: () => get<SelectionExplain>(`/selection/runs/${run}/explain/${program}/`),
    enabled: program !== null,
  })

export interface FavoriteRow {
  id: number
  program: number
  program_name: string
  university_name: string
  country: string
  level_title: string
  in_my_list: boolean
  created_at: string
}

/** Избранное — «присмотрел», в отличие от списка «подаюсь». */
export function useFavorites(enabled = true) {
  const queryClient = useQueryClient()
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['favorites'] })
    void queryClient.invalidateQueries({ queryKey: ['selection-run'] })
  }
  const query = useQuery({
    queryKey: ['favorites'],
    queryFn: () => get<{ count: number; results: FavoriteRow[] }>('/favorites/'),
    enabled,
  })
  const add = useMutation({
    mutationFn: (program: number) => post<{ id: number }>('/favorites/', { program }),
    onSuccess: invalidate,
  })
  const remove = useMutation({
    mutationFn: (program: number) =>
      api<{ detail: string }>(`/favorites/program/${program}/`, { method: 'DELETE' }),
    onSuccess: invalidate,
  })
  return { query, add, remove }
}

// --- Фаза 6: дайджест ---

export interface Digest {
  domain: string | null
  domain_title: string
  /** готовый текст — фронт его не собирает (фаза 17) */
  headline: string
  lines: string[]
  pending_line: string
  pending: { id: number; title: string; changes: number; text: string; created_at: string }[]
  recent: {
    field_title: string
    field_short: string
    old_display: string
    new_display: string
    source_title: string
    created_at: string
    student_id: number | null
    actor_name: string
  }[]
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
  /** одноразовая запись прогона — помечается в списке */
  is_probe: boolean
  date_joined: string
  password_changed_at: string | null
}

export const useUsers = (search: string) =>
  useQuery({
    queryKey: ['users', search],
    queryFn: () => get<ManagedUser[]>(`/users/${search ? `?search=${encodeURIComponent(search)}` : ''}`),
    placeholderData: (prev) => prev,
  })

/** Ссылка на установку пароля — то, что администратор передаёт человеку. */
export interface InviteLink {
  link: string
  email?: string
  minutes?: number
  detail: string
}

export function useCreateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    meta: { saved: true },
    mutationFn: (body: { email: string; full_name?: string; role?: Role }) =>
      post<ManagedUser & { invite?: InviteLink }>('/users/', body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

/** Выданный временный пароль — показывается ровно один раз (фаза 29). */
export interface IssuedPassword {
  email: string
  full_name: string
  password: string
  hours: number
  sent: boolean
  detail: string
}

export const useTempPassword = () =>
  useMutation({
    mutationFn: (id: number) => post<IssuedPassword>(`/users/${id}/temp-password/`),
  })

export type BulkUserAction = 'invite' | 'temp_password' | 'deactivate'

export function useBulkUsers() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { users: number[]; action: BulkUserAction }) =>
      post<{
        done: number
        skipped: { email: string; reason: string }[]
        issued: { full_name: string; email: string; password: string }[]
        detail: string
      }>('/users/bulk/', body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

/** Заведение учеников списком: предпросмотр и применение (фаза 29). */
export interface EnrollmentRow {
  number: number
  full_name: string
  email: string
  grade: string
  group: string
  status: 'new' | 'exists' | 'error'
  reason: string
}

export interface EnrollmentPreview {
  columns: Record<string, string>
  missing_columns: string[]
  total: number
  will_create: number
  already_exist: number
  with_errors: number
  rows: EnrollmentRow[]
  detail: string
}

export function useEnrollmentPreview() {
  return useMutation({
    mutationFn: (file: File) => {
      const body = new FormData()
      body.append('file', file)
      return api<EnrollmentPreview>('/enrollment/preview/', { method: 'POST', body })
    },
  })
}

export function useEnrollmentApply() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (rows: EnrollmentRow[]) =>
      post<{
        created: number
        letters: number
        hours: number
        skipped: { email: string; reason: string }[]
        rows: { full_name: string; email: string; password: string; sent: boolean }[]
        detail: string
      }>('/enrollment/apply/', { rows }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] })
      void queryClient.invalidateQueries({ queryKey: ['students'] })
      void queryClient.invalidateQueries({ queryKey: ['getting-started'] })
    },
  })
}

/** Выпустить свежую ссылку-приглашение и показать её (фаза 28). */
export const useInviteLink = () =>
  useMutation({
    mutationFn: (id: number) => post<InviteLink>(`/users/${id}/invite-link/`),
  })

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
    mutationFn: (body: { exam_type: string; section?: string; topic?: string; difficulty?: string; size?: number }) =>
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
  /** удалено навсегда: возвращать нечего, остался только журнал */
  purged_at: string | null
}

export interface PurgePreview {
  id?: number
  title?: string
  what: string
  summary?: string
  related?: { title: string; count: number }[]
  consequences: string[]
  confirm_word: string
  /** для массовой очистки: сколько удалений уйдёт и каких видов */
  entries?: number
  kinds?: { title: string; count: number }[]
  older_than_days?: number
}

export interface PurgedJournal {
  title: string
  purged_at: string | null
  rows: {
    id: number
    created_at: string
    object_title: string
    model_title: string
    field_title: string
    old_display: string
    new_display: string
    source: string
    actor_name: string
  }[]
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

/** Что именно уйдёт навсегда — считает сервер, а не подпись кнопки. */
export const usePurgePreview = (id: number | null) =>
  useQuery({
    queryKey: ['archive', 'purge', id],
    queryFn: () => get<PurgePreview>(`/archive/${id}/purge/`),
    enabled: id !== null,
  })

export function usePurgeFromArchive() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, confirm }: { id: number; confirm: string }) =>
      post<{ purged: number; files?: number; audit_marked?: number; detail: string }>(
        `/archive/${id}/purge/`,
        { confirm },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['archive'] })
    },
  })
}

export const useCleanupPreview = (days: number, enabled: boolean) =>
  useQuery({
    queryKey: ['archive', 'cleanup', days],
    queryFn: () => get<PurgePreview>(`/archive/cleanup/?days=${days}`),
    enabled,
  })

export function useCleanupArchive() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ days, confirm }: { days: number; confirm: string }) =>
      post<{ entries: number; purged: number; detail: string }>('/archive/cleanup/', { days, confirm }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['archive'] })
    },
  })
}

export const usePurgedJournal = (id: number | null) =>
  useQuery({
    queryKey: ['archive', 'journal', id],
    queryFn: () => get<PurgedJournal>(`/archive/${id}/journal/`),
    enabled: id !== null,
  })

/** Очистка истории загрузок: записи уходят, журнал изменений остаётся. */
export const useHistoryCleanupPreview = (days: number, enabled: boolean) =>
  useQuery({
    queryKey: ['imports', 'cleanup', days],
    queryFn: () => get<{ entries: number; detail: string }>(`/imports/cleanup/?days=${days}`),
    enabled,
  })

export function useCleanupHistory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (days: number) =>
      post<{ removed: number; audit_kept: number; detail: string }>('/imports/cleanup/', { days }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['imports'] })
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
  /** роль автора и её подпись: «администратор за домен «Экзамены»» */
  actor_role: string
  actor_role_title: string
  /** загрузку делал не владелец домена — администратор (фаза 35) */
  on_behalf: boolean
  domain_title: string
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
  skipped: { entry: number; field_title: string; student?: number; reason: string }[]
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
    meta: { saved: true },
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
  activities: {
    id: number
    title: string
    category: string
    subject: number | null
    subject_name: string
    date: string | null
    is_confirmed: boolean
  }[]
  competitions: { id: number; name: string; date: string | null; result: string }[]
  tasks: Task[]
  essays: Essay[]
}

/** Завести активность ученику. Предмет выбирается из справочника (фаза 18). */
export function useAddActivity(studentId: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { category: string; title: string; subject: number | null; date: string | null }) =>
      post<{ id: number }>('/activities/', { student: studentId, ...body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['student-rows'] })
      void client.invalidateQueries({ queryKey: ['students'] })
    },
  })
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
  requirement: DirectoryRequirement | null
  rounds: RoundInfo[]
}

/** Требования программы: пустое поле значит «требования нет», а не ноль. */
export interface DirectoryRequirement {
  id: number
  min_gpa: string | null
  min_ielts: string | null
  min_toefl: number | null
  min_sat: number | null
  min_act: number | null
  required_subjects: string
  portfolio_required: boolean
  portfolio_note: string
  is_verified: boolean
}

type RequirementBody = {
  program: number
  min_gpa: string | null
  min_ielts: string | null
  min_toefl: string | null
  min_sat: string | null
  min_act: string | null
  required_subjects: string
  portfolio_required: boolean
  portfolio_note: string
}

/** Правка справочника: вуз, программа, требования, раунд (фаза 29).
 *
 * Раньше отсюда можно было только удалить — чтобы поднять порог,
 * требования приходилось стереть и завести заново.
 */
const CATALOG_KEYS = [['programs'], ['universities'], ['catalog'], ['directory']]

function useCatalogMutation<TBody, TResult>(run: (body: TBody) => Promise<TResult>) {
  const queryClient = useQueryClient()
  return useMutation({
    meta: { saved: true },
    mutationFn: run,
    onSuccess: () => {
      CATALOG_KEYS.forEach((key) => void queryClient.invalidateQueries({ queryKey: key }))
    },
  })
}

export const useCreateUniversity = () =>
  useCatalogMutation((body: { name: string; country: string; website: string; domain: string }) =>
    post<DirectoryUniversity>('/universities/', body),
  )

export const useUpdateUniversity = () =>
  useCatalogMutation(({ id, ...body }: { id: number } & Record<string, unknown>) =>
    patch<DirectoryUniversity>(`/universities/${id}/`, body),
  )

export const useCreateProgram = () =>
  useCatalogMutation((body: { university: number; name: string; level: string }) =>
    post<DirectoryProgram>('/programs/', body),
  )

export const useUpdateProgram = () =>
  useCatalogMutation(({ id, ...body }: { id: number; university: number; name: string; level: string }) =>
    patch<DirectoryProgram>(`/programs/${id}/`, body),
  )

export const useCreateRequirement = () =>
  useCatalogMutation((body: RequirementBody) => post<DirectoryRequirement>('/requirements/', body))

export const useUpdateRequirement = () =>
  useCatalogMutation(({ id, ...body }: { id: number } & RequirementBody) =>
    patch<DirectoryRequirement>(`/requirements/${id}/`, body),
  )

export const useCreateRound = () =>
  useCatalogMutation((body: { program: number; round_type: string; deadline: string }) =>
    post<RoundInfo>('/rounds/', body),
  )

export const useUpdateRound = () =>
  useCatalogMutation(
    ({ id, ...body }: { id: number; program: number; round_type: string; deadline: string }) =>
      patch<RoundInfo>(`/rounds/${id}/`, body),
  )

export const useProgramsOf = (universityId: number | null) =>
  useQuery({
    queryKey: ['programs', universityId],
    enabled: universityId !== null,
    queryFn: () => get<Paginated<DirectoryProgram>>(`/programs/?university=${universityId}&page_size=200`),
  })

/**
 * Правка реестровой карточки ученика: имя, класс, группа, почта.
 *
 * Доменных полей здесь нет и быть не может — их ведут директора у себя
 * (инвариант №1). До фазы 30 администратор мог ученика только завести:
 * исправить опечатку в фамилии было нечем.
 */
export function useUpdateStudent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Partial<StudentWrite>) =>
      patch<StudentRow>(`/students/${id}/`, body),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ['student', variables.id] })
      void queryClient.invalidateQueries({ queryKey: ['students'] })
      void queryClient.invalidateQueries({ queryKey: ['groups'] })
    },
  })
}

/** Правка учебной группы: код, класс, куратор. */
export function useUpdateStudyGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; code: string; grade: number; curator: string }) =>
      patch<StudyGroupRow>(`/groups/${id}/`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['groups'] })
      void queryClient.invalidateQueries({ queryKey: ['students'] })
    },
  })
}

/**
 * Дочерняя строка ученика: завести и поправить.
 *
 * Один хук на все четыре таблицы — попытки, активности, соревнования
 * и вузы в списке: у них одинаковый путь (`/attempts/`, `/activities/`…)
 * и одинаковые ключи для обновления списков.
 */
function useRowMutation<T extends Record<string, unknown>>(path: string) {
  const queryClient = useQueryClient()
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['student-rows'] })
    void queryClient.invalidateQueries({ queryKey: ['students'] })
    void queryClient.invalidateQueries({ queryKey: ['student'] })
    void queryClient.invalidateQueries({ queryKey: ['match'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
  }
  const create = useMutation({
    meta: { saved: true },
    mutationFn: (body: T) => post<{ id: number }>(path, body),
    onSuccess: invalidate,
  })
  const update = useMutation({
    meta: { saved: true },
    // PATCH уходит только с изменёнными полями: сервер проверяет каждое
    // поле запроса по реестру, и служебные ключи вроде `student_name`
    // вернули бы 403 «поле ведёт другой директор»
    mutationFn: ({ id, ...body }: { id: number } & Partial<T>) =>
      patch<{ id: number }>(`${path}${id}/`, body),
    onSuccess: invalidate,
  })
  return { create, update }
}

export interface AttemptWrite extends Record<string, unknown> {
  student?: number
  exam_type: string
  attempt_format: string
  date: string
  total_score: string | number | null
}

export interface ActivityWrite extends Record<string, unknown> {
  student?: number
  category: string
  title: string
  subject: number | null
  date: string | null
  description?: string
  proof_url?: string
  is_confirmed?: boolean
}

export interface CompetitionWrite extends Record<string, unknown> {
  student?: number
  name: string
  date: string | null
  result: string
  has_certificate?: boolean
}

export interface StudentUniversityWrite extends Record<string, unknown> {
  student?: number
  program: number
  tier: string
  application_status?: string
  note?: string
}

export interface TaskWrite extends Record<string, unknown> {
  student?: number
  title: string
  category: string
  priority: string
  status?: string
  due_date: string | null
  description?: string
}

export interface EssayWrite extends Record<string, unknown> {
  student?: number
  title: string
  essay_type: string
  status?: string
}

export const useAttemptRows = () => useRowMutation<AttemptWrite>('/attempts/')
export const useActivityRows = () => useRowMutation<ActivityWrite>('/activities/')
export const useCompetitionRows = () => useRowMutation<CompetitionWrite>('/competitions/')
export const useStudentUniversityRows = () => useRowMutation<StudentUniversityWrite>('/student-universities/')
export interface TemplateWrite extends Record<string, unknown> {
  title: string
  category: string
  priority: string
  description?: string
  due_month: number | null
  due_day: number | null
  graduation_year: number | null
  grade: number | null
  is_active?: boolean
}

export interface TaskTemplate {
  id: number
  title: string
  category: string
  priority: string
  description: string
  due_month: number | null
  due_day: number | null
  graduation_year: number | null
  grade: number | null
  is_active: boolean
}

export const useTaskTemplates = () =>
  useQuery({
    queryKey: ['task-templates'],
    queryFn: () => get<Paginated<TaskTemplate>>('/task-templates/?page_size=200'),
  })

/** Шаблоны задач: из них генерируется роадмап потока. */
export const useTemplateRows = () => useRowMutation<TemplateWrite>('/task-templates/')

export const useTaskRows = () => useRowMutation<TaskWrite>('/tasks/')
export const useEssayRows = () => useRowMutation<EssayWrite>('/essays/')

// --- Банк заданий и пробные экзамены (фаза 31) ---

export interface QuestionOptionWrite {
  letter: string
  text: string
  is_correct: boolean
}

export interface QuestionWrite extends Record<string, unknown> {
  exam_type: string
  section: string
  topic: string
  difficulty: string
  text: string
  explanation?: string
  source?: string
  is_active?: boolean
  options?: QuestionOptionWrite[]
}

export interface BankQuestion {
  id: number
  exam_type: string
  section: string
  topic: string
  difficulty: string
  text: string
  explanation: string
  source: string
  is_active: boolean
  options: (QuestionOptionWrite & { id: number })[]
}

export const useQuestions = (filters: Record<string, string>) => {
  const search = new URLSearchParams({ page_size: '200' })
  Object.entries(filters).forEach(([k, v]) => {
    if (v) search.set(k, v)
  })
  const qs = search.toString()
  return useQuery({
    queryKey: ['prep-questions', qs],
    queryFn: () => get<Paginated<BankQuestion>>(`/prep/questions/?${qs}`),
    placeholderData: (prev) => prev,
  })
}

/** Задание банка: завести, поправить, убрать. */
export const useQuestionRows = () => useRowMutation<QuestionWrite>('/prep/questions/')

export interface MockSectionWrite {
  section: string
  question_count: number
  order?: number
}

export interface MockWrite extends Record<string, unknown> {
  title: string
  exam_type: string
  time_limit_minutes: number
  description?: string
  is_active?: boolean
  sections?: MockSectionWrite[]
}

/** Пробный экзамен: секции пишутся вместе с ним одним запросом. */
export const useMockRows = () => useRowMutation<MockWrite>('/prep/mocks/')

/** Массовый ввод результатов после общешкольного мока. */
export function useAttemptsBulk() {
  const queryClient = useQueryClient()
  return useMutation({
    meta: { saved: true },
    mutationFn: (rows: Record<string, unknown>[]) =>
      post<{
        created: number
        rejected: { row: number; student?: string; reason: string }[]
        detail: string
      }>('/attempts/bulk/', { rows }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['attempts'] })
      void queryClient.invalidateQueries({ queryKey: ['students'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      void queryClient.invalidateQueries({ queryKey: ['student-rows'] })
    },
  })
}

// --- Соревнования: список школы целиком (фаза 31) ---

export interface CompetitionRow {
  id: number
  student: number
  student_name: string
  name: string
  sport_type: number | null
  sport_type_name: string
  level: string
  level_title: string
  date: string | null
  result: string
  has_certificate: boolean
  proof_url: string
}

export function useCompetitions(params: { search?: string } = {}) {
  const query = new URLSearchParams({ page_size: '300' })
  if (params.search) query.set('search', params.search)
  const qs = query.toString()
  return useQuery({
    queryKey: ['competitions', qs],
    queryFn: () => get<Paginated<CompetitionRow>>(`/competitions/?${qs}`),
    placeholderData: (prev) => prev,
  })
}

// --- Комментарии к задачам и эссе (фаза 31) ---

export interface RowComment {
  id: number
  text: string
  author_name: string
  created_at: string
}

/**
 * Обсуждение под задачей или эссе.
 *
 * Один хук на оба: у них одинаковая форма и одинаковое правило — пишет
 * любой, кому запись видна, правит и убирает только автор.
 */
export function useRowComments(kind: 'task' | 'essay', id: number | null) {
  const path = kind === 'task' ? '/task-comments/' : '/essay-comments/'
  const key = [`${kind}-comments`, id]
  const queryClient = useQueryClient()
  const invalidate = () => void queryClient.invalidateQueries({ queryKey: key })

  const list = useQuery({
    queryKey: key,
    enabled: id !== null,
    queryFn: () => get<Paginated<RowComment>>(`${path}?${kind}=${id}&page_size=100`),
  })
  const add = useMutation({
    mutationFn: (text: string) => post<RowComment>(path, { [kind]: id, text }),
    onSuccess: invalidate,
  })
  const remove = useMutation({
    mutationFn: (commentId: number) => api<unknown>(`${path}${commentId}/`, { method: 'DELETE' }),
    onSuccess: invalidate,
  })
  return { list, add, remove }
}

// --- Контакты родителей (фаза 30) ---

export interface ParentContact {
  id: number
  student: number
  student_name: string
  full_name: string
  relation: string
  relation_title: string
  phone: string
  email: string
  preferred_channel: string
  channel_title: string
  note: string
  is_primary: boolean
}

export interface ContactWrite extends Record<string, unknown> {
  student?: number
  full_name: string
  relation: string
  phone: string
  email: string
  preferred_channel: string
  note: string
  is_primary: boolean
}

/** Контакты одного ученика или весь список школы с поиском. */
export function useContacts(params: { student?: number | null; search?: string } = {}) {
  const query = new URLSearchParams({ page_size: '200' })
  if (params.student) query.set('student', String(params.student))
  if (params.search) query.set('search', params.search)
  const qs = query.toString()
  return useQuery({
    queryKey: ['contacts', qs],
    queryFn: () => get<Paginated<ParentContact>>(`/contacts/?${qs}`),
    placeholderData: (prev) => prev,
  })
}

export function useContactRows() {
  const queryClient = useQueryClient()
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['contacts'] })
    void queryClient.invalidateQueries({ queryKey: ['student-rows'] })
  }
  const create = useMutation({
    meta: { saved: true },
    mutationFn: (body: ContactWrite) => post<ParentContact>('/contacts/', body),
    onSuccess: invalidate,
  })
  const update = useMutation({
    meta: { saved: true },
    mutationFn: ({ id, ...body }: { id: number } & Partial<ContactWrite>) =>
      patch<ParentContact>(`/contacts/${id}/`, body),
    onSuccess: invalidate,
  })
  return { create, update }
}

export function useCreateStudyGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    meta: { saved: true },
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

// --- Фаза 18: справочники предметов олимпиад и видов спорта ---

export interface DirectoryEntry {
  id: number
  name: string
  /** направление предмета или категория вида спорта — код */
  area?: string
  category?: string
  /** шкала экзамена (справочник экзаменов, фаза 39) */
  min_score?: string | null
  max_score?: string | null
  category_title: string
  description: string
  is_active: boolean
  sort_order: number
  usage_total: number
  created_at: string
}

export interface DirectoryUsage {
  can_delete: boolean
  usage: { model: string; title: string; count: number; archived: number }[]
  usage_total: number
  message: string
  options: { action: 'hide' | 'replace'; title: string; hint: string }[]
}

export interface DuplicateGroups {
  detail: string
  groups: {
    key: string
    entries: { id: number; name: string; is_active: boolean; usage_total: number }[]
  }[]
}

/** `subjects` — предметы олимпиад, `sport-types` — виды спорта. */
export type DirectoryKind = 'subjects' | 'sport-types' | 'exam-kinds'

export const useDirectoryEntries = (kind: DirectoryKind) =>
  useQuery({
    queryKey: ['directory', kind],
    queryFn: () => get<Paginated<DirectoryEntry>>(`/${kind}/?page_size=300`),
  })

export const useDirectoryDuplicates = (kind: DirectoryKind) =>
  useQuery({
    queryKey: ['directory-duplicates', kind],
    queryFn: () => get<DuplicateGroups>(`/${kind}/duplicates/`),
  })

/** Все действия над записью справочника — одним хуком, чтобы экран не пух. */
export function useDirectoryActions(kind: DirectoryKind) {
  const client = useQueryClient()
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['directory', kind] })
    void client.invalidateQueries({ queryKey: ['directory-duplicates', kind] })
    // состав списка выбора приходит вместе с реестром доменов
    void client.invalidateQueries({ queryKey: ['domains'] })
  }

  return {
    create: useMutation({
      meta: { saved: true },
      mutationFn: (body: Partial<DirectoryEntry>) => post<DirectoryEntry>(`/${kind}/`, body),
      onSuccess: refresh,
    }),
    update: useMutation({
      meta: { saved: true },
      mutationFn: ({ id, ...body }: Partial<DirectoryEntry> & { id: number }) =>
        patch<DirectoryEntry>(`/${kind}/${id}/`, body),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<{ detail: string }>(`/${kind}/${id}/`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
    hide: useMutation({
      mutationFn: (id: number) => post<{ detail: string }>(`/${kind}/${id}/hide/`),
      onSuccess: refresh,
    }),
    show: useMutation({
      mutationFn: (id: number) => post<{ detail: string }>(`/${kind}/${id}/show/`),
      onSuccess: refresh,
    }),
    replace: useMutation({
      mutationFn: ({ id, target }: { id: number; target: number }) =>
        post<{ detail: string; moved: number }>(`/${kind}/${id}/replace/`, { target }),
      onSuccess: refresh,
    }),
    usage: (id: number) => get<DirectoryUsage>(`/${kind}/${id}/usage/`),
  }
}

// --- Фаза 19: материалы олимпиадников ---

export interface MaterialFile {
  id: number
  original_name: string
  content_type: string
  size: number
  size_human: string
  /** ссылка ведёт на проверку прав, а не в /media/ */
  url: string
  created_at: string
}

export interface Material {
  id: number
  author: number
  author_name: string
  subject: number
  subject_name: string
  topic: string
  title: string
  description: string
  source_kind: 'own_solution' | 'own_analysis' | 'third_party'
  source_kind_title: string
  rights_confirmed: boolean
  status: 'pending' | 'approved' | 'rejected'
  status_title: string
  reject_reason: string
  request: number | null
  helpful_count: number
  marked_helpful: boolean
  can_moderate: boolean
  files: MaterialFile[]
  created_at: string
  reviewed_at: string | null
}

export interface MaterialComment {
  id: number
  material: number
  author: number
  author_name: string
  is_mine: boolean
  text: string
  created_at: string
}

export interface MaterialRequestRow {
  id: number
  author: number
  author_name: string
  subject: number
  subject_name: string
  topic: string
  text: string
  status: 'open' | 'closed'
  status_title: string
  answers: number
  created_at: string
  closed_at: string | null
}

export interface Collection {
  id: number
  name: string
  description: string
  subject: number | null
  subject_name: string
  items: {
    id: number
    material: number
    title: string
    author_name: string
    subject_name: string
    position: number
  }[]
  created_at: string
}

export interface MaterialsState {
  has_access: boolean
  is_curator: boolean
  limits: { max_file_mb: number; max_files: number; formats: string; hint: string }
}

export const useMaterialsState = () =>
  useQuery({
    queryKey: ['materials-state'],
    queryFn: () => get<MaterialsState>('/materials-state/'),
    staleTime: 60_000,
  })

export function useMaterials(params: Record<string, string | undefined>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v) search.set(k, v)
  })
  search.set('page_size', '100')
  const qs = search.toString()
  return useQuery({
    queryKey: ['materials', qs],
    queryFn: () => get<Paginated<Material>>(`/materials/?${qs}`),
    placeholderData: (prev) => prev,
  })
}

export const useMaterial = (id: number | null) =>
  useQuery({
    queryKey: ['material', id],
    enabled: id !== null,
    queryFn: () => get<Material>(`/materials/${id}/`),
  })

export const useMaterialComments = (id: number | null) =>
  useQuery({
    queryKey: ['material-comments', id],
    enabled: id !== null,
    queryFn: () => get<Paginated<MaterialComment>>(`/material-comments/?material=${id}&page_size=200`),
  })

export const useMaterialQueue = (enabled: boolean) =>
  useQuery({
    queryKey: ['material-queue'],
    enabled,
    queryFn: () =>
      get<{ summary: string; pending: Material[]; reports: MaterialReportRow[] }>('/materials/queue/'),
  })

export interface MaterialReportRow {
  id: number
  material: number | null
  comment: number | null
  reporter_name: string
  reason: string
  status: 'open' | 'resolved'
  status_title: string
  resolution: string
  created_at: string
}

export const useMaterialRequests = () =>
  useQuery({
    queryKey: ['material-requests'],
    queryFn: () => get<Paginated<MaterialRequestRow>>('/material-requests/?page_size=100'),
  })

export const useCollections = () =>
  useQuery({
    queryKey: ['material-collections'],
    queryFn: () => get<Paginated<Collection>>('/material-collections/?page_size=100'),
  })

/** Действия раздела материалов одним хуком. */
export function useMaterialActions() {
  const client = useQueryClient()
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['materials'] })
    void client.invalidateQueries({ queryKey: ['material'] })
    void client.invalidateQueries({ queryKey: ['material-queue'] })
    void client.invalidateQueries({ queryKey: ['material-requests'] })
    void client.invalidateQueries({ queryKey: ['notifications'] })
  }

  return {
    upload: useMutation({
      mutationFn: (form: FormData) => api<Material>('/materials/', { method: 'POST', body: form }),
      onSuccess: refresh,
    }),
    review: useMutation({
      mutationFn: ({
        id,
        decision,
        reason,
      }: {
        id: number
        decision: 'approve' | 'reject'
        reason?: string
      }) => post<{ detail: string }>(`/materials/${id}/review/`, { decision, reason }),
      onSuccess: refresh,
    }),
    helpful: useMutation({
      mutationFn: (id: number) =>
        post<{ marked: boolean; helpful_count: number }>(`/materials/${id}/helpful/`),
      onSuccess: refresh,
    }),
    comment: useMutation({
      mutationFn: ({ material, text }: { material: number; text: string }) =>
        post<MaterialComment>('/material-comments/', { material, text }),
      onSuccess: (created) => {
        void client.invalidateQueries({ queryKey: ['material-comments', created.material] })
      },
    }),
    removeComment: useMutation({
      mutationFn: (id: number) => api<{ detail: string }>(`/material-comments/${id}/`, { method: 'DELETE' }),
      onSuccess: () => void client.invalidateQueries({ queryKey: ['material-comments'] }),
    }),
    report: useMutation({
      mutationFn: (body: { material?: number; comment?: number; reason: string }) =>
        post<{ id: number }>('/material-reports/', body),
      onSuccess: refresh,
    }),
    resolveReport: useMutation({
      mutationFn: ({ id, resolution }: { id: number; resolution: string }) =>
        post<{ detail: string }>(`/material-reports/${id}/resolve/`, { resolution }),
      onSuccess: refresh,
    }),
    ask: useMutation({
      mutationFn: (body: { subject: number; topic: string; text: string }) =>
        post<MaterialRequestRow>('/material-requests/', body),
      onSuccess: refresh,
    }),
    createCollection: useMutation({
      mutationFn: (body: { name: string; description: string; subject: number | null }) =>
        post<Collection>('/material-collections/', body),
      onSuccess: () => void client.invalidateQueries({ queryKey: ['material-collections'] }),
    }),
    addToCollection: useMutation({
      mutationFn: ({ id, material, position }: { id: number; material: number; position: number }) =>
        post<{ detail: string }>(`/material-collections/${id}/add/`, { material, position }),
      onSuccess: () => void client.invalidateQueries({ queryKey: ['material-collections'] }),
    }),
    updateCollection: useMutation({
      mutationFn: ({ id, ...body }: { id: number; name: string; description: string }) =>
        patch<Collection>(`/material-collections/${id}/`, body),
      onSuccess: () => void client.invalidateQueries({ queryKey: ['material-collections'] }),
    }),
    removeCollection: useMutation({
      mutationFn: (id: number) =>
        api<{ detail: string }>(`/material-collections/${id}/`, { method: 'DELETE' }),
      onSuccess: () => void client.invalidateQueries({ queryKey: ['material-collections'] }),
    }),
    removeMaterial: useMutation({
      mutationFn: (id: number) => api<{ detail: string }>(`/materials/${id}/`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
    updateMaterial: useMutation({
      mutationFn: ({ id, form }: { id: number; form: FormData }) =>
        api<Material>(`/materials/${id}/`, { method: 'PATCH', body: form }),
      onSuccess: refresh,
    }),
    removeRequest: useMutation({
      mutationFn: (id: number) => api<{ detail: string }>(`/material-requests/${id}/`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
  }
}

// --- Олимпиадная группа ---

export interface GroupRow {
  id: number
  full_name: string
  grade: number
  group: string
  in_group: boolean
  materials: number
}

export const useOlympiadGroup = (filters: { q?: string; grade?: string; member?: string }) => {
  const search = new URLSearchParams()
  Object.entries(filters).forEach(([k, v]) => {
    if (v) search.set(k, v)
  })
  const qs = search.toString()
  return useQuery({
    queryKey: ['olympiad-group', qs],
    queryFn: () =>
      get<{ members: number; detail: string; students: GroupRow[] }>(`/olympiad-group/${qs ? `?${qs}` : ''}`),
    placeholderData: (prev) => prev,
  })
}

export function usePickForGroup() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ student, member }: { student: number; member: boolean }) =>
      post<{ detail: string }>('/olympiad-group/pick/', { student, member }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['olympiad-group'] })
      void client.invalidateQueries({ queryKey: ['students'] })
    },
  })
}

// --- Уведомления ---

export interface NotificationRow {
  id: number
  text: string
  link: string
  is_read: boolean
  created_at: string
}

export const useNotifications = () =>
  useQuery({
    queryKey: ['notifications'],
    queryFn: () => get<{ unread: number; rows: NotificationRow[] }>('/notifications/'),
    refetchInterval: 120_000,
  })

export function useMarkNotificationsRead() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (ids?: number[]) => post<{ marked: number }>('/notifications/read/', ids ? { ids } : {}),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['notifications'] }),
  })
}

// --- Фаза 20: операции с моделью ---

export interface LLMStatus {
  configured: boolean
  within_budget: boolean
  available: boolean
  provider: string
  /** готовый текст: почему кнопка работает или нет */
  detail: string
}

export const useLLMStatus = () =>
  useQuery({ queryKey: ['llm-status'], queryFn: () => get<LLMStatus>('/llm/status/'), staleTime: 60_000 })

export interface OperationResult {
  ok: boolean
  text: string
  lines: string[]
  offline: boolean
  suggestion: number | null
  rows: number
  detail: string
}

export interface ParseResult {
  ok: boolean
  detail: string
  suggestion?: number
  rows?: number
  university?: string
  strength?: string
  missing?: string
  /** сколько раз модель ходила на официальные сайты (фаза 27) */
  searches?: number
  /** источник факта: ссылка, цитата и дата сверки */
  source?: { url: string; quote: string; checked_at: string; title: string }
}

export interface OperationInput {
  code: string
  text?: string
  students?: number[]
  student?: number
  days?: number
}

/** Запуск операции: ответ приходит фоновой задачей, как и весь разбор. */
export const useRunOperation = () =>
  useMutation({
    mutationFn: (body: OperationInput) => post<{ task: string }>('/commands/run/', body),
  })

export const useParseUniversity = () =>
  useMutation({
    mutationFn: (text: string) => post<{ task: string }>('/commands/parse-university/', { text }),
  })

export interface MailStatus {
  configured: boolean
  host: string
  port: number
  from_email: string
  backend: string
  warning: string
  detail: string
}

/** Уходят ли письма. Спрашивает только администратор (фаза 27). */
export const useMailStatus = (enabled = true) =>
  useQuery({
    queryKey: ['mail-status'],
    queryFn: () => get<MailStatus>('/mail/status/'),
    enabled,
    staleTime: 60_000,
  })

export const useSendTestMail = () =>
  useMutation({
    mutationFn: (email: string) => post<{ ok: boolean; detail: string }>('/mail/test/', { email }),
  })

/** Сверка требований программы с официальным сайтом вуза (фаза 27). */
export const useVerifyRequirements = () =>
  useMutation({
    mutationFn: (program: number) => post<{ task: string }>('/commands/verify-requirements/', { program }),
  })

export const useParseActivity = () =>
  useMutation({
    mutationFn: (body: { text: string; student: number }) =>
      post<{ task: string }>('/commands/parse-activity/', body),
  })

export const useParseImage = () =>
  useMutation({
    mutationFn: ({
      file,
      student,
      kind,
    }: {
      file: File
      student: number
      kind: 'certificate' | 'scores'
    }) => {
      const body = new FormData()
      body.set('file', file)
      body.set('student', String(student))
      body.set('kind', kind)
      return api<{ task: string }>('/commands/parse-image/', { method: 'POST', body })
    },
  })

export interface SpendReport {
  limit: number
  spent_this_month: number
  left: number
  percent: number
  available: boolean
  days: number
  calls: number
  failures: number
  detail: string
  by_role: { role: string; role_title: string; calls: number; cost: number }[]
  by_purpose: { purpose: string; purpose_title: string; calls: number; cost: number; tokens: number }[]
  recent: {
    id: number
    created_at: string
    actor_name: string
    role_title: string
    purpose_title: string
    tokens: number
    cost: number
    is_ok: boolean
    error: string
  }[]
}

export const useSpendReport = (days = 30) =>
  useQuery({ queryKey: ['llm-spend', days], queryFn: () => get<SpendReport>(`/llm/spend/?days=${days}`) })

// --- Предпочтения интерфейса (фаза 23) -----------------------------------

export interface PreferencesPatch {
  sidebar_collapsed?: boolean
  theme?: 'light' | 'dark' | 'system'
  language?: 'ru' | 'kk' | 'en'
}

/** Сохранить предпочтения на сервере и сразу обновить `me` в кэше. */
export function useUpdatePreferences() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: PreferencesPatch) => patch<Me>('/auth/me/preferences/', body),
    onSuccess: (me) => queryClient.setQueryData(['me'], me),
  })
}

// --- Помощник в углу (фаза 25) --------------------------------------------

export interface AssistantQuickButton {
  code: string
  title: string
  needs: 'none' | 'student' | 'text' | 'image'
  hint: string
}

export interface AssistantMessage {
  id: number
  author: 'user' | 'assistant'
  text: string
  lines: string[]
  command: string
  suggestion: number | null
  offline: boolean
  affected: number
  created_at: string
}

export interface AssistantThread {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export const useAssistantQuick = (enabled: boolean) =>
  useQuery({
    queryKey: ['assistant-quick'],
    queryFn: () => get<{ buttons: AssistantQuickButton[]; model: LLMStatus }>('/assistant/quick/'),
    enabled,
    staleTime: 5 * 60_000,
  })

export const useAssistantThreads = (enabled: boolean) =>
  useQuery({
    queryKey: ['assistant-threads'],
    queryFn: () => get<AssistantThread[]>('/assistant/threads/'),
    enabled,
  })

export const useAssistantThread = (id: number | null) =>
  useQuery({
    queryKey: ['assistant-thread', id],
    queryFn: () =>
      get<{ thread: AssistantThread; messages: AssistantMessage[] }>(`/assistant/threads/${id}/`),
    enabled: id !== null,
  })

export interface AssistantAsk {
  thread?: number | null
  command?: string
  text?: string
  students?: number[]
  screen?: string
}

export function useAssistantAsk() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AssistantAsk) =>
      post<{ thread: AssistantThread; message: AssistantMessage; note?: string }>('/assistant/ask/', body),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['assistant-thread', result.thread.id] })
      void queryClient.invalidateQueries({ queryKey: ['assistant-threads'] })
    },
  })
}

export function useRejectSuggestion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<{ detail: string }>(`/suggestions/${id}/reject/`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['suggestion'] })
      void queryClient.invalidateQueries({ queryKey: ['suggestions'] })
    },
  })
}

// --- Блокировки входа (фаза 36) ------------------------------------------

export interface LoginLock {
  scope: 'account' | 'address'
  value: string
  failures: number
  seconds: number
  unlock_at: string
  message: string
}

export interface LoginLocksState {
  locks: LoginLock[]
  trusted_networks: string[]
  account_threshold: number
  address_threshold: number
  window_minutes: number
}

export const useLoginLocks = () =>
  useQuery({
    queryKey: ['login-locks'],
    queryFn: () => get<LoginLocksState>('/auth/locks/'),
    // блокировки снимаются сами по времени: список обновляется, пока экран открыт
    refetchInterval: 60_000,
  })

export function useUnlockLogin() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { scope: 'account' | 'address'; value: string }) =>
      post<{ detail: string; cleared: number }>('/auth/locks/unlock/', body),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['login-locks'] }),
    meta: { saved: true },
  })
}
