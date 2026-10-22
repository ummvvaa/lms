/**
 * Расписание групп куратора: неделя по группе, подгруппы рядом, замены
 * и отмены, кто ведёт у группы. Нажатие на урок — факты и кто отсутствовал,
 * неотмеченный урок можно напомнить учителю.
 */
import { useNavigate } from 'react-router'
import { useAcadLessons, useAcadMeta, type AcadLesson } from '../../api/academics'
import { Row, Rows, ShowAll } from '../../components/patterns'
import { Bar, Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import GroupSwitch from '../curator/GroupSwitch'
import { useGroup, useMyGroups } from '../curator/state'
import { dateWords, useWeekStart, WeekGrid, WeekNav, weekStart } from './shared'

/**
 * Полоса урока группы: идущий или следующий урок недели — предмет, учитель,
 * кабинет; полоса — сколько уроков сегодня позади, чип — сколько прошедших
 * сегодня не отмечено учителями. Всё из уроков недели на экране.
 */
function GroupNow({ lessons, today, onOpen }: { lessons: AcadLesson[]; today: string; onOpen: (lesson: AcadLesson) => void }) {
  const live = lessons.filter((lesson) => lesson.is_live).sort((a, b) => a.date.localeCompare(b.date) || a.slot - b.slot)
  const todays = live.filter((lesson) => lesson.date === today)
  const now = todays.find((lesson) => lesson.state === 'now')
  const next = live.find((lesson) => lesson.date > today || (lesson.date === today && lesson.state === 'future'))
  const shown = now ?? next
  if (!shown) return null
  const done = todays.filter((lesson) => lesson.state === 'past').length
  const unmarked = todays.filter((lesson) => lesson.state === 'past' && !lesson.marked).length
  const when = shown.date === today ? t('{slot} урок', { slot: shown.slot }) : `${shown.weekday}, ${dateWords(shown.date)}, ${t('{slot} урок', { slot: shown.slot })}`
  return (
    <section className="card card-pad card--beam stusch__now tsched__now">
      <Chip tone="accent">{now ? t('сейчас') : t('дальше')}</Chip>
      <span className="stusch__now-what">{[when, shown.subject.title, shown.teacher?.full_name ?? '', shown.room].filter(Boolean).join(' · ')}</span>
      {todays.length > 0 && (
        <>
          <div className="stusch__now-bar">
            <Bar percent={(done / todays.length) * 100} />
          </div>
          <span className="stusch__now-count num">{t('уроков сегодня: {done} из {total}', { done, total: todays.length })}</span>
        </>
      )}
      {unmarked > 0 && <Chip tone="warn">{t('не отмечено {count}', { count: unmarked })}</Chip>}
      {shown.subject.in_lms && (
        <Button variant="outline" onClick={() => onOpen(shown)}>
          {t('Открыть')}
        </Button>
      )}
    </section>
  )
}

export default function CuratorSchedule() {
  const navigate = useNavigate()
  const meta = useAcadMeta()
  const today = meta.data?.today ?? ''
  const [group, setGroup] = useGroup()
  const { groups } = useMyGroups()
  const [start, setStart] = useWeekStart()
  const from = start || (today ? weekStart(today) : '')
  const picked = group === 'all' ? (groups[0]?.code ?? '') : group
  const week = useAcadLessons({ from, group: picked }, Boolean(from))
  if (meta.isLoading || (week.isLoading && !week.data)) return <Loading kind="cards" />
  if (week.error) return <ErrorNote error={week.error} />
  if (!week.data) return null
  const data = week.data
  const changes = data.lessons.filter((lesson) => lesson.status !== 'planned' || lesson.substitute)
  const teachers = new Map<number, { name: string; subjects: Set<string> }>()
  for (const lesson of data.lessons) {
    const who = lesson.teacher
    if (!who) continue
    const found = teachers.get(who.id) ?? { name: who.full_name, subjects: new Set<string>() }
    found.subjects.add(`${lesson.subject.short_title}${lesson.cohort.kind !== 'group' ? ` (${lesson.cohort.short_name})` : ''}`)
    teachers.set(who.id, found)
  }
  const open = (lesson: AcadLesson) => navigate(`/lessons/${lesson.id}`)
  if (data.lessons.length === 0 && !start)
    return (
      <div className="lay-screen">
        <ScreenHead title={t('Расписание')} />
        <GroupSwitch groups={groups} value={group} onChange={setGroup} />
        <DataCard title={t('Расписание ещё не составлено')} empty={t('его ведут Кымбат и администратор')} />
      </div>
    )
  return (
    <div className="lay-screen stusch tsched">
      <ScreenHead
        title={t('Расписание')}
        subtitle={t('Неделя группы {group} · все уроки, отметки учителей', { group: picked })}
        actions={
          <>
            <WeekNav start={from} today={today} onChange={setStart} />
            <Button variant="outline" onClick={() => navigate('/attendance')}>
              {t('Посещаемость')}
            </Button>
          </>
        }
      />
      <GroupSwitch groups={groups} value={group === 'all' ? picked : group} onChange={setGroup} single />
      <GroupNow lessons={data.lessons} today={today} onOpen={open} />
      <section className="card card-pad stusch__week">
        <WeekGrid week={data} perspective="group" onOpen={open} unmarkedIds={data.lessons.filter((lesson) => lesson.is_live && lesson.state === 'past' && !lesson.marked).map((lesson) => lesson.id)} />
        <div className="stusch__legend">
          <Chip tone="info">{t('подгруппы рядом')}</Chip>
          <Chip tone="accent">{t('поток с другой группой')}</Chip>
          <Chip tone="warn">{t('замена или перенос')}</Chip>
        </div>
      </section>
      {/* изменений нет — свёрнутая строка во всю ширину, а не растянутая пустая карточка в ряду */}
      <div className={changes.length ? 'lay-2' : 'lay-stack'}>
        <DataCard title={t('Изменения на неделе')} count={changes.length || undefined} empty={changes.length === 0 && t('всё по плану')}>
          <Rows>
            <ShowAll>
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
            </ShowAll>
          </Rows>
        </DataCard>
        <DataCard title={t('Кто ведёт у {group}', { group: picked })} count={teachers.size || undefined} empty={teachers.size === 0 && t('на этой неделе уроков нет')}>
          <Rows>
            <ShowAll>
              {[...teachers.entries()].map(([id, row]) => (
                <Row key={id} avatar={row.name} title={row.name} note={[...row.subjects].join(', ')} />
              ))}
            </ShowAll>
          </Rows>
        </DataCard>
      </div>
    </div>
  )
}
