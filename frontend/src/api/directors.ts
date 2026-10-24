/**
 * Запросы кабинетов директоров (24.10.2026): отчёты одного места, звонки,
 * утренние отметки школы, задачи сотрудникам, результаты экзаменов, эссе,
 * олимпиады, освобождения, мероприятия и «Спорт» ученика.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, get, patch, post } from './client'

export interface StudentBrief {
  id: number
  full_name: string
  short_name: string
  group: string
  parallel: number | null
}

/* --- Отчёты -------------------------------------------------------------- */

export type ReportTopic = 'attendance' | 'parents' | 'calls' | 'grades' | 'teachers' | 'exams'

export interface SchoolReport {
  kind: string
  title: string
  source: string
  period: string
  period_title: string
  summary: string
  lines: { label: string; value: string }[]
  seen: boolean
  topic: ReportTopic
}

export interface ReportArchiveRow {
  kind: string
  title: string
  source: string
  period: string
  topic: ReportTopic
  seen: boolean
}

export const useSchoolReports = () =>
  useQuery({
    queryKey: ['school-reports'],
    queryFn: () => get<{ current: SchoolReport[]; archive: ReportArchiveRow[] }>('/directors/reports/'),
  })

export const useSchoolReport = (kind: string | null, period = '') =>
  useQuery({
    queryKey: ['school-report', kind, period],
    queryFn: () => get<SchoolReport>(`/directors/reports/${kind}/${period ? `?period=${period}` : ''}`),
    enabled: Boolean(kind),
  })

export function useReportSeen() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ kind, period }: { kind: string; period: string }) =>
      post<{ seen: boolean }>(`/directors/reports/${kind}/seen/`, { period }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['school-reports'] })
      void queryClient.invalidateQueries({ queryKey: ['school-report'] })
    },
  })
}

export const reportExportPath = (kind: string, period: string) =>
  `/directors/reports/${kind}/export/${period ? `?period=${period}` : ''}`

export interface ReportGroupRow {
  group_id: number
  group: string
  curator: string
  students: number
  reports: number
  state: 'none' | 'built' | 'checked' | 'sent'
  state_title: string
}

export const useReportGroups = (month = '') =>
  useQuery({
    queryKey: ['school-report-groups', month],
    queryFn: () => get<{ month: string; rows: ReportGroupRow[] }>(`/directors/reports/parent-groups/${month ? `?month=${month}` : ''}`),
  })

/* --- Звонки ---------------------------------------------------------------- */

export type CallOutcome = 'reached' | 'no_answer' | 'call_back'

export interface CallTodayRow {
  student_id: number
  student: string
  group: string
  urgency: string
  urgency_title: string
  reason: string
  contact: { name: string; phone: string } | null
  contact_id: number | null
  parent: string
  today: { outcome: CallOutcome; outcome_title: string } | null
}

export interface CallRuleRow {
  id: number
  code: string
  reason: string
  condition_title: string
  urgency_title: string
  is_active: boolean
}

export const useCallsToday = (enabled = true) =>
  useQuery({
    queryKey: ['calls-today'],
    queryFn: () =>
      get<{ rows: CallTodayRow[]; week: { total: number; reached: number; later: number }; rules: CallRuleRow[] }>(
        '/directors/calls/today/',
      ),
    enabled,
  })

export interface CallRow {
  id: number
  student: StudentBrief
  contact: { id: number; name: string; relation: string } | null
  outcome: CallOutcome
  outcome_title: string
  note: string
  rule: string
  by: string
  at: string
}

export const useCalls = (days = 30) =>
  useQuery({
    queryKey: ['calls', days],
    queryFn: () => get<{ rows: CallRow[]; total: number }>(`/directors/calls/?days=${days}`),
  })

export function useRecordCall() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { student: number; outcome: CallOutcome; note: string; contact?: number | null; rule?: string }) =>
      post<CallRow>('/directors/calls/', body),
    meta: { saved: true },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['calls-today'] })
      void queryClient.invalidateQueries({ queryKey: ['calls'] })
      void queryClient.invalidateQueries({ queryKey: ['school-reports'] })
      void queryClient.invalidateQueries({ queryKey: ['contacts'] })
    },
  })
}

/* --- Утренние отметки школы ------------------------------------------------- */

export interface MorningStudent extends StudentBrief {
  state: 'absent' | 'late' | 'released'
  reason: string
}

export interface MorningGroup {
  id: number
  code: string
  parallel: number
  curator: string
  size: number
  marked: boolean
  at: string
  absent: number
  late: number
  released: number
  students: MorningStudent[]
}

export const useMorning = (date = '') =>
  useQuery({
    queryKey: ['morning', date],
    queryFn: () =>
      get<{
        date: string
        groups: MorningGroup[]
        totals: { students: number; absent: number; late: number; released: number; groups: number; marked: number; last: string }
      }>(`/directors/morning/${date ? `?date=${date}` : ''}`),
  })

/* --- Задачи сотрудникам ------------------------------------------------------ */

export type StaffTaskStatus = 'open' | 'done' | 'accepted' | 'returned'

export interface StaffTask {
  id: number
  title: string
  due: string
  status: StaffTaskStatus
  status_title: string
  late: boolean
  days_late: number
  assignee: { id: number; name: string; role: string; role_title: string }
  author: string
  return_note: string
  done_at: string | null
  reminded_at: string | null
  created_at: string
}

export const useStaffTasks = (enabled = true) =>
  useQuery({
    queryKey: ['staff-tasks'],
    queryFn: () =>
      get<{ rows: StaffTask[]; month: { set: number; accepted: number; returned: number } }>('/directors/staff-tasks/'),
    enabled,
  })

export const useStaffPeople = (enabled = true) =>
  useQuery({
    queryKey: ['staff-task-people'],
    queryFn: () => get<{ rows: { id: number; name: string; role: string; role_title: string }[] }>('/directors/staff-tasks/people/'),
    enabled,
  })

export function useSetStaffTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { title: string; due: string; assignee: number }) => post<StaffTask>('/directors/staff-tasks/', body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['staff-tasks'] }),
  })
}

export function useStaffTaskAction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; action: 'accept' | 'return' | 'remind'; note?: string }) =>
      patch<StaffTask>(`/directors/staff-tasks/${id}/`, body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['staff-tasks'] }),
  })
}

export const useMyStaffTasks = (enabled = true) =>
  useQuery({
    queryKey: ['staff-tasks-mine'],
    queryFn: () => get<{ rows: StaffTask[] }>('/directors/staff-tasks/mine/'),
    enabled,
  })

export function useStaffTaskDone() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<StaffTask>(`/directors/staff-tasks/${id}/done/`),
    meta: { saved: true },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['staff-tasks-mine'] }),
  })
}

/* --- Результаты экзаменов ------------------------------------------------------ */

export interface ExamResultRow {
  id: number
  full_name: string
  group: string
  mock: string
  mock_date: string | null
  sections: string
  official: string
  official_date: string | null
  goal: string
  gap: number | null
  attempts: number
}

export interface ExamResults {
  exam: 'IELTS' | 'SAT'
  rows: ExamResultRow[]
  summary: { took: number; average: string; reached: number; with_goal: number; far: number; official: number; students: number }
  groups: string[]
}

export const useExamResults = (exam: string, group: string) =>
  useQuery({
    queryKey: ['exam-results', exam, group],
    queryFn: () => get<ExamResults>(`/directors/exam-results/?exam=${exam}${group ? `&group=${encodeURIComponent(group)}` : ''}`),
  })

export interface AttemptRow {
  id: number
  exam: string
  format: 'mock' | 'official'
  format_title: string
  date: string | null
  total: string
  sections: string
}

export const useExamHistory = (student: number | null) =>
  useQuery({
    queryKey: ['exam-results-student', student],
    queryFn: () => get<{ student: StudentBrief; attempts: AttemptRow[] }>(`/directors/exam-results/${student}/`),
    enabled: student !== null,
  })

/* --- Эссе учеников ----------------------------------------------------------------- */

export interface EssayReviewRow {
  id: number
  title: string
  kind: string
  program: string
  student: StudentBrief
  words: number
  word_limit: number | null
  submitted_at: string | null
  verdict: '' | 'ok' | 'not_ok'
  comment: string
}

export const useEssayReview = () =>
  useQuery({
    queryKey: ['essay-review'],
    queryFn: () => get<{ rows: EssayReviewRow[]; groups: string[] }>('/directors/essays/'),
  })

export const useEssayReviewDetail = (id: number | null) =>
  useQuery({
    queryKey: ['essay-review', id],
    queryFn: () =>
      get<EssayReviewRow & { text: string; comments: { text: string; at: string; author: string }[] }>(`/directors/essays/${id}/`),
    enabled: id !== null,
  })

export function useEssayVerdict() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; verdict: 'ok' | 'not_ok'; comment: string }) =>
      post<EssayReviewRow>(`/directors/essays/${id}/verdict/`, body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['essay-review'] }),
  })
}

/* --- Олимпиады и освобождения -------------------------------------------------------- */

export type OlympiadResult = 'pending' | 'participant' | 'prize' | 'winner'

export interface OlympiadRow {
  id: number
  title: string
  subject: number | null
  subject_title: string
  level: string
  level_title: string
  place: string
  starts: string
  ends: string
  participants: number | null
  pending: number | null
  entries?: {
    id: number
    student: StudentBrief
    result: OlympiadResult
    result_title: string
    released: boolean
  }[]
}

export const useOlympiadEvents = () =>
  useQuery({
    queryKey: ['olympiad-events'],
    queryFn: () => get<{ rows: OlympiadRow[]; levels: { value: string; label: string }[] }>('/directors/olympiads/'),
  })

export const useOlympiadEvent = (id: number | null) =>
  useQuery({
    queryKey: ['olympiad-event', id],
    queryFn: () => get<OlympiadRow>(`/directors/olympiads/${id}/`),
    enabled: id !== null,
  })

function useOlympiadInvalidate() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['olympiad-events'] })
    void queryClient.invalidateQueries({ queryKey: ['olympiad-event'] })
    void queryClient.invalidateQueries({ queryKey: ['releases'] })
  }
}

export function useSaveOlympiad() {
  const done = useOlympiadInvalidate()
  return useMutation({
    mutationFn: (body: { title: string; level: string; starts: string; ends: string; place: string; subject: number | null }) =>
      post<OlympiadRow>('/directors/olympiads/', body),
    onSuccess: done,
  })
}

export function useAddOlympiadEntries() {
  const done = useOlympiadInvalidate()
  return useMutation({
    mutationFn: ({ id, students }: { id: number; students: number[] }) =>
      post<{ added: number }>(`/directors/olympiads/${id}/entries/`, { students }),
    onSuccess: done,
  })
}

export function useOlympiadResult() {
  const done = useOlympiadInvalidate()
  return useMutation({
    mutationFn: ({ id, result }: { id: number; result: OlympiadResult }) =>
      patch<{ result: OlympiadResult }>(`/directors/olympiad-entries/${id}/`, { result }),
    meta: { saved: true },
    onSuccess: done,
  })
}

export interface ReleaseRow {
  id: number
  reason: string
  kind: 'olympiad' | 'sport'
  olympiad: number | null
  event: number | null
  starts: string
  ends: string
  all_day: boolean
  slot_from: number | null
  slot_to: number | null
  span: string
  label: string
  by: string
  students: StudentBrief[]
}

export const useReleases = (from: string, to: string, enabled = true) =>
  useQuery({
    queryKey: ['releases', from, to],
    queryFn: () => get<{ from: string; to: string; rows: ReleaseRow[] }>(`/directors/releases/?from=${from}&to=${to}`),
    enabled,
  })

export function useSaveRelease() {
  const done = useOlympiadInvalidate()
  return useMutation({
    mutationFn: (body: {
      olympiad: number
      students: number[]
      starts: string
      ends: string
      slot_from: number | null
      slot_to: number | null
    }) => post<ReleaseRow>('/directors/releases/', body),
    onSuccess: done,
  })
}

export function useCancelRelease() {
  const done = useOlympiadInvalidate()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api<void>(`/directors/releases/${id}/`, { method: 'DELETE' }),
    onSuccess: () => {
      done()
      void queryClient.invalidateQueries({ queryKey: ['sport-event-applications'] })
    },
  })
}

/* --- Мероприятия и заявки --------------------------------------------------------------- */

export type ApplicationStatus = 'pending' | 'accepted' | 'declined'

export interface SportEventRow {
  id: number
  title: string
  kind: 'competition' | 'event'
  kind_title: string
  sport_type: number | null
  sport_title: string
  starts_at: string
  place: string
  seats: number | null
  spectators: boolean
  past: boolean
  accepted: number
  seats_left: number | null
  pending?: number
  applications?: number
  watchers?: number
  mine?: SportApplicationRow | null
}

export interface SportApplicationRow {
  id: number
  kind: 'play' | 'watch'
  kind_title: string
  comment: string
  status: ApplicationStatus
  status_title: string
  created_at: string
  student?: StudentBrief
  release?: string
  event?: { id: number; title: string }
}

export const useSportEvents = () =>
  useQuery({ queryKey: ['sport-events'], queryFn: () => get<{ rows: SportEventRow[] }>('/directors/sport-events/') })

export const useSportApplications = () =>
  useQuery({
    queryKey: ['sport-applications'],
    queryFn: () => get<{ rows: SportApplicationRow[] }>('/directors/sport-events/applications/'),
  })

export const useSportEventApplications = (id: number | null) =>
  useQuery({
    queryKey: ['sport-event-applications', id],
    queryFn: () => get<{ event: SportEventRow; rows: SportApplicationRow[] }>(`/directors/sport-events/${id}/applications/`),
    enabled: id !== null,
  })

function useSportInvalidate() {
  const queryClient = useQueryClient()
  return () => {
    for (const key of ['sport-events', 'sport-applications', 'sport-event-applications', 'releases', 'my-sport'])
      void queryClient.invalidateQueries({ queryKey: [key] })
  }
}

export function useSaveSportEvent() {
  const done = useSportInvalidate()
  return useMutation({
    mutationFn: (body: {
      title: string
      kind: string
      sport_type: number | null
      starts_at: string
      place: string
      seats: number | null
      spectators: boolean
    }) => post<SportEventRow>('/directors/sport-events/', body),
    onSuccess: done,
  })
}

export function useDecideApplication() {
  const done = useSportInvalidate()
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: ApplicationStatus }) =>
      patch<SportApplicationRow>(`/directors/sport-applications/${id}/`, { status }),
    onSuccess: done,
  })
}

export function useReleasePlayer() {
  const done = useSportInvalidate()
  return useMutation({
    mutationFn: ({ id, slot_from, slot_to }: { id: number; slot_from: number | null; slot_to: number | null }) =>
      post<SportApplicationRow>(`/directors/sport-applications/${id}/release/`, { slot_from, slot_to }),
    meta: { saved: true },
    onSuccess: done,
  })
}

export const useMySport = (enabled = true) =>
  useQuery({ queryKey: ['my-sport'], queryFn: () => get<{ rows: SportEventRow[] }>('/my/sport-events/'), enabled })

export function useApplySport() {
  const done = useSportInvalidate()
  return useMutation({
    mutationFn: ({ id, kind, comment }: { id: number; kind: 'play' | 'watch'; comment: string }) =>
      post<SportApplicationRow>(`/my/sport-events/${id}/apply/`, { kind, comment }),
    onSuccess: done,
  })
}

export function useWithdrawSport() {
  const done = useSportInvalidate()
  return useMutation({
    mutationFn: (id: number) => api<void>(`/my/sport-applications/${id}/`, { method: 'DELETE' }),
    onSuccess: done,
  })
}
