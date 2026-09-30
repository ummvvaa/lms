/**
 * Ответы дашбордов — одни типы на дашборд и на его разделы.
 *
 * Раздел («Группы», «Риски», «Дедлайны», …) живёт отдельным экраном,
 * но берёт те же данные, что и дашборд домена. Описание ответа держим
 * в одном месте, чтобы экран и дашборд не разошлись в полях.
 */
import { tk } from '../../i18n'

/** Строка «ученик» в панелях дашбордов. */
export interface PersonRow {
  student_id: number
  student__last_name: string
  student__first_name: string
  attendance_percent?: number
  /** выполнение ДЗ за четверть: сдано вовремя из заданий со сдачей, % */
  homework_percent?: number
  /** сколько заданий со сдачей было за четверть */
  homework_total?: number
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
  /** порог «не сдаёт ДЗ вовремя» — настройка школы */
  homework_behind_pct?: number
  groups: { code: string; parallel: number; students_count: number; critical: number; filled: number }[]
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

/** Подписи треков портфолио — одни и те же на дашборде и на экране треков. */
export const TRACK_TITLES: Record<string, string> = {
  olympiad: tk('Олимпиады'),
  research: tk('Исследования'),
  startup: tk('Стартап'),
  leadership: tk('Лидерство'),
  volunteering: tk('Волонтёрство'),
  competition: tk('Конкурсы'),
}

/** Уровни соревнований — так же. */
export const SPORT_LEVELS: Record<string, string> = {
  school: tk('Школьный'),
  city: tk('Городской'),
  regional: tk('Областной'),
  national: tk('Республиканский'),
  international: tk('Международный'),
}
