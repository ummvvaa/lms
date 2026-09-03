/**
 * План поступления по конкретному вузу (фаза 41).
 *
 * У ученика может быть несколько планов — по одному на программу,
 * переключение в шапке. Дедлайн живёт в раунде подачи, не копируется:
 * сдвиг в справочнике двигает и план, и его задачи (инвариант №4).
 * Задачи собираются под программу и применяются самим учеником через
 * предложение (инвариант №3). Общий роадмап при этом остаётся.
 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  useMyUniversities,
  usePlan,
  usePlanActions,
  usePlanPreview,
  usePlanTasks,
  usePlans,
  type ApplicationPlan,
} from '../api/hooks'
import Empty from '../components/Empty'
import Icon from '../layout/icons'
import { Hero, HeroBar, HeroChip, HeroTile, Row, Rows, Tile } from '../components/patterns'
import { Bar, counted, DataCard, ErrorNote, Loading, ScreenHead, ScreenTabs } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { NativeSelectOption } from '../components/ui/native-select'
import { SelectField } from '../components/SelectField'
import { t } from '../i18n'

const CATEGORY_TITLE: Record<string, string> = {
  test: 'Экзамены и тесты',
  essay: 'Эссе',
  documents: 'Документы',
  portfolio: 'Портфолио',
  finance: 'Финансы и стипендии',
  university: 'Подача',
}

const STATUS_TONE: Record<string, 'mute' | 'warn' | 'ok'> = {
  todo: 'mute',
  in_progress: 'warn',
  review: 'warn',
  done: 'ok',
}

const STATUS_TITLE: Record<string, string> = {
  todo: 'Сделать',
  in_progress: 'В работе',
  review: 'На проверке',
  done: 'Готово',
}

/** Генерация задач: предпросмотр и применение самим учеником. */
function Generation({ plan }: { plan: ApplicationPlan }) {
  const preview = usePlanPreview(plan.id, plan.generation_status === 'done')
  const { applyTasks } = usePlanActions()

  if (plan.generation_status === 'running') {
    return (
      <div className="card card-pad">
        <span className="eyebrow">{t('Собираю задачи под эту программу…')}</span>
        <Bar percent={60} />
        <p className="muted sel__note">{t('Это пара секунд — не закрывайте страницу.')}</p>
      </div>
    )
  }
  if (plan.generation_status === 'failed') {
    return <ErrorNote error={new Error(t('Задачи не собрались — удалите план и создайте заново'))} />
  }

  const changes = preview.data?.changes ?? []
  // сгруппируем строки предложения в задачи по new_object_key
  const tasksByKey = new Map<string, Record<string, string>>()
  for (const change of changes) {
    const key = change.new_object_key
    tasksByKey.set(key, {
      ...tasksByKey.get(key),
      [change.field_short || change.field_title]: change.new_value,
    })
  }
  const proposed = [...tasksByKey.values()]

  // С фазы 48 задачи применяются сразу после сборки: подтверждением
  // стало добавление вуза в список. Эта карточка остаётся страховкой —
  // если применение не прошло, человек должен видеть почему и чем помочь
  return (
    <div className="card card-pad card--accent card--warn">
      <span className="eyebrow">{t('Задачи собраны, но ещё не в плане')}</span>
      <p className="muted sel__note">
        {t('Обычно они добавляются сами. В этот раз что-то помешало — добавьте их одним нажатием.')}
        {plan.generation_offline && ` ${t('Собрано правилами: модель сейчас не подключена.')}`}
      </p>
      <Rows>
        {proposed.slice(0, 12).map((task, index) => (
          <Row key={index} icon="checklist" tone="warn" title={Object.values(task)[0]} />
        ))}
      </Rows>
      <div className="propose__actions">
        <Button
          disabled={applyTasks.isPending || proposed.length === 0}
          onClick={() =>
            applyTasks.mutate(plan.id, {
              onSuccess: () => toast.success(t('Задачи добавлены в план')),
              onError: (error) => toast.error(error.message),
            })
          }
        >
          {t('Добавить задачи')} ({proposed.length})
        </Button>
      </div>
    </div>
  )
}

/**
 * Стратегия поступления: где ученик сейчас и что решает эта заявка.
 *
 * Собрана движком соответствия по требованиям самой программы, а не
 * написана моделью: числа и разрывы должны быть точными. Слово «шанс»
 * здесь появиться не может — это соответствие требованиям (инвариант №11).
 */
function Strategy({ plan }: { plan: ApplicationPlan }) {
  const [open, setOpen] = useState(true)
  const mine = useMyUniversities()
  const match = (mine.data ?? []).find((row) => row.program === plan.program)
  if (!match) return null

  const met = match.breakdown.filter((row) => row.is_met && !row.is_unknown)
  const unmet = match.breakdown.filter((row) => !row.is_met && !row.is_unknown)
  const unknown = match.breakdown.filter((row) => row.is_unknown)
  // главное узкое место — позиция с наибольшим весом среди незакрытых
  const bottleneck = [...unmet].sort((a, b) => b.weight - a.weight)[0]

  return (
    <section className="card card-pad card--accent card--brand plan__strategy">
      <button type="button" className="plan__strategyhead" onClick={() => setOpen((v) => !v)}>
        <Tile icon="target" tone="brand" size="lg" />
        <span className="plan__strategytext">
          <b>{t('Стратегия поступления')}</b>
          <span className="muted">{t('Где вы сейчас и что решает эта заявка')}</span>
        </span>
        <Icon name={open ? 'chevronUp' : 'chevronDown'} size={16} />
      </button>

      {open && (
        <>
          <p className="plan__strategysummary">{match.summary}</p>
          <div className="plan__strategygrid">
            <article className="plan__strategycard">
              <div className="plan__strategyrow">
                <Tile icon="check" tone="ok" size="sm" />
                <b>{t('Что уже работает')}</b>
              </div>
              <p className="muted">
                {met.length > 0
                  ? met.map((row) => row.title).join(', ')
                  : t('Пока ни одно требование программы не закрыто целиком.')}
              </p>
            </article>

            <article className="plan__strategycard">
              <div className="plan__strategyrow">
                <Tile icon="alert" tone="warn" size="sm" />
                <b>{t('Что подтянуть')}</b>
              </div>
              <p className="muted">
                {unmet.length > 0
                  ? unmet.map((row) => row.gap_phrase || row.title).join('; ')
                  : t('Все требования, по которым есть данные, закрыты.')}
              </p>
            </article>

            <article className="plan__strategycard">
              <div className="plan__strategyrow">
                <Tile icon="target" tone="risk" size="sm" />
                <b>{t('Главное узкое место')}</b>
              </div>
              <p className="muted">
                {bottleneck
                  ? `${bottleneck.title}: ${bottleneck.gap_phrase || t('не хватает данных')}`
                  : t('Узкого места нет — держите темп.')}
              </p>
            </article>

            <article className="plan__strategycard">
              <div className="plan__strategyrow">
                <Tile icon="checklist" tone="indigo" size="sm" />
                <b>{t('Что даст план')}</b>
              </div>
              <p className="muted">
                {`${counted(plan.counters.total, ['задача', 'задачи', 'задач'])} ${t('под требования этой программы; выполнено')} ${plan.counters.done}.`}
                {unknown.length > 0 && ` ${t('По части требований данных нет — они в процент не входят.')}`}
              </p>
            </article>
          </div>
          <p className="muted plan__strategynote">
            {`${t('Соответствие требованиям сейчас')}: ${match.percent}%. ${t('Это не шанс поступления и не прогноз.')}`}
          </p>
        </>
      )}
    </section>
  )
}

function PlanBody({ plan }: { plan: ApplicationPlan }) {
  const tasks = usePlanTasks(plan.id)
  const [tab, setTab] = useState<'stages' | 'timeline'>('stages')
  const hasTasks = plan.counters.total > 0

  // Задачи собираются в фоне: список успевает приехать пустым, а счётчики
  // плана — уже с числом. Перечитываем список, когда число изменилось,
  // иначе вкладки остаются пустыми до перезагрузки страницы
  const refetchTasks = tasks.refetch
  useEffect(() => {
    void refetchTasks()
  }, [plan.counters.total, refetchTasks])

  if (!hasTasks) return <Generation plan={plan} />

  const stages = tasks.data?.stages ?? []
  const allTasks = stages.flatMap((s) => s.tasks)
  const timeline = [...allTasks].sort((a, b) =>
    (a.due_date_effective ?? '9999').localeCompare(b.due_date_effective ?? '9999'),
  )

  return (
    <div>
      <Strategy plan={plan} />

      <ScreenTabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'stages', label: t('Задачи и этапы') },
          { value: 'timeline', label: t('Таймлайн') },
        ]}
      />

      {tab === 'stages' &&
        stages.map((stage) => (
          <DataCard
            key={stage.category}
            title={t(CATEGORY_TITLE[stage.category] ?? stage.category)}
            count={stage.tasks.length}
          >
            <Rows>
              {stage.tasks.map((task) => (
                <Row
                  key={task.id}
                  lead={
                    <span
                      className={`plan__check${task.status === 'done' ? ' plan__check--on' : ''}`}
                      aria-hidden="true"
                    >
                      {task.status === 'done' ? <Icon name="check" size={11} /> : null}
                    </span>
                  }
                  title={task.title}
                  note={
                    task.due_date_effective
                      ? `${t('срок')}: ${new Date(task.due_date_effective).toLocaleDateString('ru')}`
                      : undefined
                  }
                  muted={task.status === 'done'}
                  right={
                    <Badge variant={STATUS_TONE[task.status] ?? 'mute'}>
                      {t(STATUS_TITLE[task.status] ?? task.status)}
                    </Badge>
                  }
                />
              ))}
            </Rows>
          </DataCard>
        ))}

      {tab === 'timeline' && (
        <DataCard title={t('Таймлайн')} note={t('Задачи плана по сроку')} accent="indigo">
          <Rows>
            {timeline.map((task) => (
              <Row
                key={task.id}
                icon="calendar"
                tone="indigo"
                title={task.title}
                note={t(CATEGORY_TITLE[task.category] ?? task.category)}
                right={
                  <Badge variant="mute">
                    {task.due_date_effective
                      ? new Date(task.due_date_effective).toLocaleDateString('ru')
                      : t('без срока')}
                  </Badge>
                }
              />
            ))}
          </Rows>
        </DataCard>
      )}
    </div>
  )
}

/**
 * Планов нет: показываем вузы из списка ученика и даём собрать план
 * по любому из них. Раньше здесь была только ссылка в подбор, и человек,
 * пришедший по пункту меню, упирался в тупик (долг D20).
 */
function NoPlans() {
  const navigate = useNavigate()
  const mine = useMyUniversities()
  const { create } = usePlanActions()
  const rows = mine.data ?? []

  if (rows.length === 0)
    return (
      <Empty
        icon="checklist"
        title={t('Планов пока нет')}
        what={t('Добавьте вуз в свой список — план по нему соберётся сам.')}
        action={t('Открыть каталог')}
        to="/catalog"
      />
    )

  return (
    <DataCard
      title={t('Соберите план по вузу из вашего списка')}
      note={t('Обычно план появляется сам при добавлении вуза. Если его нет — соберите здесь.')}
      accent="brand"
    >
      <Rows>
        {rows.map((row) => (
          <Row
            key={row.program}
            icon="cap"
            tone="indigo"
            title={row.university_name}
            note={row.program_name}
            right={
              <Button
                size="sm"
                disabled={create.isPending}
                onClick={() =>
                  create.mutate(
                    { program: row.program },
                    {
                      onSuccess: (plan) => {
                        toast.success(t('Собираю задачи под эту программу'))
                        navigate(`/plan/${plan.id}`)
                      },
                      onError: (error) => toast.error(error.message),
                    },
                  )
                }
              >
                {t('Создать план')}
              </Button>
            }
          />
        ))}
      </Rows>
    </DataCard>
  )
}

export default function Plan() {
  const { id } = useParams()
  const navigate = useNavigate()
  const plans = usePlans()
  const { remove } = usePlanActions()

  const rows = useMemo(() => plans.data?.results ?? [], [plans.data])
  const activeId = id ? Number(id) : (rows[0]?.id ?? null)
  const plan = usePlan(activeId)

  // если открыли /plan без id, а планы есть — показываем первый
  useEffect(() => {
    if (!id && rows.length > 0) navigate(`/plan/${rows[0].id}`, { replace: true })
  }, [id, rows, navigate])

  if (plans.isLoading) return <Loading kind="cards" />
  if (plans.error) return <ErrorNote error={plans.error} />

  if (rows.length === 0) {
    return (
      <div>
        <ScreenHead
          title={t('План поступления')}
          subtitle={t('План по конкретному вузу — со своими задачами и дедлайном.')}
        />
        {/* План заводится сам при добавлении вуза (фаза 48). Кнопка
            остаётся на случай, когда его почему-то нет: пересобрать
            по программе, которая уже в списке */}
        <NoPlans />
      </div>
    )
  }

  if (plan.isLoading || !plan.data) return <Loading kind="cards" />
  const current = plan.data

  return (
    <div>
      <ScreenHead
        title={t('План поступления')}
        subtitle={t('Задачи под конкретную программу и её дедлайн')}
        actions={
          <>
            {rows.length > 1 && (
              <SelectField
                value={String(current.id)}
                onChange={(e) => navigate(`/plan/${e.target.value}`)}
                aria-label={t('Выбрать план')}
              >
                {rows.map((row) => (
                  <NativeSelectOption key={row.id} value={String(row.id)}>
                    {row.university_name} · {row.program_name}
                  </NativeSelectOption>
                ))}
              </SelectField>
            )}
            <Button variant="outline" onClick={() => navigate('/universities')}>
              {t('Мои вузы')}
            </Button>
            <Button onClick={() => navigate('/catalog')}>{t('Добавить университет')}</Button>
          </>
        }
      />

      {/* Крупная карточка плана: вуз, чипы с фактами, полоса прогресса
          и четыре плитки-числа справа — всё, что нужно знать о заявке,
          не листая экран */}
      <Hero
        tone="brand"
        eyebrow={t('План поступления')}
        title={current.university_name}
        figure="rings"
        chips={
          <>
            <HeroChip>{`${current.level_title} · ${current.program_name}`}</HeroChip>
            {current.round_type && <HeroChip>{current.round_type}</HeroChip>}
            {current.deadline && (
              <HeroChip strong>
                {`${t('Дедлайн')} ${new Date(current.deadline).toLocaleDateString('ru')}`}
              </HeroChip>
            )}
            {current.days_left !== null && (
              <HeroChip>{`${t('Осталось')} ${current.days_left} ${t('дн.')}`}</HeroChip>
            )}
          </>
        }
        aside={
          <>
            <HeroTile value={current.counters.total} label={t('Всего задач')} />
            <HeroTile value={current.counters.done} label={t('Выполнено')} />
            <HeroTile value={current.counters.in_progress} label={t('В работе')} />
            <HeroTile value={current.counters.remaining} label={t('Осталось')} />
          </>
        }
      >
        <div className="plan__progress">
          <HeroBar percent={current.progress} />
          <b className="num">{current.progress}%</b>
        </div>
      </Hero>

      <PlanBody plan={current} />

      <div className="plan__danger">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            remove.mutate(current.id, {
              onSuccess: () => {
                toast.success(t('План убран в архив'))
                navigate('/plan')
              },
              onError: (error) => toast.error(error.message),
            })
          }}
        >
          {t('Убрать этот план')}
        </Button>
        <span className="muted plan__dangernote">
          {t('Задачи уйдут в архив вместе с ним. Вуз останется в вашем списке.')}
        </span>
      </div>
    </div>
  )
}
