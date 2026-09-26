/**
 * `/students/:id` по роли: учитель видит ученика своими глазами — оценки
 * и пропуски по своим предметам; остальные — карточку целиком.
 */
import { useAuth } from '../../auth/AuthContext'
import StudentCardScreen from '../StudentCard'
import TeacherStudent from './TeacherStudent'

export default function StudentRoute() {
  const { me } = useAuth()
  if (me?.role === 'teacher') return <TeacherStudent />
  return <StudentCardScreen />
}
