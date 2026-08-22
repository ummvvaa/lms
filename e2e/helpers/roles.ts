/**
 * Учётные записи для браузерных проверок.
 *
 * Пароли берутся из окружения — те же переменные, что читает
 * management-команда `create_dev_users`. Значения по умолчанию
 * годятся только для локального контура.
 */
export interface RoleAccount {
  key: string
  email: string
  password: string
  title: string
}

const pass = (name: string, fallback: string) => process.env[name] ?? fallback

export const ACCOUNTS: RoleAccount[] = [
  {
    key: 'student',
    email: 'test.student@lms.local',
    password: pass('DEV_STUDENT_PASSWORD', 'Student!Check2026'),
    title: 'Ученик',
  },
  {
    key: 'director_behavior',
    email: 'test.behavior@lms.local',
    password: pass('DEV_BEHAVIOR_PASSWORD', 'Behavior!Check2026'),
    title: 'Директор школы — профиль и дисциплина',
  },
  {
    key: 'director_admission',
    email: 'test.admission@lms.local',
    password: pass('DEV_ADMISSION_PASSWORD', 'Admission!Check2026'),
    title: 'Директор по поступлению',
  },
  {
    key: 'director_exam',
    email: 'test.exam@lms.local',
    password: pass('DEV_EXAM_PASSWORD', 'Exam!Check2026'),
    title: 'Академический директор',
  },
  {
    key: 'director_talent',
    email: 'test.talent@lms.local',
    password: pass('DEV_TALENT_PASSWORD', 'Talent!Check2026'),
    title: 'Директор талантов',
  },
  {
    key: 'director_sport',
    email: 'test.sport@lms.local',
    password: pass('DEV_SPORT_PASSWORD', 'Sport!Check2026'),
    title: 'Директор спорта',
  },
]

export const byKey = (key: string): RoleAccount => {
  const found = ACCOUNTS.find((a) => a.key === key)
  if (!found) throw new Error(`Нет учётной записи для роли ${key}`)
  return found
}
