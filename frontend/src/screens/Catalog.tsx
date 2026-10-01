/**
 * Каталог вузов для ученика: фильтры слева, строки программ вместо карточек,
 * «чего не хватает» словами, подбор словами и «что откроется, если».
 *
 * Процент рядом с каждой программой — это соответствие требованиям,
 * не шанс поступления (инвариант №11). Ни одного вуза мимо справочника
 * здесь появиться не может: и каталог, и подбор берут записи из базы
 * (инвариант №10).
 */
import { useState } from 'react'
import { useAddToMyList, useCatalog, useCatalogFacets, usePickPrograms, useRemoveFromMyList, useWhatIf, type CatalogCard } from '../api/hooks'
import DataTable, { type Column } from '../components/DataTable'
import Field from '../components/Field'
import MatchCard from '../components/MatchCard'
import PhoneFold from '../components/PhoneFold'
import { Row, Rows, Segmented } from '../components/patterns'
import { Chip, counted, DataCard, ErrorNote, Loading, ScreenHead } from '../components/ui'
import { Button } from '../components/ui/button'
import { t, tk } from '../i18n'
import { formatDate } from '../lib/format'
import './catalog.css'

type Mode = 'catalog' | 'pick' | 'whatif'

const TIERS: { value: string; title: string; hint: string }[] = [
  { value: 'reach', title: 'reach', hint: tk('с запасом вверх') },
  { value: 'target', title: 'target', hint: tk('по силам') },
  { value: 'safety', title: 'safety', hint: tk('подстраховка') },
]

const LEVEL_TONE: Record<string, 'good' | 'warn' | 'neutral'> = { high: 'good', medium: 'warn', low: 'neutral' }

/** Чего не хватает — первая незакрытая позиция словами. */
function gapOf(card: CatalogCard): string {
  if (!card.has_requirements) return t('требования не заведены')
  if (card.is_open) return t('проходите')
  const gap = card.breakdown.find((row) => !row.is_met && !row.is_unknown && row.gap_phrase)
  return gap ? gap.gap_phrase : t('нет данных по части требований')
}

/** Кнопка «Добавить к себе» с выбором категории. */
function AddButton({ card, limitReached }: { card: CatalogCard; limitReached: boolean }) {
  const add = useAddToMyList()
  const remove = useRemoveFromMyList()
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (card.in_my_list) {
    const entry = card.my_entry!
    return (
      <span className="catalog__acts">
        <Chip tone="good" size="sm">{t('в списке')}</Chip>
        {entry.can_remove ? (
          <Button variant="ghost" size="sm" onClick={() => remove.mutate(entry.id)} disabled={remove.isPending}>
            {t('Убрать')}
          </Button>
        ) : (
          <span className="t-note">{t('добавил директор')}</span>
        )}
      </span>
    )
  }

  if (!open) {
    return (
      <Button variant="secondary" size="sm" onClick={() => setOpen(true)} disabled={limitReached}>
        {limitReached ? t('Список заполнен') : t('Добавить')}
      </Button>
    )
  }

  return (
    <span className="catalog__acts">
      {TIERS.map((tier) => (
        <Button
          key={tier.value}
          variant="outline"
          size="sm"
          disabled={add.isPending}
          title={t(tier.hint)}
          onClick={() => {
            setError(null)
            add.mutate(
              { program: card.program, tier: tier.value },
              {
                onSuccess: () => setOpen(false),
                onError: (e) => setError(e instanceof Error ? e.message : t('Не удалось добавить')),
              },
            )
          }}
        >
          {tier.title}
        </Button>
      ))}
      <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
        {t('Отмена')}
      </Button>
      {error && <Chip tone="bad" size="sm">{error}</Chip>}
    </span>
  )
}

/** «Что откроется, если»: прибавка к IELTS, SAT и GPA сегментами. */
function WhatIfPanel() {
  const [ielts, setIelts] = useState('0')
  const [sat, setSat] = useState('0')
  const [gpa, setGpa] = useState('0')
  const whatIf = useWhatIf()

  const run = (next: { ielts?: string; sat?: string; gpa?: string }) => {
    whatIf.mutate({
      ielts_delta: Number(next.ielts ?? ielts),
      sat_delta: Number(next.sat ?? sat),
      gpa_delta: Number(next.gpa ?? gpa),
    })
  }
  const data = whatIf.data
  const steps = (values: number[]) => values.map((value) => ({ value: String(value), label: value === 0 ? t('как есть') : `+${value}` }))

  return (
    <div className="acad__cols">
      <div className="acad__stack">
        {whatIf.isPending && <Loading kind="table" />}
        {data && (
          <>
            <DataCard title={t('Проходите полностью')} note={t('было {before}, станет {after}', { before: data.open_before, after: data.open_after })} />
            <div className="grid grid--cards">
              {data.results.map((row) => (
                <MatchCard key={row.program} card={row}>
                  <p className="t-note match__note">
                    {t('Соответствие {percent}% →', { percent: row.percent_before })} <b>{row.percent}%</b>
                    {row.became_open && (
                      <Chip tone="good" size="sm" className="catalog__badge">
                        {t('откроется')}
                      </Chip>
                    )}
                  </p>
                </MatchCard>
              ))}
            </div>
          </>
        )}
        {!data && !whatIf.isPending && <DataCard title={t('Пересчёт')} empty={t('подвиньте прибавку справа — список пересчитается')} />}
      </div>
      <div className="acad__stack">
        <DataCard title={t('Если сдать лучше')}>
          <div className="catalog__sliders">
            <span className="t-caps">IELTS</span>
            <Segmented value={ielts} onChange={(value) => { setIelts(value); run({ ielts: value }) }} label="IELTS" items={steps([0, 0.5, 1, 1.5, 2])} />
            <span className="t-caps">SAT</span>
            <Segmented value={sat} onChange={(value) => { setSat(value); run({ sat: value }) }} label="SAT" items={steps([0, 50, 100, 150, 200, 300])} />
            <span className="t-caps">GPA</span>
            <Segmented value={gpa} onChange={(value) => { setGpa(value); run({ gpa: value }) }} label="GPA" items={steps([0, 0.1, 0.2, 0.3, 0.5])} />
          </div>
        </DataCard>
      </div>
    </div>
  )
}

/** Подбор словами: модель видит только справочник. */
function PickPanel({ limitReached }: { limitReached: boolean }) {
  const [text, setText] = useState('')
  const pick = usePickPrograms()

  return (
    <div className="acad__cols">
      <div className="acad__stack">
        <DataCard title={t('Расскажите, чего хотите')}>
          <Field kind="textarea" name="wish" label={t('Что важно')} value={text} onChange={setText} rows={3} placeholder={t('Например: хочу в Канаду на Computer Science, важна стоимость обучения')} />
          <div className="acad__actions">
            <Button size="sm" onClick={() => pick.mutate(text)} disabled={pick.isPending || text.trim() === ''}>
              {pick.isPending ? t('Подбираю…') : t('Подобрать')}
            </Button>
          </div>
        </DataCard>
        {pick.error && <ErrorNote error={pick.error} />}
        {pick.data && (
          <>
            <div className="grid grid--cards">
              {pick.data.picks.map((row) => (
                <MatchCard key={row.program} card={row} actions={<AddButton card={row} limitReached={limitReached} />}>
                  <div className="catalog__why">
                    <p>
                      <b>{t('Почему подходит.')}</b> {row.why}
                    </p>
                    {row.missing && (
                      <p>
                        <b>{t('Чего не хватает.')}</b> {row.missing}
                      </p>
                    )}
                    {row.next_round && (
                      <p>
                        <b>{t('Ближайший раунд.')}</b> {t('{round} до {date}', { round: row.next_round.round_title, date: formatDate(row.next_round.deadline) })}
                      </p>
                    )}
                  </div>
                </MatchCard>
              ))}
            </div>
            {pick.data.note && <p className="t-note catalog__note">{pick.data.note}</p>}
            {pick.data.picks.length === 0 && <DataCard title={t('Подобрать не из чего')} empty={t('справочник вузов ещё не наполнен')} />}
          </>
        )}
      </div>
    </div>
  )
}

export default function Catalog() {
  const [mode, setMode] = useState<Mode>('catalog')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const facets = useCatalogFacets()
  const catalog = useCatalog(filters)

  const cards = catalog.data?.results ?? []
  const inList = cards.filter((c) => c.in_my_list).length
  const limit = facets.data?.list_limit ?? 15
  const limitReached = inList >= limit

  const setFilter = (name: string, value: string) => setFilters((prev) => ({ ...prev, [name]: value }))
  const hasFilters = Object.values(filters).some(Boolean)

  const columns: Column<CatalogCard>[] = [
    {
      key: 'program',
      title: t('Программа'),
      width: '34%',
      cell: (card) => (
        <>
          <b>{card.university_name}</b>
          <span className="t-note"> · {card.program_name}</span>
          {!card.is_verified && (
            <Chip tone="warn" size="sm" className="catalog__badge">
              {t('не подтверждено')}
            </Chip>
          )}
        </>
      ),
      sortBy: (card) => card.university_name,
    },
    {
      key: 'match',
      title: t('Соотв.'),
      width: '12%',
      align: 'right',
      cell: (card) => (card.has_requirements ? <Chip tone={LEVEL_TONE[card.level] ?? 'neutral'} size="sm">{`${card.percent}%`}</Chip> : <span className="t-note">{t('нет')}</span>),
      sortBy: (card) => (card.has_requirements ? card.percent : null),
    },
    { key: 'gap', title: t('Чего не хватает'), width: '22%', cell: (card) => <span className={card.is_open ? 'text-good' : undefined}>{gapOf(card)}</span> },
    {
      key: 'deadline',
      title: t('Дедлайн'),
      width: '12%',
      align: 'right',
      cell: (card) => (card.rounds[0] ? <span className="num">{formatDate(card.rounds[0].deadline)}</span> : <span className="t-note">{t('нет')}</span>),
      sortBy: (card) => card.rounds[0]?.deadline ?? null,
    },
    { key: 'add', title: t('В список'), width: '20%', cell: (card) => <AddButton card={card} limitReached={limitReached} /> },
  ]

  const filterCard = (
    <DataCard title={t('Фильтры')} right={hasFilters ? <Button variant="link" size="sm" onClick={() => setFilters({})}>{t('Сбросить')}</Button> : undefined}>
      <Field kind="text" name="search" label={t('Поиск')} value={filters.search ?? ''} onChange={(value) => setFilter('search', value)} placeholder={t('Вуз или программа')} />
      <Field kind="select" name="level" label={t('Соответствие')} value={filters.level ?? ''} onChange={(value) => setFilter('level', value)} placeholder={t('Любое')} options={(facets.data?.levels ?? []).map((level) => ({ value: level.code, title: `${level.title} · ${level.from}–${level.to}%` }))} />
      <Field kind="select" name="country" label={t('Страна')} value={filters.country ?? ''} onChange={(value) => setFilter('country', value)} placeholder={t('Все страны')} options={(facets.data?.countries ?? []).map((country) => ({ value: country, title: t(country) }))} />
      <Field kind="select" name="major" label={t('Специальность')} value={filters.major ?? ''} onChange={(value) => setFilter('major', value)} placeholder={t('Все специальности')} options={(facets.data?.majors ?? []).map((major) => ({ value: major, title: major }))} />
      <Field kind="select" name="round_type" label={t('Раунд')} value={filters.round_type ?? ''} onChange={(value) => setFilter('round_type', value)} placeholder={t('Любой раунд')} options={(facets.data?.round_types ?? []).map((round) => ({ value: round, title: round }))} />
    </DataCard>
  )

  return (
    <div>
      <ScreenHead
        title={t('Каталог вузов')}
        subtitle={`${counted(catalog.data?.count ?? 0, 'программа|программы|программ')} · ${t('в списке {count} из {limit}', { count: inList, limit })}`}
      />

      <div className="acad__toolbar">
        <Segmented<Mode>
          value={mode}
          onChange={setMode}
          label={t('Режим')}
          items={[
            { value: 'catalog', label: t('Каталог') },
            { value: 'pick', label: t('Подобрать словами') },
            { value: 'whatif', label: t('Что откроется, если') },
          ]}
        />
      </div>

      {mode === 'pick' && <PickPanel limitReached={limitReached} />}
      {mode === 'whatif' && <WhatIfPanel />}

      {mode === 'catalog' && (
        <div className="catalog__layout">
          <PhoneFold active={hasFilters}>{filterCard}</PhoneFold>
          <div className="acad__stack">
            {catalog.error && <ErrorNote error={catalog.error} />}
            {catalog.isLoading && !catalog.data && <Loading kind="table" />}
            {catalog.data && (
              <div className="card">
                <DataTable
                  columns={columns}
                  rows={cards}
                  rowKey={(card) => card.program}
                  limit={30}
                  empty={
                    <Rows>
                      <Row
                        icon="search"
                        title={hasFilters ? t('По этим фильтрам ничего нет') : t('В справочнике пока нет программ')}
                        note={hasFilters ? t('Снимите часть фильтров') : t('Программы заводит директор по поступлению')}
                        acts={hasFilters ? <Button variant="secondary" size="sm" onClick={() => setFilters({})}>{t('Снять фильтры')}</Button> : undefined}
                      />
                    </Rows>
                  }
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
