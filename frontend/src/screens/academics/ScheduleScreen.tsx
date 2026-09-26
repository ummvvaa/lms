/**
 * `/schedule` по роли: учитель — свои уроки, Кымбат и администратор —
 * неделя с правкой, куратор — расписание групп (приходит со своим шагом).
 */
import { useAuth } from '../../auth/AuthContext'
import ScheduleEditor from './ScheduleEditor'
import TeacherSchedule from './TeacherSchedule'
import CuratorSchedule from './CuratorSchedule'

export default function ScheduleScreen() {
  const { me } = useAuth()
  if (!me) return null
  if (me.role === 'teacher') return <TeacherSchedule />
  if (me.role === 'director_exam' || me.role === 'admin') return <ScheduleEditor />
  if (me.role === 'curator') return <CuratorSchedule />
  return null
}
