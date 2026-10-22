/**
 * Оценки ученика: по предметам — ФО, СОР, СОЧ, «сейчас выходит» или итог,
 * пропуски; последние оценки с комментарием учителя (оценки за ДЗ со сдачей —
 * строками «ДЗ», из 10); дни с пропусками; доля ДЗ, сданных вовремя.
 *
 * «Сейчас выходит» — числом и оценкой, без пометки о риске: ярлыков,
 * средних по группе и других учеников ученику не показывают (инвариант №7).
 *
 * Раскладка по макету: период в шапке справа, под шапкой — показатели,
 * затем главная таблица «По предметам» во всю ширину (ФО — отметками,
 * «сейчас» — полосой), ниже две колонки: последние оценки и дни с пропусками.
 */
import { useState } from 'react'
import { useMyGrades, type StudentGrades as Grades } from '../../api/academics'
import DataTable, { type Column } from '../../components/DataTable'
import { Row, Rows, ShowAll } from '../../components/patterns'
import { Bar, Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { counted, t, tk } from '../../i18n'
import { dateWords, lateTotal, PeriodSwitch } from './shared'
import { HomeworkKpi } from '../homework/myWork'
import '../dashboards/student.css'

/** Отметка в дне с пропусками словами: «SAT Math — не был», а не «SAT Math н». */
const MARK_WORD: Record<string, string> = {
  absent: tk('{subject} — не был'),
  excused: tk('{subject} — по уважительной'),
  late: tk('{subject} — опоздание'),
}

type Subject = Grades['subjects'][number]

/** Сколько последних ФО видно в строке предмета. */
const FO_IN_ROW = 6

/** Колонка «Сейчас»: итог, «выходит» с полосой процента, зачёт профориентации. */
function NowCell({ item }: { item: Subject }) {
  const s = item.stats
  const grade = s.final ?? s.quarter_grade
  if (item.career)
    return item.career.passed_at ? (
      <Chip size="sm" tone="good">
        {t('тест сдан {date}', { date: dateWords(item.career.passed_at) })}
      </Chip>
    ) : (
      <Chip size="sm">{t('тест не сдан')}</Chip>
    )
  if (item.course.subject.scheme !== 'kz') return <Chip size="sm">{t('только ФО')}</Chip>
  if (grade === null) return <Chip size="sm">{t('оценок мало для расчёта')}</Chip>
  const label = s.final !== null ? t('итог {grade}', { grade }) : s.quarter_pct !== null ? t('выходит {grade} · {pct} %', { grade, pct: s.quarter_pct }) : t('выходит {grade}', { grade })
  return (
    <span className="stugr__now">
      {s.quarter_pct !== null && (
        <span className="stugr__bar">
          <Bar percent={s.quarter_pct} />
        </span>
      )}
      <Chip size="sm" tone={s.final !== null ? 'accent' : 'neutral'}>
        {label}
      </Chip>
    </span>
  )
}

export default function StudentGrades() {
  const [period, setPeriod] = useState('')
  const { data, isLoading, error } = useMyGrades(period)
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const grades = data.grades ?? []
  const empty = data.subjects.length === 0
  // ФО предмета — те же отметки, что в «Последних оценках», по названию предмета
  const foOf = (item: Subject) => grades.filter((row) => row.kind === 'fo' && row.subject_title === item.course.subject.title).slice(0, FO_IN_ROW)
  const scale = data.scale
  const subtitle = [
    t(data.period.title),
    scale ? t('итог по шкале школы: ФО {fo} %, СОР {sor} %, СОЧ {soch} %', { fo: scale.weight_fo, sor: scale.weight_sor, soch: scale.weight_soch }) : '',
  ]
    .filter(Boolean)
    .join(' · ')

  const columns: Column<Subject>[] = [
    {
      key: 'subject',
      title: t('Предмет'),
      width: 'auto',
      phone: 'head',
      cell: (item) => (
        <span className="stugr__subj">
          <b>{item.course.subject.title}</b>
          {item.course.teacher && <span>{item.course.teacher.short}</span>}
        </span>
      ),
    },
    {
      key: 'fo',
      title: t('ФО'),
      width: '22%',
      cell: (item) => {
        if (item.career) return null
        const marks = foOf(item)
        if (marks.length === 0) return item.stats.fo_avg !== null ? <span className="num">{item.stats.fo_avg}</span> : <span className="stugr__none">{t('нет')}</span>
        return (
          <span className="stugr__marks">
            {marks.map((row) => (
              <Chip key={`${row.lesson}-${row.kind}`} size="sm">
                <span className="num">{row.value}</span>
              </Chip>
            ))}
          </span>
        )
      },
    },
    {
      key: 'sor',
      title: t('СОР'),
      width: '9%',
      align: 'right',
      cell: (item) => (item.stats.sor_max ? <span className="num">{`${item.stats.sor_got}/${item.stats.sor_max}`}</span> : <span className="stugr__none">{t('нет')}</span>),
    },
    {
      key: 'soch',
      title: t('СОЧ'),
      width: '9%',
      align: 'right',
      cell: (item) => (item.stats.soch_max ? <span className="num">{`${item.stats.soch_got}/${item.stats.soch_max}`}</span> : <span className="stugr__none">{t('нет')}</span>),
    },
    {
      key: 'absent',
      title: t('Пропуски'),
      width: '10%',
      align: 'right',
      cell: (item) => (item.stats.absent + item.stats.excused ? <span className="num">{item.stats.absent + item.stats.excused}</span> : <span className="stugr__none">{t('нет')}</span>),
    },
    {
      key: 'now',
      title: t('Сейчас'),
      width: '26%',
      cell: (item) => <NowCell item={item} />,
    },
  ]

  const att = data.attendance
  const homeworkShown = Boolean(data.homework && data.homework.total > 0 && data.homework.pct !== null)
  const kpis = [
    att.pct !== null && <Kpi key="pct" label={t('Посещаемость')} value={`${att.pct} %`} note={counted(att.total, 'урок|урока|уроков')} />,
    att.absent > 0 && <Kpi key="absent" label={t('Пропуски')} value={att.absent} note={t('без причины')} />,
    att.excused > 0 && <Kpi key="excused" label={t('По уважительной')} value={att.excused} />,
    att.late > 0 && <Kpi key="late" label={t('Опоздания')} value={att.late} note={lateTotal(att)} />,
    homeworkShown && <HomeworkKpi key="homework" homework={data.homework} />,
  ].filter(Boolean)

  return (
    <div className="lay-screen stugr">
      <ScreenHead title={t('Оценки')} subtitle={subtitle} actions={<PeriodSwitch value={data.period.code} periods={data.periods} onChange={setPeriod} />} />
      {/* показатели — только со значением: плитка «нет» ничего не говорит; дни с пропусками — рядом,
          короткий список напротив длинного оставлял пустоту */}
      <div className={data.days.length > 0 ? 'lay-main' : 'lay-stack'}>
        {kpis.length > 0 && <div className={`stugr__kpis stugr__kpis--${Math.min(kpis.length, 3)}`}>{kpis}</div>}
        {data.days.length > 0 && (
          <DataCard title={t('Дни с пропусками')} count={data.days.length}>
            <Rows>
              <ShowAll>
                {data.days.map((day) => (
                  <Row
                    key={day.date}
                    lead={<b className="num stu__slot">{Number(day.date.slice(8))}</b>}
                    title={`${day.weekday}, ${dateWords(day.date)}`}
                    note={day.marks.map((m) => t(MARK_WORD[m.mark ?? 'late'] ?? MARK_WORD.late, { subject: m.subject })).join(', ')}
                  />
                ))}
              </ShowAll>
            </Rows>
          </DataCard>
        )}
      </div>
      <DataCard className="card--beam" title={t('По предметам')} count={data.subjects.length || undefined} empty={empty && t('оценок за период ещё нет')}>
        <DataTable columns={columns} rows={data.subjects} rowKey={(item) => item.course.id} />
      </DataCard>
      <DataCard title={t('Последние оценки')} count={grades.length || undefined} empty={grades.length === 0 && t('за период оценок не было')}>
        <Rows>
          <ShowAll>
            {grades.map((row) => (
              <Row
                key={`${row.lesson}-${row.subject}-${row.kind}`}
                lead={<b className="num stu__slot">{row.value}</b>}
                title={`${row.subject_title} · ${row.kind_label}`}
                note={[dateWords(row.date), row.max ? t('из {max}', { max: row.max }) : '', row.comment ? `«${row.comment}»` : ''].filter(Boolean).join(' · ')}
                to={`/lessons/${row.lesson}`}
              />
            ))}
          </ShowAll>
        </Rows>
      </DataCard>
    </div>
  )
}
