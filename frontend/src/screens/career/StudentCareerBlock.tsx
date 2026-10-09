/**
 * Блок «Профтест» в карточке ученика у сотрудников: сданные тесты с баллами
 * и разборы. Читают учитель профориентации, администратор, Асем и куратор
 * своей группы; правка — на экране «Профтест».
 */
import { useState } from 'react'
import { useStudentCareer } from '../../api/career'
import { Row, Rows } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Loading } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tn } from '../../i18n'
import { formatDate, formatDateTime } from '../../lib/format'
import AnalysisCard from './AnalysisCard'
import ScoreBars from './ScoreBars'

export default function StudentCareerBlock({ studentId, manage = false }: { studentId: number; manage?: boolean }) {
  const query = useStudentCareer(studentId)
  const [open, setOpen] = useState<number | null>(null)
  const [analysis, setAnalysis] = useState<number | null>(null)
  if (query.isLoading) return <Loading kind="cards" />
  if (query.error) return <ErrorNote error={query.error} />
  if (!query.data) return null
  const { attempts, analyses } = query.data
  const current = analyses.find((row) => row.id === analysis) ?? null
  return (
    <div className="acad__stack">
      <DataCard title={t('Тесты профориентации')} count={attempts.length || undefined} empty={attempts.length === 0 && t('ученик ещё не проходил тестов')}>
        <Rows>
          {attempts.map((attempt) => (
            <Row
              key={attempt.id}
              icon="compass"
              tone={attempt.status === 'done' ? 'good' : 'warn'}
              title={attempt.test.title}
              note={attempt.finished_at ? t('сдан {date}', { date: formatDate(attempt.finished_at) }) : t('идёт')}
              acts={
                attempt.status === 'done' ? (
                  <Button variant="outline" size="sm" onClick={() => setOpen(open === attempt.id ? null : attempt.id)}>
                    {open === attempt.id ? t('Скрыть баллы') : t('Баллы')}
                  </Button>
                ) : undefined
              }
            />
          ))}
        </Rows>
        {attempts
          .filter((attempt) => attempt.id === open && attempt.scores)
          .map((attempt) => (
            <ScoreBars key={attempt.id} scores={attempt.scores ?? []} threshold={attempt.threshold} limit={8} />
          ))}
      </DataCard>
      <DataCard title={t('Разборы')} count={analyses.length || undefined} empty={analyses.length === 0 && t('разборов пока нет')}>
        <Rows>
          {analyses.map((row) => (
            <Row
              key={row.id}
              icon="sparkle"
              title={row.tests.map((test) => test.title).join(', ')}
              note={[formatDateTime(row.created_at), tn(row.directions.length, '{n} направление|{n} направления|{n} направлений')].join(' · ')}
              right={
                <Chip size="sm" tone={row.status === 'done' ? 'good' : row.status === 'failed' ? 'bad' : 'warn'}>
                  {row.status === 'done' ? t('готов') : row.status_title}
                </Chip>
              }
              onOpen={() => setAnalysis(row.id)}
              openLabel={t('Открыть')}
            />
          ))}
        </Rows>
      </DataCard>
      {current && <AnalysisCard analysis={current} manage={manage} onClose={() => setAnalysis(null)} />}
    </div>
  )
}
