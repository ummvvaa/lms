/**
 * Ответы дашбордов — одни типы на дашборд и на его разделы.
 *
 * Раздел («Группы», «Риски», «Дедлайны», …) живёт отдельным экраном,
 * но берёт те же данные, что и дашборд домена. Описание ответа держим
 * в одном месте, чтобы экран и дашборд не разошлись в полях.
 */

/** Строка «ученик» в панелях дашбордов. */
export interface PersonRow {
  student_id: number
  student__last_name: string
  student__first_name: string
  attendance_percent?: number
  homework_percent?: number
  remarks_count?: number
  status?: string
  portfolio_status?: string
  ielts_current?: string
  ielts_target?: string
  sat_current?: number
  sat_target?: number
  sport_name?: string
  level?: string
  rank?: string
}

export interface BehaviorData {
  total: number
  filled: number
  traffic: Record<string, number>
  worst_attendance: PersonRow[]
  worst_homework: PersonRow[]
  groups: { code: string; grade: number; students_count: number; critical: number; filled: number }[]
}

export interface Deadline {
  id: number
  deadline: string
  round_type: string
  applicants_count: number
  university: string
  country: string
  program_name: string
}

export interface AdmissionData {
  total: number
  slots: number
  slots_target: number
  statuses: Record<string, number>
  with_three_universities: number
  deadlines: Deadline[]
  popular: { name: string; n: number }[]
  no_common_app: PersonRow[]
  no_application_account: PersonRow[]
}

export interface MockDrop {
  student_id: number
  student__last_name: string
  student__first_name: string
  exam_type: string
  latest: number
  previous: number
  delta: number
}

export interface ExamData {
  buckets: Record<string, number>
  top_ielts: PersonRow[]
  top_sat: PersonRow[]
  mock_drops: MockDrop[]
  averages: { ielts: string | null; sat: number | null }
}

export interface TalentData {
  portfolio: Record<string, number>
  tracks: Record<string, number>
  days_to_november: number
  no_track: PersonRow[]
  weak_portfolio: PersonRow[]
  categories: Record<string, number>
}

export interface SportData {
  athletes: number
  strong: PersonRow[]
  no_certificate: PersonRow[]
  calendar: { name: string; date: string; participants: number }[]
  leaders: number
}

/** Подписи треков портфолио — одни и те же на дашборде и на экране треков. */
export const TRACK_TITLES: Record<string, string> = {
  olympiad: 'Олимпиады',
  research: 'Исследования',
  startup: 'Стартап',
  leadership: 'Лидерство',
  volunteering: 'Волонтёрство',
  competition: 'Конкурсы',
}

/** Уровни соревнований — так же. */
export const SPORT_LEVELS: Record<string, string> = {
  school: 'Школьный',
  city: 'Городской',
  regional: 'Областной',
  national: 'Республиканский',
  international: 'Международный',
}
