/** Нурлыбек: перспективные спортсмены, календарь соревнований, сертификаты. */
import { useNavigate } from 'react-router-dom'
import { useDashboard } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import { ErrorNote, Kpi, ListPanel, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'

interface Row {
  student_id: number
  student__last_name: string
  student__first_name: string
  sport_name?: string
  level?: string
  rank?: string
}

interface Data {
  athletes: number
  strong: Row[]
  no_certificate: Row[]
  calendar: { name: string; date: string; participants: number }[]
  leaders: number
}

const LEVELS: Record<string, string> = {
  school: 'Школьный',
  city: 'Городской',
  regional: 'Областной',
  national: 'Республиканский',
  international: 'Международный',
}

export default function SportDashboard() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDashboard<Data>('sport')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty) return <EmptyDashboard title={t('Спорт')} />

  return (
    <div>
      <ScreenHead title={t('Спорт')} subtitle={t('Спортсмены, чей профиль реально усиливает заявку.')} />

      <GettingStarted />

      <div className="grid grid--kpi">
        <Kpi value={data.athletes} label={t('Занимаются спортом')} />
        <Kpi
          value={data.strong.length}
          label={t('Сильный профиль')}
          note={t('областной уровень и выше')}
          color="var(--ok)"
        />
        <Kpi
          value={data.no_certificate.length}
          label={t('Без сертификатов')}
          note={t('достижения не подтверждены')}
          color="var(--risk)"
        />
        <Kpi
          value={data.leaders}
          label={t('Лидерские роли')}
          note={t('капитаны команд')}
          color="var(--brand)"
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
          right={(row) => <span className="chip chip-warn">{LEVELS[row.level ?? ''] ?? '—'}</span>}
        />
      </div>

      <h2 className="section" id="competitions">
        {t('Календарь соревнований')}
      </h2>
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
