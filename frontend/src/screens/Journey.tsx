/**
 * Лестница шагов ученика.
 *
 * Пять шагов — строками с номером и действием, узкой колонкой. Полоса
 * «выполнено» стоит в шапке подзаголовком; пояснений и учебного блока
 * здесь нет (решение владельца, 27.09.2026). Состояния считает сервер по базе; здесь хранится только
 * «пропустил» — как подсказка первого входа, в localStorage.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useJourney, useMyTasks, useNotifications, usePortfolio, type JourneyStep } from '../api/hooks'
import Progress from '../components/Progress'
import { Row, Rows } from '../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
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
        <DataCard title={t('Что дальше')} empty={next.length === 0 && t('задач без срока не осталось')}>
          <Rows>
            {next.map((task) => (
              <Row key={task.id} icon="checklist" title={task.title} note={task.due_date_effective ? `${t('до')} ${new Date(task.due_date_effective).toLocaleDateString('ru')}` : undefined} to="/roadmap" />
            ))}
          </Rows>
        </DataCard>
        <DataCard title={t('Что усилит заявку')} empty={strengthen.length === 0 && t('портфолио рассказано целиком')}>
          <Rows>
            {strengthen.map((step, index) => (
              <Row key={index} icon="star" tone="warn" title={t(step.text)} right={<Chip tone="warn" size="sm">{t('Не заполнено')}</Chip>} to="/my-data" />
            ))}
          </Rows>
        </DataCard>
      </div>
      <div className="acad__stack">
        <DataCard title={t('Путь пройден')}>
          <Rows>
            <Row icon="check" tone="good" title={t('Все шаги сделаны')} acts={<Button variant="secondary" size="sm" onClick={onShowSteps}>{t('Показать шаги')}</Button>} />
            <Row icon="checklist" title={t('План поступления')} note={t('задачи под каждый вуз')} acts={<Button variant="secondary" size="sm" onClick={() => navigate('/plan')}>{t('Открыть план')}</Button>} />
          </Rows>
        </DataCard>
        <DataCard title={t('Что нового')} empty={fresh.length === 0 && t('новостей пока нет')}>
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
        subtitle={`${t('Выполнено')} ${data.done} ${t('из')} ${data.total}`}
      />

      {data.complete && !showSteps && <Completed onShowSteps={() => setShowSteps(true)} />}

      {(!data.complete || showSteps) && (
        <div className="acad__narrow">
            <DataCard title={t('Пять шагов')}>
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
      )}
    </div>
  )
}
