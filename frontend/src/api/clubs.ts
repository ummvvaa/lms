/**
 * Запросы кружков (31.10.2026): кружки, правка, архив и записанные — у администратора.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, get, patch, post } from './client'
import type { ScanAnswer } from './sport'

export interface ClubStudent {
  id: number
  full_name: string
  short_name: string
  group: string
  group_id: number | null
  parallel: number
}

export interface ClubMeeting {
  weekday: number
  day: string
  starts: string
  ends: string
}

export interface ClubCard {
  id: number
  title: string
  description: string
  mentor_name: string
  /** «Пн, Чт 15:00–18:00» — с сервера */
  schedule: string
  meetings: ClubMeeting[]
  parallels: number[]
  enroll_until: string | null
  open: boolean
  marks_enabled: boolean
}

export interface ClubAdminRow extends ClubCard {
  mentor: number | null
  mentor_account: string
  enrolled: number
  archived: boolean
}

export interface ClubMember {
  id: number
  student: ClubStudent
  enrolled_at: string
  ended_at: string | null
  left: boolean
}

export interface ClubDraft {
  title: string
  description: string
  mentor_name: string
  mentor: number | null
  enroll_until: string | null
  marks_enabled: boolean
  meetings: { weekday: number; starts: string; ends: string }[]
  parallels: number[]
}

export const useClubs = (archived: boolean) =>
  useQuery({
    queryKey: ['clubs', archived],
    queryFn: () => get<{ rows: ClubAdminRow[]; archived_total: number }>(`/clubs/${archived ? '?archived=1' : ''}`),
  })

export const useMentorAccounts = () =>
  useQuery({
    queryKey: ['club-mentors'],
    queryFn: () => get<{ rows: { id: number; title: string }[] }>('/clubs/mentors/'),
  })

export const useClubMembers = (id: number | null, group: string) =>
  useQuery({
    queryKey: ['club-members', id, group],
    queryFn: () =>
      get<{ club: ClubAdminRow; rows: ClubMember[]; groups: { id: number; code: string }[]; active: number }>(
        `/clubs/${id}/members/${group ? `?group=${group}` : ''}`,
      ),
    enabled: id !== null,
  })

function useClubsRefresh() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['clubs'] })
    void queryClient.invalidateQueries({ queryKey: ['club-members'] })
    void queryClient.invalidateQueries({ queryKey: ['my-clubs'] })
    void queryClient.invalidateQueries({ queryKey: ['mentor-clubs'] })
  }
}

export function useSaveClub() {
  const refresh = useClubsRefresh()
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<ClubDraft> & { id: number | null; archived?: boolean }) =>
      id === null ? post<ClubAdminRow>('/clubs/', body) : patch<ClubAdminRow>(`/clubs/${id}/`, body),
    onSuccess: refresh,
  })
}

export function useArchiveClub() {
  const refresh = useClubsRefresh()
  return useMutation({
    mutationFn: (id: number) => api<void>(`/clubs/${id}/`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
}

/* --- Ученик: свои кружки ------------------------------------------------- */

export interface ClubHomework {
  id: number
  club: number
  text: string
  due: string
  file_name: string
  has_file: boolean
  created_at: string
  updated_at: string
  author: string
}

export interface MyClub extends ClubCard {
  enrolled: boolean
  enrolled_at: string | null
  can_enroll: boolean
  /** пересечения со своей спортивной секцией — словами с сервера */
  overlaps: string[]
  homework: ClubHomework[]
}

export interface MyClubsData {
  clubs: MyClub[]
  /** встречи своих кружков сегодня — строка на главной */
  today: { id: number; title: string; time: string }[]
  warnings?: string[]
}

export const useMyClubs = (enabled = true) =>
  useQuery({ queryKey: ['my-clubs'], queryFn: () => get<MyClubsData>('/my/clubs/'), enabled })

export function useMyClubAction() {
  const queryClient = useQueryClient()
  const done = (data: MyClubsData) => queryClient.setQueryData(['my-clubs'], data)
  return {
    enroll: useMutation({
      mutationFn: (id: number) => post<MyClubsData>(`/my/clubs/${id}/enroll/`),
      onSuccess: done,
    }),
    leave: useMutation({
      mutationFn: (id: number) => post<MyClubsData>(`/my/clubs/${id}/leave/`),
      onSuccess: done,
    }),
  }
}

/* --- Ментор своего кружка и администратор -------------------------------- */

export interface MentorClub extends ClubCard {
  enrolled: number
}

export interface MentorMember extends ClubMember {
  notes: number
}

export interface ClubNote {
  id: number
  student: ClubStudent
  text: string
  created_at: string
  author: string
}

export type MeetingState = 'none' | 'soon' | 'live' | 'past'

export interface ClubSession {
  club: ClubCard
  date: string
  state: MeetingState
  time: string
  came: number
  students: (ClubStudent & { came: boolean; method: '' | 'qr' | 'manual'; at: string | null })[]
}

export const useMentorClubs = () =>
  useQuery({ queryKey: ['mentor-clubs'], queryFn: () => get<{ clubs: MentorClub[] }>('/clubs/mine/') })

export const useClubStudents = (id: number | null) =>
  useQuery({
    queryKey: ['club-students', id],
    queryFn: () => get<{ club: ClubCard; rows: MentorMember[] }>(`/clubs/${id}/students/`),
    enabled: id !== null,
  })

export const useClubHomework = (id: number | null) =>
  useQuery({
    queryKey: ['club-homework', id],
    queryFn: () => get<{ club: ClubCard; rows: ClubHomework[] }>(`/clubs/${id}/homework/`),
    enabled: id !== null,
  })

/** Задание с файлом уходит формой: файл — частью тела запроса. */
function homeworkForm(body: { text?: string; due?: string; file?: File | null; drop_file?: boolean }): FormData {
  const form = new FormData()
  if (body.text !== undefined) form.append('text', body.text)
  if (body.due !== undefined) form.append('due', body.due)
  if (body.file) form.append('file', body.file)
  if (body.drop_file) form.append('drop_file', '1')
  return form
}

export function useHomeworkAction(club: number) {
  const queryClient = useQueryClient()
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['club-homework', club] })
    void queryClient.invalidateQueries({ queryKey: ['my-clubs'] })
  }
  return {
    publish: useMutation({
      mutationFn: (body: { text: string; due: string; file: File | null }) =>
        api<ClubHomework>(`/clubs/${club}/homework/`, { method: 'POST', body: homeworkForm(body) }),
      onSuccess: refresh,
    }),
    edit: useMutation({
      mutationFn: ({ id, ...body }: { id: number; text: string; due: string; file: File | null; drop_file: boolean }) =>
        api<ClubHomework>(`/clubs/${club}/homework/${id}/`, { method: 'PATCH', body: homeworkForm(body) }),
      onSuccess: refresh,
    }),
    withdraw: useMutation({
      mutationFn: (id: number) => api<void>(`/clubs/${club}/homework/${id}/`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
  }
}

export const homeworkFilePath = (id: number) => `/clubs/homework/${id}/file/`

export const useClubNotes = (id: number | null, student: number | null = null) =>
  useQuery({
    queryKey: ['club-notes', id, student],
    queryFn: () =>
      get<{ club: ClubCard; rows: ClubNote[] }>(`/clubs/${id}/notes/${student ? `?student=${student}` : ''}`),
    enabled: id !== null,
  })

export function useNoteAction(club: number) {
  const queryClient = useQueryClient()
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['club-notes', club] })
    void queryClient.invalidateQueries({ queryKey: ['club-students', club] })
  }
  return {
    add: useMutation({
      mutationFn: (body: { student: number; text: string }) => post<ClubNote>(`/clubs/${club}/notes/`, body),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<void>(`/clubs/notes/${id}/`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
  }
}

export const useClubSession = (id: number | null, live: boolean) =>
  useQuery({
    queryKey: ['club-session', id],
    queryFn: () => get<ClubSession>(`/clubs/${id}/session/`),
    enabled: id !== null,
    // «Пришли / Ещё нет» — опрос, пока встреча идёт, как у секций
    refetchInterval: live ? 4000 : false,
  })

export const clubSessionToken = (id: number) =>
  get<{ state: MeetingState; token: string; ttl: number; expires_in: number }>(`/clubs/${id}/session/token/`)

export function useClubMarkAction(club: number) {
  const queryClient = useQueryClient()
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ['club-session', club] })
  return {
    mark: useMutation({
      mutationFn: (student: number) => post<{ created: boolean }>(`/clubs/${club}/session/marks/`, { student }),
      onSuccess: refresh,
    }),
    unmark: useMutation({
      mutationFn: (student: number) =>
        api<void>(`/clubs/${club}/session/marks/?student=${student}`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
  }
}

export const clubScan = (token: string | null) => post<ScanAnswer>('/clubs/scan/', token ? { token } : {})

