import { describe, expect, it } from 'vitest'
import type { Role } from '../api/types'
import { careerTestsOpen, CURATOR_HIDDEN, curatorMayOpen, directorHidden, homeworkReviewOpen, NAV_GROUPS, navFor, tabsFor, usageOpen } from './nav'

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

describe('профтест у куратора', () => {
  it('раздела нет ни пунктом, ни адресом у куратора и Асем; у администратора и профориентолога — есть', () => {
    expect(navFor('curator').some((item) => item.path === '/career-tests')).toBe(false)
    expect(navFor('curator', false, { careerTests: true }).some((item) => item.path === '/career-tests')).toBe(false)
    expect(careerTestsOpen({ role: 'curator', career_tests: false })).toBe(false)
    expect(careerTestsOpen({ role: 'curator', career_tests: true })).toBe(false)
    expect(careerTestsOpen({ role: 'director_admission', career_tests: false })).toBe(false)
    expect(careerTestsOpen({ role: 'director_admission', career_tests: true })).toBe(false)
    expect(careerTestsOpen({ role: 'admin', career_tests: false })).toBe(true)
    expect(careerTestsOpen({ role: 'teacher', career_tests: true })).toBe(true)
    expect(careerTestsOpen({ role: 'teacher', career_tests: false })).toBe(false)
  })
})

describe('проверка ДЗ в навигации', () => {
  it('куратору «Проверка ДЗ» спрятана переключателем, даже со своими уроками', () => {
    const items = navFor('curator', false, { teaches: true })
    expect(items.some((item) => item.path === reviewPath)).toBe(false)
    expect(homeworkReviewOpen('curator', true)).toBe(false)
    expect(tabsFor('curator', items).map((item) => item.path)).toEqual(['/dashboard', '/queue', '/students', '/attendance'])
  })

  it('переключатель возвращает куратору пункт и адрес, не трогая остальных', () => {
    CURATOR_HIDDEN.homeworkReview = false
    try {
      const items = navFor('curator', false, { teaches: true })
      expect(items.filter((item) => item.path === reviewPath)).toHaveLength(1)
      for (const path of reviewPages) {
        expect(curatorMayOpen(path)).toBe(true)
        expect(homeworkReviewOpen('curator', true)).toBe(true)
      }
      expect(homeworkReviewOpen('curator', false)).toBe(false)
    } finally {
      CURATOR_HIDDEN.homeworkReview = true
    }
    expect(homeworkReviewOpen('teacher')).toBe(true)
    expect(homeworkReviewOpen('director_behavior', true)).toBe(false)
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
        // у директоров «Проверки ДЗ» нет (решение владельца, 24.10.2026)
        const allowed = role !== 'student' && !role.startsWith('director_') && (['teacher', 'admin'].includes(role) || teaches)
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
  it('exposes analytics only to the administrator, including direct navigation', () => {
    const roles: Role[] = ['student', 'teacher', 'curator', 'director_exam', 'admin', 'director_behavior', 'director_admission', 'director_talent', 'director_sport']
    for (const role of roles) {
      const allowed = role === 'admin'
      expect(usageOpen(role)).toBe(allowed)
      expect(navFor(role).filter((item) => item.path === '/usage')).toHaveLength(allowed ? 1 : 0)
    }
  })
})

describe('меню директоров по макету', () => {
  // состав и порядок — как в макете меню директоров; «Таблица» у всех (решение владельца, 24.10.2026)
  const menu = (role: Role, extras = {}) => {
    const items = navFor(role, true, extras)
    return NAV_GROUPS.map((group) => items.filter((item) => item.group === group.key).map((item) => item.label)).filter((labels) => labels.length > 0)
  }

  it('у каждого директора ровно пункты макета', () => {
    expect(menu('director_behavior')).toEqual([['Главная', 'Посещаемость', 'Отчёты', 'Родители', 'Риски'], ['Таблица']])
    expect(menu('director_exam')).toEqual([
      ['Главная', 'Отчёты', 'Задачи сотрудникам', 'Таблица'],
      ['Расписание', 'Подгруппы и потоки', 'Учителя', 'Успеваемость', 'Учебный год'],
      ['Результаты экзаменов', 'Mock Test онлайн', 'ТОП-30', 'Справочник экзаменов', 'Шаблоны задач'],
    ])
    expect(menu('director_admission', { teaches: true, careerTests: true })).toEqual([
      ['Главная', 'Эссе учеников', 'Таблица'],
      ['Справочник вузов', 'Дедлайны'],
    ])
    expect(menu('director_talent', { teaches: true, curator: true, materials: true })).toEqual([
      ['Главная', 'Олимпиады', 'Освобождения', 'Мои уроки'],
      ['Таблица', 'Олимпиадная группа', 'Предметы и треки'],
    ])
    expect(menu('director_sport', { teaches: true })).toEqual([['Главная', 'Мероприятия'], ['Виды спорта', 'Таблица']])
  })

  it('убранное открывается адресом только там, где его нет в списке роли', () => {
    for (const role of ['director_behavior', 'director_exam', 'director_admission', 'director_talent', 'director_sport'] as Role[]) {
      for (const path of ['/suggestions', '/homework-review', '/resources', '/import', '/career-tests']) {
        expect(directorHidden(role, path)).toBe(true)
      }
      expect(directorHidden(role, '/table')).toBe(false)
    }
    expect(directorHidden('director_exam', '/mock-imports/3')).toBe(true)
    expect(directorHidden('director_admission', '/schedule')).toBe(true)
    expect(directorHidden('director_talent', '/schedule')).toBe(false)
    expect(directorHidden('admin', '/suggestions')).toBe(false)
  })

  it('в баре телефона директора нет «Предложений»', () => {
    const tabs = (role: Role) => tabsFor(role, navFor(role)).map((item) => item.path)
    expect(tabs('director_behavior')).toEqual(['/dashboard', '/attendance', '/school-reports', '/parents'])
    expect(tabs('director_exam')).toEqual(['/dashboard', '/school-reports', '/staff-tasks', '/exam-results'])
    expect(tabs('director_sport')).toEqual(['/dashboard', '/sport-events', '/table', '/sport-types'])
  })
})
