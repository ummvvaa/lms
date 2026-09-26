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
import { Row, Rows, ShowAll, StatRow } from '../../components/patterns'
import { counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { CabinetBoard } from '../dashboards/cabinet'
import GroupSwitch from './GroupSwitch'
import TaskDialog from './TaskDialog'
import { useGroup } from './state'
import './curator.css'

const dateOf = (value: string) => new Date(value).toLocaleDateString('ru')

export default function CuratorHome() {
  const [group, setGroup] = useGroup()
  const navigate = useNavigate()
  const { data, isLoading, error } = useCuratorOverview(group)

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const groups = data.groups
  // группа в шапке — та, по которой сервер собрал ответ, а не та, что помнит вкладка (фаза 80)
  const shown = groups.length === 1 ? groups[0].code : data.group
  const students = counted(data.students_total, ['ученик', 'ученика', 'учеников'])
  const scope =
    shown === 'all'
      ? `${counted(groups.length, ['группа', 'группы', 'групп'])}, ${students}`
      : `${shown} · ${students}`

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
          <Kpi
            key={number.code}
            tone={number.tone as Tone}
            label={t(number.label)}
            value={number.value}
            to={number.to}
          />
        ))}
      </StatRow>

      {/* колонки собирает общая раскладка кабинетов: пустая карточка — одна строка
          внизу короткой колонки (фаза 80). Карточки перерисовываются по выбранной
          группе сами: ключ запроса — группа */}
      <CabinetBoard
        cards={[
          {
            key: 'queue',
            column: 'main',
            // строка очереди вдвое выше строки списка: в ней значения и кнопки
            rows: data.queue.length * 2,
            folded: data.queue.length === 0,
            node: (
              <DataCard
                title={t('Очередь подтверждений')}
                note={t('Сначала то, что сильнее расходится с текущим')}
                accent="brand"
                count={data.queue_total}
                empty={data.queue.length === 0 && t('всё подтверждено')}
                right={
                  <Button variant="outline" size="sm" onClick={() => navigate('/queue')}>
                    {t('Все')}
                  </Button>
                }
              >
                {data.queue.map((row) => (
                  <QueueRow key={row.id} row={row} />
                ))}
              </DataCard>
            ),
          },
          {
            key: 'buckets',
            column: 'aside',
            // у корзины подпись в две строки — она выше обычной строки списка
            rows: data.buckets.length * 1.5,
            node: (
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
            ),
          },
          {
            key: 'tasks',
            column: 'main',
            rows: data.tasks.length,
            folded: data.tasks.length === 0,
            narrow: true,
            node: (
              <DataCard
                title={t('Задачи на сегодня')}
                note={t('Ученик видит их в календаре и закрывает сам')}
                empty={data.tasks.length === 0 && t('открытых задач нет')}
                right={
                  <Button variant="outline" size="sm" onClick={() => navigate('/tasks')}>
                    {t('Все задачи')}
                  </Button>
                }
              >
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
            ),
          },
          {
            key: 'journal',
            column: 'aside',
            rows: data.journal.length * 1.5,
            folded: data.journal.length === 0,
            node: (
              <DataCard
                title={t('Последние действия')}
                note={t('По вашим группам — вы и владельцы доменов')}
                empty={data.journal.length === 0 && t('пока ничего не менялось')}
              >
                <Rows>
                  <ShowAll>
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
                  </ShowAll>
                </Rows>
              </DataCard>
            ),
          },
        ]}
      />
    </div>
  )
}
