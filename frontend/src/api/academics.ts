/**
 * Учебная часть: запросы к `/api/acad/…`.
 *
 * Типы повторяют словари сервера (`academics/payloads.py`): один вид урока,
 * состава и учителя на все экраны. Ключи запросов начинаются с `acad`, чтобы
 * запись отметки или правка урока сбрасывала всё учебное разом.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, get, patch, post } from './client'
import { patchJournal, type MarksAnswer } from './journalPatch'

export interface AcadSubject {
  id: number
  code: string
  /** название на языке интерфейса; нет перевода — русское */
  title: string
  /** исходное русское название — для правки названий на других языках */
  title_ru?: string
  /** название на казахском (интерфейс и отчёт родителям); пусто — русское */
  title_kk?: string
  /** название на английском (интерфейс); пусто — русское */
  title_en?: string
  short_title: string
  scheme: 'kz' | 'fo'
  scheme_title: string
  sor_max: number
  soch_max: number
}

export interface AcadPerson {
  id: number
  full_name: string
  short: string
}

export interface AcadCohort {
  id: number
  kind: 'group' | 'subgroup' | 'stream'
  kind_title: string
  name: string
  short_name: string
  group: string
  group_id?: number | null
  subject?: AcadSubject | null
  number?: number | null
  rule?: string
  groups?: number[]
  students: number
  member_ids?: number[]
  parts?: { id: number; name: string; kind: string }[]
  used?: string[] | AcadCourse[]
  candidates?: AcadStudent[]
  /** основной кабинет подгруппы */
  room?: string
  /** поток, внутри которого подгруппа */
  stream?: number | null
  /** у потока — подгруппы внутри него (английский EEP-8-1 из четырёх групп) */
  subgroups?: AcadCohort[]
}

export interface AcadCourse {
  id: number
  subject: AcadSubject
  cohort: AcadCohort
  teacher: AcadPerson | null
  title: string
  /** какой отзыв в отчёте родителям пишется по журналу */
  report_role?: '' | 'eep' | 'sat_verbal' | 'sat_math'
  report_role_title?: string
}

export interface AcadTeacher extends AcadPerson {
  email: string
  is_active: boolean
  subjects: AcadSubject[]
  subject_titles: string
  room: string
}

export interface AcadLesson {
  id: number
  course: number
  date: string
  weekday: string
  weekday_full: string
  date_words: string
  slot: number
  bell: string
  /** время начала по звонкам группы урока, «08:00»; звонка нет — пусто */
  starts: string
  room: string
  subject: AcadSubject
  cohort: AcadCohort
  teacher: AcadPerson | null
  substitute: AcadPerson | null
  actual_teacher: AcadPerson | null
  status: 'planned' | 'cancelled' | 'moved'
  status_title: string
  is_live: boolean
  reason: string
  moved_from_date: string | null
  moved_from_slot: number | null
  kind: 'fo' | 'sor' | 'soch'
  kind_label: string
  number: number | null
  max_score: number | null
  topic: string
  homework: string
  note: string
  is_one_off: boolean
  marked: boolean
  marked_at: string | null
  marked_by: AcadPerson | null
  state: 'past' | 'now' | 'future'
  title: string
}

export interface AcadStudent {
  id: number
  full_name: string
  short: string
  group: string
}

export type AcadMark = 'present' | 'absent' | 'late' | 'excused' | null

/** Опоздание: во сколько пришёл и на сколько опоздал; у опозданий до 30.09.2026 — пусто. */
export interface LateInfo {
  arrived?: string | null
  late_by?: number | null
  /** опоздание дольше правила школы считается пропуском: в листах и журнале оно читается «н» */
  late_as_absent?: boolean
}

export interface RosterRow extends AcadStudent, LateInfo {
  mark: AcadMark
  grade: number | null
  comment: string
  excused: boolean
  absences: number
  fo_avg: number | null
}

export interface AcadMeta {
  today: string
  today_words: string
  year: { id: number; title: string; starts: string; ends: string } | null
  quarters: { id: number; number: number; title: string; starts: string; ends: string; closed: boolean; current: boolean }[]
  current_quarter: number | null
  scale: {
    weight_fo: number
    weight_sor: number
    weight_soch: number
    threshold_5: number
    threshold_4: number
    threshold_3: number
    fo_max: number
    edit_days: number
  }
  reports: { cadence: string; cadence_title: string }
  subjects: AcadSubject[]
  rooms: string[]
  periods: { code: string; title: string }[]
  mark_words: Record<string, string>
  mark_short: Record<string, string>
  kinds: { code: string; title: string }[]
  may_edit_schedule: boolean
  role: string
}

export interface AcadDay {
  date: string
  weekday: string
  school_day: boolean
  is_today: boolean
}

/** Ряд недели — время начала урока по звонкам его группы (`key` — «08:00»,
 *  у урока без звонка — «#5»). `slot` — номер, если в это время он один. */
export interface AcadWeekRow {
  key: string
  starts: string
  ends: string
  slot: number | null
}

export interface AcadWeek {
  from: string
  to: string
  today: string
  slots: number[]
  /** ряды сетки по времени, собирает сервер по тем же звонкам, что накладки */
  rows: AcadWeekRow[]
  /** на экране больше одного расписания звонков: номер пишется у урока */
  mixed: boolean
  /** группы экрана, которым не назначены звонки: у их уроков нет времени. Ученику не приходит */
  no_bells?: string[]
  days: AcadDay[]
  lessons: AcadLesson[]
  ghosts: { lesson: number; date: string; slot: number; starts: string; moved_to_date: string; moved_to_slot: number }[]
}

export interface AcadConflict {
  kind: string
  text: string
  lesson: number | null
  other: number | null
  date?: string
  slot?: number
  /** с какого времени уроки пересекаются: «13:15» по звонкам групп */
  time?: string
  /** в каком виде недели накладку видно целиком: «Разобрать» открывает его */
  where?: { view: 'group' | 'teacher' | 'room'; key: string }
}

export interface AcadRequest {
  id: number
  teacher: AcadPerson
  lesson: AcadLesson
  wanted: string
  reason: string
  status: 'pending' | 'approved' | 'rejected'
  status_title: string
  answer: string
  decided_by: AcadPerson | null
  decided_at: string | null
  created_at: string
}

export interface ScheduleWeek extends AcadWeek {
  view: 'group' | 'teacher' | 'room'
  key: string
  conflicts: AcadConflict[]
  conflict_ids: number[]
  next_week_conflicts: number
  changes: AcadLesson[]
  requests: { id: number; teacher: AcadPerson; lesson: AcadLesson; wanted: string; reason: string; created_at: string }[]
  log: { id: number; when: string; who: string; text: string; lesson: number | null }[]
  groups: { id: number; code: string }[]
  teachers: AcadPerson[]
  rooms: string[]
  week_total: number
  series_total: number
  teachers_total: number
  groups_total: number
  empty: boolean
}

export interface LessonDetail {
  lesson: AcadLesson
  course: AcadCourse
  repeat: string
  roster?: RosterRow[]
  absent?: string[]
  late?: string[]
  may_mark?: boolean
  may_grade?: boolean
  locked?: boolean
  quarter_closed?: boolean
  may_edit?: boolean
  may_remind?: boolean
  may_request?: boolean
  conflicts?: AcadConflict[]
  scale?: { fo_max: number; edit_days: number }
  mine?: { mark: AcadMark; grade: number | null; comment: string; homework: string } & LateInfo
}

export interface CourseStats {
  total: number
  absent: number
  excused: number
  late: number
  /** сумма минут опозданий, где время прихода известно */
  late_minutes?: number
  /** опозданий без времени прихода — до 30.09.2026 время не записывалось */
  late_unknown?: number
  attendance_pct: number | null
  fo_avg: number | null
  fo_count: number
  sor_got: number
  sor_max: number
  sor_count: number
  soch_got: number
  soch_max: number
  soch_count: number
  quarter_pct: number | null
  quarter_grade: number | null
  final: number | null
  final_reason: string
}

export interface JournalColumn {
  lesson: number
  date: string
  weekday: string
  slot: number
  kind: 'fo' | 'sor' | 'soch'
  kind_label: string
  max_score: number | null
  state: 'past' | 'now' | 'future'
  future: boolean
  unmarked: boolean
  locked: boolean
  /** ставит ли оценку этот человек: учитель урока, заменяющий, Кымбат, администратор */
  may_grade: boolean
  /** отмечает ли посещаемость: тот, кто ведёт урок, и администратор */
  may_mark: boolean
  /** кто ведёт урок на деле — для подсказки, если оценку ставит другой */
  teacher: string
  topic: string
  is_today: boolean
}

export interface JournalCell extends LateInfo {
  mark: AcadMark
  grade: number | null
  comment: string
}

/** Клетка «ДЗ» журнала: оценка, проверено без оценки, ждёт проверки, не сдано, срок идёт. */
export interface JournalHomeworkCell {
  state: 'checked' | 'submitted' | 'missed' | 'pending'
  grade: number | null
  late: boolean
  submission: number | null
}

export interface Journal {
  course: AcadCourse
  period: { code: string; title: string; from: string; to: string }
  periods: { code: string; title: string }[]
  quarter: { id: number; number: number; title: string; ends: string; closed: boolean } | null
  scheme: 'kz' | 'fo'
  columns: JournalColumn[]
  /** колонка «ДЗ» рядом с уроком — только у уроков с ДЗ со сдачей в LMS */
  homework_columns?: { lesson: number; assignment: number; due_at: string | null }[]
  /** `homework` — клетки «ДЗ» строки в порядке `homework_columns` */
  rows: (AcadStudent & { cells: JournalCell[]; homework?: JournalHomeworkCell[]; stats: CourseStats })[]
  kpis: {
    held: number
    planned: number
    unmarked: number
    first_unmarked: number | null
    fo_avg: number | null
    low: number
    next_assessment: AcadLesson | null
  }
  today_lesson: AcadLesson | null
  topics: AcadLesson[]
  /** уроки периода строкой: список на телефоне и выбор урока для СОР или СОЧ */
  all_lessons: Pick<AcadLesson, 'id' | 'date' | 'weekday' | 'slot' | 'kind' | 'kind_label' | 'state' | 'is_live' | 'marked' | 'topic'>[]
  scale: AcadMeta['scale']
  may_edit: boolean
  is_owner: boolean
  final_window: boolean
}

export interface TeacherToday {
  today: string
  today_words: string
  now_slot: number | null
  now_ends: string | null
  teacher: AcadTeacher
  has_courses: boolean
  lessons: (AcadLesson & { absent: string[]; is_substitution: boolean })[]
  now_lesson: AcadLesson | null
  unmarked: AcadLesson[]
  week_grades: number
  journals: (AcadCourse & { students: number; held: number; planned: number; unmarked: number })[]
  assessments: AcadLesson[]
  changes: AcadLesson[]
}

export interface TeacherJournals {
  teacher: AcadTeacher
  quarter: { number: number; title: string; ends: string; closed: boolean } | null
  scale: { weight_fo: number; weight_sor: number; weight_soch: number; edit_days: number }
  rows: (AcadCourse & {
    students: number
    held: number
    planned: number
    unmarked: number
    fo_avg: number | null
    sor_done: number
    sor_all: number
    low: number
  })[]
}

export interface TeacherProfileData {
  teacher: AcadTeacher
  hours: number
  journals: number
  requests: { id: number; lesson: AcadLesson; wanted: string; reason: string; status: string; status_title: string; answer: string }[]
}

/** Уровень английского (A1–C2) — сотрудникам; ученику не показывается. */
export interface EnglishLevelInfo {
  level: string
  since: string | null
  history: { level: string; since: string; by: string }[]
  levels: string[]
  may_edit: boolean
}

export const useSetEnglishLevel = () =>
  useAcadMutation((input: { student: number; level: string; since?: string }) => post<EnglishLevelInfo>(`/acad/students/${input.student}/english-level/`, input), { saved: true })

export interface TeacherStudent {
  english?: EnglishLevelInfo
  student: AcadStudent
  curator: AcadPerson | null
  curator_email: string
  courses: {
    course: AcadCourse
    stats: CourseStats
    recent: ({ lesson: AcadLesson; mark: AcadMark; grade: number | null } & LateInfo)[]
  }[]
  excuses: AcadExcuse[]
}

export interface AcadExcuse {
  id: number
  student: number
  starts: string
  ends: string
  reason: string
  document: string
  document_title: string
  has_file: boolean
  created_by: string
  created_at: string
}

export interface StudentGrades {
  english?: EnglishLevelInfo
  student: AcadStudent
  period: { code: string; title: string; from: string; to: string }
  periods: { code: string; title: string }[]
  subjects: { course: AcadCourse; stats: CourseStats }[]
  attendance: { total: number; absent: number; excused: number; late: number; late_minutes?: number; late_unknown?: number; pct: number | null }
  days: {
    date: string
    weekday: string
    marks: { lesson: number; subject: string; slot: number; mark: AcadMark }[]
    has_absent: boolean
  }[]
  scale: { weight_fo: number; weight_sor: number; weight_soch: number; fo_max: number }
  /** оценки периода строками — с комментарием учителя */
  grades?: {
    lesson: number
    date: string
    subject: string
    subject_title: string
    /** `homework` — оценка за ДЗ со сдачей в LMS, из 10; не СОР и не СОЧ */
    kind: 'fo' | 'sor' | 'soch' | 'homework'
    kind_label: string
    value: number
    max: number | null
    comment: string
  }[]
  /** выполнение ДЗ со сдачей за период — из сдач, руками не вносится */
  homework?: { total: number; on_time: number; late: number; missed: number; pct: number | null }
  unexcused_days?: string[]
  excuses?: AcadExcuse[]
  may_excuse?: boolean
}

export interface CohortsScreen {
  groups: {
    id: number
    code: string
    students: number
    curator: string
    subgroups: AcadCohort[]
    streams: string[]
  }[]
  streams: AcadCohort[]
  subjects: AcadSubject[]
  kpis: { groups: number; students: number; subgroups: number; subgroup_groups: number; streams: number; not_split: number }
}

export interface TeacherRow extends AcadTeacher {
  hours: number
  journals: number
  week: number
  unmarked: AcadLesson[]
  fill: number | null
  last_marked: AcadLesson | null
  courses?: (AcadCourse & { hours: number; students: number })[]
}

export interface TeachersScreen {
  rows: TeacherRow[]
  kpis: { teachers: number; with_lessons: number; journals: number; unmarked_teachers: number; substitutions: number }
  subjects: AcadSubject[]
  may_create: boolean
}

export interface SchoolGrades {
  period: { code: string; title: string; from: string; to: string }
  periods: { code: string; title: string }[]
  subjects: AcadSubject[]
  heat: { group: string; group_id: number; cells: { subject: number; pct: number | null; tone: string }[]; attendance: number | null }[]
  /** `empty_journal_days` — окно «журнал без оценок», настройка школы */
  kpis: { attendance: number | null; risk: number; empty_journals: number; empty_journal_days: number; finals: number; quarter_ends: string | null }
  risk: (AcadStudent & { subjects: string[] })[]
  worst_attendance: (AcadStudent & { attendance: StudentGrades['attendance'] })[]
  /** журналы без оценок за окно школы: короткой строкой — название и учитель */
  empty_journals: { id: number; title: string; teacher: AcadPerson | null }[]
  has_courses: boolean
}

export interface GroupGrades {
  group: string
  group_id?: number
  period: { code: string; title: string; from: string; to: string }
  periods: { code: string; title: string }[]
  subjects: AcadSubject[]
  rows: (AcadStudent & {
    cells: { text: string; grade: number | null; pct: number | null; tone: string; none: string }[]
    attendance_pct: number | null
    absent: number
    excused: number
  })[]
  need_help: (AcadStudent & { low: string[]; attendance_pct: number | null })[]
  journals: (AcadCourse & { unmarked: number })[]
  /** порог посещаемости из настроек школы: ниже — процент выделен */
  attendance_below: number
  /** `unmarked_days` — окно неотмеченных уроков, настройка школы */
  kpis: { attendance: number | null; risk: number; absent: number; unmarked: number; unmarked_days: number }
  has_courses: boolean
}

export interface BellSchedule {
  id: number
  title: string
  /** название на языке интерфейса; `title` — как записано */
  name?: string
  groups: string[]
  bells: { number: number; starts: string; ends: string }[]
}

export interface YearScreen {
  year: { id: number; title: string; starts: string; ends: string } | null
  quarters: {
    id: number
    number: number
    /** название на языке интерфейса; `title` — как записано */
    name?: string
    title: string
    starts: string
    ends: string
    closed: boolean
    closed_at: string | null
    current: boolean
    past: boolean
  }[]
  /** `title` — как записано (для правки), `name` — на языке интерфейса (для показа) */
  breaks: { id: number; title: string; name?: string; starts: string; ends: string }[]
  holidays: { id: number; date: string; title: string; name?: string }[]
  /** расписания звонков карточками: у каждого свои группы, общего на всех нет (05.10.2026) */
  bell_schedules: BellSchedule[]
  /** активные группы, которым звонки не назначены: у их уроков нет времени */
  groups_without_bells: string[]
  scale: AcadMeta['scale']
  reports: {
    cadence: string
    cadence_title: string
    cadences: { code: string; title: string }[]
    sections: Record<'attendance' | 'grades' | 'exams' | 'documents' | 'curator' | 'discipline', boolean>
  }
  subjects: AcadSubject[]
}

export interface AcadDashboard {
  empty: boolean
  lessons_today?: number
  /** сколько уроков идёт сейчас — по звонкам их групп */
  now_count?: number
  unmarked?: number
  unmarked_teachers?: string[]
  changes?: number
  next_conflicts?: number
  next_conflict_text?: string
  requests?: number
  request_text?: string
  reports?: { title: string; total: number; sent: number } | null
}

/** `?a=1&b=2` из объекта без пустых значений. */
export function query(params: Record<string, string | number | null | undefined>): string {
  const pairs = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${key}=${encodeURIComponent(String(value))}`)
  return pairs.length ? `?${pairs.join('&')}` : ''
}

/** Звонки состава для списка «Урок» в формах: время — по звонкам его групп,
 *  как у сетки недели и проверки накладок. Без состава список пуст; `problem` —
 *  почему у состава нет звонков (группе не назначены, у групп потока разные). */
export function useCohortBells(cohort: number | null) {
  return useQuery({
    queryKey: ['acad', 'bells', cohort],
    queryFn: () => get<{ bells: { number: number; starts: string; ends: string }[]; problem?: string }>(`/acad/bells/${cohort ? `?cohort=${cohort}` : ''}`),
    staleTime: 60_000,
  })
}

export function useAcadMeta(enabled = true) {
  return useQuery({ queryKey: ['acad', 'meta'], queryFn: () => get<AcadMeta>('/acad/meta/'), enabled, staleTime: 60_000 })
}

export function useAcadLessons(params: Record<string, string | number | null | undefined>, enabled = true) {
  return useQuery({
    queryKey: ['acad', 'lessons', params],
    queryFn: () => get<AcadWeek>(`/acad/lessons/${query(params)}`),
    enabled,
    placeholderData: (prev) => prev,
  })
}

export function useLessonDetail(id: number | null) {
  return useQuery({
    queryKey: ['acad', 'lesson', id],
    queryFn: () => get<LessonDetail>(`/acad/lessons/${id}/`),
    enabled: id !== null && Number.isFinite(id),
  })
}

/**
 * Любая запись учебной части сбрасывает всё учебное: журнал, урок, неделю.
 *
 * Отметка и оценка (`marks`) — особый случай (D75): клетки открытых журналов
 * берутся из ответа сразу, перезапрос идёт за сводками; `meta` (год, четверти,
 * шкала) от них не меняется, уведомлений автору они не создают — эти запросы
 * не повторяются. Остальные записи (четверть, шкала, расписание) сбрасывают
 * и `meta`, и уведомления, как раньше.
 */
function useAcadMutation<TInput, TOut>(fn: (input: TInput) => Promise<TOut>, options: { saved?: boolean; marks?: boolean } = {}) {
  const client = useQueryClient()
  return useMutation({
    meta: options.saved ? { saved: true } : undefined,
    mutationFn: fn,
    onSuccess: (answer) => {
      if (options.marks) {
        const fresh = answer as unknown as MarksAnswer
        client.setQueriesData<Journal>({ queryKey: ['acad', 'journal'] }, (old) => (old ? patchJournal(old, fresh) : old))
        void client.invalidateQueries({ queryKey: ['acad'], predicate: (query) => query.queryKey[1] !== 'meta' })
        return
      }
      void client.invalidateQueries({ queryKey: ['acad'] })
      void client.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}

export const useSaveAttendance = () =>
  useAcadMutation(
    (input: { lesson: number; rows?: { student: number; mark: string; arrived?: string }[]; all_present?: boolean }) =>
      post<LessonDetail & { written: number; grades_dropped: number }>(`/acad/lessons/${input.lesson}/attendance/`, input),
    { marks: true },
  )

export const useSetGrade = () =>
  useAcadMutation(
    (input: { lesson: number; student: number; value: number | null; comment?: string }) =>
      post<LessonDetail & { grade: number | null; comment: string }>(`/acad/lessons/${input.lesson}/grade/`, input),
    { marks: true },
  )

export const useLessonMeta = () =>
  useAcadMutation(
    (input: { lesson: number; topic?: string; homework?: string; kind?: string; number?: number | null; max_score?: number | null }) =>
      patch<{ lesson: AcadLesson }>(`/acad/lessons/${input.lesson}/meta/`, input),
    { saved: true },
  )

export const useTeacherToday = (enabled = true) =>
  useQuery({ queryKey: ['acad', 'teacher-today'], queryFn: () => get<TeacherToday>('/acad/teacher/today/'), enabled })

export const useTeacherJournals = () =>
  useQuery({ queryKey: ['acad', 'teacher-journals'], queryFn: () => get<TeacherJournals>('/acad/teacher/journals/') })

export const useTeacherProfile = (enabled = true) =>
  useQuery({ queryKey: ['acad', 'teacher-profile'], queryFn: () => get<TeacherProfileData>('/acad/teacher/profile/'), enabled })

export const useTeacherStudent = (id: number | null) =>
  useQuery({
    queryKey: ['acad', 'teacher-student', id],
    queryFn: () => get<TeacherStudent>(`/acad/teacher/students/${id}/`),
    enabled: id !== null && Number.isFinite(id),
  })

export const useJournal = (id: number | null, period: string) =>
  useQuery({
    queryKey: ['acad', 'journal', id, period],
    queryFn: () => get<Journal>(`/acad/journals/${id}/${query({ period })}`),
    enabled: id !== null && Number.isFinite(id),
    placeholderData: (prev) => prev,
  })

export const useJournalFinal = () =>
  useAcadMutation(
    (input: { course: number; quarter: number; rows: { student: number; final: number | null; reason?: string }[] }) =>
      post<Journal & { written: number }>(`/acad/journals/${input.course}/final/`, input),
    { saved: true },
  )

export const useRequests = (enabled = true) =>
  useQuery({ queryKey: ['acad', 'requests'], queryFn: () => get<{ rows: AcadRequest[] }>('/acad/requests/'), enabled })

export const useSendRequest = () =>
  useAcadMutation((input: { lesson: number; wanted: string; reason: string }) => post<{ request: AcadRequest }>('/acad/requests/', input))

export const useDecideRequest = () =>
  useAcadMutation((input: { id: number; approve: boolean; answer?: string; date?: string; slot?: number; force?: boolean }) =>
    post<{ request: AcadRequest }>(`/acad/requests/${input.id}/decide/`, input),
  )

export const useRemindLesson = () => useAcadMutation((lesson: number) => post<{ reminded: string }>(`/acad/lessons/${lesson}/remind/`, {}))

// --- Правка расписания: Кымбат и администратор ------------------------------

export const useScheduleWeek = (params: { from?: string; view?: string; key?: string }) =>
  useQuery({
    queryKey: ['acad', 'schedule', params],
    queryFn: () => get<ScheduleWeek>(`/acad/schedule/${query(params)}`),
    placeholderData: (prev) => prev,
  })

export interface LessonInput {
  subject: number
  /** пусто — учитель не назначен */
  teacher: number | null
  cohort: number
  date: string
  slot: number
  room: string
  repeat: 'weekly' | 'once'
  note?: string
  force?: boolean
}

export const useCreateLesson = () =>
  useAcadMutation((input: LessonInput) => post<{ lesson: AcadLesson | null; created: number; series?: number }>('/acad/lessons/', input))

export const useCheckConflicts = () =>
  useMutation({
    mutationFn: (input: { teacher: number | null; cohort: number; date: string; slot: number; room?: string; exclude?: number }) =>
      post<{ conflicts: AcadConflict[]; school_day: boolean }>('/acad/conflicts/', input),
  })

export const useEditLesson = () =>
  useAcadMutation(
    (input: {
      id: number
      scope: 'this' | 'next'
      date?: string
      slot?: number
      room?: string
      /** пусто — учитель прежний */
      teacher?: number | null
      cohort?: number
      subject?: number
      reason?: string
      force?: boolean
    }) => post<{ lesson: AcadLesson | null; series?: number }>(`/acad/lessons/${input.id}/edit/`, input),
  )

/** Кто свободен на замену по времени звонков урока (накладка — по времени, не по номеру). */
export const useSubstitutes = (lessonId: number) =>
  useQuery({
    queryKey: ['acad', 'substitutes', lessonId],
    queryFn: () => get<{ rows: { id: number; free: boolean; busy_with: string }[] }>(`/acad/lessons/${lessonId}/substitutes/`),
  })

export const useSubstitute = () =>
  useAcadMutation((input: { id: number; teacher: number; reason: string }) => post<{ lesson: AcadLesson }>(`/acad/lessons/${input.id}/substitute/`, input))

export const useMoveLesson = () =>
  useAcadMutation((input: { id: number; date: string; slot: number; reason: string; force?: boolean }) =>
    post<{ lesson: AcadLesson }>(`/acad/lessons/${input.id}/move/`, input),
  )

export const useCancelLesson = () =>
  useAcadMutation((input: { id: number; reason: string }) => post<{ lesson: AcadLesson }>(`/acad/lessons/${input.id}/cancel/`, input))

export const useRestoreLesson = () => useAcadMutation((id: number) => post<{ lesson: AcadLesson }>(`/acad/lessons/${id}/restore/`, {}))

export const useDeletePreview = (id: number | null, scope: 'this' | 'next') =>
  useQuery({
    queryKey: ['acad', 'delete-preview', id, scope],
    queryFn: () => get<{ count: number; marked: number; from: string; to: string }>(`/acad/lessons/${id}/delete/${query({ scope })}`),
    enabled: id !== null,
  })

export const useDeleteLesson = () =>
  useAcadMutation((input: { id: number; scope: 'this' | 'next' }) =>
    post<{ deleted: number; count: number; marked: number }>(`/acad/lessons/${input.id}/delete/`, input),
  )

export const useCohorts = () => useQuery({ queryKey: ['acad', 'cohorts'], queryFn: () => get<CohortsScreen>('/acad/cohorts/') })

export const useAllCohorts = (enabled = true) =>
  useQuery({ queryKey: ['acad', 'cohorts-all'], queryFn: () => get<{ rows: AcadCohort[] }>('/acad/cohorts/all/'), enabled })

export const useCohort = (id: number | null) =>
  useQuery({ queryKey: ['acad', 'cohort', id], queryFn: () => get<AcadCohort>(`/acad/cohorts/${id}/`), enabled: id !== null })

export const useSplitGroup = () =>
  useAcadMutation((input: { group: string; subject: number; parts: number[][]; since: string; rule: string }) =>
    post<{ cohorts: AcadCohort[] }>('/acad/cohorts/split/', input),
  )

export const useMakeStream = () =>
  useAcadMutation((input: { name: string; parts: number[] }) => post<AcadCohort>('/acad/cohorts/stream/', input))

export const useUpdateCohort = () =>
  useAcadMutation((input: { id: number; members?: number[]; since?: string; name?: string; parts?: number[] }) =>
    patch<AcadCohort>(`/acad/cohorts/${input.id}/`, input),
  )

export const useDeleteCohort = () =>
  useAcadMutation((id: number) => api<{ deleted: number }>(`/acad/cohorts/${id}/`, { method: 'DELETE' }))

export const useTeachers = () => useQuery({ queryKey: ['acad', 'teachers'], queryFn: () => get<TeachersScreen>('/acad/teachers/') })

export const useTeacherDetail = (id: number | null) =>
  useQuery({ queryKey: ['acad', 'teacher', id], queryFn: () => get<TeacherRow>(`/acad/teachers/${id}/`), enabled: id !== null })

export const useUpdateTeacher = () =>
  useAcadMutation((input: { id: number; subjects?: number[]; room?: string }) => patch<TeacherRow>(`/acad/teachers/${input.id}/`, input), { saved: true })

export const useRemindTeacher = () => useAcadMutation((id: number) => post<{ reminded: number }>(`/acad/teachers/${id}/remind/`, {}))

export const useRemindAllTeachers = () => useAcadMutation(() => post<{ teachers: number }>('/acad/teachers/remind-all/', {}))

/** Раздел отчёта родителям у журнала: GE/EEP, SAT Verbal, SAT Math или нет. */
export const useCourseReportRole = () =>
  useAcadMutation((input: { course: number; report_role: string }) => post<AcadCourse>(`/acad/journals/${input.course}/report-role/`, input), { saved: true })

export const useReassignCourse = () =>
  useAcadMutation((input: { course: number; teacher: number; since: string }) => post<AcadCourse>(`/acad/journals/${input.course}/reassign/`, input))

export const useSchoolGrades = (period: string) =>
  useQuery({
    queryKey: ['acad', 'school-grades', period],
    queryFn: () => get<SchoolGrades>(`/acad/grades/school/${query({ period })}`),
    placeholderData: (prev) => prev,
  })

export const useSchoolGradesCell = (params: { group: string; subject: number; period: string } | null) =>
  useQuery({
    queryKey: ['acad', 'school-grades-cell', params],
    queryFn: () =>
      get<{ group: string; subject: AcadSubject; period: string; rows: (AcadStudent & { course: AcadCourse; stats: CourseStats })[] }>(
        `/acad/grades/school/cell/${query(params ?? {})}`,
      ),
    enabled: params !== null,
  })

export const useGroupGrades = (group: string, period: string, enabled = true) =>
  useQuery({
    queryKey: ['acad', 'group-grades', group, period],
    queryFn: () => get<GroupGrades>(`/acad/grades/group/${query({ group, period })}`),
    enabled,
    placeholderData: (prev) => prev,
  })

export const useStudentGrades = (id: number | null, period: string) =>
  useQuery({
    queryKey: ['acad', 'student-grades', id, period],
    queryFn: () => get<StudentGrades>(`/acad/students/${id}/grades/${query({ period })}`),
    enabled: id !== null,
    placeholderData: (prev) => prev,
  })

export const useMyGrades = (period: string, enabled = true) =>
  useQuery({
    queryKey: ['acad', 'my-grades', period],
    queryFn: () => get<StudentGrades>(`/acad/me/grades/${query({ period })}`),
    enabled,
    placeholderData: (prev) => prev,
  })

/** Главная ученика 8–10: числа, уроки сегодня, «Скоро», последние оценки. Считает сервер. */
export interface JuniorHome {
  date_words: string
  quarter: string
  kpis: { code: string; title: string; value: string; note: string; tone: '' | 'warn' }[]
  lessons: {
    id: number
    bell: string
    subject: string
    room: string
    cohort: string
    status: string
    status_title: string
    kind: string
    kind_label: string
    grade: number | null
    /** оценка по пятибалльной для цвета: ФО — из 10, СОР и СОЧ — по порогам шкалы */
    mark: number | null
  }[]
  lessons_empty: string
  soon: { date: string; title: string; when: string; kind: string; kind_label: string; link: string }[]
  recent: { id: number; subject: string; detail: string; value: number; mark: number | null }[]
  achievements_words: string
}

export const useMyHome = (enabled = true) =>
  useQuery({ queryKey: ['acad', 'me', 'home'], queryFn: () => get<JuniorHome>('/acad/me/home/'), enabled })

export const useMyLessons = (date: string, enabled = true) =>
  useQuery({
    queryKey: ['acad', 'my-lessons', date],
    queryFn: () => get<{ date: string; now_slot: number | null; lessons: (AcadLesson & { mine: LessonDetail['mine'] })[]; assessments: AcadLesson[] }>(
      `/acad/me/lessons/${query({ date })}`,
    ),
    enabled,
  })

export const useYear = () => useQuery({ queryKey: ['acad', 'year'], queryFn: () => get<YearScreen>('/acad/year/') })

export const useSaveYear = () => useAcadMutation((input: Record<string, unknown>) => patch<YearScreen>('/acad/year/', input), { saved: true })

export const useCloseQuarter = () =>
  useAcadMutation((input: { id: number; closed: boolean }) => post<{ quarter: { id: number; closed: boolean } }>(`/acad/year/quarters/${input.id}/close/`, input))

export const useAcadDashboard = (enabled = true) =>
  useQuery({ queryKey: ['acad', 'dashboard'], queryFn: () => get<AcadDashboard>('/acad/dashboard/'), enabled })

export const useAddExcuse = () =>
  useAcadMutation((input: { student: number; starts: string; ends: string; reason: string; document: string }) =>
    post<{ excuse: AcadExcuse }>('/acad/excuses/', input),
  )

export const useDropExcuse = () => useAcadMutation((id: number) => api<{ dropped: number }>(`/acad/excuses/${id}/`, { method: 'DELETE' }))

/** Тон оценки: 5 и 4 — норма, 3 — внимание, 2 — плохо. */
export function gradeTone(grade: number | null | undefined): 'good' | 'warn' | 'bad' | 'neutral' {
  if (grade === null || grade === undefined) return 'neutral'
  if (grade >= 4) return 'good'
  if (grade === 3) return 'warn'
  return 'bad'
}

/** Тон ФО из десяти: 8+ хорошо, 5+ средне, ниже — плохо. */
export function foTone(value: number | null | undefined, max = 10): 'good' | 'warn' | 'bad' | 'neutral' {
  if (value === null || value === undefined) return 'neutral'
  const share = value / max
  if (share >= 0.8) return 'good'
  if (share >= 0.5) return 'warn'
  return 'bad'
}

export function markTone(mark: AcadMark): 'good' | 'warn' | 'bad' | 'info' | 'neutral' {
  if (mark === 'absent') return 'bad'
  if (mark === 'excused') return 'info'
  if (mark === 'late') return 'warn'
  if (mark === 'present') return 'good'
  return 'neutral'
}

// --- Посещаемость по урокам, главная куратора, отчёты родителям (шаг 4) ---------

export interface AttendanceDayCell {
  has_lesson: boolean
  lesson?: number
  subject?: string
  teacher?: AcadPerson | null
  started?: boolean
  mark?: AcadMark
  unmarked?: boolean
  /** во сколько пришёл опоздавший и на сколько минут; время не записано — null */
  arrived?: string | null
  late_by?: number | null
  /** «н» из долгого опоздания: правило школы считает его пропуском */
  late_as_absent?: boolean
}

export interface AttendanceDayRow extends AcadStudent {
  cells: AttendanceDayCell[]
  marked: number
  absent: number
  excused: number
  late: number
}

export interface AttendanceMonthCell {
  absent: number
  excused: number
  late: number
  /** минуты опозданий дня, где время прихода записано */
  late_minutes?: number
  unmarked: number
  lessons: number
}

export interface AttendanceMonthRow extends AcadStudent {
  cells: AttendanceMonthCell[]
  pct: number | null
  absent: number
  excused: number
  late: number
  unexcused_days: string[]
}

export interface AttendanceScreen {
  group: number | null
  group_code: string
  groups: { id: number; code: string }[]
  view: 'day' | 'month'
  may_excuse: boolean
  may_remind: boolean
  /** порог посещаемости из настроек школы: ниже — процент выделен */
  attendance_below: number
  // день
  date?: string
  date_words?: string
  school_day?: boolean
  now_slot?: number | null
  slots?: { slot: number; bell: string; subjects: string[] }[]
  rows: (AttendanceDayRow | AttendanceMonthRow)[]
  absent_now?: string[]
  all_day?: (AcadStudent & { excused: boolean })[]
  totals?: { absent: number; excused: number; late: number }
  unmarked?: AcadLesson[]
  not_excused?: (AcadStudent & { days: string[] })[]
  lessons?: AcadLesson[]
  // месяц
  month?: string
  month_title?: string
  days?: { date: string; day: number; weekday: string }[]
}

export const useAcadAttendance = (params: { group?: string; view: 'day' | 'month'; date?: string; month?: string }, enabled = true) =>
  useQuery({
    queryKey: ['acad', 'attendance', params],
    queryFn: () => get<AttendanceScreen>(`/acad/attendance/${query(params)}`),
    enabled,
    placeholderData: (prev) => prev,
  })

export interface CuratorHome {
  group: string
  now_slot: number | null
  today: { group: string; lessons: number; now: AcadLesson | null; absent: string[]; unmarked: number }[]
  absent_now: string[]
  risk_grade: AcadStudent[]
  unexcused: AcadStudent[]
  reports: { title: string; total: number; draft: number; checked: number; exported: number; sent: number } | null
  cadence: string
}

export const useCuratorHome = (group: string, enabled = true) =>
  useQuery({
    queryKey: ['acad', 'curator-home', group],
    queryFn: () => get<CuratorHome>(`/acad/curator/home/${query({ group: group === 'all' ? '' : group })}`),
    enabled,
    placeholderData: (prev) => prev,
  })

export type ReportStatus = 'draft' | 'checked' | 'exported' | 'sent'

export interface ParentPhone {
  name: string
  relation: string
  phone: string
  is_primary: boolean
}

export type ReportTemplate = 'standard' | 'review' | 'progress'
export type DraftState = '' | 'pending' | 'done' | 'skipped' | 'failed'

export interface ReportRow {
  id: number
  student: AcadStudent
  title: string
  /** стандартный отчёт LMS или шаблон школы (вариант 1 или 2) */
  template: ReportTemplate
  template_title: string
  language: 'ru' | 'kk'
  draft_state: DraftState
  period_kind: 'month' | 'quarter' | 'custom'
  period_start: string
  status: ReportStatus
  status_title: string
  built_at: string | null
  checked_at: string | null
  exported_at: string | null
  sent_at: string | null
  has_word: boolean
  attendance: string
  grades: { text: string; tone: string }
  phones: ParentPhone[]
}

export interface ReportDetail extends ReportRow {
  sections: { code: string; title: string; lines: { title: string; value: string; note: string }[] }[]
  curator_word: string
  /** раздел «Слово куратора» включён в настройках отчётов */
  word_on: boolean
  curator: string
  message: string
  may_write: boolean
  file_name: string
  checked_by: string
  sent_by: string
  /** кто написал слово и когда — видно в отчёте (27.09.2026) */
  word_by: string
  word_at: string | null
  /** стандартный — только PDF; шаблоны школы — PDF и Word из одного docx */
  formats: ('pdf' | 'docx')[]
  school: SchoolReport | null
  /** «Казахский» или «Русский» — видно сверху черновика */
  language_title: string
  /** тексты правил человек: «Обновить данные» спросит, перезаписывать ли */
  texts_edited: boolean
}

/** Группа в выборе отчётов — с языком: язык отчёта по умолчанию — язык группы. */
export interface ReportGroup {
  id: number
  code: string
  language: 'ru' | 'kk'
  language_title: string
}

export interface SchoolReportLine {
  code: string
  title: string
  value: string
  note: string
}

export interface SchoolReview {
  id: number
  kind: 'eep' | 'sat_verbal' | 'sat_math' | 'subject'
  kind_title: string
  teacher: string
  subject: string
  text: string
  by_ai: boolean
  removable: boolean
}

export type SchoolTextField = 'mock_comment' | 'character' | 'summary'

/** Отчёт по шаблону школы: снимок данных, тексты, отзывы и пометки куратору. */
export interface SchoolReport {
  attendance: SchoolReportLine[]
  grades: SchoolReportLine[]
  ielts: SchoolReportLine[]
  sat: SchoolReportLine[]
  profile: SchoolReportLine[]
  texts: Record<SchoolTextField, string>
  reviews: SchoolReview[]
  gaps: string[]
  draft: { state: DraftState; title: string; note: string; at: string | null }
  fields: SchoolTextField[]
}

export interface ReportsScreen {
  group: string
  groups: ReportGroup[]
  periods: { code: string; title: string; kind: string; template: ReportTemplate }[]
  period: { code: string; title: string; template: ReportTemplate } | null
  rows: ReportRow[]
  counts: { total: number; draft: number; checked: number; exported: number; sent: number; no_phone: number }
  built_at: string | null
  cadence: string
  next_quarter_end: string | null
  may_write: boolean
  may_build: boolean
  statuses: { code: ReportStatus; title: string }[]
  templates: { code: ReportTemplate; title: string }[]
}

export const useReports = (params: { group?: string; period?: string; status?: string }, enabled = true) =>
  useQuery({
    queryKey: ['acad', 'reports', params],
    queryFn: () => get<ReportsScreen>(`/acad/reports/${query(params)}`),
    enabled,
    placeholderData: (prev) => prev,
  })

export const useReport = (id: number | null) =>
  useQuery({
    queryKey: ['acad', 'report', id],
    queryFn: () => get<ReportDetail>(`/acad/reports/${id}/`),
    enabled: id !== null,
  })

export const useSaveReportWord = () =>
  useAcadMutation((input: { id: number; curator_word: string }) => patch<ReportDetail>(`/acad/reports/${input.id}/`, { curator_word: input.curator_word }), { saved: true })

export const useCheckReport = () =>
  useAcadMutation((input: { id: number; curator_word?: string }) => post<ReportDetail>(`/acad/reports/${input.id}/check/`, input.curator_word === undefined ? {} : { curator_word: input.curator_word }))

/** «Обновить данные»: `needs_confirm` — тексты правил куратор, перезаписать только с его «да». */
export const useRefreshReport = () =>
  useAcadMutation((input: { id: number; overwrite?: boolean }) =>
    post<ReportDetail & { changed: boolean; needs_confirm: boolean; redrafting: boolean }>(`/acad/reports/${input.id}/refresh/`, input.overwrite ? { overwrite: true } : {}),
  )

/** Другой вид или язык того же отчёта: тот же ученик и период, черновик собирается заново. */
export const useSwitchReport = () =>
  useAcadMutation((input: { id: number; template: ReportTemplate; language: 'ru' | 'kk' }) =>
    post<ReportDetail & { report: number; period: string }>(`/acad/reports/${input.id}/switch/`, { template: input.template, language: input.language }),
  )

export const useReportSent = () => useAcadMutation((input: { id: number; sent: boolean }) => post<ReportDetail>(`/acad/reports/${input.id}/sent/`, { sent: input.sent }))

export const useReportsSent = () => useAcadMutation((ids: number[]) => post<{ sent: number; skipped: string[] }>('/acad/reports/sent/', { ids }))

/** «Проверено» и «Обновить данные» для всех отмеченных строк (27.09.2026). */
export const useReportsCheck = () => useAcadMutation((ids: number[]) => post<{ checked: number }>('/acad/reports/check/', { ids }))

export const useReportsRefresh = () => useAcadMutation((ids: number[]) => post<{ refreshed: number; changed: number; kept: number }>('/acad/reports/refresh/', { ids }))

/** Собрать за период: по группе, по всем или по одному ученику (`student`).
 *  Шаблон школы — вариант, язык (пусто — язык группы) и период «с — по». */
export interface BuildReportsInput {
  period?: string
  group?: string
  student?: number
  template?: ReportTemplate
  language?: '' | 'ru' | 'kk'
  date_from?: string
  date_to?: string
}

export const useBuildReports = () =>
  useAcadMutation((input: BuildReportsInput) => post<{ built: number; title: string; report: number | null; period: string }>('/acad/reports/build/', input))

/** Тексты отчёта по шаблону школы: поля и отзывы учителей. */
export const useSaveReportTexts = () =>
  useAcadMutation(
    (input: { id: number; texts?: Partial<Record<SchoolTextField, string>>; reviews?: { id: number; text: string }[] }) =>
      patch<ReportDetail>(`/acad/reports/${input.id}/`, { ...(input.texts ?? {}), ...(input.reviews ? { reviews: input.reviews } : {}) }),
    { saved: true },
  )

/** Убрать блок отзыва учителя другого предмета. */
export const useDropReportReview = () =>
  useAcadMutation((input: { id: number; review: number }) => api<ReportDetail>(`/acad/reports/${input.id}/reviews/${input.review}/`, { method: 'DELETE' }))

/** «Написать заново»: ИИ пишет тексты по данным отчёта. */
export const useRedraftReport = () => useAcadMutation((id: number) => post<ReportDetail>(`/acad/reports/${id}/draft/`, {}))

export interface ExportState {
  state: 'pending' | 'running' | 'done' | 'failed'
  done: number
  total: number
  name: string
  error: string
}

/** Архив отчётов в PDF или Word — собирается в очереди. */
export const useStartReportsExport = () =>
  useAcadMutation((input: { ids?: number[]; group?: string; period?: string; format: 'pdf' | 'docx' }) =>
    post<{ job: string; total: number }>('/acad/reports/export/', input),
  )

export const useReportsExport = (job: string | null) =>
  useQuery({
    queryKey: ['acad', 'reports-export', job],
    queryFn: () => get<ExportState>(`/acad/reports/export/${job}/`),
    enabled: job !== null,
    refetchInterval: (q) => (q.state.data && (q.state.data.state === 'done' || q.state.data.state === 'failed') ? false : 1500),
  })

/** Тон статуса отчёта: черновик — внимание, проверен — пометка, выгружен и отправлен — норма. */
export function reportTone(status: ReportStatus): 'good' | 'warn' | 'info' | 'neutral' {
  if (status === 'draft') return 'warn'
  if (status === 'checked') return 'info'
  return 'good'
}

/* --- «Риски» у Салтанат и администратора: пропуски по урокам ----------------- */

export interface RiskRow {
  id: number
  full_name: string
  short: string
  group: string
  attendance: { total: number; absent: number; excused: number; late: number; late_minutes?: number; late_unknown?: number; pct: number | null }
  unexcused_days: string[]
  /** почему ученик в «Рисках»: посещаемость ниже порога, дни без причины, опоздания */
  reasons: ('attendance' | 'unexcused' | 'late')[]
}

export interface RisksScreen {
  period: { title: string; from: string; to: string }
  threshold: number
  /** столько опозданий за период — причина «опоздания»; 0 — правило школы выключено */
  late_limit: number
  rows: RiskRow[]
  periods: { code: string; title: string }[]
}

export const useAcadRisks = (params: { period?: string; group?: string }, enabled = true) =>
  useQuery({
    queryKey: ['acad', 'risks', params],
    queryFn: () => get<RisksScreen>(`/acad/risks/${query(params)}`),
    enabled,
    placeholderData: (prev) => prev,
  })

// --- Импорт расписания из книги школы ---------------------------------------------

export interface ScheduleImportCredential {
  full_name: string
  email: string | null
  /** почта, а где её нет — логин: этим человек войдёт */
  login: string
  password: string
  expires_at: string
  group: string
}

export interface ScheduleImportReport {
  /** отпечаток файла: «Применить» принимает только тот, что был в предпросмотре */
  fingerprint: string
  applied: boolean
  errors: string[]
  warnings: { kind: string; text: string }[]
  sections: { code: string; title: string; created: number; updated: number; unchanged: number }[]
  curator_changes: { group: string; parallel: number; was: string; will: string; since: string }[]
  needs_role: { full_name: string; login: string; position: string }[]
  roles_kept: { full_name: string; role: string; file: string }[]
  stale_series: string[]
  groups_outside: string[]
  skipped_bells: number
  lessons_from: string | null
  lessons_to_create: number
  series_without_teacher: number
  /** пароли новых учёток — только в ответе «Применить», один раз */
  credentials: ScheduleImportCredential[]
  detail: string
}

function importBody(file: File, fingerprint?: string): FormData {
  const body = new FormData()
  body.append('file', file)
  if (fingerprint) body.append('fingerprint', fingerprint)
  return body
}

/** Проверка и запись состава подгрупп файлом школы (`/acad/cohorts/members/`). */
export interface SubgroupMembersReport {
  /** с какой даты запишется состав: по умолчанию начало учебного года */
  since: string
  lines: number
  matched: number
  subgroups: { id: number; name: string; stream: string; subject: string; students: number; joined: number; left: number }[]
  errors: string[]
  errors_total: number
  warnings: string[]
  ok: boolean
  applied?: boolean
  /** блоки файла школы и подгруппа, в которую лёг каждый: глазами видно, что кабинет указал верно */
  blocks: { sheet: string; header: string; subgroup: string; teacher: string; students: number }[]
  /** листы без блоков и колонок: тесты, уровни, списки класса */
  skipped: string[]
}

function membersBody(file: File, since: string, apply: boolean): FormData {
  const body = new FormData()
  body.append('file', file)
  if (since) body.append('since', since)
  if (apply) body.append('apply', 'true')
  return body
}

export function useSubgroupMembersCheck() {
  return useMutation({
    mutationFn: ({ file, since }: { file: File; since: string }) =>
      api<SubgroupMembersReport>('/acad/cohorts/members/', { method: 'POST', body: membersBody(file, since, false) }),
  })
}

export function useSubgroupMembersApply() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ file, since }: { file: File; since: string }) =>
      api<SubgroupMembersReport>('/acad/cohorts/members/', { method: 'POST', body: membersBody(file, since, true) }),
    // составы меняют неделю групп, журналы и посещаемость — вся учебная часть
    onSuccess: () => void client.invalidateQueries({ queryKey: ['acad'] }),
  })
}

export function useScheduleImportPreview() {
  return useMutation({
    mutationFn: (file: File) =>
      api<ScheduleImportReport>('/acad/schedule/import/preview/', { method: 'POST', body: importBody(file) }),
  })
}

export function useScheduleImportApply() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ file, fingerprint }: { file: File; fingerprint: string }) =>
      api<ScheduleImportReport>('/acad/schedule/import/apply/', { method: 'POST', body: importBody(file, fingerprint) }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['acad'] })
      void client.invalidateQueries({ queryKey: ['users'] })
    },
  })
}
