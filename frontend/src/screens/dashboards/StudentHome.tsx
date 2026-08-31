/**
 * Кабинет ученика: процент готовности и задачи.
 * Внутренних ярлыков здесь нет — их не отдаёт даже API (инвариант №7).
 */
import { useNavigate } from 'react-router-dom'
import { useCalendar, useJourney, useMyProfile } from '../../api/hooks'
import GettingStarted from '../../components/GettingStarted'
import TodayPanel from '../../components/TodayPanel'
import Journey from '../Journey'
import { Bar, ErrorNote, Loading, Ring, ScreenHead } from '../../components/ui'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'

/** Ближайшее событие с обратным отсчётом — на главной в любом её виде (фаза 39). */
function NearestEvent() {
  const { data } = useCalendar()
  const navigate = useNavigate()
  if (!data?.nearest) return null
  return (
    <div className="card card-pad card--accent card--teal cal__nearest">
      <div className="cal__nearestrow">
        <div>
          <span className="eyebrow">{t('Ближайшее событие')}</span>
          <div className="t-card cal__nearesttitle">
            {data.nearest.title}
            {data.nearest.pending && <Badge variant="mute">{t('ждёт проверки')}</Badge>}
          </div>
          <p className="muted cal__nearestnote">{new Date(data.nearest.date).toLocaleDateString('ru')}</p>
        </div>
        <div className="cal__nearestrow">
          <div className="num t-figure">
            {data.nearest.days_left === 0 ? t('сегодня') : `${data.nearest.days_left} ${t('дн.')}`}
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate('/calendar')}>
            {t('Календарь')}
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function StudentHome() {
  const journey = useJourney()
  const { data, isLoading, error } = useMyProfile()
  if (journey.isLoading || isLoading) return <Loading kind="cards" />

  // пока путь не пройден, лестница шагов и есть главная (фаза 37);
  // дашборд с готовностью появляется, когда все пять шагов позади.
  // Ближайшее событие с отсчётом видно в обоих видах главной
  if (journey.data && !journey.data.complete)
    return (
      <div>
        <NearestEvent />
        <Journey />
      </div>
    )

  if (error) return <ErrorNote error={error} />
  if (!data) return null

  const readiness = data.readiness

  return (
    <div>
      <ScreenHead
        title={`Привет, ${data.first_name}`}
        subtitle={t('Где вы сейчас и что двинет вас дальше всего.')}
      />

      {/* баннера про анкету здесь нет: первая строка панели «С чего начать»
          говорит ровно то же самое и ведёт туда же. Два блока подряд об одном
          и том же читаются как сбой */}
      <NearestEvent />
      <GettingStarted />

      <TodayPanel />

      <div className="split">
        <div className="card card-pad" style={{ display: 'grid', placeItems: 'center', padding: 28 }}>
          <Ring percent={readiness?.score ?? 0} size={150}>
            <div>
              <div className="num" style={{ fontSize: 34, fontWeight: 800, lineHeight: 1 }}>
                {readiness?.score ?? 0}%
              </div>
              <div className="muted" style={{ fontSize: 11.5 }}>
                {t('готовность')}
              </div>
            </div>
          </Ring>
          {readiness?.weakest_title && (
            <p className="muted" style={{ marginTop: 18, textAlign: 'center', fontSize: 13 }}>
              Больше всего сейчас даст работа над блоком «{readiness.weakest_title}».
            </p>
          )}
        </div>

        <div className="card card-pad card--accent card--brand">
          <span className="eyebrow">{t('Из чего складывается готовность')}</span>
          <div style={{ marginTop: 14 }}>
            {readiness?.parts.map((part) => (
              <div key={part.code} style={{ padding: '9px 0' }}>
                <div className="row-between" style={{ fontSize: 13, marginBottom: 6 }}>
                  <span style={{ fontWeight: 650 }}>{part.title}</span>
                  <b className="num">{Math.round(part.value)}%</b>
                </div>
                <Bar
                  percent={part.value}
                  color={part.code === readiness.weakest ? 'var(--brand)' : 'var(--teal)'}
                />
              </div>
            ))}
            {(readiness?.skipped ?? []).map((part) => (
              <div key={part.code} style={{ padding: '9px 0', opacity: 0.55 }}>
                <div className="row-between" style={{ fontSize: 13, marginBottom: 6 }}>
                  <span style={{ fontWeight: 650 }}>{part.title}</span>
                  <span className="muted" style={{ fontSize: 12 }}>
                    {t('данных пока нет')}
                  </span>
                </div>
                <Bar percent={0} color="var(--line)" />
              </div>
            ))}
            {!readiness?.parts.length && !readiness?.skipped.length && (
              <p className="muted">{t('Данных пока нет — профиль ещё заполняется.')}</p>
            )}
            {(readiness?.skipped.length ?? 0) > 0 && (
              <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
                {t('Блоки без данных в процент не входят — он считается по тем, что заполнены.')}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
