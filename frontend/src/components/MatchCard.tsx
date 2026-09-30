/**
 * Карточка программы: соответствие требованиям с разбивкой и разрывом.
 *
 * Процент — это соответствие требованиям, а не шанс поступления
 * (инвариант №11). Рядом всегда стоит разбивка: число без объяснения
 * бесполезно и вводит в заблуждение.
 */
import type { CatalogCard, MatchPosition, MatchResult } from '../api/hooks'
import { Bar, Chip, type Tone, UnverifiedNote } from './ui'
import { t, tk } from '../i18n'
import { formatDate } from '../lib/format'

const LEVEL_TONE: Record<string, Tone> = {
  high: 'good',
  medium: 'warn',
  low: 'neutral',
}

const TIER_TITLES: Record<string, string> = {
  reach: tk('reach — с запасом вверх'),
  target: tk('target — по силам'),
  safety: tk('safety — подстраховка'),
}

function positionColor(position: MatchPosition): string {
  if (position.is_met) return 'var(--good)'
  if (position.percent >= 70) return 'var(--accent)'
  return 'var(--bad)'
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
                <span className="muted">{t('нет данных')}</span>
              ) : (
                <>
                  <b>{position.percent}%</b>
                  {position.gap_phrase && <span className="muted">{t(' · не хватает {gap}', { gap: position.gap_phrase })}</span>}
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
      <Chip tone={LEVEL_TONE[level ?? ''] ?? 'neutral'} className="num match__value">
        {percent}%
      </Chip>
      <span className="muted match__caption">{t('соответствие требованиям')}</span>
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
          <Chip tone="neutral">{t('требования не заведены')}</Chip>
        )}
      </div>

      <p className="match__summary">{card.summary}</p>

      {/* Инвариант №14: непроверенный порог даёт непроверенный процент,
          и сказать об этом надо рядом с самим процентом */}
      {!card.is_verified && (
        <UnverifiedNote note={card.verification_note} website={card.university_website} />
      )}

      <MatchBreakdown breakdown={card.breakdown} />

      {rounds.length > 0 && (
        <div className="match__rounds">
          <span className="eyebrow">{t('Дедлайны раундов')}</span>
          <div className="match__roundlist">
            {rounds.map((round) => (
              <Chip key={round.id} tone="neutral" className="num">
                {round.round_type} · {formatDate(round.deadline)}
              </Chip>
            ))}
          </div>
          {nearest && (
            <p className="muted match__note">
              {t('Ближайший — {round} до {date}.', { round: nearest.round_title, date: formatDate(nearest.deadline) })}
            </p>
          )}
        </div>
      )}

      {card.in_my_list && card.my_entry && (
        <p className="muted match__note">
          {[
            t('В вашем списке как {tier}', { tier: TIER_TITLES[card.my_entry.tier] ? t(TIER_TITLES[card.my_entry.tier]) : card.my_entry.tier }),
            card.my_entry.added_by === 'student' && !card.my_entry.is_confirmed ? t('ждёт подтверждения') : '',
          ]
            .filter(Boolean)
            .join(' · ')}
        </p>
      )}

      {children}
      {actions && <div className="match__actions">{actions}</div>}
    </article>
  )
}
