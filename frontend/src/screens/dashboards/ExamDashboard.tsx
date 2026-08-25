/** Кымбат: матрица шести корзин и короткие сводки разделов. */
import { useNavigate } from 'react-router-dom'
import { useDashboard } from '../../api/hooks'
import OnboardingQueue from '../../components/OnboardingQueue'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import SectionLink from '../../components/SectionLink'
import { accentClass, Bar, ErrorNote, Loading, ScreenHead, type Accent } from '../../components/ui'
import { t } from '../../i18n'
import type { ExamData } from '../sections/data'

interface Bucket {
  key: string
  label: string
  /** смысл корзины: он же цвет числа и цвет полосы над плиткой */
  tone: Accent
  /** фильтр таблицы: плитка должна показывать этих учеников, а не просто подсвечиваться */
  filter: Record<string, string>
}

const BUCKETS: Bucket[] = [
  { key: 'ielts_low', label: 'IELTS < 6.0', tone: 'risk', filter: { ielts_max: '6.0' } },
  {
    key: 'ielts_mid',
    label: 'IELTS 6.0–7.4',
    tone: 'brand',
    filter: { ielts_min: '6.0', ielts_max: '7.5' },
  },
  { key: 'ielts_high', label: 'IELTS 7.5+', tone: 'ok', filter: { ielts_min: '7.5' } },
  { key: 'sat_low', label: 'SAT < 1200', tone: 'risk', filter: { sat_max: '1200' } },
  {
    key: 'sat_mid',
    label: 'SAT 1200–1499',
    tone: 'brand',
    filter: { sat_min: '1200', sat_max: '1500' },
  },
  { key: 'sat_high', label: 'SAT 1500+', tone: 'ok', filter: { sat_min: '1500' } },
]

export default function ExamDashboard() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useDashboard<ExamData>('exam')
  const schoolIsEmpty = useSchoolIsEmpty()
  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Экзамены')}
        hint={t('Здесь появится экзаменационная матрица')}
        what={t('Корзины по IELTS и SAT наполнятся из баллов учеников.')}
        detail={t('Каждая плитка открывает своих учеников в таблице.')}
        guide
      />
    )

  const total = Object.values(data.buckets).reduce((a, b) => a + b, 0) / 2 || 1

  return (
    <div>
      <ScreenHead
        title={t('Экзамены')}
        subtitle={t('Экзаменационная матрица. Плитка открывает этих учеников в таблице.')}
      />

      <GettingStarted />

      <OnboardingQueue />

      <div className="grid grid--kpi">
        {BUCKETS.map((bucket) => (
          <button
            key={bucket.key}
            className={`card card-pad kpi kpi--button${accentClass(bucket.tone)}`}
            onClick={() => navigate(`/table?${new URLSearchParams(bucket.filter).toString()}`)}
          >
            <div className="num kpi__value" style={{ color: `var(--${bucket.tone})` }}>
              {data.buckets[bucket.key]}
            </div>
            <div className="kpi__label">{bucket.label}</div>
            <div style={{ marginTop: 12 }}>
              <Bar percent={(data.buckets[bucket.key] / total) * 100} color={`var(--${bucket.tone})`} />
            </div>
          </button>
        ))}
      </div>

      <div className="grid grid--two">
        <SectionLink
          title={t('TOP-30')}
          value={data.top_ielts.length + data.top_sat.length}
          note={t('кандидаты на IELTS 7.5+ и SAT 1500+')}
          to="/top30"
        />
        <SectionLink
          title={t('Пробные')}
          value={data.mock_drops.length}
          note={t('у скольких балл просел с прошлой попытки')}
          to="/mocks"
        />
      </div>
    </div>
  )
}
