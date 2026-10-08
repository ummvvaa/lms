/**
 * Попытка ученика глазами сотрудника: баллы полосками и «Разрешить пройти заново»
 * (только тем, кто ведёт тесты). Прежняя попытка уходит в историю, разборы по ней остаются.
 */
import { toast } from 'sonner'
import { useCareerAttempt, useCareerRetake } from '../../api/career'
import EditDrawer from '../../components/EditDrawer'
import { ErrorNote, Loading } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { formatDate } from '../../lib/format'
import ScoreBars from './ScoreBars'

export default function AttemptDrawer({ attempt, manage, onClose }: { attempt: number; manage: boolean; onClose: () => void }) {
  const query = useCareerAttempt(attempt)
  const retake = useCareerRetake()
  const data = query.data
  return (
    <EditDrawer
      open
      onClose={onClose}
      title={data?.student?.full_name ?? t('Попытка')}
      sub={data ? [data.test.title, data.finished_at ? t('сдан {date}', { date: formatDate(data.finished_at) }) : t('идёт')].join(' · ') : undefined}
      footer={
        <>
          {manage && data?.status === 'done' && (
            <Button
              variant="outline"
              disabled={retake.isPending}
              onClick={() =>
                retake.mutate(attempt, {
                  onSuccess: () => {
                    toast.success(t('Ученик может пройти тест заново'))
                    onClose()
                  },
                  onError: (error) => toast.error(error.message),
                })
              }
            >
              {t('Разрешить пройти заново')}
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>
            {t('Закрыть')}
          </Button>
        </>
      }
    >
      {query.isLoading && <Loading />}
      {query.error && <ErrorNote error={query.error} />}
      {data?.scores && <ScoreBars scores={data.scores} threshold={data.threshold} compact />}
      {data && data.status !== 'done' && <p className="acad__note">{t('Ученик ещё отвечает — баллы появятся после сдачи')}</p>}
    </EditDrawer>
  )
}
