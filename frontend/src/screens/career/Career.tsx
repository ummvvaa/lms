/**
 * Профтест у ученика: тесты, которые открыл учитель профориентации, его попытки
 * и разборы, которые учитель решил показать (решение владельца, 08.10.2026).
 * Баллы по шкалам ученик видит сами по себе; ярлыков и чужих результатов нет.
 */
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useMyCareer, useMyStart, type CareerAnalysis, type MyCareer } from '../../api/career'
import { Row, Rows } from '../../components/patterns'
import { Bar, Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t, tn } from '../../i18n'
import { formatDate } from '../../lib/format'
import Icon from '../../layout/icons'
import './career-my.css'

type MyTest = MyCareer['tests'][number]

function statusChip(row: MyTest) {
  if (row.status === 'done')
    return (
      <Chip tone="good" size="sm">
        {t('сдан')}
      </Chip>
    )
  if (row.status === 'in_progress')
    return (
      <Chip tone="warn" size="sm">
        {t('идёт')}
      </Chip>
    )
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
            note={[
              direction.professions,
              direction.subjects ? t('Предметы: {subjects}', { subjects: direction.subjects }) : '',
              direction.exams ? t('Экзамены: {exams}', { exams: direction.exams }) : '',
            ]
              .filter(Boolean)
              .join(' · ')}
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
    start.mutate(row.id, {
      onSuccess: (attempt) => navigate(`/career/${attempt.id}`),
      onError: (error) => toast.error(error.message),
    })
  }

  /** доля пути теста: сдан — вся, идёт — отвеченная часть, не начат — ноль */
  const shareOf = (row: MyTest) =>
    row.status === 'done'
      ? 100
      : row.status === 'in_progress' && row.items
        ? (row.answered / row.items) * 100
        : 0

  const how = (
    <DataCard title={t('Как это работает')} className="cmy__how">
      <ol className="cmy__steps">
        <li>
          <Chip tone="accent" size="sm" className="num">
            1
          </Chip>
          <span>{t('Учитель профориентации открывает тест вашей группе')}</span>
        </li>
        <li>
          <Chip tone="accent" size="sm" className="num">
            2
          </Chip>
          <span>{t('Тест проходится один раз, ответы сохраняются по ходу')}</span>
        </li>
        <li>
          <Chip tone="accent" size="sm" className="num">
            3
          </Chip>
          <span>{t('Результат остаётся здесь. Пройти заново можно, если откроет учитель')}</span>
        </li>
      </ol>
    </DataCard>
  )

  return (
    <div className="lay-screen">
      <ScreenHead
        title={t('Профтест')}
        subtitle={tests.length ? t('Сдано {done} из {total}', { done, total: tests.length }) : undefined}
      />
      {tests.length === 0 ? (
        <>
          <DataCard title={t('Тесты')} empty={t('учитель профориентации ещё не открыл ни одного теста')} />
          {how}
        </>
      ) : (
        <section className="lay-3">
          <DataCard title={t('Тесты')} count={tests.length} className="lay-span2 card--beam">
            <div className="cmy__list">
              {tests.map((row) => (
                <div key={row.id} className="cmy__test">
                  <span className={`cmy__ico cmy__ico--${row.status}`} aria-hidden="true">
                    <Icon name="compass" size={20} />
                  </span>
                  <span className="cmy__name">
                    <b>{row.title}</b>
                    <span className="t-note">
                      {[
                        tn(row.items, '{n} утверждение|{n} утверждения|{n} утверждений'),
                        row.status === 'in_progress'
                          ? t('отвечено {done} из {total}', { done: row.answered, total: row.items })
                          : '',
                        row.finished_at ? t('сдан {date}', { date: formatDate(row.finished_at) }) : '',
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  </span>
                  <span className="cmy__state">
                    {statusChip(row)}
                    <Bar percent={shareOf(row)} color={row.status === 'done' ? 'var(--good)' : undefined} />
                  </span>
                  <Button
                    variant={row.status === 'done' ? 'outline' : 'default'}
                    size="sm"
                    disabled={start.isPending}
                    onClick={() => open(row)}
                  >
                    {row.status === 'done'
                      ? t('Результат')
                      : row.status === 'in_progress'
                        ? t('Продолжить')
                        : t('Начать')}
                  </Button>
                </div>
              ))}
            </div>
          </DataCard>
          {how}
        </section>
      )}
      {analyses.map((analysis) => (
        <AnalysisCard key={analysis.id} analysis={analysis} />
      ))}
    </div>
  )
}
