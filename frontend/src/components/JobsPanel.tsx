/**
 * Плашка фоновых операций (фаза 47).
 *
 * До этой фазы у подбора вузов была своя плашка, у генерации плана — своя,
 * а у разбора файла и вызовов модели не было никакой: человек нажимал
 * и не знал, идёт ли что-нибудь. Здесь одна плашка на все долгие дела.
 *
 * Несколько операций — список, а не стопка окон друг на друге. Крестик
 * прячет строку, сама операция при этом продолжается. Про конец скажет
 * колокольчик, даже если человек ушёл на другой экран.
 */
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useJobActions, useJobs } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Bar } from './ui'
import { Button } from './ui/button'
import './jobs.css'
import { t } from '../i18n'

export default function JobsPanel() {
  const { me } = useAuth()
  const navigate = useNavigate()
  const jobs = useJobs(Boolean(me))
  const { dismiss, retry } = useJobActions()

  const rows = jobs.data?.results ?? []
  if (rows.length === 0) return null

  return (
    <aside className="jobs" role="status" aria-label={t('Фоновые операции')}>
      {rows.map((job) => (
        <div key={job.id} className={`jobs__row${job.status === 'failed' ? ' jobs__row--failed' : ''}`}>
          <button
            className="jobs__body"
            onClick={() => job.link && navigate(job.link)}
            disabled={!job.link}
            title={job.link ? t('Перейти к результату') : undefined}
          >
            <span className="jobs__title">{job.title}</span>
            {job.status === 'running' ? (
              <>
                <span className="muted jobs__note">
                  {job.stage || t('идёт…')} · <b className="num">{job.percent}%</b>
                </span>
                <Bar percent={job.percent} />
              </>
            ) : (
              <span className="muted jobs__note">{job.error || t('не получилось')}</span>
            )}
          </button>
          <div className="jobs__actions">
            {job.status === 'failed' && job.can_retry && (
              <Button
                variant="outline"
                size="sm"
                disabled={retry.isPending}
                onClick={() =>
                  retry.mutate(job.id, {
                    onSuccess: () => toast.success(t('Повторяю операцию')),
                    onError: (error) => toast.error(error.message),
                  })
                }
              >
                {t('Повторить')}
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              aria-label={t('Скрыть плашку')}
              onClick={() => dismiss.mutate(job.id)}
            >
              ×
            </Button>
          </div>
        </div>
      ))}
    </aside>
  )
}
