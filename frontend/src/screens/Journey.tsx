/**
 * Лестница шагов ученика.
 *
 * Пять шагов занимают левую колонку строками с номером и действием; справа —
 * что даёт каждый шаг и ближайшая дата. Полоса «выполнено» стоит в шапке
 * подзаголовком. Состояния считает сервер по базе; здесь хранится только
 * «пропустил» — как подсказка первого входа, в localStorage.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCalendar, useJourney, useMyTasks, useNotifications, usePortfolio, type JourneyStep } from '../api/hooks'
import { shortDate } from '../components/CalendarCard'
import Progress from '../components/Progress'
import { Row, Rows } from '../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { NoteCard } from './academics/shared'
import './dashboards/student.css'

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

/** Что даёт каждый шаг — словами рядом с лестницей. */
const STEP_GIVES: Record<string, string> = {
  profile: 'Баллы и цели: от них считается соответствие вузам',
  universities: 'Список вузов: дедлайны сами станут задачами',
  documents: 'Документы: школа подтверждает, что всё на руках',
  essays: 'Эссе: черновики и замечания куратора в одном месте',
  plan: 'План по каждому вузу: задачи под требования программы',
}

/**
 * Пройденный путь: три карточки — что дальше, что усилит заявку, что нового.
 * Сам раздел при этом уходит из меню и возвращается из профиля.
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
    <div className="acad__cols">
      <div className="acad__stack">
        <DataCard title={t('Что дальше')} note={t('Три ближайших дела из вашего плана')} empty={next.length === 0 && t('задач без срока не осталось')}>
          <Rows>
            {next.map((task) => (
              <Row key={task.id} icon="checklist" title={task.title} note={task.due_date_effective ? `${t('до')} ${new Date(task.due_date_effective).toLocaleDateString('ru')}` : undefined} to="/roadmap" />
            ))}
          </Rows>
        </DataCard>
        <DataCard title={t('Что усилит заявку')} note={t('По разбору вашего профиля')} empty={strengthen.length === 0 && t('портфолио рассказано целиком')}>
          <Rows>
            {strengthen.map((step, index) => (
              <Row key={index} icon="star" tone="warn" title={t(step.text)} right={<Chip tone="warn" size="sm">{t('Не заполнено')}</Chip>} to="/my-data" />
            ))}
          </Rows>
        </DataCard>
      </div>
      <div className="acad__stack">
        <DataCard title={t('Путь пройден')} note={t('Дальше работаете по плану')}>
          <Rows>
            <Row icon="check" tone="good" title={t('Все шаги сделаны')} note={t('Раздел останется здесь на случай, если что-то нужно перезаполнить')} acts={<Button variant="secondary" size="sm" onClick={onShowSteps}>{t('Показать шаги')}</Button>} />
            <Row icon="checklist" title={t('План поступления')} note={t('задачи под каждый вуз')} acts={<Button variant="secondary" size="sm" onClick={() => navigate('/plan')}>{t('Открыть план')}</Button>} />
          </Rows>
        </DataCard>
        <DataCard title={t('Что нового')} note={t('За последнюю неделю')} empty={fresh.length === 0 && t('новостей пока нет')}>
          <Rows>
            {fresh.map((row) => (
              <Row key={row.id} icon="bell" title={row.text} note={new Date(row.created_at).toLocaleDateString('ru')} to={row.link || undefined} />
            ))}
          </Rows>
        </DataCard>
      </div>
    </div>
  )
}

export default function Journey() {
  const { data, isLoading, error } = useJourney()
  const calendar = useCalendar()
  const navigate = useNavigate()
  const [skipped, setSkipped] = useState<string[]>(readSkipped)
  // пройденный путь показывается свёрнутым; «Показать шаги» разворачивает
  // прежнюю лестницу — перезаполнить шаг иногда нужно
  const [showSteps, setShowSteps] = useState(false)

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const current = currentOf(data.steps, skipped)
  const today = calendar.data?.today ?? ''
  const upcoming = (calendar.data?.events ?? []).filter((event) => event.date >= today).slice(0, 4)

  const skip = (code: string) => {
    const next = [...new Set([...skipped, code])]
    setSkipped(next)
    localStorage.setItem(SKIP_KEY, JSON.stringify(next))
  }

  return (
    <div>
      <ScreenHead
        title={t('Ваш путь к поступлению')}
        subtitle={data.complete ? t('Все шаги пройдены — дальше работаете по плану.') : `${t('Выполнено')} ${data.done} ${t('из')} ${data.total} · ${t('Пропущенный шаг всегда можно вернуть')}`}
      />

      {data.complete && !showSteps && <Completed onShowSteps={() => setShowSteps(true)} />}

      {(!data.complete || showSteps) && (
        <div className="acad__cols">
          <div className="acad__stack">
            <DataCard title={t('Пять шагов')} note={t('От рассказа о себе до плана')}>
              <Progress percent={(data.done / Math.max(1, data.total)) * 100} label />
              <Rows>
                {data.steps.map((step, index) => {
                  const isCurrent = step.code === current && !step.done
                  const isSkipped = !step.done && !step.locked && skipped.includes(step.code) && !isCurrent
                  return (
                    <Row
                      key={step.code}
                      lead={<b className={`num stu__slot${step.done ? ' stu__slot--done' : ''}`}>{step.done ? '·' : index + 1}</b>}
                      tone={isCurrent ? 'accent' : step.done ? 'good' : 'neutral'}
                      title={t(step.title)}
                      note={step.locked ? t(step.lock_reason) : t(step.hint)}
                      muted={step.locked || isSkipped}
                      right={
                        step.done ? (
                          <Chip tone="good" size="sm">{t('Выполнено')}</Chip>
                        ) : isSkipped ? (
                          <Chip size="sm">{t('Пропущено')}</Chip>
                        ) : step.locked ? (
                          <Chip size="sm">{t('Пока закрыто')}</Chip>
                        ) : isCurrent ? (
                          <Chip tone="accent" size="sm">{t('сейчас')}</Chip>
                        ) : undefined
                      }
                      acts={
                        <>
                          {!step.locked && (
                            <Button variant={isCurrent ? 'default' : 'secondary'} size="sm" onClick={() => navigate(step.path)}>
                              {step.done || isSkipped ? t('Открыть') : t(step.action)}
                            </Button>
                          )}
                          {isCurrent && !step.done && (
                            <Button variant="ghost" size="sm" onClick={() => skip(step.code)}>
                              {t('Пропустить')}
                            </Button>
                          )}
                        </>
                      }
                    />
                  )
                })}
              </Rows>
            </DataCard>
          </div>
          <div className="acad__stack">
            <DataCard title={t('Что даёт каждый шаг')}>
              <Rows>
                {data.steps.map((step, index) => (
                  <Row key={step.code} lead={<b className="num stu__slot">{index + 1}</b>} title={t(step.title)} note={t(STEP_GIVES[step.code] ?? step.hint)} />
                ))}
              </Rows>
            </DataCard>
            <DataCard title={t('Ближайшее')} empty={upcoming.length === 0 && t('впереди пока пусто')}>
              <Rows>
                {upcoming.map((event, index) => (
                  <Row key={`${event.date}-${index}`} lead={<span className="stu__when num">{shortDate(event.date, today)}</span>} title={event.title} to={event.link} />
                ))}
              </Rows>
            </DataCard>
            <NoteCard title={t('Как это устроено')}>{t('Шаги считаются по данным: внесли баллы — шаг закрыт сам. Пропуск — только отложить: он не меняет ничего в данных.')}</NoteCard>
          </div>
        </div>
      )}
    </div>
  )
}
