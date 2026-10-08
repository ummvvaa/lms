/**
 * Профтест у ученика: тесты, которые открыл учитель профориентации, его попытки
 * и разборы, которые учитель решил показать (решение владельца, 08.10.2026).
 * Баллы по шкалам ученик видит сами по себе; ярлыков и чужих результатов нет.
 */
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useMyCareer, useMyStart, type CareerAnalysis, type MyCareer } from '../../api/career'
import { Row, Rows } from '../../components/patterns'
import { Chip, DataCard, EmptyNote, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tk, tn } from '../../i18n'
import { formatDate } from '../../lib/format'

type MyTest = MyCareer['tests'][number]

function statusChip(row: MyTest) {
  if (row.status === 'done') return <Chip tone="good" size="sm">{t('сдан')}</Chip>
  if (row.status === 'in_progress') return <Chip tone="warn" size="sm">{t('идёт')}</Chip>
  return <Chip size="sm">{t('не начат')}</Chip>
}

export function AnalysisCard({ analysis }: { analysis: CareerAnalysis }) {
  return (
    <DataCard title={t('Разбор от учителя')} note={analysis.tests.map((test) => test.title).join(' · ')}>
      {analysis.summary && <p className="acad__note">{analysis.summary}</p>}
      <Rows>
        {analysis.directions.map((direction) => (
          <Row
            key={direction.id}
            icon="target"
            title={direction.title}
            note={[direction.professions, direction.subjects ? t('Предметы: {subjects}', { subjects: direction.subjects }) : '', direction.exams ? t('Экзамены: {exams}', { exams: direction.exams }) : ''].filter(Boolean).join(' · ')}
          />
        ))}
      </Rows>
      {analysis.directions.map((direction) =>
        direction.reasoning ? (
          <p key={direction.id} className="t-note">
            <b>{direction.title}.</b> {direction.reasoning}
          </p>
        ) : null,
      )}
    </DataCard>
  )
}

export default function Career() {
  const navigate = useNavigate()
  const state = useMyCareer()
  const start = useMyStart()
  if (state.isLoading) return <Loading kind="cards" />
  if (state.error) return <ErrorNote error={state.error} />
  if (!state.data) return null
  const { tests, analyses } = state.data
  const done = tests.filter((row) => row.status === 'done').length

  const open = (row: MyTest) => {
    if (row.attempt) {
      navigate(`/career/${row.attempt}`)
      return
    }
    start.mutate(row.id, { onSuccess: (attempt) => navigate(`/career/${attempt.id}`), onError: (error) => toast.error(error.message) })
  }

  return (
    <div>
      <ScreenHead title={t('Профтест')} subtitle={tests.length ? t('Сдано {done} из {total}', { done, total: tests.length }) : undefined} />
      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard title={t('Тесты')} count={tests.length || undefined} empty={tests.length === 0 && t('учитель профориентации ещё не открыл ни одного теста')}>
            <Rows>
              {tests.map((row) => (
                <Row
                  key={row.id}
                  icon="compass"
                  tone={row.status === 'done' ? 'good' : row.status === 'in_progress' ? 'warn' : 'neutral'}
                  title={row.title}
                  note={[
                    tn(row.items, '{n} утверждение|{n} утверждения|{n} утверждений'),
                    row.status === 'in_progress' ? t('отвечено {done} из {total}', { done: row.answered, total: row.items }) : '',
                    row.finished_at ? t('сдан {date}', { date: formatDate(row.finished_at) }) : '',
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                  right={statusChip(row)}
                  acts={
                    <Button variant={row.status === 'done' ? 'outline' : 'default'} size="sm" disabled={start.isPending} onClick={() => open(row)}>
                      {row.status === 'done' ? t('Результат') : row.status === 'in_progress' ? t('Продолжить') : t('Начать')}
                    </Button>
                  }
                />
              ))}
            </Rows>
          </DataCard>
          {analyses.map((analysis) => (
            <AnalysisCard key={analysis.id} analysis={analysis} />
          ))}
        </div>
        <div className="acad__stack">
          <DataCard title={t('Как это устроено')}>
            <Rows>
              <Row lead={<b className="num stu__slot">1</b>} title={t('Отвечайте на каждое утверждение — правильных ответов нет')} />
              <Row lead={<b className="num stu__slot">2</b>} title={t('Ответы сохраняются сами, тест можно закончить позже')} />
              <Row lead={<b className="num stu__slot">3</b>} title={t('После сдачи вы увидите баллы по сферам интересов')} />
            </Rows>
          </DataCard>
          {analyses.length === 0 && tests.length > 0 && (
            <DataCard title={t('Разбор от учителя')}>
              <EmptyNote what={tk('учитель покажет разбор после обсуждения результатов')} />
            </DataCard>
          )}
        </div>
      </div>
    </div>
  )
}
