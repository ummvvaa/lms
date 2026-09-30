/**
 * План поступления по конкретному вузу.
 *
 * У ученика может быть несколько планов — по одному на программу,
 * переключение в шапке. Дедлайн живёт в раунде подачи, не копируется:
 * сдвиг в справочнике двигает и план, и его задачи (инвариант №4).
 * Задачи — левая колонка по этапам, справа дедлайн, требования и стратегия.
 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { useMyUniversities, usePlan, usePlanActions, usePlanPreview, usePlanTasks, usePlans, type ApplicationPlan } from '../api/hooks'
import Field from '../components/Field'
import Icon from '../layout/icons'
import Progress from '../components/Progress'
import { Row, Rows, Segmented, StatRow } from '../components/patterns'
import { Chip, counted, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../components/ui'
import { Button } from '../components/ui/button'
import { t } from '../i18n'
import { formatDate } from '../lib/format'

const CATEGORY_TITLE: Record<string, string> = {
  test: 'Экзамены и тесты',
  essay: 'Эссе',
  documents: 'Документы',
  portfolio: 'Портфолио',
  finance: 'Финансы и стипендии',
  university: 'Подача',
}

const STATUS_TONE: Record<string, Tone> = { todo: 'neutral', in_progress: 'warn', review: 'warn', done: 'good' }
const STATUS_TITLE: Record<string, string> = { todo: 'Сделать', in_progress: 'В работе', review: 'На проверке', done: 'Готово' }

/** Генерация задач: предпросмотр и применение самим учеником. */
function Generation({ plan }: { plan: ApplicationPlan }) {
  const preview = usePlanPreview(plan.id, plan.generation_status === 'done')
  const { applyTasks } = usePlanActions()

  if (plan.generation_status === 'running') {
    return (
      <DataCard title={t('Собираю задачи под эту программу')}>
        <Progress percent={60} label={false} />
      </DataCard>
    )
  }
  if (plan.generation_status === 'failed') {
    return <ErrorNote error={new Error(t('Задачи не собрались — удалите план и создайте заново'))} />
  }

  const changes = preview.data?.changes ?? []
  const tasksByKey = new Map<string, Record<string, string>>()
  for (const change of changes) {
    const key = change.new_object_key
    tasksByKey.set(key, { ...tasksByKey.get(key), [change.field_short || change.field_title]: change.new_value })
  }
  const proposed = [...tasksByKey.values()]

  // задачи применяются сразу после сборки; эта карточка — страховка,
  // если применение не прошло: человек видит почему и чем помочь
  return (
    <DataCard title={t('Задачи собраны, но ещё не в плане')} note={`${t('Обычно они добавляются сами. В этот раз что-то помешало — добавьте их одним нажатием.')}${plan.generation_offline ? ` ${t('Собрано правилами: модель сейчас не подключена.')}` : ''}`}>
      <Rows>
        {proposed.slice(0, 12).map((task, index) => (
          <Row key={index} icon="checklist" tone="warn" title={Object.values(task)[0]} />
        ))}
      </Rows>
      <div className="acad__actions">
        <Button disabled={applyTasks.isPending || proposed.length === 0} onClick={() => applyTasks.mutate(plan.id, { onSuccess: () => toast.success(t('Задачи добавлены в план')), onError: (error) => toast.error(error.message) })}>
          {t('Добавить задачи')} ({proposed.length})
        </Button>
      </div>
    </DataCard>
  )
}

/**
 * Стратегия поступления: где ученик сейчас и что решает эта заявка.
 * Собрана движком соответствия по требованиям самой программы: числа и разрывы
 * точные. Слово «шанс» здесь появиться не может (инвариант №11).
 */
function Strategy({ plan }: { plan: ApplicationPlan }) {
  const mine = useMyUniversities()
  const match = (mine.data ?? []).find((row) => row.program === plan.program)
  if (!match) return null
  const met = match.breakdown.filter((row) => row.is_met && !row.is_unknown)
  const unmet = match.breakdown.filter((row) => !row.is_met && !row.is_unknown)
  const unknown = match.breakdown.filter((row) => row.is_unknown)
  const bottleneck = [...unmet].sort((a, b) => b.weight - a.weight)[0]
  return (
    <DataCard title={t('Стратегия поступления')} note={`${t('Соответствие требованиям сейчас')}: ${match.percent}% · ${t('это не шанс поступления и не прогноз')}`}>
      <p className="acad__note">{match.summary}</p>
      <Rows>
        <Row icon="check" tone="good" title={t('Что уже работает')} note={met.length > 0 ? met.map((row) => row.title).join(', ') : t('Пока ни одно требование программы не закрыто целиком.')} />
        <Row icon="alert" tone="warn" title={t('Что подтянуть')} note={unmet.length > 0 ? unmet.map((row) => row.gap_phrase || row.title).join('; ') : t('Все требования, по которым есть данные, закрыты.')} />
        <Row icon="target" tone="bad" title={t('Главное узкое место')} note={bottleneck ? `${bottleneck.title}: ${bottleneck.gap_phrase || t('не хватает данных')}` : t('Узкого места нет — держите темп.')} />
        <Row icon="checklist" tone="info" title={t('Что даст план')} note={`${counted(plan.counters.total, 'задача|задачи|задач')} ${t('под требования этой программы; выполнено')} ${plan.counters.done}.${unknown.length > 0 ? ` ${t('По части требований данных нет — они в процент не входят.')}` : ''}`} />
      </Rows>
    </DataCard>
  )
}

function PlanTasks({ plan }: { plan: ApplicationPlan }) {
  const tasks = usePlanTasks(plan.id)
  const [tab, setTab] = useState<'stages' | 'timeline'>('stages')
  const hasTasks = plan.counters.total > 0
  const refetchTasks = tasks.refetch
  useEffect(() => {
    void refetchTasks()
  }, [plan.counters.total, refetchTasks])

  if (!hasTasks) return <Generation plan={plan} />

  const stages = tasks.data?.stages ?? []
  const allTasks = stages.flatMap((s) => s.tasks)
  const timeline = [...allTasks].sort((a, b) => (a.due_date_effective ?? '9999').localeCompare(b.due_date_effective ?? '9999'))

  return (
    <>
      <div className="acad__toolbar">
        <Segmented
          value={tab}
          onChange={setTab}
          label={t('Что показать')}
          items={[
            { value: 'stages', label: t('Задачи и этапы') },
            { value: 'timeline', label: t('Таймлайн') },
          ]}
        />
      </div>
      {tab === 'stages' &&
        stages.map((stage) => (
          <DataCard key={stage.category} title={t(CATEGORY_TITLE[stage.category] ?? stage.category)} count={stage.tasks.length}>
            <Rows>
              {stage.tasks.map((task) => (
                <Row
                  key={task.id}
                  lead={
                    <span className={`plan__check${task.status === 'done' ? ' plan__check--on' : ''}`} aria-hidden="true">
                      {task.status === 'done' ? <Icon name="check" size={11} /> : null}
                    </span>
                  }
                  title={task.title}
                  note={task.due_date_effective ? `${t('срок')}: ${formatDate(task.due_date_effective)}` : undefined}
                  muted={task.status === 'done'}
                  right={<Chip tone={STATUS_TONE[task.status] ?? 'neutral'} size="sm">{t(STATUS_TITLE[task.status] ?? task.status)}</Chip>}
                  to="/roadmap"
                />
              ))}
            </Rows>
          </DataCard>
        ))}
      {tab === 'timeline' && (
        <DataCard title={t('Таймлайн')}>
          <Rows>
            {timeline.map((task) => (
              <Row key={task.id} icon="calendar" title={task.title} note={t(CATEGORY_TITLE[task.category] ?? task.category)} value={task.due_date_effective ? formatDate(task.due_date_effective) : null} none={t('без срока')} />
            ))}
          </Rows>
        </DataCard>
      )}
    </>
  )
}

/** Планов нет: вузы из списка ученика и кнопка собрать план по любому. */
function NoPlans() {
  const navigate = useNavigate()
  const mine = useMyUniversities()
  const { create } = usePlanActions()
  const rows = mine.data ?? []
  return (
    <DataCard
      title={t('Соберите план по вузу из вашего списка')}
      empty={rows.length === 0 && t('добавьте вуз в свой список — план по нему соберётся сам')}
      emptyAction={
        <Button variant="secondary" size="sm" onClick={() => navigate('/catalog')}>
          {t('Открыть каталог')}
        </Button>
      }
    >
      <Rows>
        {rows.map((row) => (
          <Row
            key={row.program}
            icon="cap"
            title={row.university_name}
            note={row.program_name}
            acts={
              <Button variant="secondary" size="sm" disabled={create.isPending} onClick={() => create.mutate({ program: row.program }, { onSuccess: (plan) => { toast.success(t('Собираю задачи под эту программу')); navigate(`/plan/${plan.id}`) }, onError: (error) => toast.error(error.message) })}>
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

  useEffect(() => {
    if (!id && rows.length > 0) navigate(`/plan/${rows[0].id}`, { replace: true })
  }, [id, rows, navigate])

  if (plans.isLoading) return <Loading kind="cards" />
  if (plans.error) return <ErrorNote error={plans.error} />

  if (rows.length === 0) {
    return (
      <div>
        <ScreenHead title={t('План поступления')} />
        <div className="acad__cols">
          <div className="acad__stack">
            <NoPlans />
          </div>
        </div>
      </div>
    )
  }

  if (plan.isLoading || !plan.data) return <Loading kind="cards" />
  const current = plan.data

  return (
    <div>
      <ScreenHead
        title={current.university_name}
        subtitle={`${current.level_title} · ${current.program_name}${current.round_type ? ` · ${current.round_type}` : ''}`}
        pills={[{ label: t('План поступления') }, ...(current.deadline ? [{ label: `${t('Дедлайн')} ${formatDate(current.deadline)}`, on: true }] : [])]}
        actions={
          <>
            {rows.length > 1 && (
              <Field kind="select" name="plan" label={t('План')} value={String(current.id)} onChange={(value) => navigate(`/plan/${value}`)} options={rows.map((row) => ({ value: String(row.id), title: `${row.university_name} · ${row.program_name}` }))} className="plan__pick" />
            )}
            <Button variant="outline" size="sm" onClick={() => navigate('/universities')}>
              {t('Мои вузы')}
            </Button>
            <Button size="sm" onClick={() => navigate('/catalog')}>
              {t('Добавить университет')}
            </Button>
          </>
        }
      />
      <StatRow>
        <Kpi label={t('Всего задач')} value={current.counters.total} />
        <Kpi label={t('Выполнено')} value={current.counters.done || null} none={t('нет')} tone={current.counters.done ? 'good' : undefined} />
        <Kpi label={t('В работе')} value={current.counters.in_progress || null} none={t('нет')} />
        <Kpi label={t('До дедлайна')} value={current.days_left === null ? null : `${current.days_left} ${t('дн.')}`} none={t('дедлайн не назначен')} tone={current.days_left !== null && current.days_left <= 30 ? 'warn' : undefined} />
      </StatRow>
      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard title={t('Готовность плана')} note={`${current.progress}% · ${counted(current.counters.remaining, 'задача|задачи|задач')} ${t('осталось')}`}>
            <Progress percent={current.progress} />
          </DataCard>
          <PlanTasks plan={current} />
        </div>
        <div className="acad__stack">
          <Strategy plan={current} />
          <DataCard title={t('Убрать этот план')} note={t('Задачи уйдут в архив вместе с ним. Вуз останется в вашем списке.')}>
            <div className="acad__actions">
              <Button variant="outline" size="sm" onClick={() => remove.mutate(current.id, { onSuccess: () => { toast.success(t('План убран в архив')); navigate('/plan') }, onError: (error) => toast.error(error.message) })}>
                {t('Убрать план')}
              </Button>
            </div>
          </DataCard>
        </div>
      </div>
    </div>
  )
}
