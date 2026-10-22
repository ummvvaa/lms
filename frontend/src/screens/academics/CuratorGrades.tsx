/**
 * Успеваемость группы у куратора: ученики × предметы, посещаемость,
 * кому нужна помощь. Про учителей здесь ничего нет (решение владельца,
 * 19.10.2026): неотмеченные уроки и напоминания — дело Кымбат и администратора.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useGroupGrades, type GroupGrades } from '../../api/academics'
import DataTable, { type Column } from '../../components/DataTable'
import { ExportPreview } from '../../components/ExportPreview'
import { Avatar, Row, Rows, ShowAll, StatRow } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { plural, t } from '../../i18n'
import { usePhone } from '../../phone'
import GroupSwitch from '../curator/GroupSwitch'
import { useGroup, useMyGroups } from '../curator/state'
import { PeriodSwitch, subjectHead } from './shared'

type GradeRow = GroupGrades['rows'][number]

export default function CuratorGrades() {
  const phone = usePhone()
  const navigate = useNavigate()
  const [group, setGroup] = useGroup()
  const { groups, ready } = useMyGroups()
  const picked = group === 'all' ? (groups[0]?.code ?? '') : group
  const [period, setPeriod] = useState('')
  const { data, isLoading, error } = useGroupGrades(picked, period, ready && picked !== '')
  const [exporting, setExporting] = useState(false)
  if (!ready || (isLoading && !data)) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const switcher = <GroupSwitch groups={groups} value={group === 'all' ? picked : group} onChange={setGroup} />
  if (!data.has_courses || data.rows.length === 0)
    return (
      <div className="lay-screen">
        <ScreenHead title={t('Успеваемость')} />
        {switcher}
        <DataCard title={t('Оценок ещё нет')} empty={data.rows.length ? t('расписание не составлено') : t('в группе нет учеников')} />
      </div>
    )
  const columns: Column<GradeRow>[] = [
    {
      key: 'name',
      title: t('Ученик'),
      width: '260px',
      cell: (row) => (
        <span className="personcell">
          <Avatar name={row.full_name} size={30} />
          <b>{row.full_name}</b>
        </span>
      ),
      sortBy: (row) => row.full_name,
    },
    // таблица в ширину карточки, как у школы: колонки предметов делят место
    // поровну, шапка длинного ряда стоит вертикально, полное название — в подсказке
    ...data.subjects.map((subject, index) => ({
      key: `s${subject.id}`,
      ...subjectHead(subject, data.subjects.length),
      cell: (row: GradeRow) => {
        const cell = row.cells[index]
        if (!cell) return null
        if (cell.grade !== null) return <Chip tone={(cell.tone || 'neutral') as Tone}>{String(cell.grade)}</Chip>
        if (cell.text) return <b className="num">{cell.text}</b>
        return <span className="t-note">{cell.none}</span>
      },
      sortBy: (row: GradeRow) => row.cells[index]?.grade ?? row.cells[index]?.pct ?? null,
    })),
    {
      key: 'att',
      title: t('Посещ.'),
      hint: t('Посещаемость'),
      width: '104px',
      align: 'right',
      // ниже нормы — красным чипом, а не красным числом
      cell: (row) =>
        row.attendance_pct === null ? (
          <span className="t-note">{t('нет')}</span>
        ) : row.attendance_pct < data.attendance_below ? (
          <Chip tone="bad" size="sm" className="num">{`${row.attendance_pct} %`}</Chip>
        ) : (
          <b className="num">{row.attendance_pct} %</b>
        ),
      sortBy: (row) => row.attendance_pct,
    },
  ]
  const periods = <PeriodSwitch value={data.period.code} periods={data.periods} onChange={setPeriod} />
  return (
    <div className="lay-screen">
      {/* период — справа в шапке; на телефоне шапка прячет действия в меню,
          поэтому там он своей строкой под группами */}
      <ScreenHead
        title={t('Успеваемость')}
        subtitle={t('Оценки по предметам LMS · {period}', { period: t(data.period.title) })}
        actions={
          <>
            {!phone && periods}
            <Button variant="outline" size="sm" onClick={() => setExporting(true)}>
              {t('Выгрузить')}
            </Button>
          </>
        }
      />
      {switcher}
      {phone && <div className="acad__toolbar">{periods}</div>}
      {/* показатель без числа плиткой не рисуется — как у ученика и учителя */}
      {(data.kpis.attendance !== null || data.kpis.risk > 0 || data.kpis.absent > 0) && (
      <StatRow>
        {data.kpis.attendance !== null && <Kpi label={t('Посещаемость')} value={`${data.kpis.attendance} %`} />}
        {data.kpis.risk > 0 && <Kpi label={t('Двойка в прогнозе')} value={data.kpis.risk} tone={data.kpis.risk ? 'bad' : undefined} note={plural(data.kpis.risk, 'ученик|ученика|учеников')} />}
        {data.kpis.absent > 0 && <Kpi label={t('Пропуски без причины')} value={data.kpis.absent} action={data.kpis.absent ? { label: t('Оформить'), to: '/attendance' } : undefined} />}
      </StatRow>
      )}
      <div className="lay-main">
        <DataCard className="card--beam" title={t('{group} · по ученикам', { group: picked })} count={data.rows.length}>
          <DataTable columns={columns} rows={data.rows} rowKey={(row) => row.id} onRowClick={(row) => navigate(`/students/${row.id}?tab=grades`)} fit />
        </DataCard>
        <div className="lay-stack">
          <DataCard title={t('Кому нужна помощь')} count={data.need_help.length || undefined} empty={data.need_help.length === 0 && t('все справляются')}>
            <Rows>
              <ShowAll>
                {data.need_help.map((row) => (
                  <Row
                    key={row.id}
                    avatar={row.full_name}
                    tone="warn"
                    title={row.full_name}
                    note={[row.low.join(', '), row.attendance_pct !== null && row.attendance_pct < data.attendance_below ? t('посещаемость {pct} %', { pct: row.attendance_pct }) : ''].filter(Boolean).join(' · ')}
                    to={`/students/${row.id}?tab=grades`}
                  />
                ))}
              </ShowAll>
            </Rows>
          </DataCard>
        </div>
      </div>
      {exporting && <ExportPreview path={`/acad/grades/group/export/?group=${encodeURIComponent(picked)}&period=${encodeURIComponent(data.period.code)}`} fallback={t('успеваемость-группы.xlsx')} title={t('Выгрузка успеваемости группы')} onClose={() => setExporting(false)} />}
    </div>
  )
}
