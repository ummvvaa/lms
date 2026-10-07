/**
 * Расписание ученика: своя неделя со своей подгруппой и потоком,
 * домашние задания недели (со ссылкой на сдачу в LMS), замены и отмены,
 * ближайшие СОР и СОЧ. Ярлыков и чужих учеников здесь нет.
 */
import { useNavigate } from 'react-router'
import { useAcadLessons, useAcadMeta, type AcadLesson } from '../../api/academics'
import { Row, Rows } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import { dateWords, useWeekStart, WeekGrid, WeekNav, weekStart } from './shared'
import { WeekHomework } from '../homework/LessonHomeworkRow'

export default function StudentSchedule() {
  const navigate = useNavigate()
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

  if (data.lessons.length === 0 && !start)
    return (
      <div>
        <ScreenHead title={t('Расписание')} />
        <div className="acad__cols">
          <div className="acad__stack">
            <DataCard title={t('Расписание ещё не составлено')} empty={t('его ведут Кымбат и администратор')} />
          </div>
        </div>
      </div>
    )

  return (
    <div>
      <ScreenHead title={t('Расписание')} subtitle={t('Неделя {from} — {to}', { from: dateWords(from), to: dateWords(data.to) })} />
      <div className="wknav">
        <div className="wknav__group">
          <Chip tone="info">{t('подгруппа')}</Chip>
          <Chip tone="accent">{t('поток')}</Chip>
          <Chip tone="warn">{t('замена или перенос')}</Chip>
        </div>
        <WeekNav start={from} today={today} onChange={setStart} />
      </div>
      <WeekGrid week={data} perspective="student" onOpen={open} />
      <div className="acad__cols acad__cols--even">
        <div className="acad__stack">
          <WeekHomework lessons={data.lessons} />
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
        </div>
        <div className="acad__stack">
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
