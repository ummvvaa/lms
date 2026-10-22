/**
 * Достижения ученика: три показателя и бейджи плитками по четыре в ряд.
 *
 * Закрытые бейджи показываются с условием, а не прячутся: человек должен
 * видеть, что можно получить. Прогресс — полосой и числом «92 из 100».
 * Инвариант №12: бейдж даётся за действия, за баллы бейджей нет.
 */
import { useAchievements } from '../api/hooks'
import Icon, { type IconName } from '../layout/icons'
import { Bar, Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../components/ui'
import { t } from '../i18n'
import { formatDayMonth } from '../lib/format'
import './achievements-layout.css'

export default function Achievements() {
  const state = useAchievements()
  if (state.isLoading) return <Loading kind="cards" />
  if (state.error) return <ErrorNote error={state.error} />

  const data = state.data
  const badges = data?.badges ?? []
  const earned = badges.filter((row) => row.earned)
  const locked = [...badges.filter((row) => !row.earned)].sort((a, b) => b.percent - a.percent)
  const nearest = locked[0]
  // последний полученный — по дате получения
  const latest = [...earned]
    .filter((row) => row.earned_at)
    .sort((a, b) => String(b.earned_at).localeCompare(String(a.earned_at)))[0]

  return (
    <div className="lay-screen">
      <ScreenHead title={t('Достижения')} subtitle={t('Бейджи школы за дела в LMS — условие видно у каждого')} />
      <div className="lay-3">
        <div className="ach-beam card--beam">
          <Kpi
            label={t('Получено')}
            value={data?.earned || null}
            none={t('нет')}
            note={t('из {total} бейджей школы', { total: data?.total ?? badges.length })}
          />
        </div>
        {/* «ближе всего»: название бейджа и полоса — числа здесь не главное */}
        <div className="kpi stat ach-kpi">
          <span className="kpi__label t-caps">{t('Ближе всего')}</span>
          {nearest ? (
            <>
              <span className="kpi__value ach-kpi__name">{t(nearest.name)}</span>
              <Bar percent={nearest.percent} />
              <span className="kpi__note num">{nearest.progress}</span>
            </>
          ) : (
            <span className="kpi__value kpi__value--none">{t('нет')}</span>
          )}
        </div>
        <div className="kpi stat ach-kpi">
          <span className="kpi__label t-caps">{t('Последний')}</span>
          {latest ? (
            <>
              <span className="kpi__value ach-kpi__name">{t(latest.name)}</span>
              <span className="kpi__note">{formatDayMonth(latest.earned_at as string)}</span>
            </>
          ) : (
            <span className="kpi__value kpi__value--none">{t('нет')}</span>
          )}
        </div>
      </div>

      {badges.length === 0 ? (
        <DataCard title={t('Бейджей пока нет')} empty={t('набор достижений ведёт директор школы — как появится, он будет здесь')} />
      ) : (
        <div className="lay-4 ach-grid">
          {[...earned, ...locked].map((badge) => (
            <article key={badge.id} className={`card card-pad ach-tile${badge.earned ? ' ach-tile--on' : ''}`}>
              <span className="ach-tile__medal" aria-hidden="true">
                <Icon name={(badge.icon || 'medal') as IconName} size={24} />
              </span>
              <span className="ach-tile__name">{t(badge.name)}</span>
              <span className="ach-tile__desc">{badge.description ? t(badge.description) : badge.condition}</span>
              {badge.earned ? (
                <Chip tone="good" size="sm" className="ach-tile__chip">
                  {badge.earned_at ? formatDayMonth(badge.earned_at) : t('получен')}
                </Chip>
              ) : (
                <span className="ach-tile__progress">
                  <Bar percent={badge.percent} />
                  <span className="t-note num">{badge.progress}</span>
                </span>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
