/**
 * Успеваемость по школе: группы × предметы, посещаемость, прогноз двоек,
 * журналы без оценок. Нажатие на ячейку — ученики группы по предмету.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { gradeTone, useSchoolGrades, useSchoolGradesCell } from '../../api/academics'
import EditDrawer from '../../components/EditDrawer'
import { ExportPreview } from '../../components/ExportPreview'
import DataTable, { type Column } from '../../components/DataTable'
import { Row, Rows, ShowAll, StatRow } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { t } from '../../i18n'
import { dateWords, NoteCard, PeriodSwitch } from './shared'

function CellDrawer({ params, onClose }: { params: { group: string; subject: number; period: string }; onClose: () => void }) {
  const navigate = useNavigate()
  const { data, isLoading } = useSchoolGradesCell(params)
  type CellRow = NonNullable<typeof data>['rows'][number]
  const columns: Column<CellRow>[] = [
    { key: 'name', title: t('Ученик'), width: '40%', cell: (row) => <span><b>{row.full_name}</b><br /><span className="t-note">{row.course.cohort.short_name}</span></span> },
    { key: 'fo', title: t('ФО'), width: '15%', align: 'right', cell: (row) => (row.stats.fo_avg === null ? <span className="t-note">{t('нет')}</span> : <b className="num">{row.stats.fo_avg}</b>) },
    { key: 'sor', title: t('СОР'), width: '20%', align: 'right', cell: (row) => (row.stats.sor_max ? <b className="num">{`${row.stats.sor_got}/${row.stats.sor_max}`}</b> : <span className="t-note">{t('не писал')}</span>) },
    { key: 'now', title: t('Выходит'), width: '25%', align: 'right', cell: (row) => (row.stats.quarter_grade !== null ? <Chip tone={gradeTone(row.stats.quarter_grade) as Tone}>{String(row.stats.final ?? row.stats.quarter_grade)}</Chip> : <span className="t-note">{t('мало оценок')}</span>) },
  ]
  return (
    <EditDrawer open onClose={onClose} title={data ? `${data.subject.title} · ${data.group}` : t('Ученики')} sub={data?.period}>
      {isLoading || !data ? <Loading kind="table" /> : <DataTable columns={columns} rows={data.rows} rowKey={(row) => `${row.id}-${row.course.id}`} onRowClick={(row) => navigate(`/students/${row.id}`)} />}
    </EditDrawer>
  )
}

export default function SchoolGrades() {
  const navigate = useNavigate()
  const [period, setPeriod] = useState('')
  const { data, isLoading, error } = useSchoolGrades(period)
  const [cell, setCell] = useState<{ group: string; subject: number; period: string } | null>(null)
  const [exporting, setExporting] = useState(false)
  if (isLoading && !data) return <Loading kind="cards" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  if (!data.has_courses)
    return (
      <div>
        <ScreenHead title={t('Успеваемость')} />
        <div className="acad__cols">
          <div className="acad__stack">
            <DataCard title={t('Оценок ещё нет')} empty={t('сначала составьте расписание — журналы появятся сами')} emptyAction={<Button variant="secondary" size="sm" onClick={() => navigate('/schedule')}>{t('К расписанию')}</Button>} />
          </div>
          <div className="acad__stack">
            <NoteCard title={t('Как считается')}>{t('Итог четверти считается по весам ФО, СОР и СОЧ и порогам из «Учебного года».')}</NoteCard>
          </div>
        </div>
      </div>
    )
  return (
    <div>
      <ScreenHead
        title={t('Успеваемость')}
        subtitle={`${t('Средний процент за')} ${data.period.title.toLowerCase()} ${t('по предметам и группам. Нажмите на ячейку — откроются ученики.')}`}
        actions={
          <Button variant="outline" size="sm" onClick={() => setExporting(true)}>
            {t('Выгрузить')}
          </Button>
        }
      />
      <div className="acad__toolbar">
        <PeriodSwitch value={data.period.code} periods={data.periods} onChange={setPeriod} />
      </div>
      <StatRow>
        <Kpi label={t('Посещаемость')} value={data.kpis.attendance !== null ? `${data.kpis.attendance} %` : null} none={t('нет данных')} note={t('по урокам с отметкой')} />
        <Kpi label={t('Прогноз двойки')} value={data.kpis.risk || null} none={t('нет')} tone={data.kpis.risk ? 'bad' : undefined} note={t('учеников хотя бы по одному предмету')} />
        <Kpi label={t('Журналы без оценок')} value={data.kpis.empty_journals || null} none={t('нет')} tone={data.kpis.empty_journals ? 'warn' : undefined} note={t('за две недели')} action={data.kpis.empty_journals ? { label: t('Учителя'), to: '/teachers' } : undefined} />
        <Kpi label={t('Итоги четверти')} value={data.kpis.finals || null} none={t('нет')} note={data.kpis.quarter_ends ? `${t('выставляют до')} ${dateWords(data.kpis.quarter_ends)}` : ''} />
      </StatRow>
      <DataCard
        title={t('Группы и предметы')}
        right={
          <span className="acad__chips">
            <Chip tone="good" size="sm">85+</Chip>
            <Chip tone="info" size="sm">65–84</Chip>
            <Chip tone="warn" size="sm">40–64</Chip>
            <Chip tone="bad" size="sm">{t('ниже 40')}</Chip>
          </span>
        }
      >
        <div className="heat__scroll">
          <div className="heat" style={{ gridTemplateColumns: `minmax(0, 1.4fr) repeat(${data.subjects.length + 1}, minmax(0, 1fr))` }}>
            <div className="heat__cell heat__cell--head">{t('Группа')}</div>
            {data.subjects.map((s) => (
              <div key={s.id} className="heat__cell heat__cell--head">
                {s.short_title}
              </div>
            ))}
            <div className="heat__cell heat__cell--head">{t('Посещ.')}</div>
            {data.heat.map((row) => (
              <div key={row.group} className="heat__row">
                <div className="heat__cell heat__cell--name">{row.group}</div>
                {row.cells.map((c) => (
                  <div key={c.subject} className="heat__cell">
                    {c.pct === null ? (
                      <span className="t-note">{t('нет')}</span>
                    ) : (
                      <Button variant="ghost" size="sm" onClick={() => setCell({ group: row.group, subject: c.subject, period: data.period.code })}>
                        <Chip tone={(c.tone || 'neutral') as Tone}>{`${c.pct} %`}</Chip>
                      </Button>
                    )}
                  </div>
                ))}
                <div className="heat__cell">
                  <b className="num">{row.attendance !== null ? `${row.attendance} %` : t('нет')}</b>
                </div>
              </div>
            ))}
          </div>
        </div>
      </DataCard>
      <div className="acad__cols acad__cols--even">
        <div className="acad__stack">
          <DataCard title={t('Прогноз двойки')} count={data.risk.length || undefined} empty={data.risk.length === 0 && t('таких нет')}>
            <Rows>
              <ShowAll>
                {data.risk.map((row) => (
                  <Row key={row.id} avatar={row.full_name} tone="bad" title={row.full_name} note={`${row.group} · ${row.subjects.join(', ')}`} to={`/students/${row.id}`} />
                ))}
              </ShowAll>
            </Rows>
          </DataCard>
          <DataCard title={t('Журналы без оценок')} count={data.empty_journals.length || undefined} empty={data.empty_journals.length === 0 && t('во всех журналах есть оценки')}>
            <Rows>
              {data.empty_journals.map((course) => (
                <Row key={course.id} icon="book" tone="warn" title={course.title} note={course.teacher?.full_name ?? ''} to={`/journals/${course.id}`} />
              ))}
            </Rows>
          </DataCard>
        </div>
        <div className="acad__stack">
          <DataCard title={t('Хуже всего с посещаемостью')} count={data.worst_attendance.length || undefined} empty={data.worst_attendance.length === 0 && t('отметок нет')}>
            <Rows>
              {data.worst_attendance.map((row) => (
                <Row key={row.id} avatar={row.full_name} title={row.full_name} note={`${row.group} · ${row.attendance.absent} ${t('без причины')}, ${row.attendance.excused} ${t('по уважительной')}`} value={`${row.attendance.pct} %`} to={`/students/${row.id}`} />
              ))}
            </Rows>
          </DataCard>
        </div>
      </div>
      {cell && <CellDrawer params={cell} onClose={() => setCell(null)} />}
      {exporting && <ExportPreview path={`/acad/grades/school/export/?period=${encodeURIComponent(data.period.code)}`} fallback="успеваемость.xlsx" title={t('Выгрузка успеваемости')} onClose={() => setExporting(false)} />}
    </div>
  )
}
