/** Нурлыбек: перспективные спортсмены, календарь соревнований, сертификаты. */
import { useNavigate } from 'react-router-dom'
import { useDashboard } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import SectionLink from '../../components/SectionLink'
import { ErrorNote, Kpi, ListPanel, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import { SPORT_LEVELS as LEVELS, type SportData } from '../sections/data'
import { Badge } from '../../components/ui/badge'

export default function SportDashboard() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDashboard<SportData>('sport')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Спорт')}
        hint={t('Здесь появятся спортсмены школы')}
        what={t('Раздел соберётся из спортивных профилей.')}
        detail={t('Перспективные спортсмены, недостающие сертификаты и календарь соревнований.')}
        guide
      />
    )

  return (
    <div>
      <ScreenHead title={t('Спорт')} subtitle={t('Спортсмены, чей профиль реально усиливает заявку.')} />

      <GettingStarted />

      <div className="grid grid--kpi">
        <Kpi value={data.athletes} label={t('Занимаются спортом')} />
        <Kpi
          value={data.strong.length}
          label={t('Спортсменов областного уровня и выше')}
          note={t('их достижения весят в заявке')}
          color="var(--ok)"
          accent="ok"
        />
        <Kpi
          value={data.no_certificate.length}
          label={t('Соревнований без сертификата')}
          note={t('достижения не подтверждены')}
          color="var(--risk)"
          accent="risk"
        />
        <Kpi
          value={data.leaders}
          label={t('Лидерские роли')}
          note={t('капитаны команд')}
          color="var(--brand)"
          accent="brand"
        />
      </div>

      <div className="grid grid--two">
        <ListPanel
          title={t('Перспективные спортсмены')}
          rows={data.strong}
          limit={20}
          onOpen={(id) => navigate(`/students/${id}`)}
          right={(row) => (
            <span style={{ textAlign: 'right', fontSize: 12.5 }}>
              <b>{row.sport_name}</b>
              <br />
              <span className="muted" style={{ fontSize: 11 }}>
                {row.rank || LEVELS[row.level ?? ''] || '—'}
              </span>
            </span>
          )}
        />
        <ListPanel
          title={t('Собрать сертификаты')}
          rows={data.no_certificate}
          limit={20}
          onOpen={(id) => navigate(`/students/${id}`)}
          right={(row) => <Badge variant="warn">{LEVELS[row.level ?? ''] ?? '—'}</Badge>}
        />
      </div>

      <div className="grid grid--two" style={{ marginTop: 20 }}>
        <SectionLink
          title={t('Соревнования')}
          value={data.calendar.length}
          note={t('ближайших стартов в календаре')}
          to="/competitions"
        />
      </div>
    </div>
  )
}
