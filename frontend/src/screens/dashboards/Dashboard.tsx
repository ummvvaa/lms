/**
 * Роутер дашбордов: у каждой роли свой.
 *
 * Разделы («Группы», «Риски», «TOP-30», «Пробные», …) с фазы 26 живут
 * отдельными экранами со своими адресами, а на дашборде от них остались
 * короткие сводки со ссылкой. Прокрутки к секции здесь больше нет.
 */
import { useAuth } from '../../auth/AuthContext'
import BehaviorDashboard from './BehaviorDashboard'
import AdmissionDashboard from './AdmissionDashboard'
import ExamDashboard from './ExamDashboard'
import TalentDashboard from './TalentDashboard'
import SportDashboard from './SportDashboard'
import AdminDashboard from './AdminDashboard'
import StudentHome from './StudentHome'

export default function Dashboard() {
  const { me } = useAuth()
  if (!me) return null

  switch (me.role) {
    case 'student':
      return <StudentHome />
    case 'director_behavior':
      return <BehaviorDashboard />
    case 'director_admission':
      return <AdmissionDashboard />
    case 'director_exam':
      return <ExamDashboard />
    case 'director_talent':
      return <TalentDashboard />
    case 'director_sport':
      return <SportDashboard />
    case 'admin':
      return <AdminDashboard />
    default:
      return null
  }
}
