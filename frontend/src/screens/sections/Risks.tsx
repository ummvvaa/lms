/** Риски — отдельный экран директора школы: кто просел по посещаемости и домашним. */
import { useNavigate } from 'react-router-dom'
import { useDashboard } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import { ErrorNote, Kpi, ListPanel, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import type { BehaviorData } from './data'

export default function Risks() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDashboard<BehaviorData>('behavior')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty) return <EmptyDashboard title={t('Риски')} />

  const warn = data.traffic.needs_supervision ?? 0
  const risk = data.traffic.critical ?? 0

  return (
    <div>
      <ScreenHead
        title={t('Риски')}
        subtitle={t('Кому нужен контроль прямо сейчас. Эти ярлыки видны только сотрудникам.')}
      />

      <div className="grid grid--kpi">
        <Kpi value={risk} label={t('Ежедневный контроль')} color="var(--risk)" />
        <Kpi value={warn} label={t('Нужен контроль')} color="var(--warn)" />
      </div>

      <div className="grid grid--two">
        <ListPanel
          title={t('Худшая посещаемость')}
          rows={data.worst_attendance}
          limit={20}
          onOpen={(id) => navigate(`/students/${id}`)}
          right={(row) => <span className="chip chip-risk num">{row.attendance_percent}%</span>}
        />
        <ListPanel
          title={t('Худшие домашние работы')}
          rows={data.worst_homework ?? []}
          limit={20}
          onOpen={(id) => navigate(`/students/${id}`)}
          right={(row) => <span className="chip chip-warn num">{row.homework_percent}%</span>}
        />
      </div>
    </div>
  )
}
