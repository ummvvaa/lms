/**
 * «Мои вузы»: список ученика строками — приоритет, категория, соответствие
 * требованиям и разрыв словами; разбор раскрывается под строкой.
 *
 * Процент — соответствие заведённым требованиям, не шанс поступления
 * (инвариант №11). Внутренних ярлыков здесь нет (инвариант №7).
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useCatalog, useChangeTier, useMyUniversities, useRemoveFromMyList, useSetPriority } from '../api/hooks'
import ConfirmDialog from '../components/ConfirmDialog'
import { MatchBreakdown } from '../components/MatchCard'
import { Row, Rows, StatRow } from '../components/patterns'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead, UnverifiedNote } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { formatDate } from '../lib/format'
import './universities.css'

/** Категории списка — те же слова и в том же порядке, что в каталоге при добавлении. */
const TIERS = [
  { value: 'reach', title: 'с запасом вверх' },
  { value: 'target', title: 'по силам' },
  { value: 'safety', title: 'подстраховка' },
]

export default function MyUniversities() {
  const navigate = useNavigate()
  const mine = useMyUniversities()
  // строки каталога знают, что у ученика уже в списке и что он может убрать
  const catalog = useCatalog({})
  const remove = useRemoveFromMyList()
  const priority = useSetPriority()
  const retier = useChangeTier()
  const [editing, setEditing] = useState<number | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const [dropping, setDropping] = useState<{ id: number; name: string } | null>(null)

  if (mine.isLoading) return <Loading kind="table" />
  if (mine.error) return <ErrorNote error={mine.error} />

  const byProgram = new Map((catalog.data?.results ?? []).map((card) => [card.program, card]))
  const results = mine.data ?? []
  const openCount = results.filter((r) => r.is_open).length
  const waiting = results.filter((r) => {
    const card = byProgram.get(r.program)
    return card?.my_entry && !card.my_entry.is_confirmed
  }).length
  const nearest = results
    .map((r) => byProgram.get(r.program)?.rounds[0]?.deadline ?? null)
    .filter((d): d is string => Boolean(d))
    .sort()[0]

  return (
    <div>
      <ScreenHead
        title={t('Мои вузы')}
        subtitle={results.length === 0 ? undefined : `${counted(results.length, 'программа|программы|программ')} · ${t('по')} ${openCount} ${t('вы проходите уже сейчас')}`}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => navigate('/catalog?mode=whatif')}>
              {t('Что откроется, если')}
            </Button>
            <Button size="sm" onClick={() => navigate('/catalog')}>
              {t('Найти ещё в каталоге')}
            </Button>
          </>
        }
      />
      <StatRow>
        <Kpi label={t('В списке')} value={results.length || null} none={t('нет')} />
        <Kpi label={t('Проходите')} value={openCount || null} none={t('нет')} tone={openCount ? 'good' : undefined} />
        <Kpi label={t('Ждут подтверждения')} value={waiting || null} none={t('нет')} tone={waiting ? 'warn' : undefined} note={t('директора по поступлению')} />
        <Kpi label={t('Ближайший дедлайн')} value={nearest ? formatDate(nearest) : null} none={t('нет')} />
      </StatRow>
      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard
            title={t('Список подачи')}
            count={results.length || undefined}
            empty={results.length === 0 && t('выберите программы в каталоге — по каждой видно, проходите ли вы, а дедлайны сами станут задачами')}
            emptyAction={
              <Button variant="secondary" size="sm" onClick={() => navigate('/catalog')}>
                {t('Открыть каталог')}
              </Button>
            }
          >
            <Rows>
              {results.map((result) => {
                const card = byProgram.get(result.program)
                const entry = card?.my_entry ?? null
                const gap = result.breakdown.find((row) => !row.is_met && !row.is_unknown && row.gap_phrase)
                const tierTitle = TIERS.find((tier) => tier.value === entry?.tier)?.title
                return (
                  <div key={result.program} className="uni__item">
                    <Row
                      avatar={result.university_name}
                      title={result.university_name}
                      note={[result.program_name, result.country, tierTitle ? t(tierTitle) : '', entry && entry.added_by === 'student' && !entry.is_confirmed ? t('ждёт подтверждения') : ''].filter(Boolean).join(' · ')}
                      right={
                        <span className="catalog__acts">
                          {entry?.is_priority && <Chip tone="accent" size="sm">{t('приоритетный')}</Chip>}
                          {result.has_requirements ? (
                            <Chip tone={result.is_open ? 'good' : 'neutral'} size="sm">{result.is_open ? t('проходите') : `${result.percent}%`}</Chip>
                          ) : (
                            <Chip size="sm">{t('требования не заведены')}</Chip>
                          )}
                        </span>
                      }
                      acts={
                        <>
                          <Button variant="outline" size="sm" onClick={() => setOpen(open === result.program ? null : result.program)}>
                            {open === result.program ? t('Свернуть') : t('Разбор')}
                          </Button>
                          {entry && !entry.is_priority && (
                            <Button variant="ghost" size="sm" disabled={priority.isPending} onClick={() => priority.mutate(entry.id, { onSuccess: () => toast.success(t('Приоритетный вуз отмечен')), onError: (error) => toast.error(error.message) })}>
                              {t('Сделать приоритетным')}
                            </Button>
                          )}
                          {entry?.can_remove && (
                            <Button variant="ghost" size="sm" onClick={() => setEditing(editing === entry.id ? null : entry.id)}>
                              {t('Категория')}
                            </Button>
                          )}
                          {entry?.can_remove ? (
                            <Button variant="ghost" size="sm" disabled={remove.isPending} onClick={() => setDropping({ id: entry.id, name: `${result.university_name} · ${result.program_name}` })}>
                              {t('Убрать')}
                            </Button>
                          ) : (
                            <span className="t-note">{t('ведёт директор по поступлению')}</span>
                          )}
                        </>
                      }
                    />
                    {entry && editing === entry.id && (
                      <div className="acad__chips uni__sub">
                        <span className="t-note">{t('Куда отнести?')}</span>
                        {TIERS.map((tier) => (
                          <Button key={tier.value} variant={entry.tier === tier.value ? 'default' : 'outline'} size="sm" disabled={retier.isPending} onClick={() => retier.mutate({ id: entry.id, tier: tier.value }, { onSuccess: () => { setEditing(null); toast.success(t('Категория изменена')) }, onError: (error) => toast.error(error.message) })}>
                            {t(tier.title)}
                          </Button>
                        ))}
                      </div>
                    )}
                    {open === result.program && (
                      <div className="uni__sub">
                        {gap && !result.is_open && <p className="acad__note">{`${t('Не хватает')}: ${gap.gap_phrase}`}</p>}
                        {!result.is_verified && <UnverifiedNote note={result.verification_note} />}
                        <MatchBreakdown breakdown={result.breakdown} />
                        {card && card.rounds.length > 0 && (
                          <p className="t-note">
                            {t('Дедлайны раундов')}: {card.rounds.map((round) => `${round.round_type} · ${formatDate(round.deadline)}`).join(', ')}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </Rows>
          </DataCard>
        </div>
      </div>
      <ConfirmDialog
        open={dropping !== null}
        title={t('Убрать из списка?')}
        what={dropping ? `${t('Программа уйдёт из вашего списка:')} ${dropping.name}` : undefined}
        consequences={[t('Задачи по ней уйдут из плана. Добавить её снова можно из каталога.')]}
        confirmLabel={t('Убрать')}
        busy={remove.isPending}
        onCancel={() => setDropping(null)}
        onConfirm={() => dropping && remove.mutate(dropping.id, { onSuccess: () => { setDropping(null); toast.success(t('Программа убрана из списка')) }, onError: (error) => toast.error(error.message) })}
      />
    </div>
  )
}
