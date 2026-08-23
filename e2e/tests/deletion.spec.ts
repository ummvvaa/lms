/**
 * Фаза 14: удаление везде, архив и отмена импорта.
 *
 * Приёмка: удалённый ученик исчезает из списков, но восстанавливается
 * из архива со всеми связями; директор экзаменов не может удалить запись
 * чужого домена; загрузка видна в истории и отменяется целиком.
 */
import { expect, test, type Page } from '@playwright/test'
import { statePath } from '../helpers/auth-state'
import { watch } from '../helpers/session'

/**
 * Сценарий заводит свои записи и должен убирать их за собой даже когда
 * падает посередине: иначе демо-база обрастает «Удалимова…» и «Школьный
 * вуз…», и следующий, кто посмотрит на экраны глазами, увидит мусор.
 */
test.afterAll(async ({ browser }) => {
  const context = await browser.newContext({ storageState: statePath('admin') })
  const page = await context.newPage()
  await page.goto('/dashboard')
  const csrf = (await context.cookies()).find((c) => c.name === 'csrftoken')!.value
  const headers = { 'X-CSRFToken': csrf }

  const students = await (await page.request.get('/api/students/?search=Удалимова&page_size=100')).json()
  for (const row of students.results ?? []) {
    await page.request.delete(`/api/students/${row.id}/`, { headers })
  }
  const universities = await (
    await page.request.get('/api/universities/?search=Школьный вуз&page_size=100')
  ).json()
  for (const row of universities.results ?? []) {
    await page.request.delete(`/api/universities/${row.id}/`, { headers })
  }
  await context.close()
})

/** Свой ученик на каждый прогон: сценарий не должен зависеть от соседей. */
async function createStudent(page: Page, suffix: string) {
  const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')!.value
  const response = await page.request.post('/api/students/', {
    data: {
      last_name: `Удалимова${suffix}`,
      first_name: 'Тест',
      email: `delete.${suffix}@school.kz`,
      grade: 11,
      graduation_year: 2027,
    },
    headers: { 'X-CSRFToken': csrf },
  })
  expect(response.ok()).toBeTruthy()
  return (await response.json()) as { id: number; full_name: string }
}

test.describe('удаление ученика и возврат из архива', () => {
  test.use({ storageState: statePath('admin') })

  test('карточка уходит в архив и возвращается оттуда', async ({ page }) => {
    const diag = watch(page)
    const suffix = String(Date.now()).slice(-6)
    await page.goto('/table')
    const student = await createStudent(page, suffix)

    // добавляем ученику задачу — она должна уйти и вернуться вместе с ним
    const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')!.value
    await page.request.post('/api/tasks/', {
      data: { student: student.id, title: 'Задача на удаление', category: 'test' },
      headers: { 'X-CSRFToken': csrf },
    })

    await page.goto(`/students/${student.id}`)
    await expect(page.locator('.card__name')).toContainText('Удалимова')

    const mark = diag.mark()
    await page.getByRole('button', { name: 'Удалить ученика' }).click()
    // диалог говорит, что именно уйдёт, а не «вы уверены?»
    await expect(page.locator('.confirm__title')).toContainText('Удалить «Удалимова')
    await expect(page.locator('.confirm')).toContainText('архив')
    // удаление тянет за собой чужую работу — диалог просит набрать слово
    const confirmButton = page.locator('.confirm').getByRole('button', { name: 'Удалить', exact: true })
    await expect(confirmButton).toBeDisabled()
    await page.getByLabel('Наберите УДАЛИТЬ').fill('УДАЛИТЬ')
    await confirmButton.click()

    await expect
      .poll(() => diag.since(mark).filter((c) => c.method === 'DELETE' && c.status === 200).length)
      .toBeGreaterThan(0)
    await page.waitForURL(/\/table/)

    // из списков исчез — проверяем сырым запросом, а не глазами
    const list = await (await page.request.get(`/api/students/?search=delete.${suffix}`)).json()
    expect(list.count).toBe(0)

    // архив показывает удаление и возвращает его
    await page.goto('/archive')
    const row = page.locator('.arch__row').filter({ hasText: `Удалимова${suffix}` }).first()
    await expect(row).toBeVisible()
    await expect(row).toContainText('задачи')

    await row.getByRole('button', { name: 'Восстановить' }).click()
    await expect(page.locator('.arch__flash')).toContainText('Восстановлено записей')

    await page.reload()
    const back = await (await page.request.get(`/api/students/?search=delete.${suffix}`)).json()
    expect(back.count).toBe(1)
    const tasks = await (await page.request.get(`/api/tasks/?student=${student.id}`)).json()
    expect(tasks.count).toBe(1)
    expect(diag.consoleErrors).toEqual([])

    // за собой убираем
    await page.request.delete(`/api/students/${student.id}/`, { headers: { 'X-CSRFToken': csrf } })
  })
})

test.describe('чужой домен удалить нельзя', () => {
  test.use({ storageState: statePath('director_exam') })

  test('директор экзаменов не убирает активность директора талантов', async ({ page, browser }) => {
    const admin = await browser.newContext({ storageState: statePath('admin') })
    const adminPage = await admin.newPage()
    await adminPage.goto('/table')
    const suffix = String(Date.now()).slice(-6)
    const student = await createStudent(adminPage, suffix)
    const adminCsrf = (await admin.cookies()).find((c) => c.name === 'csrftoken')!.value

    const talent = await browser.newContext({ storageState: statePath('director_talent') })
    const talentPage = await talent.newPage()
    await talentPage.goto('/dashboard')
    const talentCsrf = (await talent.cookies()).find((c) => c.name === 'csrftoken')!.value
    const activity = await talentPage.request.post('/api/activities/', {
      data: { student: student.id, category: 'olympiad', title: 'Олимпиада по математике' },
      headers: { 'X-CSRFToken': talentCsrf },
    })
    expect(activity.ok()).toBeTruthy()
    const activityId = (await activity.json()).id

    await page.goto(`/students/${student.id}`)
    await page.getByRole('button', { name: 'Строки и записи' }).click()
    const section = page.locator('.rows').filter({ hasText: 'Активности' })
    await expect(section).toContainText('Олимпиада по математике')
    // кнопки удаления у чужого домена нет вовсе
    await expect(section.getByRole('button', { name: 'Удалить' })).toHaveCount(0)
    await expect(section).toContainText('ведёт другой директор')

    // и API отбивает попытку в обход интерфейса
    const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')!.value
    const denied = await page.request.delete(`/api/activities/${activityId}/`, {
      headers: { 'X-CSRFToken': csrf },
    })
    expect(denied.status()).toBe(403)

    await adminPage.request.delete(`/api/students/${student.id}/`, { headers: { 'X-CSRFToken': adminCsrf } })
    await talent.close()
    await admin.close()
  })
})

test.describe('история загрузок и отмена импорта', () => {
  test.use({ storageState: statePath('director_exam') })

  test('загрузка видна в истории, отмена возвращает прежние значения', async ({ page }) => {
    const diag = watch(page)
    await page.goto('/import')
    await expect(page.locator('h1')).toContainText('Импорт из файла')
    await expect(page.getByText('История загрузок')).toBeVisible()

    // ставим известное начальное значение и грузим поверх него
    const found = await (await page.request.get('/api/students/?search=test.student&page_size=1')).json()
    const studentId = found.results[0].id
    const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')!.value
    await page.request.post('/api/batch/save/', {
      data: {
        changes: [
          { student: studentId, model: 'students.ExamProfile', field: 'hours_per_week', value: 4 },
        ],
      },
      headers: { 'X-CSRFToken': csrf },
    })

    const applied = await page.request.post('/api/import/apply/', {
      data: {
        file_name: 'проверка-отката.csv',
        rows: [
          {
            student: studentId,
            changes: [
              {
                model: 'students.ExamProfile',
                field: 'hours_per_week',
                old: '4',
                new: '9',
                raw: '9',
              },
            ],
          },
        ],
      },
      headers: { 'X-CSRFToken': csrf },
    })
    expect(applied.ok()).toBeTruthy()

    await page.reload()
    const row = page.locator('.imp__row').filter({ hasText: 'проверка-отката.csv' }).first()
    await expect(row).toBeVisible()

    const mark = diag.mark()
    await row.getByRole('button', { name: 'Отменить импорт' }).click()
    await page.locator('.confirm').getByRole('button', { name: 'Отменить импорт' }).click()
    await expect
      .poll(() => diag.since(mark).filter((c) => c.url.includes('/revert/') && c.status === 200).length)
      .toBeGreaterThan(0)
    await expect(page.locator('.imp__report')).toContainText('Возвращено прежних значений')

    // значение вернулось в базе, а не только на экране
    await page.reload()
    const profile = await (await page.request.get(`/api/profiles/exam/${studentId}/`)).json()
    expect(profile.hours_per_week).toBe(4)
    expect(diag.failed).toEqual([])
    expect(diag.consoleErrors).toEqual([])
  })
})
