/**
 * Отчёт родителям на одного ученика за выбранный период (решение владельца,
 * 27.09.2026). Открывается из карточки ученика и из списка отчётов;
 * собранный отчёт открывается на экране отчётов. Делают четыре роли —
 * куратор, Кымбат, Салтанат и администратор; кнопку показывают экраны
 * по `REPORT_ROLES`, право держит сервер.
 *
 * Вид отчёта (30.09.2026): стандартный отчёт LMS — месяц или четверть;
 * шаблоны школы (вариант 1 и 2) — язык и период «с — по». Формат PDF или
 * Word выбирается при скачивании: оба делаются из одного файла.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useBuildReports, type BuildReportsInput, type ReportTemplate } from '../api/academics'
import { todayAlmaty } from '../lib/dates'
import Field from './Field'
import Modal from './Modal'
import { t } from '../i18n'
import { Button } from './ui/button'

/** Периоды на выбор: текущий и прошлый месяц, четверти. */
export function reportPeriods(): { value: string; title: string }[] {
  const today = new Date()
  const month = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
  const previous = new Date(today.getFullYear(), today.getMonth() - 1, 1)
  const previousCode = `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, '0')}`
  return [
    { value: month, title: `${t('текущий месяц')} · ${month}` },
    { value: previousCode, title: `${t('прошлый месяц')} · ${previousCode}` },
    { value: 'q1', title: t('1 четверть') },
    { value: 'q2', title: t('2 четверть') },
    { value: 'q3', title: t('3 четверть') },
    { value: 'q4', title: t('4 четверть') },
  ]
}

export const TEMPLATE_OPTIONS: { value: ReportTemplate; title: string }[] = [
  { value: 'review', title: t('Вариант 1 · отзыв об успеваемости') },
  { value: 'progress', title: t('Вариант 2 · отчёт о прогрессе') },
  { value: 'standard', title: t('Стандартный отчёт LMS') },
]

const LANGUAGE_OPTIONS = [
  { value: '', title: t('язык группы') },
  { value: 'kk', title: t('Казахский') },
  { value: 'ru', title: t('Русский') },
]

export interface ReportChoice {
  template: ReportTemplate
  language: '' | 'ru' | 'kk'
  period: string
  from: string
  to: string
}

/** С начала месяца по сегодня — самый частый период отчёта по шаблону школы. */
export function defaultChoice(): ReportChoice {
  const today = todayAlmaty()
  return { template: 'review', language: '', period: reportPeriods()[0].value, from: `${today.slice(0, 8)}01`, to: today }
}

export function choiceInput(choice: ReportChoice): BuildReportsInput {
  if (choice.template === 'standard') return { template: 'standard', period: choice.period }
  return { template: choice.template, language: choice.language, date_from: choice.from, date_to: choice.to }
}

/** Вид, язык и период отчёта — общие поля обоих окон сборки. */
export function ReportChoiceFields({ value, onChange, mark }: { value: ReportChoice; onChange: (next: ReportChoice) => void; mark?: (period: string, title: string) => string }) {
  const periods = reportPeriods()
  return (
    <>
      <Field kind="select" name="template" label={t('Вид отчёта')} value={value.template} onChange={(next) => onChange({ ...value, template: next as ReportTemplate })} options={TEMPLATE_OPTIONS} />
      {value.template === 'standard' ? (
        <Field kind="select" name="period" label={t('Период')} value={value.period} onChange={(next) => onChange({ ...value, period: next })} options={periods.map((row) => ({ value: row.value, title: mark ? mark(row.value, row.title) : row.title }))} />
      ) : (
        <>
          <Field kind="select" name="language" label={t('Язык')} value={value.language} onChange={(next) => onChange({ ...value, language: next as ReportChoice['language'] })} options={LANGUAGE_OPTIONS} />
          <div className="acad__pair">
            <Field kind="date" name="from" label={t('С')} value={value.from} max={value.to} onChange={(next) => onChange({ ...value, from: next })} />
            <Field kind="date" name="to" label={t('По')} value={value.to} min={value.from} onChange={(next) => onChange({ ...value, to: next })} />
          </div>
        </>
      )}
    </>
  )
}

export default function BuildReportDialog({ student, studentName, onClose }: { student: number; studentName: string; onClose: () => void }) {
  const build = useBuildReports()
  const navigate = useNavigate()
  const [choice, setChoice] = useState<ReportChoice>(defaultChoice)
  const [error, setError] = useState('')
  return (
    <Modal title={t('Отчёт родителям')} note={studentName} onClose={onClose}>
      <ReportChoiceFields value={choice} onChange={setChoice} />
      {error && <p className="t-note text-bad">{error}</p>}
      <div className="acad__actions">
        <Button
          disabled={build.isPending}
          onClick={() =>
            build.mutate(
              { ...choiceInput(choice), student },
              {
                onSuccess: (r) => {
                  toast.success(`${t('Отчёт собран')} · ${t(r.title)}`)
                  onClose()
                  if (r.report) navigate(`/reports?${new URLSearchParams({ open: String(r.report), ...(r.period ? { period: r.period } : {}) }).toString()}`)
                },
                onError: (e) => setError(e.message),
              },
            )
          }
        >
          {t('Собрать')}
        </Button>
        <Button variant="outline" onClick={onClose}>
          {t('Отмена')}
        </Button>
      </div>
    </Modal>
  )
}
