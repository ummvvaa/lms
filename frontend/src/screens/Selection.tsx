/**
 * Подбор вузов: запуск, экран расчёта, результат-снимок.
 *
 * Форма подбора — левая колонка, справа «как считается» и история подборов.
 * Расчёт идёт в фоне: экран можно свернуть. Результат — датированный снимок:
 * шапка показывает профиль, из которого считалось, воронка объясняет,
 * как построена подборка, а раскрывающийся разбор — из чего сложился процент.
 *
 * Все числа здесь — соответствие требованиям, не шанс поступления
 * (инвариант №11): это закреплено тестом по текстам экрана.
 */
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  useActiveSelection,
  useAddToMyList,
  useCatalogFacets,
  useFavorites,
  usePlanActions,
  useSelectionExplain,
  useSelectionRun,
  useSelectionRuns,
  useStartSelection,
  type SelectionResultRow,
  type SelectionRun,
} from '../api/hooks'
import Field from '../components/Field'
import Icon from '../layout/icons'
import Progress from '../components/Progress'
import { Row, Rows, StatRow } from '../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { formatDate } from '../lib/format'

const TIER_TONE: Record<string, Tone> = { dream: 'info', reach: 'warn', match: 'accent', safety: 'good' }

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
    <DataCard title={t('Новый подбор')}>
      <Field.Row>
        <Field kind="text" name="major" label={t('Специальность')} value={major} onChange={setMajor} placeholder="Computer Science" />
        <Field
          kind="select"
          name="level"
          label={t('Уровень')}
          value={level}
          onChange={setLevel}
          options={[
            { value: '', title: t('Любой') },
            { value: 'bachelor', title: t('Бакалавриат') },
            { value: 'master', title: t('Магистратура') },
            { value: 'foundation', title: 'Foundation' },
          ]}
        />
      </Field.Row>
      <span className="t-caps">{t('Страны (все, если не выбрать)')}</span>
      <div className="acad__chips">
        {allCountries.map((country) => (
          <Button key={country} variant={countries.includes(country) ? 'default' : 'outline'} size="sm" onClick={() => setCountries((prev) => (prev.includes(country) ? prev.filter((c) => c !== country) : [...prev, country]))}>
            {country}
          </Button>
        ))}
        {allCountries.length === 0 && <span className="t-note">{t('Справочник пока пуст')}</span>}
      </div>
      <div className="acad__actions">
        <Button disabled={start.isPending} onClick={() => start.mutate({ major, level, countries }, { onSuccess: (run) => onStarted(run), onError: (error) => toast.error(error.message) })}>
          {t('Запустить подбор')}
        </Button>
      </div>
    </DataCard>
  )
}

/** Экран расчёта: этапы отмечаются по мере прохождения. */
function ProgressCard({ run }: { run: SelectionRun }) {
  const navigate = useNavigate()
  return (
    <DataCard title={t('Идёт расчёт')} note={run.major || t('Все специальности')}>
      <Progress percent={run.progress} />
      <Rows>
        {run.stages.map((stage, index) => {
          const done = run.progress >= stage.at && run.stage !== stage.code
          const current = run.stage === stage.code
          return <Row key={stage.code} lead={<b className="num stu__slot">{index + 1}</b>} tone={done ? 'good' : current ? 'accent' : 'neutral'} title={t(stage.title)} muted={!done && !current} right={current ? <Chip tone="accent" size="sm">{t('сейчас')}</Chip> : done ? <Chip tone="good" size="sm">{t('готово')}</Chip> : undefined} />
        })}
      </Rows>
      <div className="acad__actions">
        <Button variant="outline" size="sm" onClick={() => navigate('/dashboard')}>
          {t('Свернуть — расчёт продолжится')}
        </Button>
      </div>
    </DataCard>
  )
}

/** Раскрывающийся разбор «почему такой процент» — живой, по позициям. */
function Explain({ run, program }: { run: number; program: number }) {
  const { data, isLoading } = useSelectionExplain(run, program)
  if (isLoading) return <p className="t-note">{t('Считаю разбор…')}</p>
  if (!data) return null
  return (
    <div className="sel__explain">
      {data.profile_changed && data.profile_changed_note && <p className="t-note">{data.profile_changed_note}</p>}
      {!data.is_verified && data.verification_note && <Chip tone="warn">{data.verification_note}</Chip>}
      {data.breakdown.map((row) => (
        <div key={row.code} className="sel__position">
          <div className="row-between">
            <span>
              {row.title} <span className="t-note">· {t('вес')} {Math.round(row.weight)}%</span>
            </span>
            <b className="num">{row.percent}%</b>
          </div>
          <Progress percent={row.percent} tone={row.is_met ? 'good' : 'warn'} label={false} />
          {row.criteria.map((criterion) => (
            <p key={criterion.title} className="t-note">
              {criterion.title}: {criterion.current ?? t('нет')} {t('при пороге')} {criterion.threshold}
              {criterion.gap > 0 ? ` — ${t('не хватает')} ${criterion.gap}` : ''}
            </p>
          ))}
        </div>
      ))}
      <p className="t-note">{data.summary}</p>
    </div>
  )
}

/** Строка вуза в результате: два числа — и оба соответствие, не шанс. */
function ResultRow({ run, row }: { run: SelectionRun; row: SelectionResultRow }) {
  const favorites = useFavorites(false)
  const addToList = useAddToMyList()
  const plans = usePlanActions()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [favorite, setFavorite] = useState(row.is_favorite)
  const toggleFavorite = () => {
    const action = favorite ? favorites.remove : favorites.add
    action.mutate(row.program, { onSuccess: () => setFavorite(!favorite), onError: (error) => toast.error(error.message) })
  }
  return (
    <div className="sel__result" data-program={row.program}>
      <Row
        avatar={row.university_name}
        title={row.university_name}
        note={`${row.country}${row.world_rank ? ` · #${row.world_rank}` : ''} · ${row.program_name}`}
        right={
          <span className="catalog__acts">
            {row.tier && <Chip tone={TIER_TONE[row.tier] ?? 'neutral'} size="sm">{row.tier}</Chip>}
            <Chip tone="neutral" size="sm">{`${row.percent_now}% → ${row.percent_goal}%`}</Chip>
          </span>
        }
        acts={
          <>
            <Button variant="ghost" size="icon-sm" aria-label={favorite ? t('Убрать из избранного') : t('В избранное')} aria-pressed={favorite} onClick={toggleFavorite}>
              <Icon name="heart" size={16} />
            </Button>
            <Button variant="outline" size="sm" onClick={() => setOpen(!open)}>
              {open ? t('Свернуть разбор') : t('Почему такой процент')}
            </Button>
            {!row.in_my_list && (
              <Button variant="secondary" size="sm" onClick={() => addToList.mutate({ program: row.program, tier: { dream: 'reach', reach: 'reach', match: 'target' }[row.tier] ?? 'safety' }, { onSuccess: () => toast.success(t('Добавлено в ваш список')), onError: (error) => toast.error(error.message) })}>
                {t('В мой список')}
              </Button>
            )}
            <Button variant="ghost" size="sm" disabled={plans.create.isPending} onClick={() => plans.create.mutate({ program: row.program }, { onSuccess: (plan) => navigate(`/plan/${plan.id}`), onError: (error) => (error.message.includes('409') || error.message.includes('уже есть') ? navigate('/plan') : toast.error(error.message)) })}>
              {t('Создать план')}
            </Button>
          </>
        }
      />
      {open && <Explain run={run.id} program={row.program} />}
    </div>
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
    <div className="acad__cols">
      <div className="acad__stack">
        <StatRow>
          <Kpi value={run.profile.gpa} label="GPA" none={t('нет')} />
          <Kpi value={run.profile.ielts} label="IELTS" none={t('нет')} />
          <Kpi value={run.profile.sat} label="SAT" none={t('нет')} />
          <Kpi value={run.funnel.final} label={t('В финальном списке')} tone="accent" note={`${t('из')} ${run.funnel.catalog} ${t('в каталоге')}`} />
        </StatRow>
        {tiers.map(([tier, rows]) => (
          <DataCard key={tier} title={tier.toUpperCase()} note={t(TIER_NOTE[tier] ?? '')} count={rows.length}>
            <Rows>
              {rows.map((row) => (
                <ResultRow key={row.id} run={run} row={row} />
              ))}
            </Rows>
          </DataCard>
        ))}
        {strong.length > 0 && (
          <DataCard title={t('Ещё сильные варианты')} count={strong.length}>
            <Rows>
              {strong.map((row) => (
                <ResultRow key={row.id} run={run} row={row} />
              ))}
            </Rows>
          </DataCard>
        )}
        {other.length > 0 && (
          <DataCard title={t('Другие университеты')} count={other.length}>
            <Rows>
              {other.map((row) => (
                <Row key={row.id} title={row.university_name} note={`${row.country}${row.world_rank ? ` · #${row.world_rank}` : ''} · ${row.program_name}`} />
              ))}
            </Rows>
          </DataCard>
        )}
      </div>
      <div className="acad__stack">
        <DataCard title={`${t('Подбор от')} ${formatDate(run.created_at)}`} note={`${run.major || t('Все специальности')}${run.level_title ? ` · ${run.level_title}` : ''}`}>
          <Rows>
            <Row title={t('Страны')} value={run.countries.length > 0 ? run.countries.join(', ') : t('весь справочник школы')} />
            <Row title={t('Профиль')} value={t('на момент запуска')} note={t('результат считался от него, а не от сегодняшнего')} />
          </Rows>
          <div className="acad__actions">
            <Button variant="outline" size="sm" onClick={() => navigate('/selection')}>
              {t('Перезапустить с другими условиями')}
            </Button>
          </div>
        </DataCard>
        <DataCard title={t('Текущая позиция')}>
          <p className="acad__note">{run.strategy.position}</p>
        </DataCard>
        <DataCard title={t('Что важно усилить')}>
          <p className="acad__note">{run.strategy.improve}</p>
        </DataCard>
        <DataCard title={t('Следующий шаг')}>
          <p className="acad__note">{run.strategy.next_step}</p>
          {run.strategy.offline && <p className="t-note">{t('Стратегия собрана правилами из движка соответствия: модель сейчас не подключена.')}</p>}
        </DataCard>
        <DataCard title={t('Как построена подборка')} note={`${run.funnel.catalog} → ${run.funnel.filtered} → ${run.funnel.analyzed} → ${run.funnel.final}`}>
          {Object.keys(run.tiers ?? {}).length > 0 && (
            <p className="t-note">
              {t('По категориям:')} {Object.entries(run.tiers ?? {}).map(([tier, n]) => `${tier} — ${n}`).join(', ')}
            </p>
          )}
          <Button variant="link" size="sm" onClick={() => setShowHow(!showHow)}>
            {showHow ? t('Скрыть объяснение') : t('Как считаются проценты и категории')}
          </Button>
          {showHow && (
            <ul className="sel__how">
              {(run.methodology ?? []).map((line, index) => (
                <li key={index}>{line}</li>
              ))}
            </ul>
          )}
        </DataCard>
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
        <ScreenHead title={t('Подбор вузов')} crumb={{ label: t('Подбор'), to: '/selection' }} />
        {run.data.status === 'running' && <ProgressCard run={run.data} />}
        {run.data.status === 'failed' && <ErrorNote error={new Error(run.data.error || t('Подбор не получился — запустите заново'))} />}
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
        actions={running ? <Button size="sm" onClick={() => navigate(`/selection/${running.id}`)}>{`${t('Открыть расчёт')} · ${running.progress}%`}</Button> : undefined}
      />
      <div className="acad__cols">
        <div className="acad__stack">
          {running && (
            <DataCard title={t('Идёт расчёт')} note={running.major || t('все специальности')}>
              <Progress percent={running.progress} />
            </DataCard>
          )}
          {!running && <LaunchForm onStarted={(started) => navigate(`/selection/${started.id}`)} />}
          <DataCard title={t('История подборов')} count={history.length || undefined} empty={history.length === 0 && t('подборов ещё не было — запустите первый, это пара минут')}>
            <Rows>
              {history.map((row) => (
                <Row
                  key={row.id}
                  icon="clock"
                  title={`${formatDate(row.created_at)} · ${row.major || t('все специальности')}`}
                  note={`${row.countries.length > 0 ? row.countries.join(', ') : t('без фильтра стран')} · ${row.status_title}`}
                  to={`/selection/${row.id}`}
                />
              ))}
            </Rows>
          </DataCard>
        </div>
        <div className="acad__stack">
          <DataCard title={t('Как считается')}>
            <Rows>
              <Row lead={<b className="num stu__slot">1</b>} title={t('Вы называете направление')} />
              <Row lead={<b className="num stu__slot">2</b>} title={t('Считаем соответствие')} />
              <Row lead={<b className="num stu__slot">3</b>} title={t('Показываем разбор')} note={t('Четыре категории, разрывы словами и что подтянуть до каждой программы.')} />
            </Rows>
          </DataCard>
        </div>
      </div>
    </div>
  )
}
