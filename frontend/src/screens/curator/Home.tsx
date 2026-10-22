/**
 * Главная куратора (фаза 61, учёба — шаг 4 серии).
 *
 * Слева работа: очередь и задачи на сегодня. Справа то, на что куратор
 * оглядывается: сегодня в группах по урокам, кого дёргать, отчёты
 * родителям, последние действия. Сверху четыре числа-кнопки — каждое
 * ведёт туда, где с ним что-то делают, а не просто светится.
 *
 * Все числа считает сервер (`students.attention`, `academics`): главная,
 * чипы над таблицей и карточка обязаны показывать одно и то же.
 */
import { Link, useNavigate } from 'react-router'
import { useCuratorHome } from '../../api/academics'
import { useHomeworkOverview } from '../../api/homework'
import { useCuratorOverview } from '../../api/hooks'
import { QueueRow } from '../../components/StudentQueue'
import { Row, Rows, ShowAll, StatRow } from '../../components/patterns'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { absentWords } from '../academics/shared'
import { CabinetBoard, type BoardCard } from '../dashboards/cabinet'
import GroupSwitch from './GroupSwitch'
import TaskDialog from './TaskDialog'
import { useGroup } from './state'
import { formatDate, formatDateTime } from '../../lib/format'
import './curator.css'
import './curator-layout.css'

const dateOf = (value: string) => formatDate(value)

/** Блоки учёбы на главной: сегодня по группам, кого дёргать по учёбе, отчёты.
 *  `lead` — «Сегодня в группах» главная карточка экрана: у 8–10 очереди нет. */
function useAcademicsCards(group: string, lead: boolean): BoardCard[] {
  const navigate = useNavigate()
  const { data } = useCuratorHome(group)
  // кто не сдаёт ДЗ вовремя — из сдач в LMS, только чтение (30.09.2026)
  const homework = useHomeworkOverview(group === 'all' ? '' : group)
  if (!data) return []
  // пороги «не сдаёт» — настройки школы, приходят с сервера
  const BEHIND_PCT = homework.data?.behind.pct ?? 0
  const BEHIND_MISSED = homework.data?.behind.missed ?? Number.POSITIVE_INFINITY
  const behind = (homework.data?.rows ?? []).filter((row) => (row.pct !== null && row.pct < BEHIND_PCT) || row.missed >= BEHIND_MISSED)
  const today = data.today
  const lessons = today.reduce((sum, row) => sum + row.lessons, 0)
  const trouble = [...data.risk_grade.map((row) => ({ ...row, why: t('двойка в прогнозе') })), ...data.unexcused.map((row) => ({ ...row, why: t('дни без причины') }))]
  const reports = data.reports
  return [
    {
      key: 'today',
      column: 'main',
      // плитки по две в ряд: строка плиток — примерно полторы строки списка
      rows: Math.max(1, Math.ceil(today.length / 2) * 1.5),
      folded: lessons === 0,
      node: (
        <DataCard
          className={lead && lessons > 0 ? 'card--beam' : undefined}
          title={t('Сегодня в группах')}
          empty={lessons === 0 && t('уроков сегодня нет')}
          right={
            <>
              {data.now_slot && (
                <Chip tone="accent" size="sm" className="chome__live">
                  <span className="live-dot" aria-hidden="true" />
                  {t('идёт {slot} урок', { slot: data.now_slot })}
                </Chip>
              )}
              <Button variant="link" size="sm" onClick={() => navigate('/schedule')}>
                {t('Расписание')}
              </Button>
            </>
          }
        >
          <div className="chome__groups">
            {today.map((row) => (
              <Link key={row.group} className="chome__group" to={`/attendance?group=${encodeURIComponent(row.group)}`} aria-label={`${row.group}: ${t('Открыть посещаемость')}`}>
                <span className="chome__mono" aria-hidden="true">
                  {row.group.slice(0, 2)}
                </span>
                <span className="chome__gtext">
                  <b>{`${row.group} · ${counted(row.lessons, 'урок|урока|уроков')}`}</b>
                  <span>{row.now ? t('сейчас {subject}, {room}', { subject: row.now.subject.short_title, room: row.now.room }) : row.absent.length ? absentWords(row.absent) : t('все были')}</span>
                </span>
                {row.unmarked ? (
                  <Chip tone="warn" size="sm">{t('не отмечено {count}', { count: row.unmarked })}</Chip>
                ) : row.absent.length ? (
                  <Chip size="sm">{t('нет {count}', { count: row.absent.length })}</Chip>
                ) : (
                  <Chip tone="good" size="sm">{t('все были')}</Chip>
                )}
              </Link>
            ))}
          </div>
        </DataCard>
      ),
    },
    {
      key: 'academics-trouble',
      column: 'aside',
      rows: trouble.length,
      folded: trouble.length === 0,
      node: (
        <DataCard title={t('Кого дёргать по учёбе')} empty={trouble.length === 0 && t('все справляются')}>
          <Rows>
            <ShowAll>
              {trouble.map((row) => (
                <Row key={`${row.why}-${row.id}`} avatar={row.full_name} tone="warn" title={row.full_name} note={`${row.group} · ${row.why}`} to={`/students/${row.id}?tab=grades`} />
              ))}
            </ShowAll>
          </Rows>
        </DataCard>
      ),
    },
    {
      key: 'homework-behind',
      column: 'aside',
      rows: behind.length,
      folded: behind.length === 0,
      node: (
        <DataCard
          title={t('Не сдают ДЗ вовремя')}
          hint={homework.data ? t('Сдано вовремя меньше {pct} % или не сдано заданий: {missed} и больше', { pct: BEHIND_PCT, missed: BEHIND_MISSED }) : undefined}
          empty={behind.length === 0 && t('все сдают ДЗ вовремя')}
        >
          <Rows>
            <ShowAll>
              {behind.map((row) => (
                <Row
                  key={row.id}
                  avatar={row.full_name}
                  title={row.full_name}
                  note={[row.group, t('вовремя {done} из {total}', { done: row.on_time, total: row.total }), row.missed ? t('не сдано {count}', { count: row.missed }) : ''].filter(Boolean).join(' · ')}
                  right={
                    row.pct !== null ? (
                      <Chip tone={row.pct < BEHIND_PCT ? 'bad' : 'warn'} size="sm" className="num">
                        {`${row.pct} %`}
                      </Chip>
                    ) : undefined
                  }
                  to={`/students/${row.id}?tab=grades`}
                />
              ))}
            </ShowAll>
          </Rows>
        </DataCard>
      ),
    },
    {
      key: 'reports',
      column: 'main',
      rows: 1,
      narrow: true,
      folded: reports === null || reports.total === 0,
      node: (
        <DataCard
          title={t('Отчёты родителям')}
          empty={
            (reports === null || reports.total === 0) &&
            // сервер отдаёт код расписания отчётов: month | quarter; подпись короткая —
            // свёрнутая карточка в узкой колонке на 1440 должна оставаться одной строкой
            (data.cadence === 'quarter' ? t('после закрытия четверти') : t('в конце месяца'))
          }
          right={
            <Button variant="outline" size="sm" onClick={() => navigate('/reports')}>
              {t('Открыть')}
            </Button>
          }
        >
          {reports && reports.total > 0 && (
            <Rows>
              <Row
                icon="doc"
                tone={reports.draft ? 'warn' : reports.sent === reports.total ? 'good' : 'info'}
                title={t(reports.title)}
                note={[
                  reports.draft ? t('черновиков {count}', { count: reports.draft }) : '',
                  reports.checked ? t('проверено {count}', { count: reports.checked }) : '',
                  reports.exported ? t('выгружено {count}', { count: reports.exported }) : '',
                  t('отправлено {sent} из {total}', { sent: reports.sent, total: reports.total }),
                ]
                  .filter(Boolean)
                  .join(' · ')}
                to="/reports"
              />
            </Rows>
          )}
        </DataCard>
      ),
    },
  ]
}

export default function CuratorHome() {
  const [group, setGroup] = useGroup()
  const navigate = useNavigate()
  const { data, isLoading, error } = useCuratorOverview(group)
  // свет — у очереди; у 8–10 и при пустой очереди — у «Сегодня в группах»
  const academics = useAcademicsCards(group, data?.has_admission === false || data?.queue.length === 0)

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const groups = data.groups
  // группа в шапке — та, по которой сервер собрал ответ, а не та, что помнит вкладка (фаза 80)
  const shown = groups.length === 1 ? groups[0].code : data.group
  const students = counted(data.students_total, 'ученик|ученика|учеников')
  const scope =
    shown === 'all'
      ? `${counted(groups.length, 'группа|группы|групп')}, ${students}`
      : `${shown} · ${students}`
  // у выбранных групп без поступления нет очереди, задач плана и чисел
  // поступления: главная 8–10 — про учёбу (`core/parallels.py`)
  const admission = data.has_admission

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t(data.title)}
        subtitle={
          admission
            ? `${scope} · ${t('в очереди {count}', { count: data.queue_total })} · ${t('задач с дедлайном {count}', { count: data.tasks_due })}`
            : scope
        }
        actions={admission ? <TaskDialog groups={groups} defaultGroup={group} /> : undefined}
      />
      <GroupSwitch groups={groups} value={group} onChange={setGroup} />

      {data.numbers.length > 0 && (
        <StatRow>
          {data.numbers.map((number) => (
            <Kpi key={number.code} tone={number.tone as Tone} label={t(number.label)} value={number.value} to={number.to} />
          ))}
        </StatRow>
      )}

      {/* колонки собирает общая раскладка кабинетов: пустая карточка — одна строка
          внизу короткой колонки (фаза 80). Карточки перерисовываются по выбранной
          группе сами: ключ запроса — группа */}
      <CabinetBoard
        cards={([
          {
            key: 'queue',
            column: 'main',
            // строка очереди вдвое выше строки списка: в ней значения и кнопки
            rows: data.queue.length * 2,
            folded: data.queue.length === 0,
            node: (
              <DataCard
                className={data.queue.length ? 'card--beam' : undefined}
                title={t('Очередь подтверждений')}
                count={data.queue_total}
                empty={data.queue.length === 0 && t('всё подтверждено')}
                right={
                  <Button variant="outline" size="sm" onClick={() => navigate('/queue')}>
                    {t('Все')}
                  </Button>
                }
              >
                <div className="cqueue">
                  {data.queue.map((row) => (
                    <QueueRow key={row.id} row={row} person />
                  ))}
                </div>
              </DataCard>
            ),
          },
          ...academics.filter((card) => card.key === 'today'),
          {
            key: 'tasks',
            column: 'aside',
            rows: data.tasks.length,
            folded: data.tasks.length === 0,
            narrow: true,
            node: (
              <DataCard
                title={t('Задачи на сегодня')}
                empty={data.tasks.length === 0 && t('открытых задач нет')}
                right={
                  <Button variant="outline" size="sm" onClick={() => navigate('/tasks')}>
                    {t('Все задачи')}
                  </Button>
                }
              >
                {/* узкая колонка: название сверху, ученик и срок строкой под ним — как в макете;
                    чип справа от названия рвал его по буквам */}
                <div className="chome__tasks">
                  <ShowAll to="/tasks">
                    {data.tasks.map((task) => (
                      <Link key={task.id} className="chome__task" to={`/students/${task.student}?tab=tasks`}>
                        <b>{task.title}</b>
                        <span className="chome__taskline">
                          <span>{`${task.student_name} · ${task.group}`}</span>
                          {task.due_date && (
                            <Chip tone={task.is_overdue ? 'bad' : 'neutral'} size="sm">
                              {task.is_overdue ? t('просрочена') : t('до')} {dateOf(task.due_date)}
                            </Chip>
                          )}
                        </span>
                      </Link>
                    ))}
                  </ShowAll>
                </div>
              </DataCard>
            ),
          },
          {
            key: 'buckets',
            column: 'aside',
            // у корзины подпись в две строки — она выше обычной строки списка
            rows: data.buckets.length * 1.5,
            node: (
              <DataCard title={t('Кого дёргать')}>
                <Rows>
                  {data.buckets.map((bucket) => (
                    <Row
                      key={bucket.code}
                      icon="person"
                      tone={bucket.tone as Tone}
                      title={t(bucket.title)}
                      right={<b className="num">{bucket.count}</b>}
                      onOpen={() => navigate(`/students?bucket=${bucket.code}`)}
                      openLabel={t('Открыть список')}
                    />
                  ))}
                </Rows>
              </DataCard>
            ),
          },
          // учебные сводки без строк не показываются вовсе: свёрнутые строки «все справляются»
          // только удлиняли колонку и ничего не говорили
          ...academics.filter((card) => card.key !== 'today' && !(['academics-trouble', 'homework-behind'].includes(card.key) && card.folded)),
          {
            key: 'journal',
            // у 8–10 нет очереди и задач: широкая колонка короче — журнал встаёт в неё
            column: admission ? 'aside' : 'main',
            rows: Math.min(data.journal.length, 3) * 1.5,
            folded: data.journal.length === 0,
            node: (
              <DataCard
                title={t('Последние действия')}
                empty={data.journal.length === 0 && t('пока ничего не менялось')}
              >
                <Rows>
                  <ShowAll limit={3} to="/journal">
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
                            <span className="squeue__when"> · {formatDateTime(entry.at)}</span>
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
        ] as BoardCard[]).filter((card) => admission || !['queue', 'tasks'].includes(card.key))}
      />
    </div>
  )
}
