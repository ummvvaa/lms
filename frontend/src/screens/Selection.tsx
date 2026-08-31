/**
 * Подбор вузов (фаза 40): запуск, экран расчёта, результат-снимок.
 *
 * Расчёт идёт в фоне: экран можно свернуть, поверх любого другого висит
 * плашка с процентом. Результат — датированный снимок: шапка показывает
 * профиль, из которого считалось, воронка объясняет, как построена
 * подборка, а раскрывающийся разбор — из чего сложился каждый процент.
 *
 * Все числа здесь — соответствие требованиям, не шанс поступления
 * (инвариант №11): это закреплено тестом по текстам экрана.
 */
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  useActiveSelection,
  useFavorites,
  useSelectionExplain,
  useSelectionRun,
  useSelectionRuns,
  useStartSelection,
  type SelectionResultRow,
  type SelectionRun,
} from '../api/hooks'
import { useCatalogFacets, useAddToMyList } from '../api/hooks'
import Icon from '../layout/icons'
import { Bar, DataCard, ErrorNote, Loading, Metric, MetricRow, ScreenHead } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { NativeSelect, NativeSelectOption } from '../components/ui/native-select'
import { t } from '../i18n'

const TIER_TONE: Record<string, 'indigo' | 'warn' | 'teal' | 'ok'> = {
  dream: 'indigo',
  reach: 'warn',
  match: 'teal',
  safety: 'ok',
}

const TIER_NOTE: Record<string, string> = {
  dream: 'Очень конкурентно, но стоит попробовать',
  reach: 'Амбициозно: нужны усилия, но достижимо',
  match: 'Реалистично при текущей траектории',
  safety: 'Вы уже соответствуете или превышаете требования',
}

/** Форма запуска: специальность, уровень, страны из справочника. */
function LaunchForm({ onStarted }: { onStarted: (run: SelectionRun) => void }) {
  const start = useStartSelection()
  const facets = useCatalogFacets()
  const [major, setMajor] = useState('')
  const [level, setLevel] = useState('')
  const [countries, setCountries] = useState<string[]>([])

  const allCountries: string[] = facets.data?.countries ?? []

  return (
    <div className="card card-pad sel__launch">
      <span className="eyebrow">{t('Новый подбор')}</span>
      <p className="muted sel__note">
        {t('Подбор идёт по справочнику школы и считает соответствие требованиям программ.')}
      </p>
      <div className="sel__fields">
        <label className="propose__field">
          <span className="muted propose__label">{t('Специальность')}</span>
          <Input value={major} placeholder="Computer Science" onChange={(e) => setMajor(e.target.value)} />
        </label>
        <label className="propose__field">
          <span className="muted propose__label">{t('Уровень')}</span>
          <NativeSelect size="sm" value={level} onChange={(e) => setLevel(e.target.value)}>
            <NativeSelectOption value="">{t('Любой')}</NativeSelectOption>
            <NativeSelectOption value="bachelor">{t('Бакалавриат')}</NativeSelectOption>
            <NativeSelectOption value="master">{t('Магистратура')}</NativeSelectOption>
            <NativeSelectOption value="foundation">Foundation</NativeSelectOption>
          </NativeSelect>
        </label>
        <div className="propose__field">
          <span className="muted propose__label">{t('Страны (пусто — весь справочник)')}</span>
          <div className="sel__countries">
            {allCountries.map((country) => (
              <Button
                key={country}
                variant={countries.includes(country) ? 'default' : 'outline'}
                size="sm"
                onClick={() =>
                  setCountries((prev) =>
                    prev.includes(country) ? prev.filter((c) => c !== country) : [...prev, country],
                  )
                }
              >
                {country}
              </Button>
            ))}
            {allCountries.length === 0 && <span className="muted">{t('Справочник пока пуст')}</span>}
          </div>
        </div>
      </div>
      <div className="propose__actions">
        <Button
          disabled={start.isPending}
          onClick={() =>
            start.mutate(
              { major, level, countries },
              {
                onSuccess: (run) => onStarted(run),
                onError: (error) => toast.error(error.message),
              },
            )
          }
        >
          {t('Запустить подбор')}
        </Button>
      </div>
    </div>
  )
}

/** Экран расчёта: этапы отмечаются по мере прохождения. */
function Progress({ run }: { run: SelectionRun }) {
  const navigate = useNavigate()
  return (
    <div className="card card-pad sel__progress">
      <span className="eyebrow">{t('Идёт расчёт')}</span>
      <div className="row-between" style={{ margin: '8px 0' }}>
        <b>{run.major || t('Все специальности')}</b>
        <b className="num">{run.progress}%</b>
      </div>
      <Bar percent={run.progress} />
      <ul className="rows__list" style={{ marginTop: 12 }}>
        {run.stages.map((stage, index) => {
          const done = run.progress >= stage.at && run.stage !== stage.code
          const current = run.stage === stage.code
          return (
            <li
              key={stage.code}
              className="rows__item"
              style={current ? undefined : { opacity: done ? 1 : 0.55 }}
            >
              <div className="rows__body">
                <span className="rows__label">
                  {done ? '✓ ' : `${index + 1}. `}
                  {t(stage.title)}
                  {current && <Badge variant="teal">{t('сейчас')}</Badge>}
                </span>
              </div>
            </li>
          )
        })}
      </ul>
      <div className="propose__actions" style={{ marginTop: 12 }}>
        <Button variant="outline" size="sm" onClick={() => navigate('/dashboard')}>
          {t('Свернуть — расчёт продолжится')}
        </Button>
      </div>
    </div>
  )
}

/** Раскрывающийся разбор «почему такой процент» — живой, по позициям. */
function Explain({ run, program }: { run: number; program: number }) {
  const { data, isLoading } = useSelectionExplain(run, program)
  if (isLoading) return <p className="muted sel__note">{t('Считаю разбор…')}</p>
  if (!data) return null
  return (
    <div className="sel__explain">
      {data.profile_changed && data.profile_changed_note && (
        <p className="muted sel__note">{data.profile_changed_note}</p>
      )}
      {!data.is_verified && data.verification_note && (
        <Badge variant="warn" className="badge--line">
          {data.verification_note}
        </Badge>
      )}
      {data.breakdown.map((row) => (
        <div key={row.code} className="sel__position">
          <div className="row-between">
            <span>
              {row.title}{' '}
              <span className="muted">
                · {t('вес')} {Math.round(row.weight)}%
              </span>
            </span>
            <b className="num">{row.percent}%</b>
          </div>
          <Bar percent={row.percent} color={row.is_met ? 'var(--ok)' : 'var(--warn)'} />
          {row.criteria.map((criterion) => (
            <p key={criterion.title} className="muted sel__note">
              {criterion.title}: {criterion.current ?? '—'} {t('при пороге')} {criterion.threshold}
              {criterion.gap > 0 ? ` — ${t('не хватает')} ${criterion.gap}` : ''}
            </p>
          ))}
        </div>
      ))}
      <p className="muted sel__note">{data.summary}</p>
    </div>
  )
}

/** Карточка вуза в результате: два числа — и оба соответствие, не шанс. */
function ResultCard({ run, row }: { run: SelectionRun; row: SelectionResultRow }) {
  const favorites = useFavorites(false)
  const addToList = useAddToMyList()
  const [open, setOpen] = useState(false)
  const [favorite, setFavorite] = useState(row.is_favorite)

  const toggleFavorite = () => {
    const action = favorite ? favorites.remove : favorites.add
    action.mutate(row.program, {
      onSuccess: () => setFavorite(!favorite),
      onError: (error) => toast.error(error.message),
    })
  }

  return (
    <div className="card card-pad sel__uni" data-program={row.program}>
      <div className="sel__unihead">
        <span className="sel__logo" aria-hidden>
          {row.university_name.slice(0, 1)}
        </span>
        <div className="sel__uniname">
          <b>{row.university_name}</b>
          <span className="muted sel__note">
            {row.country}
            {row.world_rank ? ` · #${row.world_rank}` : ''} · {row.program_name}
          </span>
        </div>
        {row.tier && <Badge variant={TIER_TONE[row.tier] ?? 'mute'}>{row.tier}</Badge>}
        <button
          className={`sel__heart${favorite ? ' sel__heart--on' : ''}`}
          aria-label={favorite ? t('Убрать из избранного') : t('В избранное')}
          onClick={toggleFavorite}
        >
          <Icon name="heart" size={18} />
        </button>
      </div>

      <MetricRow>
        <Metric value={`${row.percent_now}%`} label={t('Соответствие сейчас')} />
        <Metric value={`${row.percent_goal}%`} label={t('Если закрыть разрывы')} tone="ok" />
      </MetricRow>
      {row.tier && <p className="muted sel__note">{t(TIER_NOTE[row.tier] ?? '')}</p>}

      <div className="propose__actions">
        <Button variant="outline" size="sm" onClick={() => setOpen(!open)}>
          {open ? t('Свернуть разбор') : t('Почему такой процент')}
        </Button>
        {!row.in_my_list && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              addToList.mutate(
                // категории списка подачи остались тройкой reach/target/safety
                {
                  program: row.program,
                  tier: { dream: 'reach', reach: 'reach', match: 'target' }[row.tier] ?? 'safety',
                },
                {
                  onSuccess: () => toast.success(t('Добавлено в ваш список')),
                  onError: (error) => toast.error(error.message),
                },
              )
            }
          >
            {t('В мой список')}
          </Button>
        )}
      </div>
      {open && <Explain run={run.id} program={row.program} />}
    </div>
  )
}

/** Сворачиваемая секция результата. */
function Section({
  title,
  note,
  children,
  count,
}: {
  title: string
  note?: string
  count: number
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(true)
  return (
    <section className="sel__section">
      <div className="row-between sel__sectionhead">
        <span className="eyebrow">
          {title}{' '}
          <Badge variant="mute" className="num">
            {count}
          </Badge>
        </span>
        <Button variant="ghost" size="sm" onClick={() => setOpen(!open)}>
          {open ? t('Свернуть') : t('Развернуть')}
        </Button>
      </div>
      {note && open && <p className="muted sel__note">{note}</p>}
      {open && children}
    </section>
  )
}

function Result({ run }: { run: SelectionRun }) {
  const navigate = useNavigate()
  const [showHow, setShowHow] = useState(false)
  const results = run.results ?? []
  const top = results.filter((r) => r.section === 'top')
  const strong = results.filter((r) => r.section === 'strong')
  const other = results.filter((r) => r.section === 'other')
  const tiers: [string, SelectionResultRow[]][] = ['dream', 'reach', 'match', 'safety']
    .map((tier) => [tier, top.filter((r) => r.tier === tier)] as [string, SelectionResultRow[]])
    .filter(([, rows]) => rows.length > 0)

  return (
    <div>
      <div className="card card-pad sel__head">
        <div className="row-between">
          <div>
            <span className="eyebrow">
              {t('Подбор от')} {new Date(run.created_at).toLocaleDateString('ru')}
            </span>
            <div className="t-card" style={{ fontWeight: 650 }}>
              {run.major || t('Все специальности')}
              {run.level_title ? ` · ${run.level_title}` : ''}
            </div>
            <p className="muted sel__note">
              {run.countries.length > 0
                ? `${t('Страны:')} ${run.countries.join(', ')}`
                : t('Страны: весь справочник школы')}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate('/selection')}>
            {t('Перезапустить с другими условиями')}
          </Button>
        </div>
        <MetricRow>
          <Metric value={run.profile.gpa ?? '—'} label="GPA" />
          <Metric value={run.profile.ielts ?? '—'} label="IELTS" />
          <Metric value={run.profile.sat ?? '—'} label="SAT" />
          <Metric value={run.profile.grade ?? '—'} label={t('Класс')} />
          <Metric value={run.profile.graduation_year ?? '—'} label={t('Выпуск')} />
        </MetricRow>
        <p className="muted sel__note">
          {t('Это профиль на момент запуска — результат считался от него, а не от сегодняшнего.')}
        </p>
      </div>

      <div className="sel__strategy">
        <DataCard title={t('Текущая позиция')} accent="teal">
          <p className="sel__text">{run.strategy.position}</p>
        </DataCard>
        <DataCard title={t('Что важно усилить')} accent="warn">
          <p className="sel__text">{run.strategy.improve}</p>
        </DataCard>
        <DataCard title={t('Следующий шаг')} accent="brand">
          <p className="sel__text">{run.strategy.next_step}</p>
        </DataCard>
      </div>
      {run.strategy.offline && (
        <p className="muted sel__note">
          {t('Стратегия собрана правилами из движка соответствия: модель сейчас не подключена.')}
        </p>
      )}

      <div className="card card-pad">
        <span className="eyebrow">{t('Как построена подборка')}</span>
        <div className="sel__funnel">
          <Metric value={run.funnel.catalog} label={t('Программ в каталоге')} />
          <Metric value={run.funnel.filtered} label={t('Прошли фильтр')} />
          <Metric value={run.funnel.analyzed} label={t('Разобраны подробно')} />
          <Metric value={run.funnel.final} label={t('В финальном списке')} />
        </div>
        {Object.keys(run.tiers ?? {}).length > 0 && (
          <p className="muted sel__note">
            {t('По категориям:')}{' '}
            {Object.entries(run.tiers ?? {})
              .map(([tier, n]) => `${tier} — ${n}`)
              .join(', ')}
          </p>
        )}
        {run.countries.length === 0 && (
          <p className="muted sel__note">
            {t('Подбор шёл без фильтра стран.')}{' '}
            <Button variant="link" size="sm" onClick={() => navigate('/selection')}>
              {t('Запустить новый подбор с фильтром стран')}
            </Button>
          </p>
        )}
        <Button variant="outline" size="sm" onClick={() => setShowHow(!showHow)}>
          {showHow ? t('Скрыть объяснение') : t('Как считаются проценты и категории')}
        </Button>
        {showHow && (
          <ul className="sel__how">
            {(run.methodology ?? []).map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        )}
      </div>

      {tiers.map(([tier, rows]) => (
        <Section key={tier} title={tier.toUpperCase()} note={t(TIER_NOTE[tier] ?? '')} count={rows.length}>
          <div className="grid grid--two">
            {rows.map((row) => (
              <ResultCard key={row.id} run={run} row={row} />
            ))}
          </div>
        </Section>
      ))}

      {strong.length > 0 && (
        <Section
          title={t('Ещё сильные варианты')}
          note={t('Прошли подробный разбор, но не вошли в финальный список.')}
          count={strong.length}
        >
          <div className="grid grid--two">
            {strong.map((row) => (
              <ResultCard key={row.id} run={run} row={row} />
            ))}
          </div>
        </Section>
      )}

      {other.length > 0 && (
        <Section
          title={t('Другие университеты')}
          note={t(
            'Прошли фильтр по специальности, но подробно не разбирались. Порядок — по мировому рейтингу.',
          )}
          count={other.length}
        >
          <ul className="rows__list">
            {other.map((row) => (
              <li key={row.id} className="rows__item">
                <div className="rows__body">
                  <span className="rows__label">{row.university_name}</span>
                  <span className="muted rows__note">
                    {row.country}
                    {row.world_rank ? ` · #${row.world_rank}` : ''} · {row.program_name}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <div className="card card-pad">
        <span className="eyebrow">{t('Что дальше')}</span>
        <ol className="sel__next">
          <li>
            {t('Соберите шорт-лист: отметьте сердечком то, что присмотрели')} →{' '}
            <Button variant="link" size="sm" onClick={() => navigate('/favorites')}>
              {t('Избранное')}
            </Button>
          </li>
          <li>{t('Добавьте лучшие программы в свой список подачи — из карточек выше')}</li>
          <li>
            {t('Отслеживайте дедлайны и заявки')} →{' '}
            <Button variant="link" size="sm" onClick={() => navigate('/universities')}>
              {t('Мои вузы')}
            </Button>
          </li>
        </ol>
      </div>
    </div>
  )
}

export default function Selection() {
  const { id } = useParams()
  const navigate = useNavigate()
  const runId = id ? Number(id) : null
  const run = useSelectionRun(runId)
  const runs = useSelectionRuns()
  const active = useActiveSelection()

  if (runId !== null) {
    if (run.isLoading) return <Loading kind="cards" />
    if (run.error) return <ErrorNote error={run.error} />
    if (!run.data) return null
    return (
      <div>
        <ScreenHead
          title={t('Подбор вузов')}
          subtitle={t('Соответствие требованиям программ из справочника — не шанс поступления.')}
        />
        {run.data.status === 'running' && <Progress run={run.data} />}
        {run.data.status === 'failed' && (
          <ErrorNote error={new Error(run.data.error || t('Подбор не получился — запустите заново'))} />
        )}
        {run.data.status === 'done' && <Result run={run.data} />}
      </div>
    )
  }

  const history = runs.data?.results ?? []
  const running = active.data?.run

  return (
    <div>
      <ScreenHead
        title={t('Подбор вузов')}
        subtitle={t('Соответствие требованиям программ из справочника — не шанс поступления.')}
      />
      {running && (
        <div className="card card-pad card--accent card--teal" style={{ marginBottom: 16 }}>
          <div className="row-between">
            <span>
              {t('Идёт расчёт')}: <b>{running.major || t('все специальности')}</b>
            </span>
            <Button size="sm" onClick={() => navigate(`/selection/${running.id}`)}>
              {t('Открыть')} · {running.progress}%
            </Button>
          </div>
        </div>
      )}
      {!running && <LaunchForm onStarted={(started) => navigate(`/selection/${started.id}`)} />}

      <div className="card card-pad" style={{ marginTop: 16 }}>
        <span className="eyebrow">{t('История подборов')}</span>
        {history.length === 0 && (
          <p className="muted">{t('Подборов ещё не было — запустите первый, это пара минут.')}</p>
        )}
        <ul className="rows__list">
          {history.map((row) => (
            <li key={row.id} className="rows__item">
              <div className="rows__body">
                <span className="rows__label">
                  {new Date(row.created_at).toLocaleDateString('ru')} · {row.major || t('все специальности')}
                </span>
                <span className="muted rows__note">
                  {row.countries.length > 0 ? row.countries.join(', ') : t('без фильтра стран')} ·{' '}
                  {row.status_title}
                </span>
              </div>
              <Button variant="outline" size="sm" onClick={() => navigate(`/selection/${row.id}`)}>
                {t('Смотреть результат')}
              </Button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
