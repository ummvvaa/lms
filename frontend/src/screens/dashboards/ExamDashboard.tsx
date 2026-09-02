/**
 * Кабинет Кымбат — экзамены (фаза 49).
 *
 * Сверху четыре числа: средний IELTS с целью школы, средний SAT, сколько
 * моков просело и сколько слов ученика ждёт решения. Слева очередь баллов
 * и целей, справа — кто просел и какие экзамены ближе всего. Внизу
 * распределение школы по диапазонам и классы без целей.
 */
import { useNavigate } from 'react-router-dom'
import { useCabinet } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import OnboardingQueue from '../../components/OnboardingQueue'
import PendingQueue from '../../components/PendingQueue'
import { Row, Rows } from '../../components/patterns'
import { Bar, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { CabinetColumns, CabinetStats } from './cabinet'

interface ExamCabinet {
  title: string
  owner: string
  stats: Parameters<typeof CabinetStats>[0]['stats']
  drops: {
    student_id: number
    student: string
    exam: string
    previous: number
    latest: number
    delta: number
  }[]
  upcoming: { title: string; date: string; students: number }[]
  ranges: { title: string; count: number; filter: Record<string, string> }[]
  without_goals: { code: string; students: number }[]
}

export default function ExamDashboard() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useCabinet()
  const schoolIsEmpty = useSchoolIsEmpty()

  if (isLoading) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (schoolIsEmpty)
    return (
      <EmptyDashboard
        title={t('Экзамены')}
        hint={t('Здесь появятся баллы школы')}
        what={t('Средние по IELTS и SAT считаются из внесённых баллов.')}
        detail={t('Баллы вносит ученик, вы подтверждаете в очереди.')}
        guide
      />
    )

  const cabinet = data as unknown as ExamCabinet
  const maxRange = Math.max(1, ...cabinet.ranges.map((row) => row.count))

  return (
    <div>
      <ScreenHead
        title={t(cabinet.title)}
        subtitle={t(cabinet.owner)}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => navigate('/exam-kinds')}>
              {t('Банк заданий')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => navigate('/mocks')}>
              {t('Пробные')}
            </Button>
            <Button size="sm" onClick={() => navigate('/table')}>
              {t('Внести результаты')}
            </Button>
          </>
        }
      />

      <GettingStarted />
      <CabinetStats stats={cabinet.stats} />

      <CabinetColumns
        main={
          <>
            <OnboardingQueue />
            <PendingQueue note="Ученики внесли баллы и цели. Подтвердите или отклоните." />

            <DataCard
              title={t('Динамика по школе')}
              note={t('Сколько учеников в каждом диапазоне')}
              accent="teal"
            >
              {/* Полоса открывает этих учеников в таблице: число, в которое
                  нельзя провалиться, — половина ответа (правило фазы 8) */}
              {cabinet.ranges.map((range) => (
                <button
                  key={range.title}
                  type="button"
                  className="cabinet__barrow cabinet__barrow--click"
                  onClick={() => navigate(`/table?${new URLSearchParams(range.filter ?? {}).toString()}`)}
                >
                  <span className="cabinet__barhead">
                    <span>{t(range.title)}</span>
                    <b className="num">{range.count}</b>
                  </span>
                  <Bar percent={(range.count / maxRange) * 100} color="var(--teal)" />
                </button>
              ))}
            </DataCard>
          </>
        }
        aside={
          <>
            <DataCard
              title={t('Мок просел')}
              note={t('Нужно вмешаться')}
              accent="risk"
              count={cabinet.drops.length}
            >
              {cabinet.drops.length === 0 && (
                <p className="muted rows__empty">{t('Ни у кого балл не просел с прошлой попытки')}</p>
              )}
              <Rows>
                {cabinet.drops.map((drop) => (
                  <Row
                    key={`${drop.student_id}-${drop.exam}`}
                    title={drop.student}
                    note={`${drop.exam} ${drop.previous} → ${drop.latest}`}
                    right={
                      <Badge variant="risk" className="num">
                        {drop.delta}
                      </Badge>
                    }
                    onOpen={() => navigate(`/students/${drop.student_id}`)}
                    openLabel={t('Открыть карточку')}
                  />
                ))}
              </Rows>
            </DataCard>

            <DataCard title={t('Ближайшие экзамены')} note={t('И сколько человек сдают')} accent="indigo">
              {cabinet.upcoming.length === 0 && (
                <p className="muted rows__empty">{t('Дат экзаменов пока нет — их ставят ученики целями')}</p>
              )}
              <Rows>
                {cabinet.upcoming.map((row) => (
                  <Row
                    key={`${row.title}-${row.date}`}
                    title={row.title}
                    note={`${new Date(row.date).toLocaleDateString('ru')} · ${row.students} ${t('чел.')}`}
                  />
                ))}
              </Rows>
            </DataCard>

            <DataCard
              title={t('Без целей по экзаменам')}
              note={t('Не поставили цель и дату')}
              accent="warn"
              count={cabinet.without_goals.reduce((sum, row) => sum + row.students, 0)}
            >
              {cabinet.without_goals.length === 0 && (
                <p className="muted rows__empty">{t('Цели поставлены у всех групп')}</p>
              )}
              <Rows>
                {cabinet.without_goals.map((row) => (
                  <Row
                    key={row.code}
                    title={row.code}
                    note={`${row.students} ${t('чел.')}`}
                    onOpen={() => navigate(`/table?group=${encodeURIComponent(row.code)}`)}
                    openLabel={t('Открыть группу')}
                  />
                ))}
              </Rows>
            </DataCard>
          </>
        }
      />
    </div>
  )
}
