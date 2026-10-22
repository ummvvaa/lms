/**
 * Расписание ученика: своя неделя со своей подгруппой и потоком,
 * домашние задания недели (со ссылкой на сдачу в LMS), замены и отмены,
 * ближайшие СОР и СОЧ. Ярлыков и чужих учеников здесь нет.
 *
 * Раскладка по макету: неделя стрелками в шапке, под ней — главная полоса
 * «сейчас / дальше» с бегущим светом, ниже неделя одной карточкой с ключом
 * цветов; задания, СОР и СОЧ и изменения — двумя колонками под ней.
 */
import { useNavigate } from 'react-router'
import { useAcadLessons, useAcadMeta, type AcadLesson } from '../../api/academics'
import { useAuth } from '../../auth/AuthContext'
import { Row, Rows } from '../../components/patterns'
import { Bar, Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import { dateWords, useWeekStart, WeekGrid, WeekNav, weekStart } from './shared'
import { WeekHomework } from '../homework/LessonHomeworkRow'

/** Урок одной строкой: предмет, время начала, кабинет. */
function lessonLine(lesson: AcadLesson, today: string): string {
  const when = lesson.date === today ? '' : `${lesson.weekday}, ${dateWords(lesson.date)}`
  return [lesson.subject.title, when, lesson.starts || t('{slot} урок', { slot: lesson.slot }), lesson.room].filter(Boolean).join(' · ')
}

/**
 * Полоса «сейчас / дальше»: идущий урок и следующий за ним по звонкам,
 * полоса — сколько уроков сегодня уже позади. Всё из уроков недели на экране.
 */
function NowStrip({ lessons, today }: { lessons: AcadLesson[]; today: string }) {
  const live = lessons.filter((lesson) => lesson.is_live).sort((a, b) => a.date.localeCompare(b.date) || a.slot - b.slot)
  const todays = live.filter((lesson) => lesson.date === today)
  const now = todays.find((lesson) => lesson.state === 'now')
  const next = live.find((lesson) => lesson.date > today || (lesson.date === today && lesson.state === 'future'))
  if (!now && !next) return null
  const done = todays.filter((lesson) => lesson.state === 'past').length
  return (
    <section className="card card-pad card--beam stusch__now">
      <Chip tone="accent">{now ? t('сейчас') : t('дальше')}</Chip>
      <span className="stusch__now-what">{lessonLine(now ?? next!, today)}</span>
      {now && next && <span className="stusch__now-next">{t('Дальше: {lesson}', { lesson: lessonLine(next, today) })}</span>}
      {todays.length > 0 && (
        <>
          <div className="stusch__now-bar">
            <Bar percent={(done / todays.length) * 100} />
          </div>
          <span className="stusch__now-count num">{t('уроков сегодня: {done} из {total}', { done, total: todays.length })}</span>
        </>
      )}
    </section>
  )
}

export default function StudentSchedule() {
  const navigate = useNavigate()
  const { me } = useAuth()
  const meta = useAcadMeta()
  const today = meta.data?.today ?? ''
  const [start, setStart] = useWeekStart()
  const from = start || (today ? weekStart(today) : '')
  const week = useAcadLessons({ from }, Boolean(from))
  if (meta.isLoading || (week.isLoading && !week.data)) return <Loading kind="cards" />
  if (week.error) return <ErrorNote error={week.error} />
  if (!week.data) return null
  const data = week.data
  const changes = data.lessons.filter((lesson) => lesson.status !== 'planned' || lesson.substitute)
  const assessments = data.lessons.filter((lesson) => lesson.is_live && lesson.kind !== 'fo' && lesson.subject.in_lms).sort((a, b) => a.date.localeCompare(b.date))
  const open = (lesson: AcadLesson) => navigate(`/lessons/${lesson.id}`)
  const subtitle = [me?.group, t('весь день: предметы LMS и остальные уроки')].filter(Boolean).join(' · ')

  if (data.lessons.length === 0 && !start)
    return (
      <div className="lay-screen stusch">
        <ScreenHead title={t('Расписание')} />
        <DataCard title={t('Расписание ещё не составлено')} empty={t('его ведут Кымбат и администратор')} />
      </div>
    )

  return (
    <div className="lay-screen stusch">
      <ScreenHead title={t('Расписание')} subtitle={subtitle} actions={<WeekNav start={from} today={today} onChange={setStart} />} />
      <NowStrip lessons={data.lessons} today={today} />
      <section className="card card-pad stusch__week">
        <WeekGrid week={data} perspective="student" onOpen={open} />
        <div className="stusch__legend">
          <Chip tone="info">{t('подгруппа')}</Chip>
          <Chip tone="accent">{t('поток')}</Chip>
          <Chip tone="warn">{t('замена или перенос')}</Chip>
        </div>
      </section>
      <div className="lay-2 stusch__lists">
        <WeekHomework lessons={data.lessons} />
        <div className="lay-stack">
          <DataCard title={t('Ближайшие СОР и СОЧ')} count={assessments.length || undefined} empty={assessments.length === 0 && t('на этой неделе нет')}>
            <Rows>
              {assessments.map((lesson) => (
                <Row
                  key={lesson.id}
                  icon="target"
                  tone="info"
                  title={`${lesson.kind_label} · ${lesson.subject.title}`}
                  note={[`${lesson.weekday}, ${dateWords(lesson.date)}`, t('{slot} урок', { slot: lesson.slot }), lesson.topic].filter(Boolean).join(' · ')}
                  to={lesson.subject.in_lms ? `/lessons/${lesson.id}` : undefined}
                />
              ))}
            </Rows>
          </DataCard>
          <DataCard title={t('Изменения на неделе')} count={changes.length || undefined} empty={changes.length === 0 && t('всё по плану')}>
            <Rows>
              {changes.map((lesson) => (
                <Row
                  key={lesson.id}
                  icon="refresh"
                  tone="warn"
                  title={`${lesson.subject.short_title} · ${lesson.weekday}, ${dateWords(lesson.date)}, ${t('{slot} урок', { slot: lesson.slot })}`}
                  note={`${lesson.substitute ? `${t('замена:')} ${lesson.substitute.short}` : lesson.status_title}${lesson.reason ? ` · ${lesson.reason}` : ''}`}
                  to={lesson.subject.in_lms ? `/lessons/${lesson.id}` : undefined}
                />
              ))}
            </Rows>
          </DataCard>
        </div>
      </div>
    </div>
  )
}
