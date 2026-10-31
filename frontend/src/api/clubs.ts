/**
 * Запросы кружков (31.10.2026): кружки, правка, архив и записанные — у администратора.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, get, patch, post } from './client'

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
