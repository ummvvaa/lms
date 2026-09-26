/**
 * `/grades` по роли: Кымбат и администратор — по школе, куратор — своя группа,
 * ученик — свои оценки.
 */
import { useAuth } from '../../auth/AuthContext'
import CuratorGrades from './CuratorGrades'
import SchoolGrades from './SchoolGrades'
import StudentGrades from './StudentGrades'

export default function GradesScreen() {
  const { me } = useAuth()
  if (!me) return null
  if (me.role === 'director_exam' || me.role === 'admin') return <SchoolGrades />
  if (me.role === 'curator') return <CuratorGrades />
  if (me.role === 'student') return <StudentGrades />
  return null
}
