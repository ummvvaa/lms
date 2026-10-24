/**
 * Общие части кабинетов директоров (макет `coral-directors`, 24.10.2026):
 * строка отчёта и окно с цифрами, итог звонка, задачи от академического
 * директора на главной исполнителя, приветствие с датой.
 */
import { useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import {
  reportExportPath,
  useMyStaffTasks,
  useRecordCall,
  useReportSeen,
  useSchoolReport,
  useStaffTaskDone,
  type CallOutcome,
  type SchoolReport,
} from '../../api/directors'
import { downloadFile } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import Field from '../../components/Field'
import Modal from '../../components/Modal'
import { Segmented, ShowAll } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk } from '../../i18n'
import { formatDate, formatDayMonth, formatWeekday } from '../../lib/format'
import { firstNameOf } from '../dashboards/home-today'
import './directors.css'

/** «Пятница, 24 октября · …» — строка под приветствием и заголовками экранов. */
export function todayLine(rest?: string): string {
  const now = new Date()
  const day = formatWeekday(now)
  const head = `${day.charAt(0).toLocaleUpperCase()}${day.slice(1)}, ${formatDayMonth(now)}`
  return rest ? `${head} · ${rest}` : head
}

export function useGreeting(): string {
  const { me } = useAuth()
  return t('Добрый день, {name}', { name: firstNameOf(me?.full_name ?? '') })
}

/** Две буквы отчёта в квадрате строки: из названия, а не из кода. */
export function monoOf(title: string): string {
  const words = title.replace(/[«»]/g, '').split(/\s+/).filter((w) => w.length > 2)
  return ((words[0]?.[0] ?? '') + (words[1]?.[0] ?? '')).toLocaleUpperCase()
}

export function Mono({ children }: { children: ReactNode }) {
  return (
    <span className="dir__mono" aria-hidden="true">
      {children}
    </span>
  )
}

/** Состояние отчёта чипом: новый — акцент, просмотрен — серый. */
export function SeenChip({ seen }: { seen: boolean }) {
  return (
    <Chip tone={seen ? 'neutral' : 'accent'} size="sm">
      {seen ? t('просмотрено') : t('новый')}
    </Chip>
  )
}

/** Строка отчёта: квадрат, название и источник, чип и «Открыть». */
export function ReportLine({
  report,
  onOpen,
  extra,
}: {
  report: Pick<SchoolReport, 'kind' | 'title' | 'source' | 'seen'> & { summary?: string }
  onOpen: () => void
  extra?: ReactNode
}) {
  return (
    <div className="dir__row">
      <Mono>{monoOf(report.title)}</Mono>
      <span className="dir__what">
        <b>{report.title}</b>
        <span className="t-note">{[report.source, report.summary].filter(Boolean).join(' · ')}</span>
      </span>
      <SeenChip seen={report.seen} />
      <span className="dir__acts">
        {extra}
        <Button variant="ghost" size="sm" onClick={onOpen}>
          {t('Открыть')}
        </Button>
      </span>
    </div>
  )
}

/** Окно отчёта: цифры строками, «Скачать xlsx» и «Просмотрено». */
export function ReportDialog({ kind, period, onClose }: { kind: string; period?: string; onClose: () => void }) {
  const { data, isLoading, error } = useSchoolReport(kind, period ?? '')
  const seen = useReportSeen()
  const [saving, setSaving] = useState(false)
  return (
    <Modal title={data?.title ?? t('Отчёт')} note={data ? `${data.source} · ${data.period_title}` : undefined} onClose={onClose}>
      {isLoading && <Loading />}
      {error && <ErrorNote error={error} />}
      {data && (
        <>
          <div className="dir__lines">
            {data.lines.map((line) => (
              <div key={line.label} className="dir__line">
                <span>{line.label}</span>
                <b className="num">{line.value}</b>
              </div>
            ))}
          </div>
          <div className="acad__actions">
            <Button
              variant="outline"
              disabled={saving}
              onClick={() => {
                setSaving(true)
                downloadFile(reportExportPath(data.kind, data.period), `${data.title}.xlsx`)
                  .then(() => toast.success(t('Файл xlsx скачан')))
                  .catch((reason: unknown) => toast.error(reason instanceof Error ? reason.message : String(reason)))
                  .finally(() => setSaving(false))
              }}
            >
              {t('Скачать xlsx')}
            </Button>
            <Button
              disabled={data.seen || seen.isPending}
              onClick={() =>
                seen.mutate(
                  { kind: data.kind, period: data.period },
                  {
                    onSuccess: () => {
                      toast.success(t('Отмечено как просмотренное'))
                      onClose()
                    },
                  },
                )
              }
            >
              {data.seen ? t('Просмотрено') : t('Отметить просмотренным')}
            </Button>
          </div>
        </>
      )}
    </Modal>
  )
}

export const OUTCOMES: { value: CallOutcome; label: string }[] = [
  { value: 'reached', label: tk('Дозвонились') },
  { value: 'no_answer', label: tk('Не ответили') },
  { value: 'call_back', label: tk('Перезвонить') },
]

/** Тон итога звонка: дозвонились — спокойно, не ответили — серый, перезвонить — внимание. */
export const OUTCOME_TONE = { reached: 'good', no_answer: 'neutral', call_back: 'warn' } as const

/** Итог звонка: три варианта и текст; пишется в карточку ученика и в историю звонков. */
export function CallDialog({
  student,
  name,
  note,
  contact,
  rule,
  onClose,
}: {
  student: number
  name: string
  note?: string
  contact?: number | null
  rule?: string
  onClose: () => void
}) {
  const [outcome, setOutcome] = useState<CallOutcome>('reached')
  const [text, setText] = useState('')
  const record = useRecordCall()
  return (
    <Modal title={t('Итог звонка · {name}', { name })} note={note} onClose={onClose}>
      <Segmented value={outcome} onChange={setOutcome} label={t('Итог звонка')} items={OUTCOMES.map((o) => ({ value: o.value, label: t(o.label) }))} />
      <Field
        kind="textarea"
        name="call-note"
        label={t('Что сказали родители')}
        value={text}
        onChange={setText}
        placeholder={t('Например: болеет до понедельника, справка будет')}
        rows={3}
      />
      <div className="acad__actions">
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
        <Button
          disabled={record.isPending}
          onClick={() => record.mutate({ student, outcome, note: text, contact, rule }, { onSuccess: onClose })}
        >
          {t('Сохранить')}
        </Button>
      </div>
    </Modal>
  )
}

/**
 * Задачи от академического директора на главной исполнителя: учителя,
 * куратора, директора. Пусто — карточки нет: задачи бывают не всегда.
 */
export function MyStaffTasksCard({ beam = false }: { beam?: boolean }) {
  const { data } = useMyStaffTasks()
  const done = useStaffTaskDone()
  const rows = data?.rows ?? []
  if (rows.length === 0) return null
  return (
    <DataCard className={beam ? 'card--beam' : undefined} title={t('Задачи от академического директора')} count={rows.length}>
      <div className="dir__rows">
        <ShowAll>
          {rows.map((task) => (
            <div key={task.id} className="dir__row">
              <span className="dir__what">
                <b>{task.title}</b>
                <span className="t-note">
                  {task.status === 'returned' && task.return_note
                    ? t('вернули: {note}', { note: task.return_note })
                    : t('до {date}', { date: formatDate(task.due) })}
                </span>
              </span>
              <Chip tone={task.late ? 'bad' : task.status === 'done' ? 'neutral' : task.status === 'returned' ? 'warn' : 'info'} size="sm">
                {task.status === 'done' ? t('ждёт приёмки') : task.late ? t('просрочено') : task.status_title}
              </Chip>
              <span className="dir__acts">
                {task.status !== 'done' && (
                  <Button variant="outline" size="sm" disabled={done.isPending} onClick={() => done.mutate(task.id)}>
                    {t('Выполнено')}
                  </Button>
                )}
              </span>
            </div>
          ))}
        </ShowAll>
      </div>
    </DataCard>
  )
}
