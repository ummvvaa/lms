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
  usePlan,
  usePlanActions,
  usePlanPreview,
  usePlanTasks,
  usePlans,
  type ApplicationPlan,
} from '../api/hooks'
import Empty from '../components/Empty'
import { Bar, ErrorNote, Loading, Metric, MetricRow, ScreenHead, ScreenTabs } from '../components/ui'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { NativeSelect, NativeSelectOption } from '../components/ui/native-select'
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

  return (
    <div className="card card-pad card--accent card--brand">
      <span className="eyebrow">{t('Задачи готовы — примите их в план')}</span>
      <p className="muted sel__note">
        {t('Задачи собраны под требования этой программы. Это ваш план — примените их сами.')}
        {plan.generation_offline && ` ${t('Собрано правилами: модель сейчас не подключена.')}`}
      </p>
      <ul className="rows__list">
        {proposed.slice(0, 12).map((task, index) => (
          <li key={index} className="rows__item">
            <div className="rows__body">
              <span className="rows__label">{Object.values(task)[0]}</span>
            </div>
          </li>
        ))}
      </ul>
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
          {t('Принять задачи')} ({proposed.length})
        </Button>
      </div>
    </div>
  )
}

function PlanBody({ plan }: { plan: ApplicationPlan }) {
  const tasks = usePlanTasks(plan.id)
  const [tab, setTab] = useState<'stages' | 'timeline'>('stages')
  const hasTasks = plan.counters.total > 0

  if (!hasTasks) return <Generation plan={plan} />

  const stages = tasks.data?.stages ?? []
  const allTasks = stages.flatMap((s) => s.tasks)
  const timeline = [...allTasks].sort((a, b) =>
    (a.due_date_effective ?? '9999').localeCompare(b.due_date_effective ?? '9999'),
  )

  return (
    <div>
      <div className="card card-pad">
        <MetricRow>
          <Metric value={plan.counters.total} label={t('Всего задач')} />
          <Metric value={plan.counters.done} label={t('Выполнено')} tone="ok" />
          <Metric value={plan.counters.in_progress} label={t('В работе')} tone="warn" />
          <Metric value={plan.counters.remaining} label={t('Осталось')} />
        </MetricRow>
        <Bar percent={plan.progress} />
      </div>

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
          <div key={stage.category} className="card card-pad" style={{ marginBottom: 12 }}>
            <span className="eyebrow">{t(CATEGORY_TITLE[stage.category] ?? stage.category)}</span>
            <ul className="rows__list">
              {stage.tasks.map((task) => (
                <li key={task.id} className="rows__item">
                  <div className="rows__body">
                    <span className="rows__label">{task.title}</span>
                    {task.due_date_effective && (
                      <span className="muted rows__note">
                        {t('срок')}: {new Date(task.due_date_effective).toLocaleDateString('ru')}
                      </span>
                    )}
                  </div>
                  <Badge variant={STATUS_TONE[task.status] ?? 'mute'}>
                    {t(STATUS_TITLE[task.status] ?? task.status)}
                  </Badge>
                </li>
              ))}
            </ul>
          </div>
        ))}

      {tab === 'timeline' && (
        <div className="card card-pad">
          <ul className="rows__list">
            {timeline.map((task) => (
              <li key={task.id} className="rows__item">
                <div className="rows__body">
                  <span className="rows__label">{task.title}</span>
                  <span className="muted rows__note">
                    {t(CATEGORY_TITLE[task.category] ?? task.category)}
                  </span>
                </div>
                <Badge variant="mute">
                  {task.due_date_effective
                    ? new Date(task.due_date_effective).toLocaleDateString('ru')
                    : t('без срока')}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
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
        <Empty
          icon="checklist"
          title={t('Планов пока нет')}
          what={t('Создайте план по вузу из результата подбора — задачи соберутся под его требования.')}
          action={t('Открыть подбор')}
          to="/selection"
        />
      </div>
    )
  }

  if (plan.isLoading || !plan.data) return <Loading kind="cards" />
  const current = plan.data

  return (
    <div>
      <ScreenHead
        title={t('План поступления')}
        subtitle={t('Задачи под конкретную программу. Общий роадмап остаётся отдельно.')}
        actions={
          <Button variant="outline" onClick={() => navigate('/selection')}>
            {t('Добавить университет')}
          </Button>
        }
      />

      <div className="card card-pad plan__head">
        <div className="plan__headrow">
          <NativeSelect
            value={String(current.id)}
            onChange={(e) => navigate(`/plan/${e.target.value}`)}
            aria-label={t('Выбрать план')}
          >
            {rows.map((row) => (
              <NativeSelectOption key={row.id} value={String(row.id)}>
                {row.university_name} · {row.program_name}
              </NativeSelectOption>
            ))}
          </NativeSelect>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              if (!confirm(t('Удалить этот план? Его задачи уйдут в архив.'))) return
              remove.mutate(current.id, {
                onSuccess: () => {
                  toast.success(t('План удалён'))
                  navigate('/plan')
                },
                onError: (error) => toast.error(error.message),
              })
            }}
          >
            {t('Удалить план')}
          </Button>
        </div>
        <div className="plan__meta">
          <span>
            <b>{current.university_name}</b> · {current.program_name} · {current.level_title}
            {current.round_type ? ` · ${current.round_type}` : ''}
          </span>
          {current.deadline && (
            <Badge variant={current.days_left !== null && current.days_left < 30 ? 'risk' : 'teal'}>
              {t('дедлайн')} {new Date(current.deadline).toLocaleDateString('ru')}
              {current.days_left !== null ? ` · ${t('осталось')} ${current.days_left} ${t('дн.')}` : ''}
            </Badge>
          )}
        </div>
      </div>

      <PlanBody plan={current} />
    </div>
  )
}
