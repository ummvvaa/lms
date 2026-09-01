/**
 * XP, стрик и «задания на сегодня» на главной ученика.
 *
 * Никаких рейтингов и сравнения с другими: в контексте поступления это
 * вредно. Формулировки поддерживающие — ученику с нулевым стриком система
 * не сообщает, что он всё потерял, а предлагает начать.
 *
 * С фазы 48 блок собран из общего набора (карточка с плиткой в шапке,
 * строки списка через тонкую линию), но остался тем же по смыслу: задачу
 * видно и отмечают прямо здесь, а не только в роадмапе.
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGameState, useTaskStatus, type TodayTask } from '../api/hooks'
import { Row, Rows, Tile } from './patterns'
import { t } from '../i18n'
import { Checkbox } from './ui/checkbox'
import { Button } from './ui/button'
import { Badge } from './ui/badge'

const PRIORITY_TITLE: Record<string, string> = { high: 'важно', medium: 'обычное', low: 'не срочно' }

function DueChip({ task }: { task: TodayTask }) {
  if (task.days_left === null) return null
  if (task.days_left < 0)
    return (
      <Badge variant="warn" className="num">
        {t('срок прошёл')}
      </Badge>
    )
  if (task.days_left <= 7)
    return (
      <Badge variant="warn" className="num">
        {task.days_left} дн.
      </Badge>
    )
  return (
    <Badge variant="mute" className="num">
      {task.days_left} дн.
    </Badge>
  )
}

export default function TodayPanel() {
  const navigate = useNavigate()
  const { data, isLoading } = useGameState()
  const move = useTaskStatus()
  // выполненная задача уходит из списка — без короткого подтверждения
  // это выглядит так, будто она просто пропала
  const [earned, setEarned] = useState<number | null>(null)

  useEffect(() => {
    if (earned === null) return
    const timer = window.setTimeout(() => setEarned(null), 4000)
    return () => window.clearTimeout(timer)
  }, [earned])

  if (isLoading || !data) return null

  return (
    <section className="card card-pad card--accent card--teal today">
      <header className="home__cardhead">
        <Tile icon="check" tone="teal" size="lg" />
        <span className="home__cardtitle">
          <b>{t('Задания на сегодня')}</b>
          <span className="muted">
            {t('уровень')} {data.level} · {data.level_step - data.level_progress} {t('XP до следующего')}
          </span>
        </span>
        {earned !== null && (
          <Badge variant="ok" className="num today__earned">
            +{earned} XP · готово
          </Badge>
        )}
      </header>

      {data.today.length === 0 && (
        <div className="today__empty">
          <p className="muted">
            {t(
              'На сегодня задач нет. Задачи собираются из ваших вузов и их дедлайнов — выберите вузы, и план появится сам.',
            )}
          </p>
          <Button size="sm" onClick={() => navigate('/catalog')}>
            {t('Открыть каталог')}
          </Button>
        </div>
      )}

      {data.today.length > 0 && (
        <Rows>
          {data.today.map((task) => (
            <Row
              key={task.id}
              lead={
                <Checkbox
                  checked={task.status === 'done'}
                  disabled={move.isPending}
                  onCheckedChange={() =>
                    move.mutate({ id: task.id, status: 'done' }, { onSuccess: () => setEarned(task.xp) })
                  }
                />
              }
              title={task.title}
              note={`${PRIORITY_TITLE[task.priority] ?? task.priority}${
                task.university_name ? ` · ${task.university_name}` : ''
              }`}
              right={
                <span className="today__right">
                  <DueChip task={task} />
                  <Badge variant="brand" className="num">
                    +{task.xp} XP
                  </Badge>
                </span>
              }
            />
          ))}
        </Rows>
      )}

      <div className="today__streak">
        <Badge variant={data.streak_days ? 'ok' : 'mute'} className="num">
          Стрик: {data.streak_days ?? 0}
        </Badge>
        <span className="today__phrase">{data.streak_phrase}</span>
      </div>
    </section>
  )
}
