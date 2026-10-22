/**
 * Главная ученика 11 в новом языке, раскладка по макету.
 *
 * Сверху главная карточка — готовность к подаче по доменам, рядом ближайшие
 * даты; ниже в ряд — что закрыть, задачи с галочкой, ДЗ к сдаче; внизу уроки
 * дня по звонкам. На телефоне — шапка с аватаром, «следующий урок», два числа
 * в ряд, уроки дня списком, дальше остальные карточки столбиком.
 * Баллы, документы, вузы, эссе и подготовка — в своих разделах.
 *
 * Внутренних ярлыков здесь нет — их не отдаёт даже API (инвариант №7).
 */
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useMyLessons } from '../../api/academics'
import { useMyHomework } from '../../api/homework'
import {
  useCalendar,
  useGameState,
  useHomeCues,
  useMyProfile,
  useMyTasks,
  useTaskStatus,
} from '../../api/hooks'
import { useAuth } from '../../auth/AuthContext'
import { Row, Rows, ShowAll } from '../../components/patterns'
import { Bar, Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { Checkbox } from '../../components/ui/checkbox'
import { t, tk, tn } from '../../i18n'
import { todayAlmaty } from '../../lib/dates'
import { usePhone } from '../../phone'
import { MarkChip } from '../academics/shared'
import { formatDate, formatDateTime, formatDayMonth, formatWeekday } from '../../lib/format'
import {
  Columns,
  DateBox,
  findNext,
  firstNameOf,
  NextLessonCard,
  PhoneHead,
  TodayList,
  type TodayLesson,
} from './home-today'
import './student.css'
import './student-home.css'

const MARK_WORDS: Record<string, string> = {
  present: tk('был'),
  absent: tk('не был'),
  late: tk('опоздал'),
  excused: tk('уважительная'),
}

/** ДЗ, которые нужно сдать в LMS: ближайший срок сверху, открываются экраном сдачи. */
function HomeworkDue() {
  const navigate = useNavigate()
  const { data } = useMyHomework()
  if (!data) return null
  const rows = data.items
    .filter((item) => item.state === 'todo')
    .sort((a, b) => (a.due_at ?? '9999').localeCompare(b.due_at ?? '9999'))
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
  // открытых задач нет — карточки нет: пояснение о том, кто их ставит, ничего не даёт
  if (open.length === 0) return null
  return (
    <DataCard
      title={t('Задачи')}
      count={open.length || undefined}
      note={game.data?.streak_phrase || undefined}
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
                      move.mutate(
                        { id: task.id, status: 'done' },
                        {
                          onSuccess: () => toast.success(t('Задача выполнена')),
                          onError: (error) => toast.error(error.message),
                        },
                      )
                    }
                  />
                }
                title={task.title}
                note={[
                  task.university_name ?? '',
                  due
                    ? due === today
                      ? t('сегодня')
                      : t('до {date}', { date: formatDate(due) })
                    : t('без срока'),
                ]
                  .filter(Boolean)
                  .join(' · ')}
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

/** Уроки дня в общем виде: отметка, «сейчас» или отмена — чипом. */
function useTodayLessons(): { lessons: TodayLesson[]; nowSlot: number | null; ready: boolean } {
  const { data } = useMyLessons(todayAlmaty())
  if (!data) return { lessons: [], nowSlot: null, ready: false }
  const now = data.now_slot
  return {
    ready: true,
    nowSlot: now,
    lessons: data.lessons.map((lesson) => ({
      key: String(lesson.id),
      slot: lesson.slot,
      bell: lesson.bell,
      subject: `${lesson.subject.title}${lesson.kind !== 'fo' && lesson.subject.in_lms ? ` · ${lesson.kind_label}` : ''}`,
      meta: [lesson.room, lesson.actual_teacher?.short ?? ''].filter(Boolean).join(' · '),
      chip: !lesson.is_live ? (
        <Chip tone="warn" size="sm">
          {lesson.status_title}
        </Chip>
      ) : lesson.mine?.mark ? (
        <MarkChip
          mark={lesson.mine.mark}
          words={MARK_WORDS}
          size="sm"
          lateBy={lesson.mine.late_by}
          lateAsAbsent={lesson.mine.late_as_absent}
        />
      ) : lesson.slot === now ? (
        <Chip tone="accent" size="sm">
          {t('сейчас')}
        </Chip>
      ) : undefined,
      to: lesson.subject.in_lms ? `/lessons/${lesson.id}` : undefined,
    })),
  }
}

/** Уроки дня по звонкам на ноутбуке: предмет, кабинет, учитель, моя отметка. */
function LessonsToday() {
  const today = useTodayLessons()
  if (!today.ready) return null
  return (
    <TodayList
      title={t('Уроки сегодня')}
      lessons={today.lessons}
      nowSlot={today.nowSlot}
      note={today.nowSlot ? t('идёт {slot} урок', { slot: today.nowSlot }) : undefined}
      empty={t('уроков сегодня нет')}
    />
  )
}

/**
 * Готовность к подаче по доменам: процент крупно, домены полосами.
 * Домен без данных подписан, а не спрятан.
 */
function ReadinessBlock({ className }: { className?: string }) {
  const { data } = useMyProfile()
  const readiness = data?.readiness
  if (!readiness) return null
  const rows = [
    // домены без данных не показываются: пустая строка в разбивке ничего не говорит
    ...readiness.parts.map((part) => ({
      code: part.code,
      title: part.title,
      value: part.value as number | null,
    })),
  ]
  if (rows.length === 0) return null
  return (
    <DataCard
      className={`stuhome__ready${className ? ` ${className}` : ''}`}
      title={t('Готовность к подаче')}
      right={
        readiness.weakest_title ? (
          <Chip tone="accent" size="sm" className="stuhome__readychip">
            {t('Больше всего сейчас даст: {block}', { block: readiness.weakest_title })}
          </Chip>
        ) : undefined
      }
    >
      <div className="stuhome__readybody">
        <b className="num stuhome__score">{readiness.score}%</b>
        <div className="stuhome__bars">
          {rows.map((row) => (
            <div key={row.code} className="stuhome__barrow">
              <span className="stuhome__barname">{row.title}</span>
              <Bar
                percent={row.value ?? 0}
                color={row.code === readiness.weakest ? undefined : 'var(--good)'}
              />
              <span className="num stuhome__barval">{row.value ?? 0}%</span>
            </div>
          ))}
        </div>
      </div>
    </DataCard>
  )
}

export default function StudentHome() {
  const navigate = useNavigate()
  const phone = usePhone()
  const { me } = useAuth()
  const profile = useMyProfile()
  const calendar = useCalendar()
  const cues = useHomeCues()
  // те же запросы, что у карточек ниже: по ним решается, какая карточка пуста
  const tasks = useMyTasks()
  const homework = useMyHomework()
  const today = useTodayLessons()

  if (profile.isLoading) return <Loading kind="cards" />
  if (profile.error) return <ErrorNote error={profile.error} />
  if (!profile.data) return null

  const nearest = calendar.data?.nearest ?? null
  const day = calendar.data?.today ?? todayAlmaty()
  const upcoming = (calendar.data?.events ?? []).filter((event) => event.date >= day).slice(0, 6)
  const cueRows = cues.data?.cues ?? []
  const openTasks = (tasks.data ?? []).filter((task) => task.status !== 'done').length
  const todo = (homework.data?.items ?? []).filter((item) => item.state === 'todo')
  const readiness = profile.data.readiness
  const greeting = t('Привет, {name}', { name: profile.data.first_name || firstNameOf(me?.full_name ?? '') })

  const nearestCard = (
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
              lead={<DateBox iso={event.date} today={day} />}
              title={event.title}
              note={event.kind_title}
              right={event.pending ? <Chip size="sm">{t('ждёт проверки')}</Chip> : undefined}
              to={event.link}
            />
          ))}
        </ShowAll>
      </Rows>
    </DataCard>
  )
  const cuesCard = (
    <DataCard
      title={t('Что закрыть')}
      count={cueRows.length || undefined}
      empty={cueRows.length === 0 && t('незакрытых мест нет')}
    >
      <div className="stuhome__cues">
        {cueRows.map((cue) => (
          <div key={cue.code} className="stuhome__cue">
            <div className="stuhome__cuetext">
              <b>{t(cue.title)}</b>
              <span className="t-note">{t(cue.note)}</span>
            </div>
            <Button variant="secondary" size="sm" onClick={() => navigate(cue.path)}>
              {t(cue.action)}
            </Button>
          </div>
        ))}
      </div>
    </DataCard>
  )
  const lessonsEmpty = t('уроков сегодня нет')

  if (phone)
    return (
      <div className="lay-screen">
        <PhoneHead
          title={greeting}
          line={[`${formatWeekday(day)}, ${formatDayMonth(day)}`, me?.group].filter(Boolean).join(' · ')}
        />
        {today.ready && (
          <NextLessonCard
            lessons={today.lessons}
            nowSlot={today.nowSlot}
            empty={lessonsEmpty}
            tiles={false}
          />
        )}
        <div className="stuhome__pair">
          <Kpi
            label={t('ДЗ к сдаче')}
            value={String(todo.length)}
            chip={todo.some((item) => item.past_due) ? { label: t('срок прошёл'), tone: 'bad' } : undefined}
            to="/homework"
          />
          {readiness && <Kpi label={t('Готовность к подаче')} value={`${readiness.score}%`} />}
        </div>
        {/* без звонков главный урок не выбрать — уроки дня уже строками в карточке выше */}
        {today.ready && (findNext(today.lessons, today.nowSlot)?.index ?? -1) >= 0 && (
          <TodayList
            title={t('Сегодня')}
            lessons={today.lessons}
            nowSlot={today.nowSlot}
            empty={lessonsEmpty}
          />
        )}
        {nearestCard}
        {cuesCard}
        {openTasks > 0 && <TasksBlock />}
        <ReadinessBlock />
        <HomeworkDue />
      </div>
    )

  return (
    <div className="lay-screen">
      <ScreenHead
        title={greeting}
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
        actions={
          <Button variant="outline" onClick={() => navigate('/schedule')}>
            {t('Расписание')}
          </Button>
        }
      />

      {/* две колонки: готовность и «Что закрыть» слева, короткие карточки стопкой справа —
          столбцы кончаются вровень, без пустоты внутри карточек ряда */}
      <Columns
        main={[
          {
            key: 'ready',
            folded: !readiness,
            node: readiness ? <ReadinessBlock className="card--beam" /> : null,
          },
          { key: 'cues', folded: cueRows.length === 0, node: cuesCard },
        ]}
        aside={[
          { key: 'nearest', folded: upcoming.length === 0, node: nearestCard },
          { key: 'homework', folded: todo.length === 0, node: <HomeworkDue /> },
          ...(openTasks > 0 ? [{ key: 'tasks', folded: false, node: <TasksBlock /> }] : []),
        ]}
      />

      <LessonsToday />
    </div>
  )
}
