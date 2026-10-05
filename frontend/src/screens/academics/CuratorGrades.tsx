/**
 * Успеваемость группы у куратора: ученики × предметы, посещаемость,
 * кому нужна помощь, журналы учителей с неотмеченными уроками.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useGroupGrades, useRemindTeacher, type GroupGrades } from '../../api/academics'
import DataTable, { type Column } from '../../components/DataTable'
import { ExportPreview } from '../../components/ExportPreview'
import { Row, Rows, StatRow } from '../../components/patterns'
import { Chip, DataCard, ErrorNote, Kpi, Loading, ScreenHead, type Tone } from '../../components/ui'
import { Button } from '../../components/ui/button'
import { plural, t, tn } from '../../i18n'
import GroupSwitch from '../curator/GroupSwitch'
import { useGroup, useMyGroups } from '../curator/state'
import { PeriodSwitch } from './shared'

type GradeRow = GroupGrades['rows'][number]

export default function CuratorGrades() {
  const navigate = useNavigate()
  const [group, setGroup] = useGroup()
  const { groups, ready } = useMyGroups()
  const picked = group === 'all' ? (groups[0]?.code ?? '') : group
  const [period, setPeriod] = useState('')
  const { data, isLoading, error } = useGroupGrades(picked, period, ready && picked !== '')
  const remind = useRemindTeacher()
  const [exporting, setExporting] = useState(false)
  if (!ready || (isLoading && !data)) return <Loading kind="table" />
  if (error) return <ErrorNote error={error} />
  if (!data) return null
  const switcher = <GroupSwitch groups={groups} value={group === 'all' ? picked : group} onChange={setGroup} />
  if (!data.has_courses || data.rows.length === 0)
    return (
      <div>
        <ScreenHead title={t('Успеваемость')} />
        {switcher}
        <DataCard title={t('Оценок ещё нет')} empty={data.rows.length ? t('расписание не составлено') : t('в группе нет учеников')} />
      </div>
    )
  const columns: Column<GradeRow>[] = [
    { key: 'name', title: t('Ученик'), width: '200px', cell: (row) => <b>{row.full_name}</b>, sortBy: (row) => row.full_name },
    // колонка предмета не уже 96 px: короткое название из справочника («Геом.», «Англ.»)
    // читается целиком, полное — в подсказке; таблица шире карточки едет
    // внутри неё, ученик закреплён слева (правило 4, 27.09.2026)
    ...data.subjects.map((subject, index) => ({
      key: `s${subject.id}`,
      title: subject.short_title,
      hint: subject.title,
      width: '96px',
      align: 'right' as const,
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
      width: '96px',
      align: 'right',
      cell: (row) => (row.attendance_pct === null ? <span className="t-note">{t('нет')}</span> : <b className={`num${row.attendance_pct < data.attendance_below ? ' text-bad' : ''}`}>{row.attendance_pct} %</b>),
      sortBy: (row) => row.attendance_pct,
    },
  ]
  return (
    <div>
      <ScreenHead
        title={t('Успеваемость')}
        actions={
          <Button variant="outline" size="sm" onClick={() => setExporting(true)}>
            {t('Выгрузить')}
          </Button>
        }
      />
      {switcher}
      <div className="acad__toolbar">
        <PeriodSwitch value={data.period.code} periods={data.periods} onChange={setPeriod} />
      </div>
      <StatRow>
        <Kpi label={t('Посещаемость')} value={data.kpis.attendance !== null ? `${data.kpis.attendance} %` : null} none={t('нет данных')} />
        <Kpi label={t('Двойка в прогнозе')} value={data.kpis.risk || null} none={t('нет')} tone={data.kpis.risk ? 'bad' : undefined} note={plural(data.kpis.risk, 'ученик|ученика|учеников')} />
        <Kpi label={t('Пропуски без причины')} value={data.kpis.absent || null} none={t('нет')} action={data.kpis.absent ? { label: t('Оформить'), to: '/attendance' } : undefined} />
        <Kpi label={t('Не отмечено учителями')} value={data.kpis.unmarked || null} none={t('всё отмечено')} note={tn(data.kpis.unmarked_days, 'за {n} день|за {n} дня|за {n} дней')} tone={data.kpis.unmarked ? 'warn' : undefined} />
      </StatRow>
      <div className="card">
        <DataTable columns={columns} rows={data.rows} rowKey={(row) => row.id} onRowClick={(row) => navigate(`/students/${row.id}?tab=grades`)} minWidth={`${200 + 96 + data.subjects.length * 96}px`} />
      </div>
      <div className="acad__cols acad__cols--even">
        <div className="acad__stack">
          <DataCard title={t('Кому нужна помощь')} count={data.need_help.length || undefined} empty={data.need_help.length === 0 && t('все справляются')}>
            <Rows>
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
            </Rows>
          </DataCard>
        </div>
        <div className="acad__stack">
          <DataCard title={t('Журналы учителей')} count={data.journals.length}>
            <Rows>
              {data.journals.map((course) => (
                <Row
                  key={course.id}
                  icon="book"
                  tone={course.unmarked ? 'warn' : 'good'}
                  title={`${course.subject.short_title} · ${course.teacher?.short ?? ''}`}
                  note={`${course.cohort.name} · ${course.unmarked ? tn(course.unmarked, 'не отмечен {n} урок|не отмечено {n} урока|не отмечено {n} уроков') : t('всё отмечено')}`}
                  acts={
                    course.unmarked && course.teacher ? (
                      <Button variant="secondary" size="sm" onClick={() => remind.mutate(course.teacher?.id ?? 0, { onSuccess: () => toast.success(t('Напоминание ушло')), onError: (e) => toast.error(e.message) })}>
                        {t('Напомнить')}
                      </Button>
                    ) : undefined
                  }
                />
              ))}
            </Rows>
          </DataCard>
        </div>
      </div>
      {exporting && <ExportPreview path={`/acad/grades/group/export/?group=${encodeURIComponent(picked)}&period=${encodeURIComponent(data.period.code)}`} fallback={t('успеваемость-группы.xlsx')} title={t('Выгрузка успеваемости группы')} onClose={() => setExporting(false)} />}
    </div>
  )
}
