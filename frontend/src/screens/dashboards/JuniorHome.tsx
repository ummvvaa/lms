/**
 * Главная ученика 8–10: учёба вместо готовности к подаче.
 *
 * Раскладка по макету: сверху главная карточка «следующий урок» с уроками
 * дня плитками и рядом кольцо посещаемости; ниже три карточки — ДЗ к сдаче,
 * последние оценки, «Скоро» (СОР, СОЧ, олимпиады, соревнования); внизу
 * числа-ссылки — средний балл, ближайший СОР, достижения. На телефоне —
 * шапка с аватаром, «следующий урок», два числа в ряд и уроки дня списком.
 * Всё считает сервер (`academics/junior_home.py`); поступления здесь нет ни строкой.
 */
import { useNavigate } from 'react-router'
import { gradeTone, useMyHome, type JuniorHome as HomeData } from '../../api/academics'
import { useAuth } from '../../auth/AuthContext'
import { Row, Rows } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, Ring, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { todayAlmaty } from '../../lib/dates'
import { usePhone } from '../../phone'
import {
  Columns,
  DateBox,
  findNext,
  firstNameOf,
  NextLessonCard,
  PhoneHead,
  TodayList,
  type TodayLesson,
} from './home-today'
import './student.css'
import './student-home.css'

/** Куда ведёт число: балл и посещаемость — к оценкам, СОР — к календарю, достижения — к олимпиадам. */
const KPI_LINK: Record<string, string> = {
  average: '/grades',
  attendance: '/grades',
  sor: '/calendar',
  achievements: '/olympiads',
}

/** Цвет чипа «Скоро»: СОЧ тяжелее СОР, олимпиады и спорт — пометкой. */
// ДЗ к сдаче в LMS — своим тоном: строка ведёт в задание (`/homework/<id>`)
const SOON_TONE: Record<string, Tone> = {
  sor: 'warn',
  soch: 'bad',
  olympiad: 'info',
  competition: 'info',
  homework: 'accent',
}

type Kpis = HomeData['kpis']

/** Уроки дня в общем виде: оценка, статус или вид работы — чипом. */
function todayLessons(data: HomeData): TodayLesson[] {
  return data.lessons.map((lesson) => ({
    key: String(lesson.id),
    slot: null,
    bell: lesson.bell,
    subject: lesson.subject,
    meta: [lesson.cohort, lesson.room].filter(Boolean).join(' · '),
    chip: lesson.status_title ? (
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
    ) : undefined,
  }))
}

/** Число-показатель с сервера: подпись — чипом, если у числа есть тон. */
function KpiOf({ kpi }: { kpi: Kpis[number] }) {
  return (
    <Kpi
      label={t(kpi.title)}
      value={kpi.value || null}
      note={kpi.note}
      tone={kpi.tone || undefined}
      to={KPI_LINK[kpi.code]}
    />
  )
}

/** Посещаемость кольцом: процент — то же число, что в показателе. */
function AttendanceCard({ kpi }: { kpi: Kpis[number] }) {
  const percent = Number.parseInt(kpi.value, 10)
  const known = Number.isFinite(percent)
  return (
    <DataCard className="stuhome__attend" title={t(kpi.title)}>
      <div className="stuhome__ring">
        {known ? (
          <Ring percent={percent}>
            <b className="num t-value">{kpi.value}</b>
          </Ring>
        ) : (
          <b className="kpi__value kpi__value--none">{t('нет')}</b>
        )}
        <Chip
          tone={kpi.tone === 'warn' ? 'warn' : known ? 'good' : 'neutral'}
          size="sm"
          className="stuhome__ringchip"
        >
          {kpi.note}
        </Chip>
      </div>
    </DataCard>
  )
}

/** Строки «Скоро»: ключ с номером строки — два одинаковых ДЗ на один день не сливаются. */
function SoonRows({ rows, chips }: { rows: HomeData['soon']; chips: boolean }) {
  const today = todayAlmaty()
  return (
    <Rows>
      {rows.map((row, index) => (
        <Row
          key={`${row.kind}-${row.link}-${row.date}-${index}`}
          lead={<DateBox iso={row.date} today={today} />}
          title={row.title}
          note={row.when}
          to={row.link}
          right={
            chips ? (
              <Chip tone={SOON_TONE[row.kind] ?? 'neutral'} size="sm">
                {row.kind_label}
              </Chip>
            ) : undefined
          }
        />
      ))}
    </Rows>
  )
}

export default function JuniorHome() {
  const navigate = useNavigate()
  const phone = usePhone()
  const { me } = useAuth()
  const home = useMyHome()

  if (home.isLoading) return <Loading kind="cards" />
  if (home.error) return <ErrorNote error={home.error} />
  if (!home.data) return null
  const data = home.data

  const lessons = todayLessons(data)
  const kpi = (code: string) => data.kpis.find((item) => item.code === code)
  const attendance = kpi('attendance')
  const others = data.kpis.filter((item) => item.code !== 'attendance')
  const greeting = t('Привет, {name}', { name: firstNameOf(me?.full_name ?? '') })
  const homework = data.soon.filter((row) => row.kind === 'homework')
  const soon = data.soon.filter((row) => row.kind !== 'homework')

  const homeworkCard = (
    <DataCard
      title={t('ДЗ к сдаче')}
      count={homework.length || undefined}
      empty={homework.length === 0 && t('сдавать сейчас нечего')}
      right={
        <Button variant="link" size="sm" onClick={() => navigate('/homework')}>
          {t('Все')}
        </Button>
      }
    >
      <SoonRows rows={homework} chips={false} />
    </DataCard>
  )
  const recentCard = (
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
            lead={
              <Chip tone={gradeTone(row.mark) as Tone} size="sm" className="stuhome__mark num">
                {String(row.mark ?? row.value)}
              </Chip>
            }
            title={row.subject}
            note={row.detail}
          />
        ))}
      </Rows>
    </DataCard>
  )
  const soonCard = (
    <DataCard
      title={t('Скоро')}
      empty={soon.length === 0 && t('в ближайший месяц работ и соревнований нет')}
      right={
        <Button variant="link" size="sm" onClick={() => navigate('/calendar')}>
          {t('Календарь')}
        </Button>
      }
    >
      <SoonRows rows={soon} chips />
    </DataCard>
  )

  if (phone)
    return (
      <div className="lay-screen">
        <PhoneHead title={greeting} line={[data.date_words, me?.group].filter(Boolean).join(' · ')} />
        <NextLessonCard
          lessons={lessons}
          empty={data.lessons_empty || t('уроков сегодня нет')}
          tiles={false}
        />
        <div className="stuhome__pair">
          <Kpi label={t('ДЗ к сдаче')} value={String(homework.length)} to="/homework" />
          {attendance && <KpiOf kpi={attendance} />}
        </div>
        {/* без звонков главный урок не выбрать — уроки дня уже строками в карточке выше */}
        {(findNext(lessons)?.index ?? -1) >= 0 && (
          <TodayList
            title={t('Сегодня')}
            lessons={lessons}
            empty={data.lessons_empty || t('уроков сегодня нет')}
          />
        )}
        {soonCard}
        {homework.length > 0 && homeworkCard}
        {recentCard}
        <div className="stuhome__pair">
          {others.map((item) => (
            <KpiOf key={item.code} kpi={item} />
          ))}
        </div>
      </div>
    )

  return (
    <div className="lay-screen">
      <ScreenHead
        title={greeting}
        subtitle={[data.date_words, data.quarter].filter(Boolean).join(' · ')}
        actions={
          <Button variant="outline" onClick={() => navigate('/schedule')}>
            {t('Расписание')}
          </Button>
        }
      />

      {/* две колонки вместо рядов: короткие карточки стоят стопкой справа, и столбцы
          кончаются вровень, а не карточка напротив длинной с пустотой внутри */}
      <Columns
        main={[
          {
            key: 'next',
            folded: false,
            node: (
              <NextLessonCard lessons={lessons} empty={data.lessons_empty || t('уроков сегодня нет')} tiles />
            ),
          },
          { key: 'recent', folded: data.recent.length === 0, node: recentCard },
        ]}
        aside={[
          {
            key: 'attendance',
            folded: !attendance,
            node: attendance ? <AttendanceCard kpi={attendance} /> : null,
          },
          { key: 'homework', folded: homework.length === 0, node: homeworkCard },
          { key: 'soon', folded: soon.length === 0, node: soonCard },
        ]}
      />

      <div className={`lay-${Math.max(others.length, 1)}`}>
        {others.map((item) => (
          <KpiOf key={item.code} kpi={item} />
        ))}
      </div>
    </div>
  )
}
