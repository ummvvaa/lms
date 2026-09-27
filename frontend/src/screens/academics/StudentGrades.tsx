/**
 * Оценки ученика: по предметам — ФО, СОР, СОЧ, «сейчас выходит» или итог,
 * пропуски; последние оценки с комментарием учителя; дни с пропусками.
 *
 * «Сейчас выходит» — числом и оценкой, без пометки о риске: ярлыков,
 * средних по группе и других учеников ученику не показывают (инвариант №7).
 */
import { useState } from 'react'
import { useMyGrades } from '../../api/academics'
import { Row, Rows, ShowAll, StatRow } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead } from '../../components/ui'
import { t } from '../../i18n'
import { dateWords, PeriodSwitch } from './shared'
import '../dashboards/student.css'

export default function StudentGrades() {
  const [period, setPeriod] = useState('')
  const { data, isLoading, error } = useMyGrades(period)
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const grades = data.grades ?? []
  const empty = data.subjects.length === 0
  return (
    <div>
      <ScreenHead title={t('Оценки')} />
      <div className="acad__toolbar">
        <PeriodSwitch value={data.period.code} periods={data.periods} onChange={setPeriod} />
      </div>
      <StatRow>
        <Kpi label={t('Посещаемость')} value={data.attendance.pct !== null ? `${data.attendance.pct} %` : null} none={t('уроков с отметкой не было')} note={`${t('уроков')} ${data.attendance.total}`} />
        <Kpi label={t('Пропуски')} value={data.attendance.absent || null} none={t('нет')} note={t('без причины')} />
        <Kpi label={t('По уважительной')} value={data.attendance.excused || null} none={t('нет')} />
        <Kpi label={t('Опоздания')} value={data.attendance.late || null} none={t('нет')} />
      </StatRow>
      <div className="acad__cols">
        <div className="acad__stack">
          <DataCard title={t('По предметам')} count={data.subjects.length || undefined} empty={empty && t('оценок за период ещё нет')}>
            <Rows>
              {data.subjects.map((item) => {
                const s = item.stats
                const grade = s.final ?? s.quarter_grade
                return (
                  <Row
                    key={item.course.id}
                    icon="book"
                    title={item.course.subject.title}
                    note={
                      <span className="stug__nums">
                        <span>
                          {t('ФО')} <b>{s.fo_avg ?? t('нет')}</b>
                        </span>
                        {s.sor_max ? (
                          <span>
                            {t('СОР')} <b>{s.sor_got}</b>/{s.sor_max}
                          </span>
                        ) : null}
                        {s.soch_max ? (
                          <span>
                            {t('СОЧ')} <b>{s.soch_got}</b>/{s.soch_max}
                          </span>
                        ) : null}
                        {s.absent + s.excused ? (
                          <span>
                            {t('пропусков')} <b>{s.absent + s.excused}</b>
                          </span>
                        ) : null}
                      </span>
                    }
                    right={
                      item.course.subject.scheme === 'kz' ? (
                        grade !== null ? (
                          <Chip tone={s.final !== null ? 'accent' : 'neutral'}>{s.final !== null ? `${t('итог')} ${grade}` : `${t('выходит')} ${grade}${s.quarter_pct !== null ? ` · ${s.quarter_pct} %` : ''}`}</Chip>
                        ) : (
                          <Chip>{t('оценок мало для расчёта')}</Chip>
                        )
                      ) : (
                        <Chip>{t('только ФО')}</Chip>
                      )
                    }
                  />
                )
              })}
            </Rows>
          </DataCard>
          <DataCard title={t('Последние оценки')} count={grades.length || undefined} empty={grades.length === 0 && t('за период оценок не было')}>
            <Rows>
              <ShowAll>
                {grades.map((row) => (
                  <Row
                    key={`${row.lesson}-${row.subject}`}
                    lead={<b className="num stu__slot">{row.value}</b>}
                    title={`${row.subject_title} · ${row.kind_label}`}
                    note={[dateWords(row.date), row.max ? `${t('из')} ${row.max}` : '', row.comment ? `«${row.comment}»` : ''].filter(Boolean).join(' · ')}
                    to={`/lessons/${row.lesson}`}
                  />
                ))}
              </ShowAll>
            </Rows>
          </DataCard>
        </div>
        <div className="acad__stack">
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
    </div>
  )
}
