/**
 * Группы — отдельный экран директора школы.
 *
 * Раньше это была секция дашборда, до которой надо было доскроллить.
 * Данные те же, что и у дашборда (`/dashboards/behavior/`), запрос общий:
 * TanStack Query отдаёт его из кэша.
 */
import { useDashboard } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import { Bar, Chip, EmptyNote, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import type { BehaviorData } from './data'

export default function Groups() {
  const { data, isLoading, error } = useDashboard<BehaviorData>('behavior')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Группы')}
        hint={t('Здесь появятся учебные группы')}
        what={t('Заведите группы — и по ним пойдёт вся раскладка.')}
        detail={t(
          'У каждой группы видно число учеников, заполненность профилей и сколько человек в зоне риска.',
        )}
      />
    )

  return (
    <div>
      <ScreenHead
        title={t('Группы')}
        subtitle={t('Заполненность профилей и зона риска по каждой учебной группе.')}
      />

      <div className="grid grid--cards">
        {data.groups.map((g) => (
          <div key={g.code} className="card card-pad">
            <div className="row-between">
              <b className="t-value">{g.code}</b>
              <Chip tone="neutral" className="num">
                {g.students_count} чел.
              </Chip>
            </div>
            <div className="row-between mt-3.5 mx-0 mb-1.5 t-note">
              <span className="muted">{t('Заполненность профилей')}</span>
              <b className="num">{g.students_count ? Math.round((g.filled / g.students_count) * 100) : 0}%</b>
            </div>
            <Bar percent={g.students_count ? (g.filled / g.students_count) * 100 : 0} />
            {g.critical > 0 && (
              <div className="mt-3">
                <Chip tone="bad" className="num">
                  {g.critical} в зоне риска
                </Chip>
              </div>
            )}
          </div>
        ))}
        {data.groups.length === 0 && <EmptyNote what="учебных групп пока нет" who="заводит администратор" />}
      </div>
    </div>
  )
}
