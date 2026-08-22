/**
 * XP, стрик и «задания на сегодня» на дашборде ученика.
 *
 * Никаких рейтингов и сравнения с другими: в контексте поступления это
 * вредно. Формулировки поддерживающие — ученику с нулевым стриком система
 * не сообщает, что он всё потерял, а предлагает начать.
 */
import { useGameState, useTaskStatus, type TodayTask } from '../api/hooks'
import { Bar } from './ui'

const PRIORITY_TITLE: Record<string, string> = { high: 'важно', medium: 'обычное', low: 'не срочно' }

function DueChip({ task }: { task: TodayTask }) {
  if (task.days_left === null) return null
  if (task.days_left < 0) return <span className="chip chip-warn num">срок прошёл</span>
  if (task.days_left <= 7) return <span className="chip chip-warn num">{task.days_left} дн.</span>
  return <span className="chip chip-mute num">{task.days_left} дн.</span>
}

export default function TodayPanel() {
  const { data, isLoading } = useGameState()
  const move = useTaskStatus()

  if (isLoading || !data) return null

  return (
    <div className="split today">
      <div className="card card-pad">
        <span className="eyebrow">Задания на сегодня</span>
        {data.today.length === 0 && (
          <p className="muted today__empty">
            Сейчас задач нет. Загляните в каталог — там видно, куда вы проходите уже сейчас.
          </p>
        )}
        <div className="today__list">
          {data.today.map((task) => (
            <div key={task.id} className="today__task">
              <label className="today__check">
                <input
                  type="checkbox"
                  checked={task.status === 'done'}
                  disabled={move.isPending}
                  onChange={() => move.mutate({ id: task.id, status: 'done' })}
                />
                <span>
                  <b className="today__title">{task.title}</b>
                  <span className="muted today__meta">
                    {PRIORITY_TITLE[task.priority] ?? task.priority}
                    {task.university_name ? ` · ${task.university_name}` : ''}
                  </span>
                </span>
              </label>
              <span className="today__right">
                <DueChip task={task} />
                <span className="chip chip-brand num">+{task.xp} XP</span>
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="card card-pad">
        <span className="eyebrow">Ваш прогресс</span>
        <div className="today__level">
          <b className="num today__xp">{data.xp}</b>
          <span className="muted"> XP · уровень {data.level}</span>
        </div>
        <Bar percent={(data.level_progress / data.level_step) * 100} />
        <p className="muted today__meta">До следующего уровня — {data.level_step - data.level_progress} XP</p>

        <div className="today__streak">
          <span className={`chip ${data.streak_days ? 'chip-ok' : 'chip-mute'} num`}>
            {data.streak_days ? `🔥 ${data.streak_days}` : '🔥 0'}
          </span>
          <span className="today__phrase">{data.streak_phrase}</span>
        </div>

        {data.recent.length > 0 && (
          <div className="today__recent">
            <span className="eyebrow">Последнее</span>
            {data.recent.slice(0, 4).map((event, i) => (
              <div key={i} className="row-between today__event">
                <span className="muted">{event.note || event.kind_title}</span>
                <b className="num">+{event.amount}</b>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
