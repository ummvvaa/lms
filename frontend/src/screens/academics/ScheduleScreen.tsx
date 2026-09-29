/**
 * `/schedule` по роли: учитель — свои уроки, Кымбат и администратор —
 * неделя с правкой, куратор — расписание групп, ученик — своя неделя.
 */
import { useAuth } from '../../auth/AuthContext'
import ScheduleEditor from './ScheduleEditor'
import TeacherSchedule from './TeacherSchedule'
import CuratorSchedule from './CuratorSchedule'
import StudentSchedule from './StudentSchedule'
import MyLessons from './MyLessons'

export default function ScheduleScreen() {
  const { me } = useAuth()
  if (!me) return null
  if (me.role === 'teacher') return <TeacherSchedule />
  if (me.role === 'director_exam' || me.role === 'admin') return <ScheduleEditor />
  if (me.role === 'curator') return <CuratorSchedule />
  if (me.role === 'student') return <StudentSchedule />
  // директор, который ведёт уроки: своя неделя и отметка своих уроков
  if (me.teaches) return <MyLessons />
  return null
}
