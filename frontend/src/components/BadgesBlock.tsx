/**
 * Блок достижений (фаза 46): в портфолио и в статистике подготовки.
 *
 * Показывает несколько ближайших бейджей с прогрессом и ведёт на экран
 * достижений. Закрытые не прячутся: ученик должен видеть, что можно
 * получить, — иначе достижения превращаются в лотерею.
 */
import { useAchievements } from '../api/hooks'
import Icon, { type IconName } from '../layout/icons'
import { Link } from 'react-router'
import { Bar, Chip, DataCard } from './ui'
import './badges.css'
import { t } from '../i18n'

export default function BadgesBlock({ limit = 4 }: { limit?: number }) {
  const state = useAchievements()
  const data = state.data
  if (!data || data.total === 0) return null

  // сначала полученные, потом самые близкие к получению
  const rows = [...data.badges]
    .sort((a, b) => Number(b.earned) - Number(a.earned) || b.percent - a.percent)
    .slice(0, limit)

  return (
    <DataCard
      // не «Достижения»: рядом в портфолио уже есть карточка достижений
      // ученика, и два одинаковых заголовка на одном экране путают
      title={t('Бейджи')}
      note={t('{earned} из {total}', { earned: data.earned, total: data.total })}
      right={
        <Link className="badges__all" to="/achievements">
          {t('Все достижения')}
        </Link>
      }
    >
      <ul className="badges__list">
        {rows.map((badge) => (
          <li key={badge.id} className="badges__row">
            <span className={`badges__icon${badge.earned ? ' badges__icon--on' : ''}`} aria-hidden="true">
              <Icon name={(badge.icon || 'medal') as IconName} size={18} />
            </span>
            <span className="badges__name">
              <b>{badge.name}</b>
              <span className="muted badges__hint">{badge.earned ? badge.description : badge.condition}</span>
            </span>
            {badge.earned ? (
              <Chip tone="good">{t('получен')}</Chip>
            ) : (
              <span className="badges__progress">
                <Bar percent={badge.percent} />
                <span className="muted num">{badge.progress}</span>
              </span>
            )}
          </li>
        ))}
      </ul>
    </DataCard>
  )
}
