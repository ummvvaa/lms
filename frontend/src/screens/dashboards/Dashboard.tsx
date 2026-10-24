/**
 * Роутер дашбордов: у каждой роли свой.
 *
 * Разделы («Группы», «Риски», «TOP-30», «Пробные», …) с фазы 26 живут
 * отдельными экранами со своими адресами, а на дашборде от них остались
 * короткие сводки со ссылкой. Прокрутки к секции здесь больше нет.
 */
import { useAuth } from '../../auth/AuthContext'
import SchoolHome from '../directors/SchoolHome'
import AdmissionHome from '../directors/AdmissionHome'
import ExamHome from '../directors/ExamHome'
import TalentHome from '../directors/TalentHome'
import SportHome from '../directors/SportHome'
import AdminDashboard from './AdminDashboard'
import CuratorHome from '../curator/Home'
import StudentHome from './StudentHome'
import JuniorHome from './JuniorHome'
import TeacherToday from '../academics/TeacherToday'

export default function Dashboard() {
  const { me } = useAuth()
  if (!me) return null

  switch (me.role) {
    case 'student':
      // главная 8–10 — учёба; главная 11 не меняется (`core/parallels.py`)
      return me.has_admission === false ? <JuniorHome /> : <StudentHome />
    case 'director_behavior':
      // главная по макету кабинетов директоров (24.10.2026); прежний `BehaviorDashboard` остался в коде
      return <SchoolHome />
    case 'director_admission':
      return <AdmissionHome />
    case 'director_exam':
      return <ExamHome />
    case 'director_talent':
      return <TalentHome />
    case 'director_sport':
      return <SportHome />
    case 'curator':
      return <CuratorHome />
    case 'teacher':
      return <TeacherToday />
    case 'admin':
      return <AdminDashboard />
    default:
      return null
  }
}
