/**
 * Сдача ДЗ в LMS (решение владельца, 30.09.2026): задание урока, загрузка
 * файлов прямо в хранилище по подписанной ссылке, сдача ученика, проверка
 * учителя, сводка «кто не сдаёт» для куратора и руководителей.
 *
 * Файл идёт с устройства в хранилище мимо сервера: сервер выдаёт ссылку
 * (или ссылки частей для большого файла), экран кладёт байты, сервер
 * проверяет, что пришло. Отдаётся файл короткой подписанной ссылкой после
 * проверки прав (`useFileLink`).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, get, post, put } from './client'
import { query } from './academics'
import type { AcadPerson } from './academics'
import { t } from '../i18n'

export type FileKind = 'pdf' | 'image' | 'audio' | 'video' | 'other'

export interface HomeworkFile {
  id: number
  name: string
  kind: FileKind
  content_type: string
  size: number
  /** PDF, склеенный из снимков: сколько было фото */
  photos: number | null
  state: 'uploading' | 'ready'
}

export type LatePolicy = 'accept' | 'close'

export interface HomeworkLesson {
  id: number
  date: string
  slot: number
  subject: string
  cohort: string
  cohort_kind: 'group' | 'subgroup' | 'stream'
  teacher: AcadPerson | null
  course: number
}

export interface HomeworkAssignment {
  id: number
  lesson: HomeworkLesson
  /** текст ДЗ урока */
  text: string
  requires_submission: boolean
  due_at: string | null
  late_policy: LatePolicy
  late_policy_title: string
  files: HomeworkFile[]
}

export interface HomeworkSubmission {
  id: number
  text: string
  link: string
  comment: string
  submitted_at: string | null
  /** на сколько минут позже срока; вовремя — null */
  late_minutes: number | null
  checked_at: string | null
  /** 1–10; проверено без оценки — null при заполненном checked_at */
  grade: number | null
  teacher_comment: string
  files: HomeworkFile[]
  /** только у проверяющего */
  student?: { id: number; full_name: string; short: string; group: string }
  checked_by?: string
}

export interface HomeworkLimits {
  file_mb: number
  video_mb: number
  max_files: number
}

/* --- Учитель: ДЗ урока ------------------------------------------------------ */

export interface LessonHomework {
  lesson: number
  assignment: number | null
  requires_submission: boolean
  due_at: string | null
  late_policy: LatePolicy
  files: HomeworkFile[]
  /** сроки на выбор: начало следующего урока журнала и «сегодня 20:00» */
  options: { next_lesson: string | null; evening: string }
  recipients: { count: number; cohort: string; kind: 'group' | 'subgroup' | 'stream' }
  policies: { code: LatePolicy; title: string }[]
  may_edit: boolean
  limits: HomeworkLimits
}

export const useLessonHomework = (lesson: number | null) =>
  useQuery({
    queryKey: ['homework', 'lesson', lesson],
    queryFn: () => get<LessonHomework>(`/homework/lessons/${lesson}/`),
    enabled: lesson !== null,
  })

function useHomeworkMutation<TInput, TOut>(fn: (input: TInput) => Promise<TOut>, saved = false) {
  const client = useQueryClient()
  return useMutation({
    meta: saved ? { saved: true } : undefined,
    mutationFn: fn,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['homework'] })
      void client.invalidateQueries({ queryKey: ['acad'] })
    },
  })
}

export const useSaveLessonHomework = () =>
  useHomeworkMutation(
    (input: { lesson: number; requires_submission: boolean; due_at: string | null; late_policy: LatePolicy }) =>
      put<LessonHomework>(`/homework/lessons/${input.lesson}/`, input),
    true,
  )

/* --- Файлы ---------------------------------------------------------------- */

interface UploadPlan {
  file: number
  method: 'single' | 'multipart'
  url?: string
  upload_id: string
  part_size?: number
  parts?: { number: number; url: string }[]
}

/**
 * Загрузить файл: к заданию урока (`{ lesson }`, учитель) или в свою работу
 * (`{ assignment }`, ученик). Большой файл — по частям; `onProgress` — доля 0…1.
 */
export async function uploadHomeworkFile(
  target: { lesson: number } | { assignment: number },
  file: Blob & { name?: string },
  options: {
    name?: string
    photos?: number
    onProgress?: (share: number) => void
    /** строка файла заведена: сорвётся загрузка — её убирают `useDropHomeworkFile`, иначе сдача ждёт её вечно */
    onStart?: (file: number) => void
  } = {},
): Promise<HomeworkFile> {
  const name = options.name ?? file.name ?? t('файл')
  const plan = await post<UploadPlan>('/homework/uploads/', {
    ...target,
    name,
    size: file.size,
    content_type: file.type,
    photos: options.photos,
  })
  options.onStart?.(plan.file)
  const parts: { number: number; etag: string }[] = []
  if (plan.method === 'single' && plan.url) {
    await putBytes(plan.url, file, (loaded) => options.onProgress?.(loaded / Math.max(file.size, 1)))
  } else {
    const size = plan.part_size ?? file.size
    let sent = 0
    for (const part of plan.parts ?? []) {
      const chunk = file.slice((part.number - 1) * size, part.number * size)
      const etag = await putBytes(part.url, chunk, (loaded) => options.onProgress?.((sent + loaded) / Math.max(file.size, 1)))
      sent += chunk.size
      parts.push({ number: part.number, etag })
    }
  }
  return post<HomeworkFile>(`/homework/files/${plan.file}/complete/`, { parts })
}

/** PUT байтов на подписанный адрес с ходом загрузки; ответ — ETag (нужен частям). */
function putBytes(url: string, body: Blob, onProgress: (loaded: number) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('PUT', url)
    // локальное хранилище разработки — адрес самого сайта: нужна сессия и CSRF
    if (url.startsWith('/')) {
      request.withCredentials = true
      const token = document.cookie.match(/csrftoken=([^;]+)/)?.[1]
      if (token) request.setRequestHeader('X-CSRFToken', token)
    }
    request.upload.onprogress = (event) => onProgress(event.loaded)
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) resolve((request.getResponseHeader('ETag') ?? '').replace(/"/g, ''))
      else reject(new Error(t('Файл не загрузился (HTTP {status}) — попробуйте ещё раз', { status: request.status })))
    }
    request.onerror = () => reject(new Error(t('Файл не загрузился: нет связи с хранилищем — попробуйте ещё раз')))
    request.send(body)
  })
}

export const useDropHomeworkFile = () =>
  useHomeworkMutation((id: number) => api<{ dropped: number }>(`/homework/files/${id}/`, { method: 'DELETE' }))

export interface FileLink extends HomeworkFile {
  url: string
}

/** Короткая подписанная ссылка на файл — после проверки прав; живёт минуты. */
export const fetchFileLink = (id: number, download = false) => get<FileLink>(`/homework/files/${id}/link/${download ? '?download=1' : ''}`)

export const useFileLink = (id: number | null) =>
  useQuery({
    queryKey: ['homework', 'link', id],
    queryFn: () => fetchFileLink(id as number),
    enabled: id !== null,
    // ссылка живёт 5 минут — берём новую раньше
    staleTime: 3 * 60 * 1000,
  })

/* --- Ученик ---------------------------------------------------------------- */

export type StudentState = 'todo' | 'review' | 'checked' | 'missed'

export interface MyHomework extends HomeworkAssignment {
  state: StudentState
  past_due: boolean
  submission: HomeworkSubmission | null
}

export interface MyHomeworkList {
  items: MyHomework[]
  counts: Record<StudentState, number>
  limits: HomeworkLimits
  now: string
}

export interface MyHomeworkDetail extends MyHomework {
  /** можно ли сейчас сдать или заменить работу; нельзя — причина словами */
  may_change: boolean
  change_note: string
  limits: HomeworkLimits
}

export const useMyHomework = (enabled = true) =>
  useQuery({ queryKey: ['homework', 'my'], queryFn: () => get<MyHomeworkList>('/homework/my/'), enabled })

export const useMyHomeworkDetail = (id: number | null) =>
  useQuery({
    queryKey: ['homework', 'my', id],
    queryFn: () => get<MyHomeworkDetail>(`/homework/my/${id}/`),
    enabled: id !== null,
  })

export const useSubmitHomework = () =>
  useHomeworkMutation((input: { id: number; text: string; link: string; comment: string }) => post<MyHomeworkDetail>(`/homework/my/${input.id}/submit/`, input))

/* --- Учитель: проверка ----------------------------------------------------- */

export type ReviewTab = 'unchecked' | 'running' | 'checked'

export interface ReviewItem extends HomeworkAssignment {
  total: number
  submitted: number
  unchecked: number
  tab: ReviewTab
}

export const useReviewList = () =>
  useQuery({ queryKey: ['homework', 'review'], queryFn: () => get<{ items: ReviewItem[]; counts: Record<ReviewTab, number> }>('/homework/review/') })

export interface ReviewStudent {
  student: { id: number; full_name: string; short: string; group: string }
  state: 'unchecked' | 'checked' | 'missed'
  /** «н» в день урока */
  absent: boolean
  submission: HomeworkSubmission | null
}

export interface ReviewDetail extends ReviewItem {
  students: ReviewStudent[]
  may_check: boolean
}

export const useReviewDetail = (id: number | null) =>
  useQuery({
    queryKey: ['homework', 'review', id],
    queryFn: () => get<ReviewDetail>(`/homework/review/${id}/`),
    enabled: id !== null,
  })

export const useCheckSubmission = () =>
  useHomeworkMutation((input: { id: number; mark: number | null; comment: string }) =>
    post<HomeworkSubmission>(`/homework/submissions/${input.id}/check/`, { grade: input.mark, comment: input.comment }),
  )

/* --- Куратор и руководители -------------------------------------------------- */

export interface HomeworkOverviewRow {
  id: number
  full_name: string
  short: string
  group: string
  total: number
  on_time: number
  late: number
  missed: number
  pct: number | null
}

export const useHomeworkOverview = (group = '') =>
  useQuery({
    queryKey: ['homework', 'overview', group],
    queryFn: () =>
      get<{ period: { start: string; end: string }; rows: HomeworkOverviewRow[]; groups: string[]; behind: { pct: number; missed: number } }>(
        `/homework/overview/${query({ group })}`,
      ),
  })

/** Выполнение ДЗ за период — из сдач, руками не вносится. */
export interface HomeworkCompletion {
  total: number
  on_time: number
  late: number
  missed: number
  pct: number | null
}
