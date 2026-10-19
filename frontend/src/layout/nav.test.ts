import { describe, expect, it } from 'vitest'
import type { Role } from '../api/types'
import { curatorMayOpen, homeworkReviewOpen, navFor, tabsFor, usageOpen } from './nav'

const reviewPath = '/homework-review'
const reviewPages = [reviewPath, `${reviewPath}/42`]

describe('профтест в меню ученика', () => {
  it('у 8–10 без каталога вузов «Профтест» стоит в «Основном», у 11 — в «Поступлении»', () => {
    const junior = navFor('student', false, { sections: ['/dashboard', '/schedule', '/career'] })
    expect(junior.find((item) => item.path === '/career')?.group).toBe('main')
    expect(junior.some((item) => item.group === 'admission')).toBe(false)
    const senior = navFor('student', false, { sections: ['/dashboard', '/catalog', '/career'] })
    expect(senior.find((item) => item.path === '/career')?.group).toBe('admission')
  })
})

describe('проверка ДЗ в навигации', () => {
  it('куратор со своими уроками видит пункт и проходит оба шлюза страницы', () => {
    const items = navFor('curator', false, { teaches: true })
    expect(items.filter((item) => item.path === reviewPath)).toHaveLength(1)
    // В App адрес проверяют и общий шлюз куратора, и право на проверку ДЗ.
    for (const path of reviewPages) {
      expect(curatorMayOpen(path)).toBe(true)
      expect(homeworkReviewOpen('curator', true)).toBe(true)
    }
    // На телефоне новый пункт доступен через «Ещё», четвёрка вкладок прежняя.
    expect(tabsFor('curator', items).map((item) => item.path)).toEqual(['/dashboard', '/queue', '/students', '/documents'])
  })

  it('куратор без уроков не получает пункт или доступ по прямому адресу', () => {
    for (const teaches of [false, undefined]) {
      expect(navFor('curator', false, { teaches }).some((item) => item.path === reviewPath)).toBe(false)
      for (const path of reviewPages) {
        expect(curatorMayOpen(path) && homeworkReviewOpen('curator', teaches)).toBe(false)
      }
    }
  })

  it('право остальных ролей и отсутствие повторов пункта сохраняются', () => {
    const roles: Role[] = ['student', 'teacher', 'director_exam', 'admin', 'director_behavior', 'director_admission', 'director_talent', 'director_sport']
    for (const role of roles) {
      for (const teaches of [false, true]) {
        const allowed = role !== 'student' && (['teacher', 'director_exam', 'admin'].includes(role) || teaches)
        expect(homeworkReviewOpen(role, teaches)).toBe(allowed)
        expect(navFor(role, false, { teaches }).filter((item) => item.path === reviewPath)).toHaveLength(allowed ? 1 : 0)
      }
    }
  })

  it('чужие разделы по-прежнему закрыты куратору', () => {
    for (const path of ['/users', '/import', '/school-settings']) {
      expect(curatorMayOpen(path)).toBe(false)
    }
  })
})


describe('куратор без групп 11', () => {
  it('не получает очередь, документы и задачи ни пунктом, ни в баре, ни адресом', () => {
    const items = navFor('curator', false, { admission: false })
    for (const path of ['/queue', '/documents', '/tasks']) {
      expect(items.some((item) => item.path === path)).toBe(false)
      expect(curatorMayOpen(path, false)).toBe(false)
      expect(curatorMayOpen(path, true)).toBe(true)
    }
    expect(items.some((item) => item.path === '/students')).toBe(true)
    expect(tabsFor('curator', items).map((item) => item.path)).toEqual(['/dashboard', '/students', '/attendance', '/schedule'])
  })

  it('куратор с группой 11 и без ответа сервера видит кабинет целиком', () => {
    for (const admission of [true, null, undefined]) {
      const items = navFor('curator', false, { admission })
      expect(items.some((item) => item.path === '/documents')).toBe(true)
      expect(curatorMayOpen('/documents', admission)).toBe(true)
    }
  })
})

describe('usage permissions', () => {
  it('exposes analytics only to the administrator and school director, including direct navigation', () => {
    const roles: Role[] = ['student', 'teacher', 'curator', 'director_exam', 'admin', 'director_behavior', 'director_admission', 'director_talent', 'director_sport']
    for (const role of roles) {
      const allowed = role === 'admin' || role === 'director_behavior'
      expect(usageOpen(role)).toBe(allowed)
      expect(navFor(role).filter((item) => item.path === '/usage')).toHaveLength(allowed ? 1 : 0)
    }
  })
})
