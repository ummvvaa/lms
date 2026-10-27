/**
 * Запросы спортивных секций и билетов (27.10.2026): секции и часы, запись,
 * занятие с QR, посещаемость, раздачи билетов — у директора спорта и администратора;
 * «Моя секция», отметка по QR и билеты — у ученика; секция ученика — у куратора.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, get, patch, post } from './client'

export interface SectionStudent {
  id: number
  full_name: string
  short_name: string
  group: string
  parallel: number
}

export interface SlotRow {
  id: number
  section: number
  weekday: number
  day: string
  day_short: string
  starts: string
  ends: string
  parallel_from: number
  parallel_to: number
  room: string
  capacity: number
  taken?: number
  free?: number
}

export interface EnrollSettings {
  enroll_until: string | null
  open: boolean
}

export interface SectionRow {
  id: number
  title: string
  sport_type: number | null
  address: string
  enrolled: number
  no_hour: number
  capacity: number
  slots: SlotRow[]
}

export interface EnrollmentRow {
  id: number
  student: SectionStudent
  section: number
  section_title: string
  slot: number | null
  slot_title: string
  enrolled_at: string
  source: 'lms' | 'bot' | 'director'
  source_title: string
  slot_set_by_director: boolean
  percent: number | null
}

export interface SectionDetail {
  id: number
  title: string
  address: string
  slots: (SlotRow & { students: EnrollmentRow[] })[]
  no_hour: EnrollmentRow[]
}

export const useSections = () =>
  useQuery({
    queryKey: ['sport-sections'],
    queryFn: () => get<{ settings: EnrollSettings; rows: SectionRow[] }>('/sport/sections/'),
  })

export const useSection = (id: number | null) =>
  useQuery({
    queryKey: ['sport-section', id],
    queryFn: () => get<SectionDetail>(`/sport/sections/${id}/`),
    enabled: id !== null,
  })

function useSectionsRefresh() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['sport-sections'] })
    void queryClient.invalidateQueries({ queryKey: ['sport-section'] })
    void queryClient.invalidateQueries({ queryKey: ['sport-attendance'] })
  }
}

export function useEnrollSettings() {
  const refresh = useSectionsRefresh()
  return useMutation({
    mutationFn: (enroll_until: string | null) => patch<EnrollSettings>('/sport/settings/', { enroll_until }),
    onSuccess: refresh,
  })
}

export interface SlotDraft {
  id?: number
  key?: string
  weekday: number
  starts: string
  ends: string
  parallel_from: number
  parallel_to: number
  room: string
  capacity: number
}

export function useSaveSection() {
  const refresh = useSectionsRefresh()
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: number
      address: string
      slots: SlotDraft[]
      moves: Record<string, string | number | null>
    }) => patch<SectionDetail>(`/sport/sections/${id}/`, body),
    onSuccess: refresh,
  })
}

export function useEnrollStudent() {
  const refresh = useSectionsRefresh()
  return useMutation({
    mutationFn: (body: { student: number; slot: number }) => post<EnrollmentRow>('/sport/enrollments/', body),
    onSuccess: refresh,
  })
}

export function useMoveEnrollment() {
  const refresh = useSectionsRefresh()
  return useMutation({
    mutationFn: ({ id, slot }: { id: number; slot: number }) =>
      patch<EnrollmentRow>(`/sport/enrollments/${id}/`, { slot }),
    onSuccess: refresh,
  })
}

export function useRemoveEnrollment() {
  const refresh = useSectionsRefresh()
  return useMutation({
    mutationFn: (id: number) => api<void>(`/sport/enrollments/${id}/`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
}

export interface StudentHit extends SectionStudent {
  section: string
  slot: string
}

export const useStudentSearch = (query: string) =>
  useQuery({
    queryKey: ['sport-student-search', query],
    queryFn: () => get<{ rows: StudentHit[] }>(`/sport/students/?q=${encodeURIComponent(query)}`),
    enabled: query.trim().length >= 2,
    placeholderData: keepPreviousData,
  })

/* --- Занятие и QR ------------------------------------------------------- */

export type SessionState = 'soon' | 'live' | 'past'

export interface SessionRow extends SlotRow {
  title: string
  address: string
  date: string
  state: SessionState
  enrolled: number
  came: number
}

export interface SessionStudent extends SectionStudent {
  came: boolean
  method: '' | 'qr' | 'manual'
  at: string | null
}

export const useSessionsToday = () =>
  useQuery({
    queryKey: ['sport-sessions-today'],
    queryFn: () => get<{ date: string; now: string; rows: SessionRow[] }>('/sport/sessions/today/'),
    refetchInterval: 60_000,
  })

/** «Пришли / Ещё нет» — опрос раз в несколько секунд, пока занятие на экране. */
export const useSession = (id: number | null, live: boolean) =>
  useQuery({
    queryKey: ['sport-session', id],
    queryFn: () => get<SessionRow & { students: SessionStudent[] }>(`/sport/sessions/${id}/`),
    enabled: id !== null,
    refetchInterval: live ? 4_000 : false,
  })

export interface SessionToken {
  state: SessionState | 'none'
  token: string
  ttl: number
  expires_in: number
}

export const sessionToken = (id: number) => get<SessionToken>(`/sport/sessions/${id}/token/`)

export function useSessionAction() {
  const queryClient = useQueryClient()
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['sport-session'] })
    void queryClient.invalidateQueries({ queryKey: ['sport-sessions-today'] })
  }
  return {
    end: useMutation({
      mutationFn: (id: number) => post<SessionRow>(`/sport/sessions/${id}/end/`),
      onSuccess: refresh,
    }),
    mark: useMutation({
      mutationFn: ({ id, student }: { id: number; student: number }) =>
        post<{ created: boolean }>(`/sport/sessions/${id}/marks/`, { student }),
      onSuccess: refresh,
    }),
    unmark: useMutation({
      mutationFn: ({ id, student }: { id: number; student: number }) =>
        api<void>(`/sport/sessions/${id}/marks/?student=${student}`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
  }
}

export type ScanState =
  'login' | 'marked' | 'already' | 'stale' | 'foreign' | 'not_started' | 'ended' | 'not_enrolled' | 'no_hour'

export interface ScanBrief {
  section: string
  slot: string
  day: string
  starts: string
  ends: string
  grades: string
  address: string
}

export interface ScanAnswer {
  state: ScanState
  session?: ScanBrief
  mine?: { section: string; slot: string }
  marked_at?: string
  starts_at?: string
  hold_seconds?: number
}

export const scan = (token: string | null) => post<ScanAnswer>('/sport/scan/', token ? { token } : {})

/* --- Посещаемость ------------------------------------------------------- */

export type MarkCell = '' | 'qr' | 'manual' | 'absent'

export interface AttendanceData {
  section: number
  slot: SlotRow
  slot_title: string
  month: string
  dates: string[]
  held: string[]
  rows: { student: SectionStudent; cells: MarkCell[]; percent: number | null; below: boolean }[]
  figures: {
    average: number | null
    sessions: number
    sessions_total: number
    below: number
    manual: number
    threshold: number
  }
  sections: { id: number; title: string; slots: (SlotRow & { title: string })[] }[]
}

export const useSectionAttendance = (params: {
  section: number | null
  slot: number | null
  month: string
}) =>
  useQuery({
    queryKey: ['sport-attendance', params],
    queryFn: () => {
      const query = new URLSearchParams({ month: params.month })
      if (params.slot) query.set('slot', String(params.slot))
      else if (params.section) query.set('section', String(params.section))
      return get<AttendanceData>(`/sport/attendance/?${query.toString()}`)
    },
    placeholderData: keepPreviousData,
  })

/* --- Секция ученика у куратора ------------------------------------------- */

export interface StudentSectionInfo {
  enrolled: boolean
  section?: string
  address?: string
  slot?: string
  slot_day?: string
  percent?: number | null
  below?: boolean
  marks?: { date: string; came: boolean; method: string; at: string | null }[]
}

export const useStudentSection = (id: number | null) =>
  useQuery({
    queryKey: ['sport-student-section', id],
    queryFn: () => get<StudentSectionInfo>(`/sport/students/${id}/section/`),
    enabled: id !== null,
  })

export interface SectionColumn {
  section: string
  slot: string
  percent: number | null
  below: boolean
}

export const useStudentsSections = (group: number | null) =>
  useQuery({
    queryKey: ['sport-students-sections', group],
    queryFn: () =>
      get<{ rows: Record<string, SectionColumn> }>(
        `/sport/students/sections/${group ? `?group=${group}` : ''}`,
      ),
  })

/* --- Ученик: «Моя секция» ------------------------------------------------ */

export interface MySectionData extends EnrollSettings {
  parallel: number
  enrollment: {
    id: number
    section: number
    section_title: string
    address: string
    slot: SlotRow | null
    source: string
    next_at: string | null
    percent: number | null
    marks: { date: string; came: boolean; method: string; at: string | null }[]
    came: number
  } | null
  sections: { id: number; title: string; address: string; slots: SlotRow[] }[]
}

export const useMySection = () =>
  useQuery({ queryKey: ['my-section'], queryFn: () => get<MySectionData>('/my/section/') })

export function useMySectionAction() {
  const queryClient = useQueryClient()
  const done = (data: MySectionData) => queryClient.setQueryData(['my-section'], data)
  return {
    enroll: useMutation({
      mutationFn: (slot: number) => post<MySectionData>('/my/section/enroll/', { slot }),
      onSuccess: done,
    }),
    leave: useMutation({
      mutationFn: () => post<MySectionData>('/my/section/leave/'),
      onSuccess: done,
    }),
  }
}

/* --- Билеты --------------------------------------------------------------- */

export type DropStage = 'announce' | 'open' | 'gone' | 'past'

export interface TicketDropRow {
  id: number
  title: string
  event_at: string
  place: string
  count: number
  opens_at: string
  pickup: string
  parallel_from: number
  parallel_to: number
  offer_minutes: number
  stage: DropStage
  received: number
  queued?: number
  left: number
}

export type ClaimStatus = 'received' | 'queued' | 'offered' | 'declined' | 'expired' | 'left' | 'missed'

export interface TicketClaimRow {
  id: number
  student: SectionStudent
  pressed_at: string
  status: ClaimStatus
  status_title: string
  from_queue: boolean
  place: number | null
  offer_until: string | null
}

export const useTicketDrops = () =>
  useQuery({
    queryKey: ['sport-tickets'],
    queryFn: () => get<{ now: string; rows: TicketDropRow[] }>('/sport/tickets/'),
    refetchInterval: 15_000,
  })

export const useTicketDrop = (id: number | null) =>
  useQuery({
    queryKey: ['sport-ticket', id],
    queryFn: () =>
      get<TicketDropRow & { announced: number; claims: TicketClaimRow[] }>(`/sport/tickets/${id}/`),
    enabled: id !== null,
    refetchInterval: 10_000,
  })

export interface TicketDraft {
  title: string
  event_at: string
  place: string
  count: number
  opens_at: string
  pickup: string
  parallel_from: number
  parallel_to: number
}

export function useTicketActions() {
  const queryClient = useQueryClient()
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['sport-tickets'] })
    void queryClient.invalidateQueries({ queryKey: ['sport-ticket'] })
  }
  return {
    publish: useMutation({
      mutationFn: (body: TicketDraft) => post<TicketDropRow>('/sport/tickets/', body),
      onSuccess: refresh,
    }),
    missed: useMutation({
      mutationFn: (claim: number) => post<TicketClaimRow>(`/sport/ticket-claims/${claim}/missed/`),
      onSuccess: refresh,
    }),
  }
}

export interface MyDropRow extends TicketDropRow {
  mine: {
    status: ClaimStatus
    status_title: string
    place: number | null
    offer_until: string | null
    from_queue: boolean
  } | null
}

export const useMyTickets = () =>
  useQuery({
    queryKey: ['my-tickets'],
    queryFn: () => get<{ now: string; rows: MyDropRow[] }>('/my/tickets/'),
    refetchInterval: 20_000,
  })

export function useMyTicketAction() {
  const queryClient = useQueryClient()
  const done = () => void queryClient.invalidateQueries({ queryKey: ['my-tickets'] })
  return {
    claim: useMutation({
      mutationFn: (id: number) => post<MyDropRow>(`/my/tickets/${id}/claim/`),
      onSuccess: done,
    }),
    decline: useMutation({
      mutationFn: (id: number) => post<MyDropRow>(`/my/tickets/${id}/decline/`),
      onSuccess: done,
    }),
    accept: useMutation({
      mutationFn: (id: number) => post<MyDropRow>(`/my/tickets/${id}/accept/`),
      onSuccess: done,
    }),
  }
}
