/**
 * Главная ученика в новом языке.
 *
 * На главной — то, что нужно сегодня (решение владельца, 07.10.2026): слева
 * уроки по звонкам, ДЗ к сдаче, задачи с галочкой, готовность к подаче;
 * справа ближайшие даты и незакрытые места. Баллы, документы, вузы, эссе
 * и подготовка — в своих разделах: каждая карточка в одном месте.
 * Цветных полотен и карусели нет: пояснение — строкой, кнопка — в строке.
 *
 * Внутренних ярлыков здесь нет — их не отдаёт даже API (инвариант №7).
 */
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useMyLessons } from '../../api/academics'
import { useMyHomework } from '../../api/homework'
import { useCalendar, useGameState, useHomeCues, useMyProfile, useMyTasks, useTaskStatus } from '../../api/hooks'
import { shortDate } from '../../components/CalendarCard'
import { Row, Rows, ShowAll } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Checkbox } from '../../components/ui/checkbox'
import Progress from '../../components/Progress'
import { t, tk, tn } from '../../i18n'
import { todayAlmaty } from '../../lib/dates'
import { MarkChip } from '../academics/shared'
import { CabinetBoard } from './cabinet'
import { formatDate, formatDateTime } from '../../lib/format'
import './student.css'


const MARK_WORDS: Record<string, string> = {
  present: tk('был'),
  absent: tk('не был'),
  late: tk('опоздал'),
  excused: tk('уважительная'),
}

/** Уроки сегодня по звонкам: предмет, кабинет, учитель, моя отметка. */
function LessonsToday() {
  const navigate = useNavigate()
  const { data } = useMyLessons(todayAlmaty())
  if (!data) return null
  const rows = data.lessons
  const now = data.now_slot
  return (
    <DataCard
      title={t('Уроки сегодня')}
      count={rows.length || undefined}
      note={now ? t('идёт {slot} урок', { slot: now }) : undefined}
      empty={rows.length === 0 && t('уроков сегодня нет')}
      right={
        <Button variant="link" size="sm" onClick={() => navigate('/schedule')}>
          {t('Расписание')}
        </Button>
      }
    >
      <Rows>
        {rows.map((lesson) => (
          <Row
            key={lesson.id}
            lead={<b className="num stu__slot">{lesson.slot}</b>}
            title={`${lesson.subject.title}${lesson.kind !== 'fo' && lesson.subject.in_lms ? ` · ${lesson.kind_label}` : ''}`}
            note={[lesson.bell, lesson.room, lesson.actual_teacher?.short ?? ''].filter(Boolean).join(' · ')}
            right={
              !lesson.is_live ? (
                <Chip tone="warn" size="sm">
                  {lesson.status_title}
                </Chip>
              ) : lesson.mine?.mark ? (
                <MarkChip mark={lesson.mine.mark} words={MARK_WORDS} size="sm" lateBy={lesson.mine.late_by} lateAsAbsent={lesson.mine.late_as_absent} />
              ) : lesson.slot === now ? (
                <Chip tone="accent" size="sm">
                  {t('сейчас')}
                </Chip>
              ) : undefined
            }
            to={lesson.subject.in_lms ? `/lessons/${lesson.id}` : undefined}
          />
        ))}
      </Rows>
    </DataCard>
  )
}

/** ДЗ, которые нужно сдать в LMS: ближайший срок сверху, открываются экраном сдачи. */
function HomeworkDue() {
  const navigate = useNavigate()
  const { data } = useMyHomework()
  if (!data) return null
  const rows = data.items.filter((item) => item.state === 'todo').sort((a, b) => (a.due_at ?? '9999').localeCompare(b.due_at ?? '9999'))
  return (
    <DataCard
      title={t('ДЗ к сдаче')}
      count={rows.length || undefined}
      empty={rows.length === 0 && t('сдавать сейчас нечего')}
      right={
        <Button variant="link" size="sm" onClick={() => navigate('/homework')}>
          {t('Все')}
        </Button>
      }
    >
      <Rows>
        <ShowAll>
          {rows.map((item) => (
            <Row
              key={item.id}
              icon="homework"
              title={item.lesson.subject}
              note={item.due_at ? t('до {when}', { when: formatDateTime(item.due_at) }) : t('без срока')}
              right={
                item.past_due ? (
                  <Chip tone="bad" size="sm">
                    {t('срок прошёл')}
                  </Chip>
                ) : undefined
              }
              to={`/homework/${item.id}`}
            />
          ))}
        </ShowAll>
      </Rows>
    </DataCard>
  )
}

/**
 * Задачи — полный список вместо раздела «Роадмап» (решение владельца, 07.10.2026):
 * открытые задачи по сроку, ближайшие сверху, длинный список сворачивается.
 * Галочка закрывает задачу; XP за действие начисляет сервер.
 */
function TasksBlock() {
  const tasks = useMyTasks()
  const game = useGameState()
  const move = useTaskStatus()
  const today = todayAlmaty()
  if (!tasks.data) return null
  const open = tasks.data
    .filter((task) => task.status !== 'done')
    .sort((a, b) => (a.due_date_effective ?? '9999').localeCompare(b.due_date_effective ?? '9999'))
  return (
    <DataCard
      title={t('Задачи')}
      count={open.length || undefined}
      note={game.data?.streak_phrase || undefined}
      empty={open.length === 0 && t('открытых задач нет: их ставят куратор и школа, дедлайны вузов добавляются сами')}
    >
      <Rows>
        <ShowAll>
          {open.map((task) => {
            const due = task.due_date_effective
            return (
              <Row
                key={task.id}
                lead={
                  <Checkbox
                    aria-label={task.title}
                    checked={false}
                    disabled={move.isPending}
                    onCheckedChange={() =>
                      move.mutate({ id: task.id, status: 'done' }, { onSuccess: () => toast.success(t('Задача выполнена')), onError: (error) => toast.error(error.message) })
                    }
                  />
                }
                title={task.title}
                note={[task.university_name ?? '', due ? (due === today ? t('сегодня') : t('до {date}', { date: formatDate(due) })) : t('без срока')].filter(Boolean).join(' · ')}
                right={
                  due !== null && due < today ? (
                    <Chip tone="bad" size="sm">
                      {t('просрочена')}
                    </Chip>
                  ) : undefined
                }
              />
            )
          })}
        </ShowAll>
      </Rows>
    </DataCard>
  )
}

/** Готовность к подаче по доменам: домен без данных подписан, а не спрятан. */
function ReadinessBlock() {
  const { data } = useMyProfile()
  const readiness = data?.readiness
  if (!readiness) return null
  const rows = [
    ...readiness.parts.map((part) => ({ code: part.code, title: part.title, value: part.value as number | null })),
    ...readiness.skipped.map((part) => ({ code: part.code, title: part.title, value: null as number | null })),
  ]
  return (
    <DataCard
      title={t('Готовность к подаче')}
      note={readiness.weakest_title ? t('Больше всего сейчас даст: {block}', { block: readiness.weakest_title }) : t('Из чего складывается ваш процент')}
      right={<b className="num t-value">{readiness.score}%</b>}
      empty={rows.length === 0 && t('данных пока нет — профиль ещё заполняется')}
    >
      <Rows>
        {rows.map((row) => (
          <Row
            key={row.code}
            title={row.title}
            note={row.value === null ? t('данных пока нет') : undefined}
            right={row.value === null ? undefined : <span className="prep__rowbar"><Progress percent={row.value} tone={row.code === readiness.weakest ? 'accent' : 'good'} /></span>}
          />
        ))}
      </Rows>
      {readiness.skipped.length > 0 && <p className="t-note">{t('Блоки без данных в процент не входят — он считается по тем, что заполнены.')}</p>}
    </DataCard>
  )
}

export default function StudentHome() {
  const navigate = useNavigate()
  const profile = useMyProfile()
  const calendar = useCalendar()
  const cues = useHomeCues()

  if (profile.isLoading) return <Loading kind="cards" />
  if (profile.error) return <ErrorNote error={profile.error} />
  if (!profile.data) return null

  const nearest = calendar.data?.nearest ?? null
  const today = calendar.data?.today ?? todayAlmaty()
  const upcoming = (calendar.data?.events ?? []).filter((event) => event.date >= today).slice(0, 6)
  const cueRows = cues.data?.cues ?? []

  return (
    <div>
      <ScreenHead
        title={t('Главная')}
        subtitle={
          nearest
            ? nearest.days_left === 0
              ? t('{title} — сегодня', { title: nearest.title })
              : tn(
                  nearest.days_left,
                  'До ближайшего дедлайна {n} день: {title}|До ближайшего дедлайна {n} дня: {title}|До ближайшего дедлайна {n} дней: {title}',
                  { title: nearest.title },
                )
            : undefined
        }
      />

      <CabinetBoard
        cards={[
          { key: 'lessons', column: 'main', rows: 6, node: <LessonsToday /> },
          { key: 'homework', column: 'main', rows: 4, node: <HomeworkDue /> },
          { key: 'tasks', column: 'main', rows: 5, node: <TasksBlock /> },
          { key: 'readiness', column: 'main', rows: 5, node: <ReadinessBlock /> },
          {
            key: 'nearest',
            column: 'aside',
            rows: upcoming.length,
            folded: upcoming.length === 0,
            node: (
              <DataCard
                title={t('Ближайшее')}
                empty={upcoming.length === 0 && t('впереди пока пусто')}
                right={
                  <Button variant="link" size="sm" onClick={() => navigate('/calendar')}>
                    {t('Календарь')}
                  </Button>
                }
              >
                <Rows>
                  <ShowAll>
                    {upcoming.map((event, index) => (
                      <Row
                        key={`${event.date}-${index}`}
                        lead={<span className="stu__when num">{shortDate(event.date, today)}</span>}
                        title={event.title}
                        note={event.kind_title}
                        right={event.pending ? <Chip size="sm">{t('ждёт проверки')}</Chip> : undefined}
                        to={event.link}
                      />
                    ))}
                  </ShowAll>
                </Rows>
              </DataCard>
            ),
          },
          {
            key: 'cues',
            column: 'aside',
            rows: cueRows.length,
            folded: cueRows.length === 0,
            node: (
              <DataCard title={t('Что закрыть')} empty={cueRows.length === 0 && t('незакрытых мест нет')}>
                <Rows>
                  {cueRows.map((cue) => (
                    <Row
                      key={cue.code}
                      icon="bulb"
                      tone="accent"
                      title={t(cue.title)}
                      note={t(cue.note)}
                      acts={
                        <Button variant="secondary" size="sm" onClick={() => navigate(cue.path)}>
                          {t(cue.action)}
                        </Button>
                      }
                    />
                  ))}
                </Rows>
              </DataCard>
            ),
          },
        ]}
      />
    </div>
  )
}
