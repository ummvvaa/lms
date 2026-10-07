import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { LastUserMail, MailResultNotice } from './UserMail'

describe('результат отправки писем', () => {
  it('показывает ошибку почты и причины пропуска даже при успешном ответе API', () => {
    const html = renderToStaticMarkup(createElement(MailResultNotice, { result: {
      sent: 0, queued: 0, failed: 1, detail: 'Отправлено 0, в очереди 0, пропущено 1, ошибок отправки 1',
      skipped: [{ email: 'recent@example.test', reason: 'Письмо уже уходило 06.10' }],
      failures: [{ email: 'failed@example.test', reason: 'SMTP 550' }],
    } }))
    expect(html).toContain('Отправлено 0, в очереди 0, пропущено 1, ошибок отправки 1')
    expect(html).toContain('SMTP 550')
    expect(html).toContain('Письмо уже уходило 06.10')
  })

  it('отделяет письма в очереди от уже отправленных', () => {
    const html = renderToStaticMarkup(createElement(MailResultNotice, { result: {
      sent: 2, queued: 3, failed: 0, skipped: [], detail: 'Отправлено 2, в очереди 3, пропущено 0',
    } }))
    expect(html).toContain('Отправлено 2, в очереди 3, пропущено 0')
  })
})

describe('дата последнего письма', () => {
  it('не принимает старую живую ссылку за доказательство отправки', () => {
    const html = renderToStaticMarkup(createElement(LastUserMail, { user: {
      password_state: 'invite_issued', last_mail_sent_at: null,
    } }))
    expect(html).toContain('Нет данных об отправке')
    expect(html).not.toContain('Последнее письмо:')
  })

  it('показывает подтверждённую отправку по времени Алматы', () => {
    const html = renderToStaticMarkup(createElement(LastUserMail, { user: {
      password_state: 'ready', last_mail_sent_at: '2026-10-06T21:15:00Z',
    } }))
    expect(html).toContain('07.10.2026, 02:15')
    expect(html).not.toContain('Нет данных об отправке')
  })
})
