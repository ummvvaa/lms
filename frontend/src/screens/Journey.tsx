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
import { useJourney, useMyTasks, useNotifications, usePortfolio, type JourneyStep } from '../api/hooks'
import { Row, Rows, Tile } from '../components/patterns'
import { Bar, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
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

/**
 * Пройденный путь (фаза 49).
 *
 * Пять шагов позади — лестница сворачивается в одну строку, а вместо неё
 * три карточки: что дальше, что усилит заявку, что нового. Сам раздел
 * при этом уходит из меню (решение владельца) и возвращается из профиля;
 * сюда попадают те, кто его вернул или пришёл по ссылке.
 */
function Completed({ onShowSteps }: { onShowSteps: () => void }) {
  const navigate = useNavigate()
  const tasks = useMyTasks()
  const portfolio = usePortfolio()
  const notifications = useNotifications()

  const next = (tasks.data ?? []).filter((task) => task.status !== 'done').slice(0, 3)
  const strengthen = (portfolio.data?.next_steps ?? []).slice(0, 3)
  const fresh = (notifications.data?.rows ?? []).slice(0, 3)

  return (
    <div>
      <div className="card card-pad card--accent card--ok journey__done">
        <Tile icon="check" tone="ok" size="lg" />
        <div className="journey__donetext">
          <b>{t('Путь пройден')}</b>
          <p className="muted">
            {t(
              'Дальше работаете по плану. Раздел останется здесь на случай, если что-то нужно перезаполнить.',
            )}
          </p>
        </div>
        <Button onClick={() => navigate('/plan')}>{t('Открыть план')}</Button>
        <Button variant="outline" onClick={onShowSteps}>
          {t('Показать шаги')}
        </Button>
      </div>

      <div className="journey__cards">
        <DataCard title={t('Что дальше')} note={t('Три ближайших дела из вашего плана')} accent="brand">
          {next.length === 0 && <p className="muted rows__empty">{t('Задач без срока не осталось')}</p>}
          <Rows>
            {next.map((task) => (
              <Row
                key={task.id}
                title={task.title}
                note={
                  task.due_date_effective
                    ? `${t('до')} ${new Date(task.due_date_effective).toLocaleDateString('ru')}`
                    : undefined
                }
                onOpen={() => navigate('/roadmap')}
                openLabel={t('Открыть задачу')}
              />
            ))}
          </Rows>
        </DataCard>

        <DataCard title={t('Что усилит заявку')} note={t('По разбору вашего профиля')} accent="teal">
          {strengthen.length === 0 && (
            <p className="muted rows__empty">{t('Портфолио рассказано целиком')}</p>
          )}
          <Rows>
            {strengthen.map((step, index) => (
              <Row
                key={index}
                title={t(step.text)}
                right={<Badge variant="warn">{t('Не заполнено')}</Badge>}
                onOpen={() => navigate('/my-data')}
                openLabel={t('Заполнить')}
              />
            ))}
          </Rows>
        </DataCard>

        <DataCard title={t('Что нового')} note={t('За последнюю неделю')} accent="indigo">
          {fresh.length === 0 && <p className="muted rows__empty">{t('Новостей пока нет')}</p>}
          <Rows>
            {fresh.map((row) => (
              <Row
                key={row.id}
                title={row.text}
                note={new Date(row.created_at).toLocaleDateString('ru')}
                onOpen={row.link ? () => navigate(row.link) : undefined}
                openLabel={t('Открыть')}
              />
            ))}
          </Rows>
        </DataCard>
      </div>
    </div>
  )
}

export default function Journey() {
  const { data, isLoading, error } = useJourney()
  const navigate = useNavigate()
  const [skipped, setSkipped] = useState<string[]>(readSkipped)
  // пройденный путь показывается свёрнутым; «Показать шаги» разворачивает
  // прежнюю лестницу — перезаполнить шаг иногда нужно
  const [showSteps, setShowSteps] = useState(false)

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

      {data.complete && !showSteps && <Completed onShowSteps={() => setShowSteps(true)} />}

      {(!data.complete || showSteps) && (
        <>
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
                      <p className="muted journey__hint">
                        {step.locked ? t(step.lock_reason) : t(step.hint)}
                      </p>
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
        </>
      )}
    </div>
  )
}
