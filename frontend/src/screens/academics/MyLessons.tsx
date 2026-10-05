/**
 * «Мои уроки» у директора, который ведёт уроки (решение владельца, 29.09.2026):
 * математику ведёт директор талантов. Роль у учётки одна, поэтому кабинета
 * учителя целиком у него нет — только своя неделя, а урок открывается
 * и отмечается как у учителя. Сервер отдаёт ему только его уроки.
 */
import { useNavigate } from 'react-router'
import { useAcadLessons, useAcadMeta } from '../../api/academics'
import { Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import { useWeekStart, WeekGrid, WeekNav, weekStart } from './shared'

export default function MyLessons() {
  const navigate = useNavigate()
  const meta = useAcadMeta()
  const today = meta.data?.today ?? ''
  const [start, setStart] = useWeekStart()
  const from = start || (today ? weekStart(today) : '')
  const week = useAcadLessons({ from }, Boolean(from))

  if (meta.isLoading || week.isLoading) return <Loading kind="cards" />
  if (week.error) return <ErrorNote error={week.error} />
  if (!week.data) return null

  return (
    <div>
      <ScreenHead title={t('Мои уроки')} />
      <div className="wknav">
        <div className="wknav__group">
          <Chip tone="info">{t('нажмите на урок — откроется отметка')}</Chip>
        </div>
        <WeekNav start={from} today={today} onChange={setStart} />
      </div>
      {week.data.lessons.length === 0 ? (
        <DataCard title={t('Уроков на этой неделе нет')} empty={t('ваши уроки появятся здесь')} />
      ) : (
        <WeekGrid
          week={week.data}
          perspective="teacher"
          onOpen={(lesson) => navigate(`/lessons/${lesson.id}`)}
          unmarkedIds={week.data.lessons.filter((lesson) => lesson.is_live && lesson.state === 'past' && !lesson.marked).map((lesson) => lesson.id)}
        />
      )}
    </div>
  )
}
