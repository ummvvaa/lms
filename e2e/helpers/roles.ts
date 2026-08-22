/**
 * Учётные записи для браузерных проверок.
 *
 * Ходим под теми же записями, что заводит `manage.py create_dev_users`.
 */
export interface RoleAccount {
  key: string
  email: string
  password: string
  title: string
}

/**
 * Пароль берётся из окружения — тех же переменных, что читает команда
 * `create_dev_users`. Значений по умолчанию нет намеренно: файла
 * с паролями у проекта не должно быть даже в тестах.
 */
const pass = (name: string): string => {
  const value = process.env[name]
  if (!value) {
    throw new Error(
      `Не задана переменная ${name}. Возьмите её из deploy/.env: ` +
        'браузерные проверки ходят под теми же учётными записями, что заводит create_dev_users.',
    )
  }
  return value
}

export const ACCOUNTS: RoleAccount[] = [
  {
    key: 'student',
    email: 'test.student@lms.local',
    password: pass('DEV_STUDENT_PASSWORD'),
    title: 'Ученик',
  },
  {
    key: 'director_behavior',
    email: 'test.behavior@lms.local',
    password: pass('DEV_BEHAVIOR_PASSWORD'),
    title: 'Директор школы — профиль и дисциплина',
  },
  {
    key: 'director_admission',
    email: 'test.admission@lms.local',
    password: pass('DEV_ADMISSION_PASSWORD'),
    title: 'Директор по поступлению',
  },
  {
    key: 'director_exam',
    email: 'test.exam@lms.local',
    password: pass('DEV_EXAM_PASSWORD'),
    title: 'Академический директор',
  },
  {
    key: 'director_talent',
    email: 'test.talent@lms.local',
    password: pass('DEV_TALENT_PASSWORD'),
    title: 'Директор талантов',
  },
  {
    key: 'director_sport',
    email: 'test.sport@lms.local',
    password: pass('DEV_SPORT_PASSWORD'),
    title: 'Директор спорта',
  },
  {
    key: 'admin',
    email: 'test.admin@lms.local',
    password: pass('DEV_ADMIN_PASSWORD'),
    title: 'Администратор',
  },
]

export const byKey = (key: string): RoleAccount => {
  const found = ACCOUNTS.find((a) => a.key === key)
  if (!found) throw new Error(`Нет учётной записи для роли ${key}`)
  return found
}
