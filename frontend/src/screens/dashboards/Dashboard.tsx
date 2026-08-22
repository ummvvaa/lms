/**
 * Роутер дашбордов: у каждой роли свой.
 *
 * Разделы навигации директора (`/top30`, `/deadlines`, …) — это секции
 * того же дашборда. Маршрут прокручивает к нужному блоку и подсвечивает его,
 * а не показывает тот же экран с начала, будто пункт меню ничего не делает.
 */
import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { anchorFor } from '../../layout/nav'
import BehaviorDashboard from './BehaviorDashboard'
import AdmissionDashboard from './AdmissionDashboard'
import ExamDashboard from './ExamDashboard'
import TalentDashboard from './TalentDashboard'
import SportDashboard from './SportDashboard'
import OverviewDashboard from './OverviewDashboard'
import StudentHome from './StudentHome'

/** Прокрутка к секции раздела. Ждём отрисовки данных, поэтому с повтором. */
function useScrollToSection(anchor: string | undefined): void {
  useEffect(() => {
    if (!anchor) {
      window.scrollTo({ top: 0 })
      return
    }
    let attempts = 0
    const timer = window.setInterval(() => {
      const target = document.getElementById(anchor)
      attempts += 1
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' })
        target.classList.add('section--target')
        window.setTimeout(() => target.classList.remove('section--target'), 1600)
      }
      if (target || attempts > 20) window.clearInterval(timer)
    }, 150)
    return () => window.clearInterval(timer)
  }, [anchor])
}

export default function Dashboard() {
  const { me } = useAuth()
  const location = useLocation()
  useScrollToSection(me ? anchorFor(me.role, location.pathname) : undefined)

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
      return <OverviewDashboard />
    default:
      return null
  }
}
