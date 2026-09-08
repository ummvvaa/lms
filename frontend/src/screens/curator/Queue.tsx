/**
 * Очередь подтверждений куратора (фаза 61).
 *
 * Строки и решения — те же, что у директоров (`QueueRow`): подтвердить,
 * поправить и подтвердить, отклонить с причиной. Своё здесь только то,
 * чего у директорского экрана нет: вкладки по домену, порядок и выбор
 * группы. Границу «свои ученики» держит сервер (фаза 60), «резкий
 * скачок» тоже приходит с сервера.
 *
 * Вкладка «Документы» появится в фазе 62 вместе с их подтверждением —
 * пустой вкладки здесь нет намеренно.
 */
import { useState } from 'react'
import { toast } from 'sonner'
import {
  useCuratorOverview,
  useReviewSuggestion,
  useStudentQueue,
  type StudentQueueRow,
} from '../../api/hooks'
import { QueueRow } from '../../components/StudentQueue'
import { ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import GroupSwitch from './GroupSwitch'
import { useGroup } from './state'
import './curator.css'

/** Четыре частые причины отказа — подставляются в поле одним нажатием. */
const REASONS = [
  'Нет подтверждающего файла',
  'Скан нечёткий',
  'Не совпадает с сертификатом',
  'Не тот документ',
]

type Sort = 'diff' | 'date'
type Tab = 'all' | 'exam'

export default function CuratorQueue() {
  const [group, setGroup] = useGroup()
  const [tab, setTab] = useState<Tab>('all')
  const [sort, setSort] = useState<Sort>('diff')
  const [checked, setChecked] = useState<number[]>([])

  const overview = useCuratorOverview(group)
  const queue = useStudentQueue(group)
  const { confirmMany } = useReviewSuggestion()

  if (queue.isLoading) return <Loading kind="table" />
  if (queue.error) return <ErrorNote error={queue.error} />

  const all = queue.data?.results ?? []
  const exams = all.filter((row) => row.domain === 'exam')
  const rows = tab === 'exam' ? exams : all
  const shown = [...rows].sort((a, b) =>
    sort === 'diff'
      ? b.divergence - a.divergence
      : new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )

  const confirmChecked = () =>
    confirmMany.mutate(checked, {
      onSuccess: (result) => {
        const skipped = result.skipped?.length ?? 0
        toast.success(
          `${t('Подтверждено предложений:')} ${result.confirmed}` +
            (skipped ? `. ${t('Уже решено раньше:')} ${skipped}` : ''),
        )
        setChecked([])
      },
      onError: (error) => toast.error(error.message),
    })

  const tabButton = (value: Tab, label: string, count: number) => (
    <button
      type="button"
      className={`ctabs__tab${tab === value ? ' ctabs__tab--on' : ''}`}
      aria-pressed={tab === value}
      onClick={() => setTab(value)}
    >
      {label} <span className="ctabs__count">{count}</span>
    </button>
  )

  return (
    <div>
      <ScreenHead
        title={t('Очередь подтверждений')}
        subtitle={t('Ученик внёс, вы подтверждаете. Отклонение всегда с причиной: ученик её увидит.')}
      />
      <GroupSwitch groups={overview.data?.groups ?? []} value={group} onChange={setGroup} />

      <p className="cnote">
        {t(
          'Ту же очередь по всей школе видит владелец домена. Кто первый нажал, того и запись в журнале: второму система скажет, кем и когда это уже решено.',
        )}
      </p>

      <div className="card card-pad">
        <div className="cqueue__head">
          <div className="ctabs">
            {tabButton('all', t('Все'), all.length)}
            {tabButton('exam', t('Экзамены'), exams.length)}
          </div>
          <div className="cqueue__sort">
            <span className="muted">{t('Порядок')}</span>
            <Button variant={sort === 'diff' ? 'default' : 'outline'} size="sm" onClick={() => setSort('diff')}>
              {t('по расхождению')}
            </Button>
            <Button variant={sort === 'date' ? 'default' : 'outline'} size="sm" onClick={() => setSort('date')}>
              {t('по времени')}
            </Button>
          </div>
        </div>

        {shown.length === 0 && (
          <p className="muted">{t('Здесь пусто. Строки появятся, когда ученики внесут данные о себе.')}</p>
        )}

        {shown.map((row: StudentQueueRow) => (
          <QueueRow
            key={row.id}
            row={row}
            reasons={REASONS}
            checked={checked.includes(row.id)}
            onCheck={(value) =>
              setChecked((prev) => (value ? [...prev, row.id] : prev.filter((id) => id !== row.id)))
            }
          />
        ))}

        {checked.length > 0 && (
          <div className="squeue__bulk">
            <Button size="sm" disabled={confirmMany.isPending} onClick={confirmChecked}>
              {t('Подтвердить отмеченные')} ({checked.length})
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setChecked([])}>
              {t('Снять отметки')}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
