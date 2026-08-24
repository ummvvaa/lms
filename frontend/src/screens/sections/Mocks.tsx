/** Пробные — отдельный экран академического директора: назначение моков и падения баллов. */
import { useNavigate } from 'react-router-dom'
import { useDashboard } from '../../api/hooks'
import PlatformMocks from '../../components/PlatformMocks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import { ErrorNote, ListPanel, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import type { ExamData } from './data'

export default function Mocks() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDashboard<ExamData>('exam')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Пробные')}
        hint={t('Здесь появятся пробные экзамены и просадки')}
        what={t(
          'Моки на платформе назначаются отсюда, а падение балла относительно прошлой попытки система находит сама. Для этого нужны ученики и хотя бы одна попытка экзамена.',
        )}
      />
    )

  return (
    <div>
      <ScreenHead
        title={t('Пробные')}
        subtitle={t('Моки на платформе и те, у кого балл просел с прошлой попытки.')}
      />

      <PlatformMocks />

      <ListPanel
        title={t('Мок упал — нужно вмешаться')}
        rows={data.mock_drops}
        limit={30}
        onOpen={(id) => navigate(`/students/${id}`)}
        right={(row) => (
          <span className="chip chip-risk num">
            {row.exam_type} {row.delta}
          </span>
        )}
      />
    </div>
  )
}
