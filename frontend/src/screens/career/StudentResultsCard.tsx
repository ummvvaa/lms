/**
 * Результаты ученика глазами сотрудника — окно по центру, как видит сам ученик:
 * баллы по шкалам полосками по каждому сданному тесту (вкладки, если тестов
 * несколько); тому, кто ведёт тесты, — «Разрешить пройти заново».
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCareerRetake, useStudentCareer } from '../../api/career'
import Modal from '../../components/Modal'
import { ErrorNote, Loading, ScreenTabs } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { formatDate } from '../../lib/format'
import ScoreBars from './ScoreBars'
import { shortTitle } from './shortTitle'

export default function StudentResultsCard({ student, attempt, manage, onClose }: { student: number; attempt?: number | null; manage: boolean; onClose: () => void }) {
  const query = useStudentCareer(student)
  const retake = useCareerRetake()
  const [picked, setPicked] = useState<number | null>(attempt ?? null)
  const done = (query.data?.attempts ?? []).filter((row) => row.status === 'done')
  const current = done.find((row) => row.id === picked) ?? done[0] ?? null
  return (
    <Modal
      wide
      title={[t('Результаты'), query.data?.student.full_name, current?.finished_at ? formatDate(current.finished_at) : null].filter(Boolean).join(' · ')}
      note={query.data ? [query.data.student.group, t('сдано тестов: {n}', { n: done.length })].filter(Boolean).join(' · ') : undefined} onClose={onClose}>
      {query.isLoading && <Loading />}
      {query.error && <ErrorNote error={query.error} />}
      {query.data && done.length === 0 && <p className="acad__note">{t('ученик ещё не сдал ни одного теста')}</p>}
      {current && (
        <>
          <div className="cresults__head">
            {done.length > 1 && (
              <ScreenTabs value={String(current.id)} onChange={(value) => setPicked(Number(value))} items={done.map((row) => ({ value: String(row.id), label: shortTitle(row.test.title) }))} />
            )}
            <p className="t-note">{current.test.title}</p>
            <p className="t-note">{t('Полоска — от наименьшего возможного балла к наибольшему')}</p>
          </div>
          <ScoreBars scores={current.scores ?? []} threshold={current.threshold} />
        </>
      )}
      <div className="toolbar ctest__foot">
        {manage && current && (
          <Button
            variant="outline"
            disabled={retake.isPending}
            onClick={() =>
              retake.mutate(current.id, {
                onSuccess: () => toast.success(t('Ученик может пройти тест заново')),
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
      </div>
    </Modal>
  )
}
