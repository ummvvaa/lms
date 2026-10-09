/**
 * Результаты ученика глазами сотрудника — окно по центру, как видит сам ученик:
 * баллы по шкалам полосками по каждому сданному тесту (вкладки, если тестов
 * несколько); тому, кто ведёт тесты, — «Разрешить пройти заново».
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { useCareerRetake, useStudentCareer } from '../../api/career'
import Modal from '../../components/Modal'
import { Chip, ErrorNote, Loading, ScreenTabs } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { formatDate } from '../../lib/format'
import ScoreBars from './ScoreBars'

export default function StudentResultsCard({ student, attempt, manage, onClose }: { student: number; attempt?: number | null; manage: boolean; onClose: () => void }) {
  const query = useStudentCareer(student)
  const retake = useCareerRetake()
  const [picked, setPicked] = useState<number | null>(attempt ?? null)
  const done = (query.data?.attempts ?? []).filter((row) => row.status === 'done')
  const current = done.find((row) => row.id === picked) ?? done[0] ?? null
  return (
    <Modal wide title={query.data?.student.full_name ?? t('Результаты')} note={query.data ? [query.data.student.group, t('сдано тестов: {n}', { n: done.length })].filter(Boolean).join(' · ') : undefined} onClose={onClose}>
      {query.isLoading && <Loading />}
      {query.error && <ErrorNote error={query.error} />}
      {query.data && done.length === 0 && <p className="acad__note">{t('ученик ещё не сдал ни одного теста')}</p>}
      {done.length > 1 && (
        <ScreenTabs value={String(current?.id ?? '')} onChange={(value) => setPicked(Number(value))} items={done.map((row) => ({ value: String(row.id), label: row.test.title }))} />
      )}
      {current && (
        <>
          <div className="toolbar mb-0">
            <Chip size="sm" tone="good">{t('сдан {date}', { date: formatDate(current.finished_at ?? '') })}</Chip>
            <span className="t-note">{t('Полоска — от наименьшего возможного балла к наибольшему')}</span>
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
