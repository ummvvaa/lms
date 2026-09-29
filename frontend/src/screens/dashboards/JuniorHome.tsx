/**
 * Главная ученика 8–10: учёба вместо готовности к подаче.
 *
 * Сверху четыре числа — средний балл за четверть, посещаемость, ближайший
 * СОР, достижения. Слева уроки сегодня с оценками, справа «Скоро» (СОР, СОЧ,
 * олимпиады, соревнования) и последние оценки. Всё считает сервер
 * (`academics/junior_home.py`); поступления здесь нет ни строкой.
 */
import { useNavigate } from 'react-router-dom'
import { gradeTone, useMyHome } from '../../api/academics'
import { Row, Rows, StatRow } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { CabinetBoard } from './cabinet'
import './student.css'

/** Куда ведёт число: балл и СОР — к оценкам и календарю, достижения — к олимпиадам. */
const KPI_LINK: Record<string, string> = {
  average: '/grades',
  attendance: '/grades',
  sor: '/calendar',
  achievements: '/olympiads',
}

/** Цвет чипа «Скоро»: СОЧ тяжелее СОР, олимпиады и спорт — пометкой. */
const SOON_TONE: Record<string, Tone> = { sor: 'warn', soch: 'bad', olympiad: 'info', competition: 'info' }

export default function JuniorHome() {
  const navigate = useNavigate()
  const home = useMyHome()

  if (home.isLoading) return <Loading kind="cards" />
  if (home.error) return <ErrorNote error={home.error} />
  if (!home.data) return null
  const data = home.data

  return (
    <div>
      <ScreenHead title={t('Главная')} subtitle={[data.date_words, data.quarter].filter(Boolean).join(' · ')} />

      <StatRow>
        {data.kpis.map((kpi) => (
          <Kpi
            key={kpi.code}
            label={t(kpi.title)}
            value={kpi.value || null}
            note={kpi.note}
            tone={kpi.tone || undefined}
            to={KPI_LINK[kpi.code]}
          />
        ))}
      </StatRow>

      <CabinetBoard
        cards={[
          {
            key: 'lessons',
            column: 'main',
            rows: Math.max(data.lessons.length, 1),
            node: (
              <DataCard
                title={t('Уроки сегодня')}
                count={data.lessons.length || undefined}
                empty={data.lessons.length === 0 && data.lessons_empty}
                right={
                  <Button variant="link" size="sm" onClick={() => navigate('/schedule')}>
                    {t('Расписание')}
                  </Button>
                }
              >
                <Rows>
                  {data.lessons.map((lesson) => (
                    <Row
                      key={lesson.id}
                      lead={<span className="num t-note">{lesson.bell}</span>}
                      title={lesson.subject}
                      note={[lesson.cohort, lesson.room].filter(Boolean).join(' · ')}
                      right={
                        lesson.status_title ? (
                          <Chip tone="warn" size="sm">
                            {lesson.status_title}
                          </Chip>
                        ) : lesson.grade !== null ? (
                          <Chip tone={gradeTone(lesson.mark) as Tone} size="sm">
                            {String(lesson.grade)}
                          </Chip>
                        ) : lesson.kind_label ? (
                          <Chip tone={SOON_TONE[lesson.kind] ?? 'warn'} size="sm">
                            {lesson.kind_label}
                          </Chip>
                        ) : undefined
                      }
                    />
                  ))}
                </Rows>
              </DataCard>
            ),
          },
          {
            key: 'soon',
            column: 'aside',
            rows: Math.max(data.soon.length, 1),
            node: (
              <DataCard
                title={t('Скоро')}
                empty={data.soon.length === 0 && t('в ближайший месяц работ и соревнований нет')}
                right={
                  <Button variant="link" size="sm" onClick={() => navigate('/calendar')}>
                    {t('Календарь')}
                  </Button>
                }
              >
                <Rows>
                  {data.soon.map((row) => (
                    <Row
                      key={`${row.kind}-${row.date}-${row.title}`}
                      title={row.title}
                      note={row.when}
                      to={row.link}
                      right={
                        <Chip tone={SOON_TONE[row.kind] ?? 'neutral'} size="sm">
                          {row.kind_label}
                        </Chip>
                      }
                    />
                  ))}
                </Rows>
              </DataCard>
            ),
          },
          {
            key: 'recent',
            column: 'aside',
            rows: Math.max(data.recent.length, 1),
            node: (
              <DataCard
                title={t('Последние оценки')}
                empty={data.recent.length === 0 && t('оценок пока нет')}
                right={
                  <Button variant="link" size="sm" onClick={() => navigate('/grades')}>
                    {t('Оценки')}
                  </Button>
                }
              >
                <Rows>
                  {data.recent.map((row) => (
                    <Row
                      key={row.id}
                      title={row.subject}
                      note={row.detail}
                      right={
                        <Chip tone={gradeTone(row.mark) as Tone} size="sm">
                          {String(row.mark ?? row.value)}
                        </Chip>
                      }
                    />
                  ))}
                </Rows>
              </DataCard>
            ),
          },
        ]}
      />
    </div>
  )
}
