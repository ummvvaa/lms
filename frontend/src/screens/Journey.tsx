/**
 * Лестница шагов ученика (фаза 37).
 *
 * Пока путь не пройден, это главный экран кабинета: пять шагов
 * с прогрессом. Состояния считает сервер по базе; здесь хранится только
 * «пропустил» — как подсказка первого входа, в localStorage: пропуск
 * не факт о данных, а жест «вернусь позже».
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useJourney, type JourneyStep } from '../api/hooks'
import { Bar, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { t } from '../i18n'

const SKIP_KEY = 'journey.skipped'

function readSkipped(): string[] {
  try {
    return JSON.parse(localStorage.getItem(SKIP_KEY) ?? '[]') as string[]
  } catch {
    return []
  }
}

/** Текущий шаг — первый не сделанный, не запертый и не отложенный. */
function currentOf(steps: JourneyStep[], skipped: string[]): string | null {
  const open = steps.filter((s) => !s.done && !s.locked)
  return (open.find((s) => !skipped.includes(s.code)) ?? open[0])?.code ?? null
}

export default function Journey() {
  const { data, isLoading, error } = useJourney()
  const navigate = useNavigate()
  const [skipped, setSkipped] = useState<string[]>(readSkipped)

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const current = currentOf(data.steps, skipped)

  const skip = (code: string) => {
    const next = [...new Set([...skipped, code])]
    setSkipped(next)
    localStorage.setItem(SKIP_KEY, JSON.stringify(next))
  }

  return (
    <div>
      <ScreenHead
        title={t('Ваш путь к поступлению')}
        subtitle={
          data.complete
            ? t('Все шаги пройдены — дальше работаете по плану.')
            : t('Пять шагов: от рассказа о себе до плана. Пропущенный шаг всегда можно вернуть.')
        }
      />

      <div className="card card-pad journey__progress">
        <div className="row-between" style={{ marginBottom: 8 }}>
          <span className="eyebrow">{t('Выполнено')}</span>
          <b className="num">
            {data.done} {t('из')} {data.total}
          </b>
        </div>
        <Bar percent={(data.done / data.total) * 100} />
      </div>

      <div className="journey__steps">
        {data.steps.map((step, index) => {
          const isCurrent = step.code === current && !step.done
          const isSkipped = !step.done && !step.locked && skipped.includes(step.code) && !isCurrent
          return (
            <section
              key={step.code}
              className={`card card-pad journey__step${isCurrent ? ' card--accent card--brand' : ''}`}
              style={step.locked || isSkipped ? { opacity: 0.66 } : undefined}
              data-step={step.code}
            >
              <div className="journey__row">
                <span className={`journey__num num${step.done ? ' journey__num--done' : ''}`} aria-hidden>
                  {step.done ? '✓' : index + 1}
                </span>
                <div className="journey__body">
                  <div className="journey__title">
                    {t(step.title)}
                    {step.done && <Badge variant="ok">{t('Выполнено')}</Badge>}
                    {isSkipped && <Badge variant="mute">{t('Пропущено')}</Badge>}
                    {step.locked && <Badge variant="mute">{t('Пока закрыто')}</Badge>}
                  </div>
                  <p className="muted journey__hint">{step.locked ? t(step.lock_reason) : t(step.hint)}</p>
                </div>
                <div className="journey__actions">
                  {!step.locked && (
                    <Button
                      variant={isCurrent ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => navigate(step.path)}
                    >
                      {step.done || isSkipped ? t('Открыть') : t(step.action)}
                    </Button>
                  )}
                  {isCurrent && !step.done && (
                    <Button variant="ghost" size="sm" onClick={() => skip(step.code)}>
                      {t('Пропустить')}
                    </Button>
                  )}
                </div>
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}
