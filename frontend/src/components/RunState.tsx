/**
 * Строка запуска фоновой операции на месте её кнопки.
 *
 * Пока запуск в очереди или идёт — «Идёт разбор… с 11:42» и «Отменить»
 * (тем, кто запустил, и администратору). Не получился — причина простыми
 * словами и «Запустить заново»; отменён — подпись «Отменён» и та же кнопка.
 * Готовый запуск строки не оставляет: результат уже на экране.
 * Уйти со страницы можно — запуск продолжится, про конец скажет колокольчик.
 */
import { toast } from 'sonner'
import { isActiveRun, useJobActions, type JobRow } from '../api/hooks'
import { t } from '../i18n'
import { formatTime } from '../lib/format'
import { Chip } from './ui'
import { Button } from './ui/button'
import './jobs.css'

export default function RunState({
  run,
  running,
  onRestart,
  restarting = false,
  onChanged,
}: {
  run: JobRow | null | undefined
  /** что идёт, словами: «Идёт разбор…», «Идёт подбор…» */
  running: string
  /** «Запустить заново»; нет — кнопки нет */
  onRestart?: () => void
  restarting?: boolean
  /** перечитать экран после отмены */
  onChanged?: () => void
}) {
  const { cancel } = useJobActions()
  if (!run || run.status === 'done') return null

  if (isActiveRun(run)) {
    const since = run.started_at ?? run.created_at
    return (
      <div className="runstate" role="status">
        <span className="runstate__text">
          {run.status === 'queued' ? t('В очереди') : running}{' '}
          <span className="num">{t('с {time}', { time: formatTime(since) })}</span>
        </span>
        {run.can_cancel && (
          <Button
            variant="outline"
            size="sm"
            disabled={cancel.isPending}
            onClick={() =>
              cancel.mutate(run.id, {
                onSuccess: () => {
                  toast.success(t('Запуск отменён'))
                  onChanged?.()
                },
                onError: (error) => toast.error(error.message),
              })
            }
          >
            {t('Отменить')}
          </Button>
        )}
      </div>
    )
  }

  const failed = run.status === 'failed'
  return (
    <div className="runstate" role="status">
      <Chip size="sm" tone={failed ? 'bad' : 'neutral'}>
        {run.status_title}
      </Chip>
      {failed && <span className="runstate__text runstate__reason">{run.error || t('не получилось')}</span>}
      {onRestart && (
        <Button variant="outline" size="sm" disabled={restarting} onClick={onRestart}>
          {t('Запустить заново')}
        </Button>
      )}
    </div>
  )
}
