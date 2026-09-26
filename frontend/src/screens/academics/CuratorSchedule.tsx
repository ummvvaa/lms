/**
 * Расписание групп куратора: неделя по группе, подгруппы рядом, замены
 * и отмены, кто ведёт у группы. Нажатие на урок — факты и кто отсутствовал,
 * неотмеченный урок можно напомнить учителю.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAcadLessons, useAcadMeta, type AcadLesson } from '../../api/academics'
import { Row, Rows } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import GroupSwitch from '../curator/GroupSwitch'
import { useGroup, useMyGroups } from '../curator/state'
import { dateWords, WeekGrid, WeekNav, weekStart } from './shared'

export default function CuratorSchedule() {
  const navigate = useNavigate()
  const meta = useAcadMeta()
  const today = meta.data?.today ?? ''
  const [group, setGroup] = useGroup()
  const { groups } = useMyGroups()
  const [start, setStart] = useState('')
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
      <div>
        <ScreenHead title={t('Расписание')} />
        <GroupSwitch groups={groups} value={group} onChange={setGroup} />
        <div className="acad__cols">
          <div className="acad__stack">
            <DataCard title={t('Расписание ещё не составлено')} empty={t('его ведут Кымбат и администратор')} />
          </div>
          <div className="acad__stack">
            <DataCard title={t('Что здесь будет')}>
              <p className="acad__note">{t('Уроки ваших групп по дням, подгруппы рядом, замены и отмены. Нажмите на урок — увидите, кто отсутствовал.')}</p>
            </DataCard>
          </div>
        </div>
      </div>
    )
  return (
    <div>
      <ScreenHead
        title={t('Расписание')}
        actions={
          <Button variant="outline" size="sm" onClick={() => navigate('/attendance')}>
            {t('Посещаемость')}
          </Button>
        }
      />
      <GroupSwitch groups={groups} value={group === 'all' ? picked : group} onChange={setGroup} />
      <div className="wknav">
        <div className="wknav__group">
          <Chip tone="info">{t('подгруппы рядом')}</Chip>
          <Chip tone="accent">{t('поток с другой группой')}</Chip>
          <Chip tone="warn">{t('замена или перенос')}</Chip>
        </div>
        <WeekNav start={from} today={today} onChange={setStart} />
      </div>
      <WeekGrid week={data} perspective="group" onOpen={open} unmarkedIds={data.lessons.filter((lesson) => lesson.is_live && lesson.state === 'past' && !lesson.marked).map((lesson) => lesson.id)} />
      <div className="acad__cols acad__cols--even">
        <div className="acad__stack">
          <DataCard title={t('Изменения на неделе')} count={changes.length || undefined} empty={changes.length === 0 && t('всё по плану')}>
            <Rows>
              {changes.map((lesson) => (
                <Row
                  key={lesson.id}
                  icon="refresh"
                  tone="warn"
                  title={`${lesson.subject.short_title} · ${lesson.weekday}, ${dateWords(lesson.date)}, ${lesson.slot} ${t('урок')}`}
                  note={`${lesson.substitute ? `${t('замена:')} ${lesson.substitute.short}` : lesson.status_title}${lesson.reason ? ` · ${lesson.reason}` : ''}`}
                  to={`/lessons/${lesson.id}`}
                />
              ))}
            </Rows>
          </DataCard>
        </div>
        <div className="acad__stack">
          <DataCard title={`${t('Кто ведёт у')} ${picked}`} count={teachers.size || undefined} empty={teachers.size === 0 && t('на этой неделе уроков нет')}>
            <Rows>
              {[...teachers.entries()].map(([id, row]) => (
                <Row key={id} avatar={row.name} title={row.name} note={[...row.subjects].join(', ')} />
              ))}
            </Rows>
          </DataCard>
        </div>
      </div>
    </div>
  )
}
