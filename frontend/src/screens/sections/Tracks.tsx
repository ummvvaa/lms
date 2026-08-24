/** Треки — отдельный экран директора талантов: распределение и те, у кого трека нет. */
import { useNavigate } from 'react-router-dom'
import { useDashboard } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import { Bar, ErrorNote, ListPanel, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import { TRACK_TITLES, type TalentData } from './data'

export default function Tracks() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDashboard<TalentData>('talent')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Треки')}
        hint={t('Здесь появится распределение по трекам')}
        what={t(
          'Трек — то, чем ученик усиливает заявку: олимпиады, исследования, стартап, лидерство, волонтёрство, конкурсы. Появятся ученики — появится и разбивка, и список тех, у кого трек не выбран.',
        )}
      />
    )

  // самый частый трек задаёт длину полосы: иначе один-два ученика рисуют полный столбик
  const top = Math.max(1, ...Object.keys(TRACK_TITLES).map((key) => data.tracks[key] ?? 0))

  return (
    <div>
      <ScreenHead
        title={t('Треки')}
        subtitle={t('Чем ученик усиливает заявку. Без основного трека портфолио собирается вслепую.')}
      />

      <div className="card card-pad">
        <span className="eyebrow">{t('По трекам')}</span>
        <div style={{ marginTop: 14 }}>
          {Object.entries(TRACK_TITLES).map(([key, title]) => (
            <div key={key} style={{ padding: '9px 0' }}>
              <div className="row-between" style={{ fontSize: 13, marginBottom: 6 }}>
                <span style={{ fontWeight: 650 }}>{title}</span>
                <b className="num">{data.tracks[key] ?? 0}</b>
              </div>
              <Bar percent={((data.tracks[key] ?? 0) / top) * 100} color="var(--warn)" />
            </div>
          ))}
        </div>
      </div>

      <h2 className="section">{t('Трек не выбран — нужно решение')}</h2>
      <ListPanel
        title={t('Без основного трека')}
        rows={data.no_track}
        limit={30}
        onOpen={(id) => navigate(`/students/${id}`)}
      />
    </div>
  )
}
