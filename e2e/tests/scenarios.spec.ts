/**
 * Сценарии, которые обход кнопками не ловит: сохранение переживает
 * перезагрузку, ввод мусора даёт внятный отказ, список не обрезается молча,
 * ученику не показываются внутренние ярлыки.
 */
import { expect, test } from '@playwright/test'
import { statePath } from '../helpers/auth-state'
import { byKey } from '../helpers/roles'
import { watch } from '../helpers/session'

/** Внутренние ярлыки, которых ученик не должен видеть (инвариант №7). */
const INTERNAL_WORDS = [
  'critical',
  'needs_supervision',
  'can_execute',
  'Ежедневный контроль',
  'Нужен контроль',
  'Слабое',
  'Сильное',
  'A — готов к подаче',
  'C — критический',
]

test.describe('таблица директора', () => {
  test.use({ storageState: statePath('director_exam') })

  test('правка в таблице переживает перезагрузку', async ({ page }) => {
    await page.goto('/table')
    await expect(page.locator('table.grid-tbl tbody tr').first()).toBeVisible()

    const value = `Проверка ${Date.now() % 100000}`
    const cell = page.locator('input[data-col]').nth(5) // «Преподаватель» — текстовое поле
    const column = await page
      .locator('table.grid-tbl thead th')
      .nth(7)
      .innerText()
      .catch(() => '')
    expect(column).toContain('Преподаватель')

    await cell.fill(value)
    await Promise.all([
      page.waitForResponse((r) => r.url().includes('/api/batch/save/')),
      page.getByRole('button', { name: 'Сохранить' }).click(),
    ])

    await page.reload()
    await expect(page.locator('input[data-col]').nth(5)).toHaveValue(value)
  })

  test('нечисловое значение отклоняется внятно, а не пятисоткой', async ({ page }) => {
    const diag = watch(page)
    await page.goto('/table')
    await expect(page.locator('table.grid-tbl tbody tr').first()).toBeVisible()

    await page.locator('input[data-col="0"]').first().fill('не число')
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/api/batch/save/')),
      page.getByRole('button', { name: 'Сохранить' }).click(),
    ])

    expect(response.status(), 'сервер не должен отвечать 500 на мусор в ячейке').toBeLessThan(500)
    await expect(page.locator('.toolbar')).toContainText(/отклонено|не сохранено|ошибк/i)
    expect(diag.pageErrors).toEqual([])
  })

  test('в таблицу попадают все ученики, а не первая страница', async ({ page }) => {
    const counts = await page.request.get('/api/students/?page_size=500')
    const payload = await counts.json()
    await page.goto('/table')
    await expect(page.locator('table.grid-tbl tbody tr').first()).toBeVisible()
    await expect
      .poll(async () => page.locator('table.grid-tbl tbody tr').count(), { timeout: 15_000 })
      .toBe(payload.count)
  })
})

test.describe('карточка ученика', () => {
  test.use({ storageState: statePath('director_exam') })

  test('правка на карточке пишется в историю и остаётся после перезагрузки', async ({ page }) => {
    const list = await (await page.request.get('/api/students/?page_size=1')).json()
    const id = list.results[0].id

    await page.goto(`/students/${id}`)
    await expect(page.locator('.card__name')).toBeVisible()

    const value = String(4 + (Date.now() % 5))
    const input = page.locator('.domain--mine input.domain__input').nth(4) // «Часов в неделю»
    await input.fill(value)
    await Promise.all([
      page.waitForResponse((r) => r.url().includes('/api/batch/save/')),
      page.getByRole('button', { name: 'Сохранить' }).click(),
    ])

    await page.reload()
    await expect(page.locator('.domain--mine input.domain__input').nth(4)).toHaveValue(value)

    await page.getByRole('button', { name: 'История изменений' }).click()
    await expect(page.locator('table.history')).toContainText('hours_per_week')
  })
})

test.describe('кабинет ученика', () => {
  test.use({ storageState: statePath('student') })

  for (const route of ['/dashboard', '/roadmap', '/universities', '/essays', '/alumni']) {
    test(`на ${route} нет внутренних ярлыков`, async ({ page }) => {
      await page.goto(route)
      await page.waitForTimeout(800)
      const text = await page.locator('body').innerText()
      for (const word of INTERNAL_WORDS) {
        expect(text, `ярлык «${word}» виден ученику`).not.toContain(word)
      }
    })
  }

  test('ученик не попадает на дашборды директоров', async ({ page }) => {
    const response = await page.request.get('/api/dashboards/admission/')
    expect(response.status()).toBe(403)
  })
})
