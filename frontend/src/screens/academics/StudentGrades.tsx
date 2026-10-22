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
import { Row, Rows, ShowAll, StatRow } from '../../components/patterns'
import { Bar, Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { counted, t } from '../../i18n'
import { dateWords, lateTotal, PeriodSwitch } from './shared'
import { HomeworkKpi } from '../homework/myWork'
import '../dashboards/student.css'

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

  return (
    <div className="lay-screen stugr">
      <ScreenHead title={t('Оценки')} subtitle={subtitle} actions={<PeriodSwitch value={data.period.code} periods={data.periods} onChange={setPeriod} />} />
      <StatRow>
        <Kpi label={t('Посещаемость')} value={data.attendance.pct !== null ? `${data.attendance.pct} %` : null} none={t('уроков с отметкой не было')} note={counted(data.attendance.total, 'урок|урока|уроков')} />
        <Kpi label={t('Пропуски')} value={data.attendance.absent || null} none={t('нет')} note={t('без причины')} />
        <Kpi label={t('По уважительной')} value={data.attendance.excused || null} none={t('нет')} />
        <Kpi label={t('Опоздания')} value={data.attendance.late || null} none={t('нет')} note={lateTotal(data.attendance)} />
        <HomeworkKpi homework={data.homework} />
      </StatRow>
      <DataCard className="card--beam" title={t('По предметам')} count={data.subjects.length || undefined} empty={empty && t('оценок за период ещё нет')}>
        <DataTable columns={columns} rows={data.subjects} rowKey={(item) => item.course.id} />
      </DataCard>
      <div className={grades.length > 0 && data.days.length > 0 ? 'lay-2 stugr__lists' : 'lay-stack stugr__lists'}>
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
        <DataCard title={t('Дни с пропусками')} count={data.days.length || undefined} empty={data.days.length === 0 && t('пропусков нет')}>
          <Rows>
            <ShowAll>
              {data.days.map((day) => (
                <Row
                  key={day.date}
                  lead={<b className="num stu__slot">{Number(day.date.slice(8))}</b>}
                  title={`${day.weekday}, ${dateWords(day.date)}`}
                  note={day.marks.map((m) => `${m.subject} ${m.mark === 'absent' ? t('н') : m.mark === 'excused' ? t('у') : t('оп')}`).join(', ')}
                />
              ))}
            </ShowAll>
          </Rows>
        </DataCard>
      </div>
    </div>
  )
}
