/**
 * Группы — отдельный экран директора школы.
 *
 * Раньше это была секция дашборда, до которой надо было доскроллить.
 * Данные те же, что и у дашборда (`/dashboards/behavior/`), запрос общий:
 * TanStack Query отдаёт его из кэша.
 */
import { useDashboard } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import { Bar, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import type { BehaviorData } from './data'

export default function Groups() {
  const { data, isLoading, error } = useDashboard<BehaviorData>('behavior')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty) return <EmptyDashboard title={t('Группы')} />

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
              <b style={{ fontSize: 17 }}>{g.code}</b>
              <span className="chip chip-mute num">{g.students_count} чел.</span>
            </div>
            <div className="row-between" style={{ margin: '14px 0 6px', fontSize: 12.5 }}>
              <span className="muted">{t('Заполненность профилей')}</span>
              <b className="num">{g.students_count ? Math.round((g.filled / g.students_count) * 100) : 0}%</b>
            </div>
            <Bar percent={g.students_count ? (g.filled / g.students_count) * 100 : 0} />
            {g.critical > 0 && (
              <div style={{ marginTop: 12 }}>
                <span className="chip chip-risk num">{g.critical} в зоне риска</span>
              </div>
            )}
          </div>
        ))}
        {data.groups.length === 0 && <p className="muted">{t('Учебных групп пока нет.')}</p>}
      </div>
    </div>
  )
}
