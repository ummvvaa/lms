/**
 * Расходы на модель — экран администратора.
 *
 * Видно, сколько потрачено с начала месяца, кто и на что тратит.
 * При исчерпании лимита операции отключаются, и здесь об этом сказано
 * прямо — чтобы не искать причину по логам.
 */
import { useState } from 'react'
import { useSpendReport } from '../api/hooks'
import Empty from '../components/Empty'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import './materials.css'
import { t } from '../i18n'

const money = (value: number) => `$${value.toFixed(2)}`

export default function Spend() {
  const [days, setDays] = useState(30)
  const report = useSpendReport(days)

  if (report.isLoading) return <Loading />
  if (report.isError) return <ErrorNote error={report.error} />
  if (!report.data) return null

  const data = report.data

  return (
    <div>
      <ScreenHead
        title={t('Расходы на модель')}
        subtitle={t('Каждый вызов записан: кто, когда, какая операция, сколько токенов и денег.')}
      />

      <p className={`chip ${data.available ? 'chip-mute' : 'chip-risk'} mat__flash`}>{data.detail}</p>

      <div className="grid grid--two">
        <div className="card card-pad">
          <span className="eyebrow">{t('Расход за месяц')}</span>
          <p className="num" style={{ fontSize: 28, fontWeight: 700, margin: '6px 0' }}>
            {money(data.spent_this_month)}
            {data.limit > 0 && (
              <span className="muted" style={{ fontSize: 15 }}>
                {' '}
                из {money(data.limit)}
              </span>
            )}
          </p>
          {data.limit > 0 && (
            <div className="spend__bar" aria-label={`Использовано ${data.percent}%`}>
              <span style={{ width: `${data.percent}%` }} />
            </div>
          )}
          {data.limit === 0 && (
            <p className="muted">{t('Лимит не задан — задаётся переменной LLM_MONTHLY_LIMIT.')}</p>
          )}
        </div>

        <div className="card card-pad">
          <span className="eyebrow">За {days} дней</span>
          <p className="muted">
            {t('Вызовов: ')}
            <b className="num">{data.calls}</b>
            {data.failures > 0 && (
              <>
                {' · '}неудачных: <b className="num">{data.failures}</b>
              </>
            )}
          </p>
          <div className="toolbar" style={{ marginBottom: 0 }}>
            {[7, 30, 90].map((n) => (
              <button
                key={n}
                className={`btn btn-sm ${days === n ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setDays(n)}
              >
                {n} дней
              </button>
            ))}
          </div>
        </div>
      </div>

      {data.calls === 0 ? (
        <Empty
          title={t('Модель ещё не вызывали')}
          what={t('Пока платить не за что: помощником ещё не пользовались.')}
          hint={t('Каждый вызов модели попадает сюда со стоимостью по прейскуранту из настроек.')}
        />
      ) : (
        <>
          <h2 className="section">{t('Кто тратит')}</h2>
          <div className="card card-pad">
            <table className="tbl dir__table">
              <thead>
                <tr>
                  <th>{t('Роль')}</th>
                  <th>{t('Вызовов')}</th>
                  <th>{t('Стоимость')}</th>
                </tr>
              </thead>
              <tbody>
                {data.by_role.map((row) => (
                  <tr key={row.role}>
                    <td>{row.role_title}</td>
                    <td className="num">{row.calls}</td>
                    <td className="num">{money(row.cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2 className="section">{t('На что')}</h2>
          <div className="card card-pad">
            <table className="tbl dir__table">
              <thead>
                <tr>
                  <th>{t('Операция')}</th>
                  <th>{t('Вызовов')}</th>
                  <th>{t('Токенов')}</th>
                  <th>{t('Стоимость')}</th>
                </tr>
              </thead>
              <tbody>
                {data.by_purpose.map((row) => (
                  <tr key={row.purpose}>
                    <td>{row.purpose_title}</td>
                    <td className="num">{row.calls}</td>
                    <td className="num">{row.tokens}</td>
                    <td className="num">{money(row.cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2 className="section">{t('Последние вызовы')}</h2>
          <div className="card card-pad">
            <table className="history">
              <tbody>
                {data.recent.map((row) => (
                  <tr key={row.id}>
                    <td className="muted history__when">{new Date(row.created_at).toLocaleString('ru')}</td>
                    <td>{row.actor_name}</td>
                    <td className="muted">{row.role_title}</td>
                    <td>{row.purpose_title}</td>
                    <td className="num">{row.tokens}</td>
                    <td className="num">{money(row.cost)}</td>
                    <td>
                      {row.is_ok ? (
                        <span className="chip chip-ok">{t('успех')}</span>
                      ) : (
                        <span className="chip chip-risk">{row.error || 'сбой'}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
