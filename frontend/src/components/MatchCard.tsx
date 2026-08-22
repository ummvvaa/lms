/**
 * Карточка программы: соответствие требованиям с разбивкой и разрывом.
 *
 * Процент — это соответствие требованиям, а не шанс поступления
 * (инвариант №11). Рядом всегда стоит разбивка: число без объяснения
 * бесполезно и вводит в заблуждение.
 */
import type { CatalogCard, MatchPosition, MatchResult } from '../api/hooks'
import { Bar } from './ui'

const LEVEL_TONE: Record<string, string> = {
  high: 'chip-ok',
  medium: 'chip-warn',
  low: 'chip-mute',
}

const TIER_TITLES: Record<string, string> = {
  reach: 'reach — с запасом вверх',
  target: 'target — по силам',
  safety: 'safety — подстраховка',
}

function positionColor(position: MatchPosition): string {
  if (position.is_met) return 'var(--ok)'
  if (position.percent >= 70) return 'var(--brand)'
  return 'var(--risk)'
}

export function MatchBreakdown({ breakdown }: { breakdown: MatchPosition[] }) {
  if (breakdown.length === 0) return null
  return (
    <div className="match__breakdown">
      {breakdown.map((position) => (
        <div key={position.code} className="match__row">
          <div className="row-between match__rowhead">
            <span>{position.title}</span>
            <span className="num">
              {position.is_unknown ? (
                <span className="muted">нет данных</span>
              ) : (
                <>
                  <b>{position.percent}%</b>
                  {position.gap_phrase && <span className="muted"> · не хватает {position.gap_phrase}</span>}
                </>
              )}
            </span>
          </div>
          <Bar percent={position.percent} color={positionColor(position)} />
        </div>
      ))}
    </div>
  )
}

export function MatchPercent({ percent, level }: { percent: number; level?: string }) {
  return (
    <div className="match__percent">
      <b className={`num match__value chip ${LEVEL_TONE[level ?? ''] ?? 'chip-mute'}`}>{percent}%</b>
      <span className="muted match__caption">соответствие требованиям</span>
    </div>
  )
}

/**
 * Карточку рисуем и по «голому» результату соответствия — например,
 * в пересчёте «что откроется, если», где раундов в ответе нет.
 */
type CardLike = MatchResult & Partial<Omit<CatalogCard, keyof MatchResult>>

export default function MatchCard({
  card,
  actions,
  children,
}: {
  card: CardLike
  actions?: React.ReactNode
  children?: React.ReactNode
}) {
  const rounds = card.rounds ?? []
  const nearest = rounds[0]

  return (
    <article className="card card-pad match">
      <div className="row-between match__head">
        <div>
          <b className="match__title">{card.university_name}</b>
          <p className="muted match__sub">
            {card.country} · {card.program_name}
          </p>
        </div>
        {card.has_requirements ? (
          <MatchPercent percent={card.percent} level={card.level} />
        ) : (
          <span className="chip chip-mute">требования не заведены</span>
        )}
      </div>

      <p className="match__summary">{card.summary}</p>

      <MatchBreakdown breakdown={card.breakdown} />

      {rounds.length > 0 && (
        <div className="match__rounds">
          <span className="eyebrow">Дедлайны раундов</span>
          <div className="match__roundlist">
            {rounds.map((round) => (
              <span key={round.id} className="chip chip-mute num">
                {round.round_type} · {new Date(round.deadline).toLocaleDateString('ru')}
              </span>
            ))}
          </div>
          {nearest && (
            <p className="muted match__note">
              Ближайший — {nearest.round_title} до {new Date(nearest.deadline).toLocaleDateString('ru')}.
            </p>
          )}
        </div>
      )}

      {card.in_my_list && card.my_entry && (
        <p className="muted match__note">
          В вашем списке как {TIER_TITLES[card.my_entry.tier] ?? card.my_entry.tier}
          {card.my_entry.added_by === 'student' && !card.my_entry.is_confirmed && ' · ждёт подтверждения'}
        </p>
      )}

      {children}
      {actions && <div className="match__actions">{actions}</div>}
    </article>
  )
}
