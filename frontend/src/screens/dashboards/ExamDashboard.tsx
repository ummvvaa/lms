/**
 * Кабинет Кымбат — экзамены (фаза 49).
 *
 * Сверху три числа: средний IELTS с целью школы, средний SAT и сколько
 * слов ученика ждёт решения. «Мок просел» плиткой не стоит: он ниже списком,
 * где по каждому ученику есть действие, — второй раз незачем (фаза 80). Слева очередь баллов и целей и распределение
 * школы по диапазонам, справа — кто просел, группы без целей и ближайшие
 * экзамены. Колонки собирает `CabinetBoard` (фаза 80): пустая карточка —
 * одна строка внизу короткой колонки, список длиннее пяти строк свёрнут.
 */
import { useNavigate } from 'react-router-dom'
import { useCabinet, usePendingOnboarding, useStudentQueue } from '../../api/hooks'
import EmptyDashboard, { useSchoolIsEmpty } from '../../components/EmptyDashboard'
import GettingStarted from '../../components/GettingStarted'
import OnboardingQueue from '../../components/OnboardingQueue'
import PendingQueue from '../../components/PendingQueue'
import { Row, Rows, ShowAll } from '../../components/patterns'
import { Bar, Chip, DataCard, ErrorNote, Loading, ScreenHead } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { CabinetBoard, CabinetStats } from './cabinet'
import { useAcademicsCard } from '../academics/AcademicsBlock'

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
  // те же запросы, что у самих очередей: раскладке нужно знать, пусты ли они
  const students = useStudentQueue()
  const answers = usePendingOnboarding()
  // блок «Учёба»: уроки сегодня, не отмечено, просьбы, отчёты
  const academics = useAcademicsCard()

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
  const scored = cabinet.ranges.reduce((sum, row) => sum + row.count, 0)
  const queue = students.data?.results.length ?? 0
  const onboarding = answers.data?.length ?? 0

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

      <CabinetBoard
        cards={[
          academics,
          onboarding > 0 && {
            key: 'onboarding',
            column: 'main',
            rows: onboarding * 2,
            node: <OnboardingQueue />,
          },
          {
            key: 'queue',
            column: 'main',
            // строка очереди вдвое выше строки списка: в ней значения и кнопки
            rows: queue * 2,
            folded: queue === 0,
            node: <PendingQueue note="Ученики внесли баллы и цели. Подтвердите или отклоните." fold />,
          },
          {
            key: 'drops',
            column: 'aside',
            rows: cabinet.drops.length,
            folded: cabinet.drops.length === 0,
            node: (
              <DataCard
                title={t('Мок просел')}
                note={t('Нужно вмешаться')}
                accent="risk"
                count={cabinet.drops.length}
                empty={cabinet.drops.length === 0 && t('ни у кого балл не просел')}
              >
                <Rows>
                  <ShowAll>
                    {cabinet.drops.map((drop) => (
                      <Row
                        key={`${drop.student_id}-${drop.exam}`}
                        title={drop.student}
                        note={`${drop.exam} ${drop.previous} → ${drop.latest}`}
                        right={
                          <Chip tone="risk" className="num">
                            {drop.delta}
                          </Chip>
                        }
                        onOpen={() => navigate(`/students/${drop.student_id}`)}
                        openLabel={t('Открыть карточку')}
                      />
                    ))}
                  </ShowAll>
                </Rows>
              </DataCard>
            ),
          },
          {
            key: 'ranges',
            column: 'main',
            rows: cabinet.ranges.length,
            folded: scored === 0,
            narrow: true,
            node: (
              <DataCard
                title={t('Динамика по школе')}
                note={t('Сколько учеников в каждом диапазоне')}
                accent="teal"
                empty={scored === 0 && t('баллов пока нет')}
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
            ),
          },
          {
            key: 'without-goals',
            column: 'aside',
            rows: cabinet.without_goals.length,
            folded: cabinet.without_goals.length === 0,
            node: (
              <DataCard
                title={t('Без целей по экзаменам')}
                note={t('Не поставили цель и дату')}
                accent="warn"
                count={cabinet.without_goals.reduce((sum, row) => sum + row.students, 0)}
                empty={cabinet.without_goals.length === 0 && t('цели поставлены у всех групп')}
              >
                <Rows>
                  <ShowAll>
                    {cabinet.without_goals.map((row) => (
                      <Row
                        key={row.code}
                        title={row.code}
                        note={`${row.students} ${t('чел.')}`}
                        onOpen={() => navigate(`/table?group=${encodeURIComponent(row.code)}`)}
                        openLabel={t('Открыть группу')}
                      />
                    ))}
                  </ShowAll>
                </Rows>
              </DataCard>
            ),
          },
          {
            key: 'upcoming',
            column: 'aside',
            rows: cabinet.upcoming.length,
            folded: cabinet.upcoming.length === 0,
            node: (
              <DataCard
                title={t('Ближайшие экзамены')}
                note={t('И сколько человек сдают')}
                accent="indigo"
                empty={cabinet.upcoming.length === 0 && t('дат экзаменов нет')}
              >
                <Rows>
                  <ShowAll>
                    {cabinet.upcoming.map((row) => (
                      <Row
                        key={`${row.title}-${row.date}`}
                        title={row.title}
                        note={`${new Date(row.date).toLocaleDateString('ru')} · ${row.students} ${t('чел.')}`}
                      />
                    ))}
                  </ShowAll>
                </Rows>
              </DataCard>
            ),
          },
        ]}
      />
    </div>
  )
}
