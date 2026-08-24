/** Соревнования — отдельный экран директора спорта: календарь ближайших стартов. */
import { useDashboard } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import { ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import type { SportData } from './data'

export default function Competitions() {
  const { data, isLoading, error } = useDashboard<SportData>('sport')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Соревнования')}
        hint={t('Здесь появится календарь ближайших стартов')}
        what={t(
          'Каждое соревнование — строка с датой и числом заявленных учеников. Записи заводятся в карточке ученика или приходят загрузкой.',
        )}
      />
    )

  return (
    <div>
      <ScreenHead
        title={t('Соревнования')}
        subtitle={t('Ближайшие старты и сколько учеников на них заявлено.')}
      />

      <div className="grid grid--cards">
        {data.calendar.map((row) => (
          <div key={`${row.name}-${row.date}`} className="card card-pad">
            <b style={{ fontSize: 15 }}>{row.name}</b>
            <p className="muted" style={{ fontSize: 12.5, margin: '4px 0 12px' }}>
              {new Date(row.date).toLocaleDateString('ru')}
            </p>
            <span className="chip chip-mute num">{row.participants} участников</span>
          </div>
        ))}
        {data.calendar.length === 0 && <p className="muted">{t('Предстоящих соревнований нет.')}</p>}
      </div>
    </div>
  )
}
