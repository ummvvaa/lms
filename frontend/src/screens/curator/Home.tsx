/**
 * Главная куратора (фаза 61).
 *
 * Слева работа: очередь и задачи на сегодня. Справа то, на что куратор
 * оглядывается: корзины «кого дёргать» и последние действия по своим
 * группам. Сверху четыре числа-кнопки — каждое ведёт туда, где с ним
 * что-то делают, а не просто светится.
 *
 * Все числа считает сервер (`students.attention`): главная, чипы над
 * таблицей и карточка обязаны показывать одно и то же.
 */
import { useNavigate } from 'react-router-dom'
import { useCuratorOverview } from '../../api/hooks'
import { QueueRow } from '../../components/StudentQueue'
import { Row, Rows, StatCard, StatRow } from '../../components/patterns'
import { counted, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import type { IconName } from '../../layout/icons'
import { t } from '../../i18n'
import GroupSwitch from './GroupSwitch'
import TaskDialog from './TaskDialog'
import { useGroup } from './state'
import './curator.css'

/** Иконка числа-кнопки по коду: список закрытый, как и сами числа. */
const ICONS: Record<string, IconName> = {
  queue: 'bulb',
  nogoal: 'target',
  nomock: 'clock',
  overdue: 'alert',
}

type Tone = 'brand' | 'teal' | 'indigo' | 'ok' | 'warn' | 'risk' | 'mute'

const dateOf = (value: string) => new Date(value).toLocaleDateString('ru')

export default function CuratorHome() {
  const [group, setGroup] = useGroup()
  const navigate = useNavigate()
  const { data, isLoading, error } = useCuratorOverview(group)

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const groups = data.groups
  const scope =
    group === 'all'
      ? `${counted(groups.length, ['группа', 'группы', 'групп'])}, ${counted(data.students_total, ['ученик', 'ученика', 'учеников'])}`
      : `${group} · ${counted(data.students_total, ['ученик', 'ученика', 'учеников'])}`

  return (
    <div>
      <ScreenHead
        title={t(data.title)}
        subtitle={`${scope} · ${t('в очереди')} ${data.queue_total} · ${t('задач с дедлайном')} ${data.tasks_due}`}
        actions={<TaskDialog groups={groups} defaultGroup={group} />}
      />
      <GroupSwitch groups={groups} value={group} onChange={setGroup} />

      <StatRow>
        {data.numbers.map((number) => (
          <StatCard
            key={number.code}
            icon={ICONS[number.code] ?? 'layers'}
            tone={number.tone as Tone}
            label={t(number.label)}
            value={number.value}
            onClick={() => navigate(number.to)}
          />
        ))}
      </StatRow>

      <div className="cgrid">
        <div className="cgrid__main">
          <DataCard
            title={t('Очередь подтверждений')}
            note={t('Сначала то, что сильнее расходится с текущим')}
            accent="brand"
            right={
              <Button variant="outline" size="sm" onClick={() => navigate('/queue')}>
                {t('Все')} {data.queue_total}
              </Button>
            }
          >
            {data.queue.length === 0 && <p className="muted">{t('Очередь пуста — всё подтверждено')}</p>}
            {data.queue.map((row) => (
              <QueueRow key={row.id} row={row} />
            ))}
          </DataCard>

          <DataCard
            title={t('Задачи на сегодня')}
            note={t('Ученик видит их в календаре и закрывает сам')}
            right={
              <Button variant="outline" size="sm" onClick={() => navigate('/tasks')}>
                {t('Все задачи')}
              </Button>
            }
          >
            {data.tasks.length === 0 && <p className="muted">{t('Открытых задач нет')}</p>}
            <Rows>
              {data.tasks.map((task) => (
                <Row
                  key={task.id}
                  icon="checklist"
                  tone={task.is_overdue ? 'risk' : 'mute'}
                  title={task.title}
                  note={`${task.student_name} · ${task.group}`}
                  right={
                    task.due_date ? (
                      <Badge variant={task.is_overdue ? 'risk' : 'mute'}>
                        {task.is_overdue ? t('просрочена') : t('до')} {dateOf(task.due_date)}
                      </Badge>
                    ) : undefined
                  }
                  onOpen={() => navigate(`/students/${task.student}?tab=tasks`)}
                  openLabel={t('Открыть ученика')}
                />
              ))}
            </Rows>
          </DataCard>
        </div>

        <div className="cgrid__side">
          <DataCard title={t('Кого дёргать')} note={t('Клик открывает список этих учеников')}>
            <Rows>
              {data.buckets.map((bucket) => (
                <Row
                  key={bucket.code}
                  icon="person"
                  tone={bucket.tone as Tone}
                  title={t(bucket.title)}
                  note={t(bucket.hint)}
                  right={<b className="num">{bucket.count}</b>}
                  onOpen={() => navigate(`/students?bucket=${bucket.code}`)}
                  openLabel={t('Открыть список')}
                />
              ))}
            </Rows>
          </DataCard>

          <DataCard title={t('Последние действия')} note={t('По вашим группам — вы и владельцы доменов')}>
            {data.journal.length === 0 && <p className="muted">{t('Пока ничего не менялось')}</p>}
            <Rows>
              {data.journal.map((entry) => (
                <Row
                  key={entry.id}
                  icon="clock"
                  title={`${entry.what}: ${entry.value}`}
                  note={
                    <>
                      {entry.who}
                      {entry.student_group ? ` · ${entry.student_group}` : ''}
                      {/* время своим элементом: эталоны раскладки маскируют
                          именно его — оно настоящее и меняется каждым прогоном */}
                      <span className="squeue__when"> · {new Date(entry.at).toLocaleString('ru')}</span>
                    </>
                  }
                  muted
                />
              ))}
            </Rows>
          </DataCard>
        </div>
      </div>
    </div>
  )
}
