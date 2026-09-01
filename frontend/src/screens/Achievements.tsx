/**
 * Достижения ученика (фаза 46).
 *
 * Закрытые бейджи показываются с замком и условием, а не прячутся:
 * человек должен видеть, что можно получить. Прогресс — числом «92 из 100»,
 * а не галочкой: «осталось восемь» двигает вперёд, «не получено» — нет.
 *
 * Инвариант №12: бейдж даётся за действия. За балл экзамена, GPA или статус
 * бейджа быть не может — набор мер закрыт на сервере.
 */
import { useAchievements } from '../api/hooks'
import Empty from '../components/Empty'
import { StatCard, StatRow } from '../components/patterns'
import Icon, { type IconName } from '../layout/icons'
import { Bar, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Badge } from '../components/ui/badge'
import '../components/badges.css'
import { t } from '../i18n'

export default function Achievements() {
  const state = useAchievements()

  if (state.isLoading) return <Loading kind="cards" />
  if (state.error) return <ErrorNote error={state.error} />

  const data = state.data
  const badges = data?.badges ?? []
  const earned = badges.filter((row) => row.earned)
  const locked = badges.filter((row) => !row.earned)

  return (
    <div>
      <ScreenHead
        title={t('Достижения')}
        subtitle={t('Бейджи даются за действия: заполнил, решил, написал, поделился. За баллы бейджей нет.')}
      />

      <StatRow>
        <StatCard
          icon="medal"
          tone="brand"
          label={t('Получено')}
          value={data?.earned ?? 0}
          note={t('бейджей из набора школы')}
        />
        <StatCard
          icon="star"
          tone="indigo"
          label={t('Ещё можно взять')}
          value={locked.length}
          note={t('условие видно у каждого')}
        />
      </StatRow>

      {badges.length === 0 && (
        <Empty
          icon="medal"
          title={t('Бейджей пока нет')}
          what={t('Набор достижений ведёт директор школы — как появится, он будет здесь.')}
          hint={t('Условие бейджа — строка справочника: новый бейдж заводится без выката.')}
        />
      )}

      {earned.length > 0 && (
        <>
          <span className="eyebrow">{t('Получено')}</span>
          <div className="grid grid--cards badges__grid">
            {earned.map((badge) => (
              <article key={badge.id} className="card card-pad badges__card card--accent card--brand">
                <span className="badges__icon badges__icon--on" aria-hidden="true">
                  <Icon name={(badge.icon || 'medal') as IconName} size={22} />
                </span>
                <b>{badge.name}</b>
                <p className="muted badges__hint">{badge.description}</p>
                <Badge variant="ok">
                  {t('получен')}
                  {badge.earned_at ? ` · ${new Date(badge.earned_at).toLocaleDateString('ru')}` : ''}
                </Badge>
              </article>
            ))}
          </div>
        </>
      )}

      {locked.length > 0 && (
        <>
          <span className="eyebrow">{t('Ещё не получено')}</span>
          <div className="grid grid--cards badges__grid">
            {locked.map((badge) => (
              <article key={badge.id} className="card card-pad badges__card badges__card--locked">
                <span className="badges__icon" aria-hidden="true">
                  <Icon name={(badge.icon || 'medal') as IconName} size={22} />
                </span>
                <b>{badge.name}</b>
                <p className="muted badges__hint">{badge.description || badge.condition}</p>
                <div className="badges__progress">
                  <Bar percent={badge.percent} />
                  <span className="muted num">{badge.progress}</span>
                </div>
              </article>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
