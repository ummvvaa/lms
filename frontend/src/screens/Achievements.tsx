/**
 * Достижения ученика: бейджи строками с прогрессом, а не карточками три в ряд.
 *
 * Закрытые бейджи показываются с условием, а не прячутся: человек должен
 * видеть, что можно получить. Прогресс — числом «92 из 100».
 * Инвариант №12: бейдж даётся за действия, за баллы бейджей нет.
 */
import { useAchievements } from '../api/hooks'
import Progress from '../components/Progress'
import { Row, Rows, StatRow } from '../components/patterns'
import Icon, { type IconName } from '../layout/icons'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../components/ui'
import { t } from '../i18n'
import { NoteCard } from './academics/shared'

export default function Achievements() {
  const state = useAchievements()
  if (state.isLoading) return <Loading kind="cards" />
  if (state.error) return <ErrorNote error={state.error} />

  const data = state.data
  const badges = data?.badges ?? []
  const earned = badges.filter((row) => row.earned)
  const locked = [...badges.filter((row) => !row.earned)].sort((a, b) => b.percent - a.percent)

  return (
    <div>
      <ScreenHead title={t('Достижения')} subtitle={t('Бейджи даются за действия: заполнил, решил, написал, поделился. За баллы бейджей нет.')} />
      <StatRow>
        <Kpi tone="accent" label={t('Получено')} value={data?.earned || null} none={t('нет')} note={t('бейджей из набора школы')} />
        <Kpi label={t('Ещё можно взять')} value={locked.length || null} none={t('нет')} note={t('условие видно у каждого')} />
        <Kpi label={t('Ближайший')} value={locked[0] ? `${Math.round(locked[0].percent)}%` : null} none={t('нет')} note={locked[0]?.name} />
      </StatRow>
      <div className="acad__cols">
        <div className="acad__stack">
          {badges.length === 0 && <DataCard title={t('Бейджей пока нет')} empty={t('набор достижений ведёт директор школы — как появится, он будет здесь')} />}
          {earned.length > 0 && (
            <DataCard title={t('Получено')} count={earned.length}>
              <Rows>
                {earned.map((badge) => (
                  <Row key={badge.id} lead={<span className="stu__slot"><Icon name={(badge.icon || 'medal') as IconName} size={18} /></span>} tone="good" title={badge.name} note={badge.description} right={<Chip tone="good" size="sm">{badge.earned_at ? new Date(badge.earned_at).toLocaleDateString('ru') : t('получен')}</Chip>} />
                ))}
              </Rows>
            </DataCard>
          )}
          {locked.length > 0 && (
            <DataCard title={t('Ещё не получено')} count={locked.length}>
              <Rows>
                {locked.map((badge) => (
                  <Row
                    key={badge.id}
                    lead={<span className="stu__slot"><Icon name={(badge.icon || 'medal') as IconName} size={18} /></span>}
                    title={badge.name}
                    note={badge.description || badge.condition}
                    right={
                      <span className="badges__progress">
                        <Progress percent={badge.percent} label={false} />
                        <span className="t-note num">{badge.progress}</span>
                      </span>
                    }
                  />
                ))}
              </Rows>
            </DataCard>
          )}
        </div>
        <div className="acad__stack">
          <NoteCard title={t('Как это устроено')}>{t('Условие бейджа — строка справочника школы: новый бейдж заводится без выката. Рейтингов и сравнения с другими учениками здесь нет.')}</NoteCard>
        </div>
      </div>
    </div>
  )
}
