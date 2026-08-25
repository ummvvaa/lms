/**
 * Каталог вузов для ученика: поиск, фильтры, соответствие, подбор словами.
 *
 * Процент рядом с каждой программой — это соответствие требованиям,
 * не шанс поступления (инвариант №11). Ни одного вуза мимо справочника
 * здесь появиться не может: и каталог, и подбор берут записи из базы
 * (инвариант №10).
 */
import { useState } from 'react'
import {
  useAddToMyList,
  useCatalog,
  useCatalogFacets,
  usePickPrograms,
  useRemoveFromMyList,
  useWhatIf,
  type CatalogCard,
} from '../api/hooks'
import Empty from '../components/Empty'
import MatchCard from '../components/MatchCard'
import { ErrorNote, Loading, ScreenHead } from '../components/ui'
import './catalog.css'
import { t } from '../i18n'

type Mode = 'catalog' | 'pick' | 'whatif'

const TIERS: { value: string; title: string; hint: string }[] = [
  { value: 'reach', title: 'reach', hint: 'с запасом вверх' },
  { value: 'target', title: 'target', hint: 'по силам' },
  { value: 'safety', title: 'safety', hint: 'подстраховка' },
]

/** Кнопка «Добавить к себе» с выбором категории. */
function AddButton({ card, limitReached }: { card: CatalogCard; limitReached: boolean }) {
  const add = useAddToMyList()
  const remove = useRemoveFromMyList()
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (card.in_my_list) {
    const entry = card.my_entry!
    return (
      <>
        <span className="chip chip-ok">{t('уже в вашем списке')}</span>
        {entry.can_remove ? (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => remove.mutate(entry.id)}
            disabled={remove.isPending}
          >
            {t('Убрать')}
          </button>
        ) : (
          <span className="muted catalog__hint">{t('добавил директор — снять может он')}</span>
        )}
      </>
    )
  }

  if (!open) {
    return (
      <button className="btn btn-primary btn-sm" onClick={() => setOpen(true)} disabled={limitReached}>
        {limitReached ? 'Список заполнен' : 'Добавить к себе'}
      </button>
    )
  }

  return (
    <>
      <span className="muted catalog__hint">{t('Куда отнести?')}</span>
      {TIERS.map((tier) => (
        <button
          key={tier.value}
          className="btn btn-ghost btn-sm"
          disabled={add.isPending}
          onClick={() => {
            setError(null)
            add.mutate(
              { program: card.program, tier: tier.value },
              {
                onSuccess: () => setOpen(false),
                onError: (e) => setError(e instanceof Error ? e.message : 'Не удалось добавить'),
              },
            )
          }}
        >
          {tier.title} <span className="muted">· {tier.hint}</span>
        </button>
      ))}
      <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
        {t('Отмена')}
      </button>
      {error && <span className="chip chip-risk">{error}</span>}
    </>
  )
}

/** «Что откроется, если»: ползунки по IELTS, SAT и GPA. */
function WhatIfPanel() {
  const [ielts, setIelts] = useState(0)
  const [sat, setSat] = useState(0)
  const [gpa, setGpa] = useState(0)
  const whatIf = useWhatIf()

  const run = (next: { ielts?: number; sat?: number; gpa?: number }) => {
    const payload = {
      ielts_delta: next.ielts ?? ielts,
      sat_delta: next.sat ?? sat,
      gpa_delta: next.gpa ?? gpa,
    }
    whatIf.mutate(payload)
  }

  const data = whatIf.data

  return (
    <div>
      <div className="card card-pad catalog__sliders">
        <span className="eyebrow">{t('Подвигайте ползунки')}</span>
        <label className="catalog__slider">
          <span>
            IELTS <b className="num">+{ielts.toFixed(1)}</b>
          </span>
          <input
            type="range"
            min={0}
            max={2}
            step={0.5}
            value={ielts}
            onChange={(e) => {
              const value = Number(e.target.value)
              setIelts(value)
              run({ ielts: value })
            }}
          />
        </label>
        <label className="catalog__slider">
          <span>
            SAT <b className="num">+{sat}</b>
          </span>
          <input
            type="range"
            min={0}
            max={300}
            step={10}
            value={sat}
            onChange={(e) => {
              const value = Number(e.target.value)
              setSat(value)
              run({ sat: value })
            }}
          />
        </label>
        <label className="catalog__slider">
          <span>
            GPA <b className="num">+{gpa.toFixed(1)}</b>
          </span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={gpa}
            onChange={(e) => {
              const value = Number(e.target.value)
              setGpa(value)
              run({ gpa: value })
            }}
          />
        </label>
        <p className="muted catalog__hint">
          {t('Это пересчёт по заведённым требованиям, а не обещание. Ничего не сохраняется.')}
        </p>
      </div>

      {whatIf.isPending && <Loading />}
      {data && (
        <>
          <p className="chip chip-ok">
            Проходите полностью: было {data.open_before}, станет {data.open_after}
          </p>
          <div className="grid grid--cards">
            {data.results.map((row) => (
              <MatchCard key={row.program} card={row}>
                <p className="muted match__note">
                  Соответствие {row.percent_before}% → <b>{row.percent}%</b>
                  {row.became_open && <span className="chip chip-ok catalog__badge">{t('откроется')}</span>}
                </p>
              </MatchCard>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

/** Подбор словами: модель видит только справочник. */
function PickPanel({ limitReached }: { limitReached: boolean }) {
  const [text, setText] = useState('')
  const pick = usePickPrograms()

  return (
    <div>
      <div className="card card-pad">
        <span className="eyebrow">{t('Расскажите, чего хотите')}</span>
        <textarea
          className="assistant__input"
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t('Например: хочу в Канаду на Computer Science, важна стоимость обучения')}
        />
        <div className="toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
          <span className="toolbar__spacer" />
          <button
            className="btn btn-primary btn-sm"
            onClick={() => pick.mutate(text)}
            disabled={pick.isPending || text.trim() === ''}
          >
            {pick.isPending ? 'Подбираю…' : 'Подобрать'}
          </button>
        </div>
      </div>

      {pick.error && <ErrorNote error={pick.error} />}
      {pick.data && (
        <>
          {pick.data.note && <p className="card card-pad catalog__note">{pick.data.note}</p>}
          <div className="grid grid--cards">
            {pick.data.picks.map((row) => (
              <MatchCard
                key={row.program}
                card={row}
                actions={<AddButton card={row} limitReached={limitReached} />}
              >
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
                      <b>{t('Ближайший раунд.')}</b> {row.next_round.round_title} до{' '}
                      {new Date(row.next_round.deadline).toLocaleDateString('ru')}
                    </p>
                  )}
                </div>
              </MatchCard>
            ))}
            {pick.data.picks.length === 0 && (
              <p className="muted">{t('Подобрать не из чего — справочник вузов ещё не наполнен.')}</p>
            )}
          </div>
        </>
      )}
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
  // «ничего не нашлось» и «справочник пуст» — разные новости, и говорить
  // о них надо по-разному
  const hasFilters = Object.values(filters).some(Boolean)

  return (
    <div>
      <ScreenHead
        title={t('Каталог вузов')}
        subtitle={t(
          'Процент показывает, насколько ваши баллы отвечают требованиям программы. Поступление зависит ещё и от эссе, портфолио и конкурса.',
        )}
      />

      <div className="toolbar">
        <button
          className={`tab${mode === 'catalog' ? ' tab--active' : ''}`}
          onClick={() => setMode('catalog')}
        >
          {t('Каталог')}
        </button>
        <button className={`tab${mode === 'pick' ? ' tab--active' : ''}`} onClick={() => setMode('pick')}>
          {t('Подобрать словами')}
        </button>
        <button className={`tab${mode === 'whatif' ? ' tab--active' : ''}`} onClick={() => setMode('whatif')}>
          {t('Что откроется, если')}
        </button>
        <span className="toolbar__spacer" />
        <span className={`chip ${limitReached ? 'chip-warn' : 'chip-mute'} num`}>
          в списке {inList} из {limit}
        </span>
      </div>

      {mode === 'pick' && <PickPanel limitReached={limitReached} />}
      {mode === 'whatif' && <WhatIfPanel />}

      {mode === 'catalog' && (
        <>
          <div className="toolbar">
            <input
              className="input"
              placeholder={t('Вуз или программа')}
              value={filters.search ?? ''}
              onChange={(e) => setFilter('search', e.target.value)}
            />
            <select
              className="input"
              value={filters.country ?? ''}
              onChange={(e) => setFilter('country', e.target.value)}
            >
              <option value="">{t('Все страны')}</option>
              {(facets.data?.countries ?? []).map((country) => (
                <option key={country} value={country}>
                  {country}
                </option>
              ))}
            </select>
            <select
              className="input"
              value={filters.major ?? ''}
              onChange={(e) => setFilter('major', e.target.value)}
            >
              <option value="">{t('Все специальности')}</option>
              {(facets.data?.majors ?? []).map((major) => (
                <option key={major} value={major}>
                  {major}
                </option>
              ))}
            </select>
            <select
              className="input"
              value={filters.round_type ?? ''}
              onChange={(e) => setFilter('round_type', e.target.value)}
            >
              <option value="">{t('Любой раунд')}</option>
              {(facets.data?.round_types ?? []).map((round) => (
                <option key={round} value={round}>
                  {round}
                </option>
              ))}
            </select>
            <select
              className="input"
              value={filters.level ?? ''}
              onChange={(e) => setFilter('level', e.target.value)}
            >
              <option value="">{t('Любое соответствие')}</option>
              {(facets.data?.levels ?? []).map((level) => (
                <option key={level.code} value={level.code}>
                  {level.from}–{level.to}% · {level.title}
                </option>
              ))}
            </select>
            <span className="chip chip-mute num">{catalog.data?.count ?? 0}</span>
          </div>

          {catalog.isLoading && <Loading />}
          {catalog.error && <ErrorNote error={catalog.error} />}

          <div className="grid grid--cards">
            {cards.map((card) => (
              <MatchCard
                key={card.program}
                card={card}
                actions={<AddButton card={card} limitReached={limitReached} />}
              />
            ))}
          </div>
          {!catalog.isLoading && cards.length === 0 && (
            <Empty
              title={hasFilters ? 'По этим фильтрам ничего нет' : 'В справочнике пока нет программ'}
              what={
                hasFilters
                  ? 'Под эти фильтры не подошла ни одна программа — снимите часть.'
                  : 'Программы заводит директор по поступлению — как появятся, они будут здесь.'
              }
              hint={
                hasFilters
                  ? 'Фильтры складываются: страна, специальность и уровень соответствия сужают выдачу одновременно.'
                  : 'Каталог строится только из справочника школы: выдуманных вузов в нём быть не может.'
              }
              action={hasFilters ? 'Снять фильтры' : undefined}
              onAction={hasFilters ? () => setFilters({}) : undefined}
            />
          )}
        </>
      )}
    </div>
  )
}
