/**
 * `/grades` по роли: Кымбат и администратор — по школе, куратор — своя группа,
 * ученик — свои оценки (приходит со своим шагом).
 */
import { useAuth } from '../../auth/AuthContext'
import CuratorGrades from './CuratorGrades'
import SchoolGrades from './SchoolGrades'

export default function GradesScreen() {
  const { me } = useAuth()
  if (!me) return null
  if (me.role === 'director_exam' || me.role === 'admin') return <SchoolGrades />
  if (me.role === 'curator') return <CuratorGrades />
  return null
}
