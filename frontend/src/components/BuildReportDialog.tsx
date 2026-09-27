/**
 * Отчёт родителям на одного ученика за выбранный период (решение владельца,
 * 27.09.2026). Открывается из карточки ученика и из списка отчётов;
 * собранный отчёт открывается на экране отчётов. Делают четыре роли —
 * куратор, Кымбат, Салтанат и администратор; кнопку показывают экраны
 * по `REPORT_ROLES`, право держит сервер.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useBuildReports } from '../api/academics'
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

export default function BuildReportDialog({ student, studentName, onClose }: { student: number; studentName: string; onClose: () => void }) {
  const build = useBuildReports()
  const navigate = useNavigate()
  const periods = reportPeriods()
  const [period, setPeriod] = useState(periods[0].value)
  const [error, setError] = useState('')
  return (
    <Modal title={t('Отчёт родителям')} note={studentName} onClose={onClose}>
      <Field kind="select" name="period" label={t('Период')} value={period} onChange={setPeriod} options={periods} error={error || undefined} />
      <div className="acad__actions">
        <Button
          disabled={build.isPending}
          onClick={() =>
            build.mutate(
              { period, student },
              {
                onSuccess: (r) => {
                  toast.success(`${t('Отчёт собран')} · ${t(r.title)}`)
                  onClose()
                  if (r.report) navigate(`/reports?open=${r.report}`)
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
