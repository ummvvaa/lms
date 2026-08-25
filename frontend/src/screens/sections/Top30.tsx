/** TOP-30 — отдельный экран академического директора: кандидаты по IELTS и по SAT. */
import { useNavigate } from 'react-router-dom'
import { useDashboard } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import { ErrorNote, ListPanel, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import type { ExamData, PersonRow } from './data'

/** Балл и цель одной строкой справа. */
function score(current: string | number | undefined, target: string | number | undefined) {
  return (
    <span className="num" style={{ textAlign: 'right', fontSize: 13 }}>
      <b>{current ?? '—'}</b>
      <br />
      <span className="muted" style={{ fontSize: 11 }}>
        цель {target ?? '—'}
      </span>
    </span>
  )
}

export default function Top30() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDashboard<ExamData>('exam')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('TOP-30')}
        hint={t('Здесь появятся кандидаты с сильными баллами')}
        what={t('Список строится по текущим баллам IELTS и SAT.')}
        detail={t('Наверх поднимаются те, у кого баллы уже открывают сильные программы.')}
      />
    )

  const open = (id: number) => navigate(`/students/${id}`)

  return (
    <div>
      <ScreenHead
        title={t('TOP-30')}
        subtitle={t('Кандидаты, у которых баллы уже открывают сильные программы.')}
      />

      <div className="grid grid--two">
        <ListPanel
          title={t('TOP-30 · кандидаты на IELTS 7.5+')}
          rows={data.top_ielts}
          limit={30}
          onOpen={open}
          right={(row: PersonRow) => score(row.ielts_current, row.ielts_target)}
        />
        <ListPanel
          title={t('TOP-30 · кандидаты на SAT 1500+')}
          rows={data.top_sat}
          limit={30}
          onOpen={open}
          right={(row: PersonRow) => score(row.sat_current, row.sat_target)}
        />
      </div>
    </div>
  )
}
