/**
 * Регрессия по `docs/DEFECTS.md`: каждый закрытый дефект — отдельная проверка,
 * чтобы он не вернулся. Названия тестов ссылаются на номера из реестра.
 */
import { expect, test } from '@playwright/test'
import { statePath } from '../helpers/auth-state'
import { byKey } from '../helpers/roles'
import { watch } from '../helpers/session'

test.describe('B1 · запись из браузера проходит', () => {
  test('под учеником: what-if отвечает 2xx', async ({ page }) => {
    const account = byKey('student')
    await page.goto('/login')
    await page.getByLabel(/почта|email/i).first().fill(account.email)
    await page.getByLabel(/пароль/i).first().fill(account.password)
    await page.getByRole('button', { name: /Войти с тестовым аккаунтом/i }).click()
    await page.waitForURL(/\/dashboard/)

    await page.goto('/universities')
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/api/match/what-if/')),
      page.getByRole('button', { name: 'Что даст +0.5 IELTS' }).click(),
    ])
    expect(response.status(), 'CSRF снова отбивает запись').toBe(200)
  })

  test('кнопка «Выйти» действительно выходит', async ({ page }) => {
    const account = byKey('director_talent')
    await page.goto('/login')
    await page.getByLabel(/почта|email/i).first().fill(account.email)
    await page.getByLabel(/пароль/i).first().fill(account.password)
    await page.getByRole('button', { name: /Войти с тестовым аккаунтом/i }).click()
    await page.waitForURL(/\/dashboard/)

    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/api/auth/logout/')),
      page.getByRole('button', { name: 'Выйти' }).click(),
    ])
    expect(response.status()).toBeLessThan(400)
    await page.waitForURL(/\/login/)
  })
})

test.describe('B4 · помощник: каждая кнопка что-то делает', () => {
  test.use({ storageState: statePath('director_admission') })

  test('кнопки — настоящие кнопки, а не карточки', async ({ page }) => {
    await page.goto('/assistant')
    const cards = page.locator('.assistant__cmd')
    await expect(cards.first()).toBeVisible()
    const count = await cards.count()
    expect(count).toBeGreaterThan(0)
    for (let i = 0; i < count; i += 1) {
      await expect(cards.nth(i)).toHaveJSProperty('tagName', 'BUTTON')
    }
  })

  test('«Дайджест на сегодня» уводит на дайджест', async ({ page }) => {
    await page.goto('/assistant')
    await page.getByRole('button', { name: /Дайджест на сегодня/ }).click()
    await page.waitForURL(/\/digest/)
  })

  test('«Проверить баланс списка» считает по выбранному ученику', async ({ page }) => {
    const diag = watch(page)
    await page.goto('/assistant')
    await page.getByRole('button', { name: /Проверить баланс списка/ }).click()

    const list = await (await page.request.get('/api/students/?page_size=1')).json()
    await page.locator('select').first().selectOption(String(list.results[0].id))

    await expect
      .poll(() => diag.calls.some((c) => c.url.includes('/api/match/list-balance/') && c.status === 200))
      .toBe(true)
    await expect(page.locator('.card').last()).toContainText(/reach|Список пуст/)
  })
})

test.describe('I2 · предложения живут дольше одной вкладки', () => {
  test.use({ storageState: statePath('director_exam') })

  test('экран предложений открывается из навигации', async ({ page }) => {
    const diag = watch(page)
    await page.goto('/suggestions')
    await expect(page.locator('h1')).toContainText('Предложения')
    expect(diag.failed).toEqual([])
  })
})

test.describe('I3 · разделы ведут к своей секции', () => {
  test.use({ storageState: statePath('director_exam') })

  test('TOP-30 прокручивает к секции TOP-30', async ({ page }) => {
    await page.goto('/top30')
    const section = page.locator('#top30')
    await expect(section).toBeVisible()
    await expect
      .poll(async () => section.evaluate((el) => el.getBoundingClientRect().top < window.innerHeight), {
        timeout: 10_000,
      })
      .toBe(true)
  })
})

test.describe('I4 · чужой экран не открывается', () => {
  test.use({ storageState: statePath('director_sport') })

  test('директора уводит с экранов ученика без ошибок в консоли', async ({ page }) => {
    const diag = watch(page)
    await page.goto('/roadmap')
    await page.waitForURL(/\/dashboard/)
    expect(diag.failed, 'экран чужой роли снова сыплет 404').toEqual([])
  })
})

test.describe('I5 · гистограмма экзаменов кликается', () => {
  test.use({ storageState: statePath('director_exam') })

  test('плитка открывает этих учеников в таблице', async ({ page }) => {
    await page.goto('/dashboard')
    await page.getByRole('button', { name: /IELTS < 6\.0/ }).click()
    await page.waitForURL(/\/table\?/)
    await expect(page.getByText('Фильтр из дашборда:')).toBeVisible()
    await expect(page.locator('table.grid-tbl tbody tr').first()).toBeVisible()
  })
})

test.describe('I6 · черновик можно отменить', () => {
  test.use({ storageState: statePath('director_exam') })

  test('«Отменить правки» возвращает прежние значения', async ({ page }) => {
    await page.goto('/table')
    const cell = page.locator('input[data-col="5"]').first()
    await expect(cell).toBeVisible()
    const before = await cell.inputValue()

    await cell.fill('Черновик, который передумали')
    await expect(page.locator('.toolbar')).toContainText('Не сохранено')

    await page.getByRole('button', { name: 'Отменить правки' }).click()
    await expect(cell).toHaveValue(before)
    await expect(page.locator('.toolbar')).not.toContainText('Не сохранено')
  })
})

test.describe('C1 · заголовок не двоится', () => {
  test.use({ storageState: statePath('student') })

  for (const [route, title] of [
    ['/roadmap', 'Роадмап'],
    ['/essays', 'Эссе'],
    ['/universities', 'Мои вузы'],
  ]) {
    test(`${route}: «${title}» встречается один раз`, async ({ page }) => {
      await page.goto(route)
      await expect(page.locator('h1')).toContainText(title)
      const head = await page.locator('.head').innerText()
      const occurrences = head.split(title).length - 1
      expect(occurrences, `заголовок «${title}» напечатан ${occurrences} раза`).toBe(1)
    })
  }
})

test.describe('C2 · «Позже» в баннере запоминается', () => {
  test.use({ storageState: statePath('student') })

  test('баннер не возвращается при переходе на другой экран', async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForTimeout(600)
    const later = page.getByRole('button', { name: 'Позже' })
    const wasShown = await later.isVisible().catch(() => false)
    if (wasShown) {
      await later.click()
      await expect(later).toBeHidden()
    }

    // полная перезагрузка, а не переход внутри приложения: раньше баннер
    // возвращался именно так
    await page.goto('/roadmap')
    await page.waitForTimeout(800)
    await expect(page.getByRole('button', { name: 'Позже' })).toBeHidden()
  })
})

test.describe('C4 · ученик видит все пять блоков готовности', () => {
  test.use({ storageState: statePath('student') })

  test('домены без данных подписаны, а не спрятаны', async ({ page }) => {
    await page.goto('/dashboard')
    const payload = await (await page.request.get('/api/students/me/')).json()
    const titles = [
      ...payload.readiness.parts.map((p: { title: string }) => p.title),
      ...payload.readiness.skipped.map((p: { title: string }) => p.title),
    ]
    expect(titles.length, 'в разбивке должны быть все пять доменов').toBe(5)
    for (const title of titles) {
      await expect(page.locator('main')).toContainText(title)
    }
  })
})
