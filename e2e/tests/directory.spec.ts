/**
 * Фаза 13: стартовый справочник и плашка «данные не подтверждены».
 *
 * Приёмка: у Асем на экране справочника кнопка заводит 20 вузов с плашками,
 * кнопка «Подтвердить данные» снимает плашку и переживает перезагрузку,
 * а «Удалить стартовый справочник» убирает ровно заготовку — вуз,
 * заведённый руками, остаётся на месте.
 */
import { expect, test, type Page } from '@playwright/test'
import { statePath } from '../helpers/auth-state'
import { watch } from '../helpers/session'

const SEED_MARK = 'Стартовый справочник'

/** Состояние справочника из API — «видно в базе» проверяем именно так. */
async function directoryState(page: Page) {
  const seed = await (await page.request.get('/api/catalog/seed/')).json()
  return seed as {
    universities: number
    unverified: number
    own_universities: number
    held_by_students: number
  }
}

async function ensureSeed(page: Page) {
  const state = await directoryState(page)
  if (state.universities > 0) return
  await page.getByRole('button', { name: 'Заполнить стартовый справочник' }).click()
  await expect.poll(async () => (await directoryState(page)).universities).toBeGreaterThan(0)
}

test.describe('справочник у директора по поступлению', () => {
  test.use({ storageState: statePath('director_admission') })

  test('кнопка заводит стартовый справочник, и он виден после перезагрузки', async ({ page }) => {
    const diag = watch(page)
    await page.goto('/directory')
    await expect(page.locator('h1')).toContainText('Вузы и программы')

    // начинаем с чистого стартового справочника, чтобы кнопка реально сработала
    if ((await directoryState(page)).universities > 0) {
      await page.getByRole('button', { name: 'Удалить стартовый справочник' }).click()
      await page.getByLabel('Наберите УДАЛИТЬ').fill('УДАЛИТЬ')
      await page.getByRole('button', { name: 'Удалить заготовку' }).click()
      await expect.poll(async () => (await directoryState(page)).universities).toBe(0)
    }

    const mark = diag.mark()
    await page.getByRole('button', { name: 'Заполнить стартовый справочник' }).click()
    // ушёл запрос, ответ 2xx
    await expect
      .poll(() => diag.since(mark).filter((c) => c.method === 'POST' && c.url.includes('/catalog/seed/')).length)
      .toBeGreaterThan(0)
    expect(diag.failed).toEqual([])

    const state = await directoryState(page)
    expect(state.universities).toBe(20)
    expect(state.unverified).toBe(20)

    await page.reload()
    await expect(page.locator('.dir__row').first()).toBeVisible()
    await expect(page.locator('.dir__row').first().getByText('не подтверждено')).toBeVisible()
    expect(diag.consoleErrors).toEqual([])
  })

  test('«Подтвердить данные» снимает плашку и держится после перезагрузки', async ({ page }) => {
    const diag = watch(page)
    await page.goto('/directory')
    await ensureSeed(page)
    await page.reload()

    const row = page.locator('.dir__row').filter({ hasText: SEED_MARK }).first()
    const name = await row.locator('.dir__name').innerText()

    const mark = diag.mark()
    await row.getByRole('button', { name: 'Подтвердить данные' }).click()
    await expect
      .poll(() => diag.since(mark).filter((c) => c.method === 'POST' && c.url.includes('/catalog/verify/')).length)
      .toBeGreaterThan(0)
    expect(diag.failed).toEqual([])

    await page.reload()
    const again = page.locator('.dir__row').filter({ hasText: name }).first()
    await expect(again.getByText('подтверждено', { exact: true })).toBeVisible()
    await expect(again.locator('.unverified')).toHaveCount(0)
    expect(diag.consoleErrors).toEqual([])
  })

  test('удаление заготовки не трогает вуз, заведённый школой', async ({ page }) => {
    const diag = watch(page)
    await page.goto('/directory')
    await ensureSeed(page)

    const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken')!.value
    const own = await page.request.post('/api/universities/', {
      data: { name: `Школьный вуз ${Date.now()}`, country: 'Казахстан' },
      headers: { 'X-CSRFToken': csrf },
    })
    expect(own.ok()).toBeTruthy()
    const ownName = (await own.json()).name as string

    await page.reload()
    await page.getByRole('button', { name: 'Удалить стартовый справочник' }).click()
    // подтверждение просит набрать слово: случайным кликом не пройти
    const confirmButton = page.getByRole('button', { name: 'Удалить заготовку' })
    await expect(confirmButton).toBeDisabled()
    await page.getByLabel('Наберите УДАЛИТЬ').fill('УДАЛИТЬ')
    await confirmButton.click()

    await expect.poll(async () => (await directoryState(page)).universities).toBe(0)
    expect(diag.failed.filter((c) => c.status !== 409)).toEqual([])

    await page.reload()
    await expect(page.locator('.dir__row').filter({ hasText: ownName })).toHaveCount(1)
    await expect(page.locator('.dir__row').filter({ hasText: SEED_MARK })).toHaveCount(0)

    // за собой убираем: сценарий не должен оставлять следов в справочнике
    await page.request.delete(`/api/universities/${(await own.json()).id}/`, {
      headers: { 'X-CSRFToken': csrf },
    })
  })
})

test.describe('плашка глазами ученика', () => {
  test('непроверенная программа приходит ученику только с оговоркой', async ({ browser }) => {
    const staff = await browser.newContext({ storageState: statePath('director_admission') })
    const staffPage = await staff.newPage()
    await staffPage.goto('/directory')
    await ensureSeed(staffPage)
    await staff.close()

    const context = await browser.newContext({ storageState: statePath('student') })
    const page = await context.newPage()
    const diag = watch(page)
    await page.goto('/catalog')

    const card = page.locator('.match').filter({ has: page.locator('.unverified') }).first()
    await expect(card).toBeVisible()
    await expect(card.locator('.unverified')).toContainText('Данные не подтверждены')
    // оговорка стоит рядом с процентом, а не вместо него (инвариант №11 и №14)
    await expect(card.locator('.match__value')).toContainText('%')
    expect(diag.failed).toEqual([])
    expect(diag.consoleErrors).toEqual([])
    await context.close()
  })
})
